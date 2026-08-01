"""Public form endpoints — RETIRED (Aug 2026 change batch, item 1).

The unauthenticated request form was retired: deposit requests are now raised
exclusively through the authenticated in-app form. These routes return
410 Gone so old bookmarks and shared form links fail loudly instead of
silently, and the frontend /form page shows a sign-in notice.

Legacy notes:
- Requests submitted through the old form carry submitter_email; notification
  recipient resolution (_find_target_user) still honours it — do not remove.
- DepositRequestService.create_public remains in the service layer for that
  same history.
- The public_form_fields SystemConfig rows and the admin Form Links data are
  retained untouched in the database in case the feature is ever revived.
"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/public", tags=["public-form"])

_GONE_DETAIL = (
    "The public request form has been retired. Please sign in to the "
    "Advance Deposit Tracker and raise your request from the dashboard."
)


def _gone() -> None:
    raise HTTPException(status_code=410, detail=_GONE_DETAIL)


@router.get("/form-config")
async def get_public_form_config() -> None:
    _gone()


@router.get("/masters")
async def get_masters() -> None:
    _gone()


@router.post("/submit")
async def submit_public_form() -> None:
    _gone()
