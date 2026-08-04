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
TYPE_TRANCHE_TT_ATTACHED = "tranche_tt_attached"
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

    tranche_paid / tranche_tt_attached go to the merchandiser who raised the
    request; tranche_updated goes to the Accounts Team.
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
    if type_ == TYPE_TRANCHE_TT_ATTACHED:
        return {
            "title": "TT copy attached",
            "body": f"The TT copy for {tranche_label} of {request_number} is now available.",
            "url": f"/merchandiser/{request_id}",
            "attachment_url": tt_copy_url,
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
    """After a tranche payment or TT upload — bell + push to the merchandiser
    who raised the request, naming the paid tranche and request number.

    event: 'paid' or 'tt_attached'. When the tranche payment completed the
    whole request, HoM / super admins also get the payment-processed email.
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
            type_ = TYPE_TRANCHE_TT_ATTACHED if event == "tt_attached" else TYPE_TRANCHE_PAID
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


async def notify_tranche_rejected(request_id: UUID, tranche_id: UUID, reason: str) -> None:
    """After Accounts/HoM reject a tranche — bell + push to the merchandiser
    who raised the request, including the mandatory reason and a prompt to add
    replacement tranches (Aug 2026 rejection workflow).

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
                "title": "Tranche rejected",
                "body": (
                    f"{tranche.label} of {request.request_number} was rejected by the "
                    f"Accounts team. Reason: {reason} — add a replacement tranche so "
                    "the request total matches again."
                ),
                "url": f"/merchandiser/{request_id}",
                "attachment_url": None,
            }
            target = await _find_target_user(session, request)
            if target is None:
                logger.info(
                    "No target user for tranche-rejected notification — skipping",
                    request_id=str(request_id),
                )
                return
            await _deliver_to_users(
                session, [target], TYPE_TRANCHE_REJECTED, message, request.id
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
