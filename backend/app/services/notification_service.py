"""
Payment notifications: in-app bell + Web Push to the request's merchandiser,
email to HoM / super admins.

Trigger logic (dedupe ledger = notifications row with type "payment_processed"
for the deposit request):

- TT copy uploaded (request already processed):
    - no payment_processed notification yet → send "Payment processed" WITH the
      Drive link (this is the normal process-then-upload path).
    - one already exists (the fallback fired first) → send a follow-up
      "tt_copy_attached" notification carrying the link.
- Payment processed:
    - TT copy already attached (uploaded pre-process) → notify immediately with
      the link.
    - not attached → do nothing; wait for the upload (or the fallback job).
- Fallback (scheduler, every 30 min): requests processed >1 h ago with no TT
  copy and no payment_processed notification → plain "Payment processed"
  notice so the merchandiser is never left unaware.

Background entry points follow the seed_snapshot_for_request contract: own
session, failures logged and swallowed.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.deposit_request import DepositRequest
from app.models.enums import RequestStatus, UserRole
from app.models.masters import User
from app.models.notification import Notification
from app.models.payment import PaymentDetails
from app.models.workflow import StatusHistory
from app.repositories.notification_repo import (
    NotificationRepository,
    PushSubscriptionRepository,
)
from app.services.email_service import build_payment_processed_email, send_email

logger = get_logger(__name__)
settings = get_settings()

TYPE_PAYMENT_PROCESSED = "payment_processed"
TYPE_TT_COPY_ATTACHED = "tt_copy_attached"
TYPE_TRANCHE_PAID = "tranche_paid"
# TYPE_TRANCHE_TT_ATTACHED was removed 4 Aug 2026 — a TT upload alone no
# longer notifies; the merchandiser hears when the tranche is marked paid.
TYPE_TRANCHE_UPDATED = "tranche_updated"
TYPE_TRANCHE_REJECTED = "tranche_rejected"
TYPE_HOM_APPROVED = "hom_approved"
TYPE_HOM_REJECTED = "hom_rejected"
TYPE_ADJUSTMENT_REQUESTED = "adjustment_requested"
TYPE_ADJUSTMENT_RECORDED = "adjustment_recorded"
TYPE_ADJUSTMENT_DECIDED = "adjustment_decided"
TYPE_REQUEST_CREATED = "request_created"
TYPE_REQUEST_PENDING_HOM = "request_pending_hom"
TYPE_STATUS_CHANGED = "status_changed"
TYPE_FILE_REMARK_RAISED = "file_remark_raised"
TYPE_FILE_REMARK_RESOLVED = "file_remark_resolved"
TYPE_REQUEST_REJECTED = "request_rejected"

_EMAIL_ROLES = (UserRole.HEAD_OF_MERCHANDISER, UserRole.SUPER_ADMIN)


# ── Pure helpers (unit-tested, no I/O) ───────────────────────────────────────


def build_notification_message(
    type_: str, request_number: str, request_id: UUID | str, tt_copy_url: str | None
) -> dict:
    """Title/body/url/attachment for a notification row and push payload."""
    url = f"/merchandiser/{request_id}"
    if type_ == TYPE_TT_COPY_ATTACHED:
        return {
            "title": "TT copy attached",
            "body": f"The TT copy for {request_number} is now available.",
            "url": url,
            "attachment_url": tt_copy_url,
        }
    body = f"Payment for {request_number} has been processed."
    if tt_copy_url:
        body += " TT copy attached."
    return {
        "title": "Payment processed",
        "body": body,
        "url": url,
        "attachment_url": tt_copy_url,
    }


def build_tranche_notification_message(
    type_: str,
    request_number: str,
    tranche_label: str,
    request_id: UUID | str,
    tt_copy_url: str | None = None,
    changes: str | None = None,
) -> dict:
    """Title/body/url/attachment for tranche-level notifications.

    tranche_paid goes to the merchandiser who raised the request (and carries
    the TT link); tranche_updated goes to the Accounts Team. The old
    tranche_tt_attached notification was removed on 4 Aug 2026 — a TT upload
    alone no longer notifies anyone.
    """
    if type_ == TYPE_TRANCHE_UPDATED:
        body = f"{tranche_label} of {request_number} was updated by the merchandiser."
        if changes:
            body += f" {changes}"
        return {
            "title": "Tranche updated",
            "body": body,
            "url": f"/accounts/{request_id}",
            "attachment_url": None,
        }
    body = f"{tranche_label} of {request_number} has been paid."
    if tt_copy_url:
        body += " TT copy attached."
    return {
        "title": "Tranche paid",
        "body": body,
        "url": f"/merchandiser/{request_id}",
        "attachment_url": tt_copy_url,
    }


def build_hom_decision_message(
    type_: str, request_number: str, request_id: UUID | str, remarks: str
) -> dict:
    """Title/body/url for HoM approve/reject notifications.

    Both go to the merchandiser who raised the request and deep-link to the
    merchandiser view. The reason is always included — it is mandatory.
    """
    url = f"/merchandiser/{request_id}"
    if type_ == TYPE_HOM_REJECTED:
        return {
            "title": "Request rejected",
            "body": f"{request_number} was rejected by the Head of Merchandiser. Reason: {remarks}",
            "url": url,
            "attachment_url": None,
        }
    return {
        "title": "Request approved",
        "body": (
            f"{request_number} was approved by the Head of Merchandiser "
            f"and moved to the payment queue. Reason: {remarks}"
        ),
        "url": url,
        "attachment_url": None,
    }


def build_adjustment_notification_message(
    type_: str,
    amount: str,
    source_label: str,
    source_request_number: str,
    destination_label: str,
    destination_request_number: str,
    reason: str | None = None,
    decision: str | None = None,
) -> dict:
    """Title/body/url for Adjust Invoice notifications (change note B2/B3).

    adjustment_requested / adjustment_recorded go to the Accounts Team;
    adjustment_decided goes back to the merchandiser who raised the request.
    All deep-link to the Adjust Invoices module.
    """
    move = (
        f"{amount} from {source_label} of {source_request_number} "
        f"to {destination_label} of {destination_request_number}"
    )
    url = "/adjust-invoices"
    if type_ == TYPE_ADJUSTMENT_REQUESTED:
        body = f"A merchandiser requested reallocating {move}."
        if reason:
            body += f" Reason: {reason}"
        return {"title": "Adjustment approval requested", "body": body,
                "url": url, "attachment_url": None}
    if type_ == TYPE_ADJUSTMENT_DECIDED:
        body = f"Your adjustment request ({move}) was {decision}."
        if reason:
            body += f" Reason: {reason}"
        return {"title": f"Adjustment {decision}", "body": body,
                "url": url, "attachment_url": None}
    body = f"An invoice adjustment was recorded: {move}."
    if reason:
        body += f" Reason: {reason}"
    return {"title": "Invoice adjustment recorded", "body": body,
            "url": url, "attachment_url": None}


def build_status_change_message(
    new_status: str,
    request_number: str,
    request_id: UUID | str,
    actor_is_merchandiser: bool,
    remarks: str | None = None,
) -> dict:
    """Title/body/url for hold / resume / cancel / reopen notifications
    (Aug 2026 batch, item 1.2 — these transitions previously emitted nothing).

    Merchandiser-side actions notify the Accounts Team (deep-link to the
    accounts view); accounts-side actions notify the raising merchandiser.
    """
    actor = "the merchandiser" if actor_is_merchandiser else "the Accounts team"
    titles_bodies = {
        "hold_by_merchandiser": ("Request on hold", f"{request_number} was put on hold by {actor}."),
        "hold_by_accounts": ("Request on hold", f"{request_number} was put on hold by {actor}."),
        "pending_payment": ("Request resumed", f"{request_number} was resumed by {actor} and is back in the payment queue."),
        "cancelled_by_merchandiser": ("Request cancelled", f"{request_number} was cancelled by {actor}."),
        "cancelled_by_accounts": ("Request cancelled", f"{request_number} was cancelled by {actor}."),
        "reopened": ("Request reopened", f"{request_number} was reopened by {actor}."),
    }
    title, body = titles_bodies.get(
        new_status, ("Request updated", f"{request_number} status changed to {new_status}.")
    )
    if remarks:
        body += f" Remarks: {remarks}"
    url = f"/accounts/{request_id}" if actor_is_merchandiser else f"/merchandiser/{request_id}"
    return {"title": title, "body": body, "url": url, "attachment_url": None}


def decide_on_tt_upload(request_is_processed: bool, already_notified: bool) -> str | None:
    """Which notification (if any) to send when a TT copy is uploaded."""
    if not request_is_processed:
        return None  # uploaded pre-process — the process step will notify
    return TYPE_TT_COPY_ATTACHED if already_notified else TYPE_PAYMENT_PROCESSED


def decide_on_process(has_tt_copy: bool, already_notified: bool) -> str | None:
    """Which notification (if any) to send when a payment is processed."""
    if already_notified:
        return None
    return TYPE_PAYMENT_PROCESSED if has_tt_copy else None


def resolve_target(created_by: UUID | None, submitter_email: str | None) -> tuple[str, str | None]:
    """How to find the merchandiser to notify: ('created_by'|'email'|'none', email)."""
    if created_by is not None:
        return "created_by", None
    if submitter_email:
        return "email", submitter_email.strip().lower()
    return "none", None


def is_subscription_gone(status_code: int | None) -> bool:
    """404/410 from the push service = endpoint permanently gone → delete it."""
    return status_code in (404, 410)


# ── Web Push (sync, run in a thread) ─────────────────────────────────────────


def _send_push_sync(endpoint: str, p256dh: str, auth: str, payload: str) -> str:
    """Send one push message. Returns 'ok', 'gone', or 'error'."""
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info={
                "endpoint": endpoint,
                "keys": {"p256dh": p256dh, "auth": auth},
            },
            data=payload,
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": f"mailto:{settings.vapid_claims_email or 'admin@example.com'}"},
        )
        return "ok"
    except WebPushException as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        if is_subscription_gone(status_code):
            return "gone"
        logger.warning("Push send failed", endpoint=endpoint[:60], status=status_code, error=str(exc))
        return "error"
    except Exception as exc:
        logger.warning("Push send crashed", endpoint=endpoint[:60], error=str(exc))
        return "error"


# ── Core delivery ────────────────────────────────────────────────────────────


async def _find_target_user(session: AsyncSession, request: DepositRequest) -> User | None:
    mode, email = resolve_target(request.created_by, request.submitter_email)
    if mode == "created_by":
        return await session.get(User, request.created_by)
    if mode == "email":
        result = await session.execute(
            select(User).where(func.lower(User.email) == email, User.is_active == True)  # noqa: E712
        )
        return result.scalar_one_or_none()
    return None


async def _push_to_user(session: AsyncSession, user_id: UUID, message: dict) -> None:
    """Send the push payload to every subscription of the user; prune dead ones."""
    if not settings.vapid_private_key:
        return  # push not configured — bell row already written
    sub_repo = PushSubscriptionRepository(session)
    subs = await sub_repo.list_for_user(user_id)
    if not subs:
        return
    payload = json.dumps(message)
    gone: list[str] = []
    for sub in subs:
        outcome = await asyncio.to_thread(
            _send_push_sync, sub.endpoint, sub.p256dh, sub.auth, payload
        )
        if outcome == "gone":
            gone.append(sub.endpoint)
    if gone:
        await sub_repo.delete_by_endpoints(gone)
        logger.info("Pruned dead push subscriptions", count=len(gone))


async def _email_admins(session: AsyncSession, request_number: str, tt_copy_url: str | None) -> None:
    result = await session.execute(
        select(User.email).where(User.role.in_(_EMAIL_ROLES), User.is_active == True)  # noqa: E712
    )
    recipients = [row[0] for row in result.all()]
    if not recipients:
        return
    subject, text, html = build_payment_processed_email(request_number, tt_copy_url)
    await send_email(recipients, subject, text, html)


async def _deliver(
    session: AsyncSession,
    request: DepositRequest,
    type_: str,
    tt_copy_url: str | None,
) -> None:
    """Write the bell row, push to the merchandiser, email HoM/super admins."""
    message = build_notification_message(type_, request.request_number, request.id, tt_copy_url)
    target = await _find_target_user(session, request)

    if target is not None:
        session.add(
            Notification(
                user_id=target.id,
                type=type_,
                title=message["title"],
                body=message["body"],
                url=message["url"],
                attachment_url=message["attachment_url"],
                deposit_request_id=request.id,
            )
        )
        await session.commit()
        await _push_to_user(session, target.id, message)
        await session.commit()
    else:
        logger.info(
            "No target user for notification — skipping bell/push",
            request_id=str(request.id),
        )

    # Emails go to HoM + super admins regardless of bell target, but only for
    # the primary payment_processed notification (not the follow-up).
    if type_ == TYPE_PAYMENT_PROCESSED:
        await _email_admins(session, request.request_number, tt_copy_url)


async def _active_users_with_role(session: AsyncSession, role: UserRole) -> list[User]:
    result = await session.execute(
        select(User).where(User.role == role, User.is_active == True)  # noqa: E712
    )
    return list(result.scalars().all())


async def _deliver_to_users(
    session: AsyncSession,
    users: list[User],
    type_: str,
    message: dict,
    deposit_request_id: UUID | None,
) -> None:
    """Bell rows + pushes for a list of recipients (fan-out helper)."""
    if not users:
        return
    for user in users:
        session.add(
            Notification(
                user_id=user.id,
                type=type_,
                title=message["title"],
                body=message["body"],
                url=message["url"],
                attachment_url=message.get("attachment_url"),
                deposit_request_id=deposit_request_id,
            )
        )
    await session.commit()
    for user in users:
        await _push_to_user(session, user.id, message)
    await session.commit()


async def _load_request(session: AsyncSession, request_id: UUID) -> DepositRequest | None:
    result = await session.execute(
        select(DepositRequest)
        .where(DepositRequest.id == request_id)
        .options(selectinload(DepositRequest.payment))
    )
    return result.scalar_one_or_none()


# ── BackgroundTasks entry points ─────────────────────────────────────────────


async def notify_tt_copy_uploaded(request_id: UUID) -> None:
    """After a TT copy upload — own session, failures logged and swallowed."""
    from app.core.database import AsyncSessionFactory

    try:
        async with AsyncSessionFactory() as session:
            request = await _load_request(session, request_id)
            if request is None or request.payment is None:
                return
            repo = NotificationRepository(session)
            already = await repo.exists_for_request(request_id, TYPE_PAYMENT_PROCESSED)
            type_ = decide_on_tt_upload(
                request.current_status == RequestStatus.PAYMENT_PROCESSED, already
            )
            if type_ is None:
                return
            await _deliver(session, request, type_, request.payment.tt_copy_url)
    except Exception as exc:
        logger.error("notify_tt_copy_uploaded failed", request_id=str(request_id), error=str(exc))


async def notify_payment_processed_if_ready(request_id: UUID) -> None:
    """After processing — notify immediately only if the TT copy already exists."""
    from app.core.database import AsyncSessionFactory

    try:
        async with AsyncSessionFactory() as session:
            request = await _load_request(session, request_id)
            if request is None:
                return
            tt_url = request.payment.tt_copy_url if request.payment else None
            repo = NotificationRepository(session)
            already = await repo.exists_for_request(request_id, TYPE_PAYMENT_PROCESSED)
            type_ = decide_on_process(bool(tt_url), already)
            if type_ is None:
                return
            await _deliver(session, request, type_, tt_url)
    except Exception as exc:
        logger.error(
            "notify_payment_processed_if_ready failed", request_id=str(request_id), error=str(exc)
        )


async def notify_tranche_event(request_id: UUID, tranche_id: UUID, event: str) -> None:
    """After a tranche is explicitly marked paid — bell + push to the
    merchandiser who raised the request, naming the paid tranche and request
    number and carrying the TT link.

    event: 'paid' (the only event since 4 Aug 2026 — TT uploads no longer
    notify). When the tranche payment completed the whole request,
    HoM / super admins also get the payment-processed email.
    Own session; failures logged and swallowed (BackgroundTasks contract).
    """
    from app.core.database import AsyncSessionFactory
    from app.models.tranche import PaymentTranche

    try:
        async with AsyncSessionFactory() as session:
            request = await _load_request(session, request_id)
            tranche = await session.get(PaymentTranche, tranche_id)
            if request is None or tranche is None:
                return
            type_ = TYPE_TRANCHE_PAID
            message = build_tranche_notification_message(
                type_, request.request_number, tranche.label, request.id,
                tt_copy_url=tranche.tt_copy_url,
            )
            target = await _find_target_user(session, request)
            if target is not None:
                session.add(
                    Notification(
                        user_id=target.id,
                        type=type_,
                        title=message["title"],
                        body=message["body"],
                        url=message["url"],
                        attachment_url=message["attachment_url"],
                        deposit_request_id=request.id,
                    )
                )
                await session.commit()
                await _push_to_user(session, target.id, message)
                await session.commit()
            # Full payment completion keeps the existing admin email behaviour.
            if (
                type_ == TYPE_TRANCHE_PAID
                and request.current_status == RequestStatus.PAYMENT_PROCESSED
            ):
                await _email_admins(session, request.request_number, tranche.tt_copy_url)
    except Exception as exc:
        logger.error(
            "notify_tranche_event failed",
            request_id=str(request_id), tranche_id=str(tranche_id), error=str(exc),
        )


async def notify_tranche_added(
    request_id: UUID, tranche_id: UUID, reopened: bool = False
) -> None:
    """After a merchandiser adds a tranche — bell + push to every active
    Accounts Team user AND super admin (19 Aug 2026 fix: adds previously
    reused the generic 'updated' notification, which skipped super admins).
    When the add reopened a completed file, the message says so.

    Own session; failures logged and swallowed (BackgroundTasks contract).
    """
    from app.core.database import AsyncSessionFactory
    from app.models.tranche import PaymentTranche

    try:
        async with AsyncSessionFactory() as session:
            request = await _load_request(session, request_id)
            tranche = await session.get(PaymentTranche, tranche_id)
            if request is None or tranche is None:
                return
            body = (
                f"{tranche.label} ({tranche.amount}) was added to "
                f"{request.request_number}"
                + (
                    " — the completed file has been REOPENED for the additional amount."
                    if reopened
                    else " by the merchandiser."
                )
            )
            message = {
                "title": "File reopened — new tranche" if reopened else "New tranche added",
                "body": body,
                "url": f"/accounts/{request_id}",
                "attachment_url": None,
            }
            result = await session.execute(
                select(User).where(
                    User.role.in_([UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN]),
                    User.is_active == True,  # noqa: E712
                )
            )
            targets = list(result.scalars().all())
            for user in targets:
                session.add(
                    Notification(
                        user_id=user.id,
                        type=TYPE_TRANCHE_UPDATED,
                        title=message["title"],
                        body=message["body"],
                        url=message["url"],
                        attachment_url=None,
                        deposit_request_id=request.id,
                    )
                )
            await session.commit()
            for user in targets:
                await _push_to_user(session, user.id, message)
            await session.commit()
    except Exception as exc:
        logger.error(
            "notify_tranche_added failed",
            request_id=str(request_id), tranche_id=str(tranche_id), error=str(exc),
        )


async def notify_tranche_released(request_id: UUID, tranche_id: UUID) -> None:
    """After the merchandiser releases a 'Yet to be Released' tranche
    (19 Aug 2026) — bell + push to every active Accounts Team user and super
    admin: the tranche is now payable.

    Own session; failures logged and swallowed (BackgroundTasks contract).
    """
    from app.core.database import AsyncSessionFactory
    from app.models.tranche import PaymentTranche

    try:
        async with AsyncSessionFactory() as session:
            request = await _load_request(session, request_id)
            tranche = await session.get(PaymentTranche, tranche_id)
            if request is None or tranche is None:
                return
            message = {
                "title": "Tranche released — ready to pay",
                "body": (
                    f"{tranche.label} ({tranche.amount}) of "
                    f"{request.request_number} was released by the "
                    f"merchandiser and can now be paid."
                ),
                "url": f"/accounts/{request_id}",
                "attachment_url": None,
            }
            result = await session.execute(
                select(User).where(
                    User.role.in_([UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN]),
                    User.is_active == True,  # noqa: E712
                )
            )
            targets = list(result.scalars().all())
            for user in targets:
                session.add(
                    Notification(
                        user_id=user.id,
                        type=TYPE_TRANCHE_UPDATED,
                        title=message["title"],
                        body=message["body"],
                        url=message["url"],
                        attachment_url=None,
                        deposit_request_id=request.id,
                    )
                )
            await session.commit()
            for user in targets:
                await _push_to_user(session, user.id, message)
            await session.commit()
    except Exception as exc:
        logger.error(
            "notify_tranche_released failed",
            request_id=str(request_id), tranche_id=str(tranche_id), error=str(exc),
        )


async def send_release_reminders() -> None:
    """Daily scheduler job (19 Aug 2026): remind each merchandiser about
    their 'Yet to be Released' tranches (2 onwards) starting 5 days before
    the tentative payment date — "5 days left", "4 days left", …, "due
    today", then "overdue by N days" until released or the file closes.
    Bell + push, one notification per tranche per daily run.

    Own session; failures logged and swallowed (scheduler contract).
    """
    from datetime import date as date_cls
    from datetime import timedelta

    from app.core.database import AsyncSessionFactory
    from app.models.deposit_request import DepositRequest
    from app.models.enums import TrancheStatus
    from app.models.tranche import PaymentTranche

    try:
        async with AsyncSessionFactory() as session:
            today = date_cls.today()
            result = await session.execute(
                select(PaymentTranche, DepositRequest)
                .join(
                    DepositRequest,
                    DepositRequest.id == PaymentTranche.deposit_request_id,
                )
                .where(
                    PaymentTranche.status == TrancheStatus.UNPAID,
                    PaymentTranche.released_at.is_(None),
                    PaymentTranche.tranche_number > 1,
                    PaymentTranche.tentative_payment_date.isnot(None),
                    PaymentTranche.tentative_payment_date <= today + timedelta(days=5),
                    DepositRequest.is_deleted == False,  # noqa: E712
                    DepositRequest.current_status == RequestStatus.PENDING_PAYMENT,
                    DepositRequest.created_by.isnot(None),
                )
            )
            rows = result.all()
            sent = 0
            for tranche, request in rows:
                days_left = (tranche.tentative_payment_date - today).days
                if days_left > 0:
                    when = f"{days_left} day{'s' if days_left != 1 else ''} left"
                elif days_left == 0:
                    when = "due TODAY"
                else:
                    when = f"overdue by {-days_left} day{'s' if days_left != -1 else ''}"
                message = {
                    "title": f"Release reminder — {when}",
                    "body": (
                        f"{tranche.label} ({tranche.amount}) of "
                        f"{request.request_number} is due on "
                        f"{tranche.tentative_payment_date.strftime('%d/%m/%Y')} and is "
                        f"still Yet to be Released. Release it so Accounts can pay."
                    ),
                    "url": f"/merchandiser/{request.id}",
                    "attachment_url": None,
                }
                session.add(
                    Notification(
                        user_id=request.created_by,
                        type=TYPE_TRANCHE_UPDATED,
                        title=message["title"],
                        body=message["body"],
                        url=message["url"],
                        attachment_url=None,
                        deposit_request_id=request.id,
                    )
                )
                await session.commit()
                await _push_to_user(session, request.created_by, message)
                await session.commit()
                sent += 1
            if sent:
                logger.info("release reminders sent", count=sent)
    except Exception as exc:
        logger.error("send_release_reminders failed", error=str(exc))


async def notify_tranche_updated(request_id: UUID, tranche_id: UUID, changes: str) -> None:
    """After a merchandiser edits an unpaid tranche — bell + push to every
    active Accounts Team user so they work from the latest values.

    Own session; failures logged and swallowed (BackgroundTasks contract).
    """
    from app.core.database import AsyncSessionFactory
    from app.models.tranche import PaymentTranche

    try:
        async with AsyncSessionFactory() as session:
            request = await _load_request(session, request_id)
            tranche = await session.get(PaymentTranche, tranche_id)
            if request is None or tranche is None:
                return
            message = build_tranche_notification_message(
                TYPE_TRANCHE_UPDATED, request.request_number, tranche.label, request.id,
                changes=changes,
            )
            result = await session.execute(
                select(User).where(
                    User.role == UserRole.ACCOUNTS_TEAM, User.is_active == True  # noqa: E712
                )
            )
            accounts_users = list(result.scalars().all())
            for user in accounts_users:
                session.add(
                    Notification(
                        user_id=user.id,
                        type=TYPE_TRANCHE_UPDATED,
                        title=message["title"],
                        body=message["body"],
                        url=message["url"],
                        attachment_url=None,
                        deposit_request_id=request.id,
                    )
                )
            await session.commit()
            for user in accounts_users:
                await _push_to_user(session, user.id, message)
            await session.commit()
    except Exception as exc:
        logger.error(
            "notify_tranche_updated failed",
            request_id=str(request_id), tranche_id=str(tranche_id), error=str(exc),
        )


async def notify_hom_decision(request_id: UUID, decision: str, remarks: str) -> None:
    """After a HoM approve/reject — bell + push to the merchandiser who raised
    the request, including the mandatory reason.

    decision: 'approved' or 'rejected'. Resolves the recipient via
    _find_target_user (handles both created_by and public-form
    submitter_email). Own session; failures logged and swallowed
    (BackgroundTasks contract).
    """
    from app.core.database import AsyncSessionFactory

    try:
        async with AsyncSessionFactory() as session:
            request = await _load_request(session, request_id)
            if request is None:
                return
            type_ = TYPE_HOM_REJECTED if decision == "rejected" else TYPE_HOM_APPROVED
            message = build_hom_decision_message(
                type_, request.request_number, request.id, remarks
            )
            target = await _find_target_user(session, request)
            if target is None:
                logger.info(
                    "No target user for HoM decision notification — skipping",
                    request_id=str(request_id),
                )
                return
            session.add(
                Notification(
                    user_id=target.id,
                    type=type_,
                    title=message["title"],
                    body=message["body"],
                    url=message["url"],
                    attachment_url=None,
                    deposit_request_id=request.id,
                )
            )
            await session.commit()
            await _push_to_user(session, target.id, message)
            await session.commit()
    except Exception as exc:
        logger.error(
            "notify_hom_decision failed",
            request_id=str(request_id), decision=decision, error=str(exc),
        )


async def notify_request_created(request_id: UUID) -> None:
    """After a request is created OR enters the payment queue via HoM approval
    (Aug 2026 batch, item 1.2 — neither previously notified anyone).

    pending_hom_approval → every active Head of Merchandiser ("approval
    required"); pending_payment → every active Accounts Team user ("awaiting
    payment processing"). Own session; failures logged and swallowed.
    """
    from app.core.database import AsyncSessionFactory

    try:
        async with AsyncSessionFactory() as session:
            request = await _load_request(session, request_id)
            if request is None:
                return
            if request.current_status == RequestStatus.PENDING_HOM_APPROVAL:
                message = {
                    "title": "Approval required",
                    "body": (
                        f"New request {request.request_number} from a flagged supplier "
                        "awaits Head of Merchandiser approval."
                    ),
                    "url": f"/hom/{request.id}",
                    "attachment_url": None,
                }
                users = await _active_users_with_role(session, UserRole.HEAD_OF_MERCHANDISER)
                await _deliver_to_users(session, users, TYPE_REQUEST_PENDING_HOM, message, request.id)
            elif request.current_status == RequestStatus.PENDING_PAYMENT:
                message = {
                    "title": "New Supplier Advance Payment Request",
                    "body": (
                        f"{request.request_number} is in the payment queue "
                        "awaiting processing."
                    ),
                    "url": f"/accounts/{request.id}",
                    "attachment_url": None,
                }
                users = await _active_users_with_role(session, UserRole.ACCOUNTS_TEAM)
                await _deliver_to_users(session, users, TYPE_REQUEST_CREATED, message, request.id)
    except Exception as exc:
        logger.error(
            "notify_request_created failed", request_id=str(request_id), error=str(exc)
        )


async def notify_status_change(
    request_id: UUID, new_status: str, actor_role: str, remarks: str | None = None
) -> None:
    """After hold / resume / cancel / reopen — the counterpart is notified
    (Aug 2026 batch, item 1.2: transition_status emitted nothing before).

    Merchandiser actions fan out to the Accounts Team; accounts-side actions
    (accounts_team / super_admin / finance_admin) go to the raising
    merchandiser via _find_target_user. Own session; failures logged and
    swallowed (BackgroundTasks contract).
    """
    from app.core.database import AsyncSessionFactory

    try:
        async with AsyncSessionFactory() as session:
            request = await _load_request(session, request_id)
            if request is None:
                return
            actor_is_merchandiser = actor_role == UserRole.MERCHANDISER.value
            message = build_status_change_message(
                new_status, request.request_number, request.id,
                actor_is_merchandiser, remarks,
            )
            if actor_is_merchandiser:
                users = await _active_users_with_role(session, UserRole.ACCOUNTS_TEAM)
                await _deliver_to_users(session, users, TYPE_STATUS_CHANGED, message, request.id)
            else:
                target = await _find_target_user(session, request)
                if target is None:
                    logger.info(
                        "No target user for status-change notification — skipping",
                        request_id=str(request_id),
                    )
                    return
                await _deliver_to_users(session, [target], TYPE_STATUS_CHANGED, message, request.id)
    except Exception as exc:
        logger.error(
            "notify_status_change failed",
            request_id=str(request_id), new_status=new_status, error=str(exc),
        )


async def notify_request_rejected_by_accounts(request_id: UUID, reason: str) -> None:
    """After Accounts reject a whole request (terminal, UAT Aug 2026
    item 12) — bell + push to the merchandiser who raised it AND every
    active Head of Merchandiser, so HoM sees their approved request bounce.

    Own session; failures logged and swallowed (BackgroundTasks contract).
    """
    from app.core.database import AsyncSessionFactory

    try:
        async with AsyncSessionFactory() as session:
            request = await _load_request(session, request_id)
            if request is None:
                return
            body = (
                f"Request {request.request_number} was rejected by the Accounts "
                f"team. Reason: {reason}. The request is now closed and can no "
                "longer be edited."
            )
            # Same content, but each audience's link opens their own view.
            target = await _find_target_user(session, request)
            if target is not None:
                await _deliver_to_users(
                    session, [target], TYPE_REQUEST_REJECTED,
                    {
                        "title": "Request rejected by Accounts",
                        "body": body,
                        "url": f"/merchandiser/{request_id}",
                        "attachment_url": None,
                    },
                    request.id,
                )
            homs = [
                u
                for u in await _active_users_with_role(
                    session, UserRole.HEAD_OF_MERCHANDISER
                )
                if target is None or u.id != target.id
            ]
            if homs:
                await _deliver_to_users(
                    session, homs, TYPE_REQUEST_REJECTED,
                    {
                        "title": "Request rejected by Accounts",
                        "body": body,
                        "url": f"/hom/{request_id}",
                        "attachment_url": None,
                    },
                    request.id,
                )
            if target is None and not homs:
                logger.info(
                    "No recipients for request-rejected notification — skipping",
                    request_id=str(request_id),
                )
    except Exception as exc:
        logger.error(
            "notify_request_rejected_by_accounts failed",
            request_id=str(request_id), error=str(exc),
        )


async def notify_tranche_rejected(request_id: UUID, tranche_id: UUID, reason: str) -> None:
    """After Accounts/HoM reject a tranche — bell + push to the merchandiser
    who raised the request (with a prompt to add replacement tranches) AND
    to every active Head of Merchandiser (10 Aug 2026 follow-up: HoM hears
    about BOTH rejection levels, tranche and whole-request), each audience
    with the mandatory reason and its own deep link.

    Own session; failures logged and swallowed (BackgroundTasks contract).
    """
    from app.core.database import AsyncSessionFactory
    from app.models.tranche import PaymentTranche

    try:
        async with AsyncSessionFactory() as session:
            request = await _load_request(session, request_id)
            tranche = await session.get(PaymentTranche, tranche_id)
            if request is None or tranche is None:
                return
            target = await _find_target_user(session, request)
            if target is not None:
                await _deliver_to_users(
                    session, [target], TYPE_TRANCHE_REJECTED,
                    {
                        "title": "Tranche rejected",
                        "body": (
                            f"{tranche.label} of {request.request_number} was rejected by the "
                            f"Accounts team. Reason: {reason} — add a replacement tranche so "
                            "the request total matches again."
                        ),
                        "url": f"/merchandiser/{request_id}",
                        "attachment_url": None,
                    },
                    request.id,
                )
            homs = [
                u
                for u in await _active_users_with_role(
                    session, UserRole.HEAD_OF_MERCHANDISER
                )
                if target is None or u.id != target.id
            ]
            if homs:
                await _deliver_to_users(
                    session, homs, TYPE_TRANCHE_REJECTED,
                    {
                        "title": "Tranche rejected",
                        "body": (
                            f"{tranche.label} of {request.request_number} was rejected by the "
                            f"Accounts team. Reason: {reason}. The merchandiser has been asked "
                            "to add replacement tranches."
                        ),
                        "url": f"/hom/{request_id}",
                        "attachment_url": None,
                    },
                    request.id,
                )
            if target is None and not homs:
                logger.info(
                    "No recipients for tranche-rejected notification — skipping",
                    request_id=str(request_id),
                )
    except Exception as exc:
        logger.error(
            "notify_tranche_rejected failed",
            request_id=str(request_id), tranche_id=str(tranche_id), error=str(exc),
        )


async def notify_tranche_removed(request_id: UUID, label: str) -> None:
    """After a merchandiser deletes a tranche — bell + push to every active
    Accounts Team user. The tranche row is gone, so the label travels as an
    argument instead of being loaded.

    Own session; failures logged and swallowed (BackgroundTasks contract).
    """
    from app.core.database import AsyncSessionFactory

    try:
        async with AsyncSessionFactory() as session:
            request = await _load_request(session, request_id)
            if request is None:
                return
            message = {
                "title": "Tranche removed",
                "body": f"{label} of {request.request_number} was removed by the merchandiser.",
                "url": f"/accounts/{request_id}",
                "attachment_url": None,
            }
            result = await session.execute(
                select(User).where(
                    User.role == UserRole.ACCOUNTS_TEAM, User.is_active == True  # noqa: E712
                )
            )
            accounts_users = list(result.scalars().all())
            for user in accounts_users:
                session.add(
                    Notification(
                        user_id=user.id,
                        type=TYPE_TRANCHE_UPDATED,
                        title=message["title"],
                        body=message["body"],
                        url=message["url"],
                        attachment_url=None,
                        deposit_request_id=request.id,
                    )
                )
            await session.commit()
            for user in accounts_users:
                await _push_to_user(session, user.id, message)
            await session.commit()
    except Exception as exc:
        logger.error(
            "notify_tranche_removed failed",
            request_id=str(request_id), label=label, error=str(exc),
        )


async def _load_adjustment_context(session: AsyncSession, adjustment_id: UUID):
    """(adjustment, message-builder kwargs) or (None, None) if rows vanished."""
    from app.repositories.tranche_repo import TrancheRepository

    from app.models.tranche import InvoiceAdjustment

    adjustment = await session.get(InvoiceAdjustment, adjustment_id)
    if adjustment is None:
        return None, None
    repo = TrancheRepository(session)
    source = await repo.get_with_request(adjustment.source_tranche_id)
    destination = await repo.get_with_request(adjustment.destination_tranche_id)
    if source is None or destination is None:
        return None, None
    kwargs = {
        "amount": str(adjustment.amount),
        "source_label": source.label,
        "source_request_number": source.deposit_request.request_number,
        "destination_label": destination.label,
        "destination_request_number": destination.deposit_request.request_number,
    }
    return adjustment, kwargs


async def notify_adjustment_created(adjustment_id: UUID) -> None:
    """After an adjustment is raised/recorded — bell + push to every active
    Accounts Team user (excluding the actor), per change note B2/B3.

    Pending (merchandiser-raised) adjustments send 'adjustment_requested';
    immediately-completed ones send 'adjustment_recorded'.
    Own session; failures logged and swallowed (BackgroundTasks contract).
    """
    from app.core.database import AsyncSessionFactory
    from app.models.enums import AdjustmentStatus

    try:
        async with AsyncSessionFactory() as session:
            adjustment, kwargs = await _load_adjustment_context(session, adjustment_id)
            if adjustment is None:
                return
            type_ = (
                TYPE_ADJUSTMENT_REQUESTED
                if adjustment.status == AdjustmentStatus.PENDING_APPROVAL
                else TYPE_ADJUSTMENT_RECORDED
            )
            message = build_adjustment_notification_message(
                type_, reason=adjustment.reason, **kwargs
            )
            result = await session.execute(
                select(User).where(
                    User.role == UserRole.ACCOUNTS_TEAM,
                    User.is_active == True,  # noqa: E712
                    User.id != adjustment.performed_by,
                )
            )
            accounts_users = list(result.scalars().all())
            for user in accounts_users:
                session.add(
                    Notification(
                        user_id=user.id,
                        type=type_,
                        title=message["title"],
                        body=message["body"],
                        url=message["url"],
                        attachment_url=None,
                        deposit_request_id=None,
                    )
                )
            await session.commit()
            for user in accounts_users:
                await _push_to_user(session, user.id, message)
            await session.commit()
    except Exception as exc:
        logger.error(
            "notify_adjustment_created failed",
            adjustment_id=str(adjustment_id), error=str(exc),
        )


async def notify_adjustment_decided(adjustment_id: UUID, decision: str, reason: str) -> None:
    """After Accounts approves/rejects — bell + push back to the user who
    raised the adjustment request, including the mandatory reason.

    Own session; failures logged and swallowed (BackgroundTasks contract).
    """
    from app.core.database import AsyncSessionFactory

    try:
        async with AsyncSessionFactory() as session:
            adjustment, kwargs = await _load_adjustment_context(session, adjustment_id)
            if adjustment is None:
                return
            message = build_adjustment_notification_message(
                TYPE_ADJUSTMENT_DECIDED, reason=reason, decision=decision, **kwargs
            )
            session.add(
                Notification(
                    user_id=adjustment.performed_by,
                    type=TYPE_ADJUSTMENT_DECIDED,
                    title=message["title"],
                    body=message["body"],
                    url=message["url"],
                    attachment_url=None,
                    deposit_request_id=None,
                )
            )
            await session.commit()
            await _push_to_user(session, adjustment.performed_by, message)
            await session.commit()
    except Exception as exc:
        logger.error(
            "notify_adjustment_decided failed",
            adjustment_id=str(adjustment_id), decision=decision, error=str(exc),
        )


async def _load_file_remark_context(session: AsyncSession, remark_id: UUID):
    from app.models.file_remark import FileRemark

    remark = await session.get(FileRemark, remark_id)
    if remark is None:
        return None, None
    request = await _load_request(session, remark.deposit_request_id)
    return remark, request


def _file_remark_body(remark, request_number: str) -> str:
    # Same wording as the audit summary — category, files, amounts, split
    # targets, optional remark.
    from app.services.file_remark_service import FileRemarkService

    return FileRemarkService._summary(remark, request_number)


async def notify_file_remark_raised(remark_id: UUID) -> None:
    """After a file remark is raised — bell + push to every active Accounts
    user except the actor (CIO batch 2, Aug 2026).

    Own session; failures logged and swallowed (BackgroundTasks contract).
    """
    from app.core.database import AsyncSessionFactory

    try:
        async with AsyncSessionFactory() as session:
            remark, request = await _load_file_remark_context(session, remark_id)
            if remark is None or request is None:
                return
            message = {
                "title": "File remark raised",
                "body": _file_remark_body(remark, request.request_number),
                "url": "/file-remarks",
                "attachment_url": None,
            }
            users = [
                u for u in await _active_users_with_role(session, UserRole.ACCOUNTS_TEAM)
                if u.id != remark.created_by
            ]
            await _deliver_to_users(
                session, users, TYPE_FILE_REMARK_RAISED, message, request.id
            )
    except Exception as exc:
        logger.error(
            "notify_file_remark_raised failed", remark_id=str(remark_id), error=str(exc)
        )


async def notify_file_remark_decided(remark_id: UUID) -> None:
    """After Accounts approve or reject a file remark (UAT Aug 2026,
    item 14) — bell + push back to the user who raised it, naming the
    decision and including the note/reason when given. Also handles legacy
    'resolved' rows, worded as resolved.

    Own session; failures logged and swallowed (BackgroundTasks contract).
    """
    from app.core.database import AsyncSessionFactory

    try:
        async with AsyncSessionFactory() as session:
            remark, request = await _load_file_remark_context(session, remark_id)
            if remark is None or request is None:
                return
            wording = {
                "approved": "approved and processed",
                "rejected": "rejected",
            }.get(remark.status, "resolved")
            body = (
                f"Your file remark on {request.request_number} was {wording} by "
                "the Accounts team."
            )
            if remark.response_note:
                body += f" Response: {remark.response_note}"
            message = {
                "title": f"File remark {wording.split()[0]}",
                "body": body,
                "url": "/file-remarks",
                "attachment_url": None,
            }
            creator = await session.get(User, remark.created_by)
            if creator is None:
                return
            await _deliver_to_users(
                session, [creator], TYPE_FILE_REMARK_RESOLVED, message, request.id
            )
    except Exception as exc:
        logger.error(
            "notify_file_remark_decided failed", remark_id=str(remark_id), error=str(exc)
        )


# ── Fallback scheduler job ───────────────────────────────────────────────────


async def send_fallback_notifications(session_factory: async_sessionmaker) -> int:
    """Plain 'payment processed' notice for requests processed >1 h ago with no
    TT copy and no notification yet. Returns how many were sent."""
    try:
        async with session_factory() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
            processed_at = (
                select(
                    StatusHistory.deposit_request_id,
                    func.max(StatusHistory.changed_at).label("processed_at"),
                )
                .where(StatusHistory.new_status == RequestStatus.PAYMENT_PROCESSED)
                .group_by(StatusHistory.deposit_request_id)
                .subquery()
            )
            notified = (
                select(Notification.deposit_request_id)
                .where(Notification.type == TYPE_PAYMENT_PROCESSED)
                .subquery()
            )
            stmt = (
                select(DepositRequest)
                .join(processed_at, processed_at.c.deposit_request_id == DepositRequest.id)
                .outerjoin(
                    PaymentDetails, PaymentDetails.deposit_request_id == DepositRequest.id
                )
                .where(
                    DepositRequest.current_status == RequestStatus.PAYMENT_PROCESSED,
                    processed_at.c.processed_at < cutoff,
                    PaymentDetails.tt_copy_url.is_(None),
                    DepositRequest.id.notin_(select(notified.c.deposit_request_id)),
                )
                .options(selectinload(DepositRequest.payment))
            )
            requests = list((await session.execute(stmt)).scalars().all())
            for request in requests:
                try:
                    await _deliver(session, request, TYPE_PAYMENT_PROCESSED, None)
                except Exception as exc:
                    logger.error(
                        "Fallback notification failed",
                        request_id=str(request.id),
                        error=str(exc),
                    )
                    await session.rollback()
            if requests:
                logger.info("Fallback payment notifications sent", count=len(requests))
            return len(requests)
    except Exception as exc:
        logger.error("send_fallback_notifications crashed", error=str(exc))
        return 0
