# Notification Matrix — audited 1 Aug 2026 (batch item 1.2)

Every state change in the system, who gets notified, and by which trigger.
"Bell + push" = a `notifications` row plus Web Push to every registered
subscription of the recipient(s). All triggers run via `BackgroundTasks` with
the own-session / log-and-swallow contract in
`backend/app/services/notification_service.py`.

Recipient resolution for "the merchandiser" is `_find_target_user` — handles
both `created_by` and legacy public-form `submitter_email` rows. Role
fan-outs go to every **active** user of that role.

## Existing before this batch

| Event | Recipient(s) | Type | Since |
|---|---|---|---|
| Payment processed (request-level, legacy) | Merchandiser (+ email to HoM/super admins) | `payment_processed` | pre-July |
| Request-level TT copy attached | Merchandiser | `tt_copy_attached` | pre-July |
| Tranche marked paid | Merchandiser | `tranche_paid` | 0018 |
| Tranche TT copy attached | Merchandiser | `tranche_tt_attached` | 0018 |
| Tranche edited by merchandiser | Accounts Team | `tranche_updated` | 0018 |
| HoM approved / rejected | Merchandiser (reason included) | `hom_approved` / `hom_rejected` | July C4 |
| Adjustment raised (pending) | Accounts Team (excl. actor) | `adjustment_requested` | July B2/B3 |
| Adjustment recorded (completed) | Accounts Team (excl. actor) | `adjustment_recorded` | July B2 |
| Adjustment approved / rejected | Raising merchandiser (reason included) | `adjustment_decided` | July B3 |
| Tranche added by merchandiser | Accounts Team | `tranche_updated` | Aug ph.3 |
| Tranche deleted by merchandiser | Accounts Team | `tranche_removed` (type `tranche_updated`) | Aug ph.3 |
| Fallback: processed >1 h, no TT, never notified | Merchandiser | `payment_processed` | pre-July (scheduler) |

## Gaps found by this audit → filled in Phase 5

| Event | Recipient(s) | Type | Trigger point |
|---|---|---|---|
| Request created (→ pending_payment) | Accounts Team | `request_created` | `POST /requests` |
| Request created flagged (→ pending_hom_approval) | Head of Merchandiser users | `request_pending_hom` | `POST /requests` |
| Request enters payment queue via HoM approval | Accounts Team | `request_created` | `POST /{id}/hom-approve` |
| Hold by merchandiser | Accounts Team | `status_changed` | `POST /{id}/hold` |
| Hold by accounts | Merchandiser | `status_changed` | `POST /{id}/hold` |
| Resume (either side) | The counterpart | `status_changed` | `POST /{id}/resume` |
| Cancel by merchandiser | Accounts Team | `status_changed` | `POST /{id}/cancel` |
| Cancel by accounts | Merchandiser | `status_changed` | `POST /{id}/cancel` |
| Reopen (accounts) | Merchandiser | `status_changed` | `POST /{id}/reopen` |

Routing rule for `status_changed`: the actor's counterpart is notified —
merchandiser actions fan out to Accounts (deep-link `/accounts/{id}`),
accounts-side actions (accounts_team / super_admin) go to the raising
merchandiser (deep-link `/merchandiser/{id}`). Remarks are appended when
present.

## Known non-triggers (deliberate)

- `super_admin` / `finance_admin` are not included in role fan-outs (matches
  the pre-existing `tranche_updated` behaviour; revisit if admins want the
  noise).
- Payment-details saves (request- or tranche-level) don't notify — they are
  accounts' own working data; the merchandiser hears when the tranche is
  actually paid.
- Ship-date recording doesn't notify (Ship Date scope is deferred entirely).
- Request soft-delete (super admin) doesn't notify.
