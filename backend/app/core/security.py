"""Authentication: Google sign-in verification + app-issued JWTs.

Login flow (popup auth-code flow, no third-party auth service):
  1. Frontend opens the Google popup and receives a one-time auth code.
  2. POST /api/v1/auth/google/login exchanges the code with Google using the
     server-side client secret, then verifies the returned ID token.
  3. The backend issues its own HS256 JWT (signed with SECRET_KEY) that every
     subsequent request carries as a Bearer token.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import httpx
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from jose import JWTError, jwt

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_JWT_ALGORITHM = "HS256"
_JWT_ISSUER = "finance-operations"


async def exchange_google_auth_code(code: str) -> dict[str, Any]:
    """Exchange a Google auth code for verified ID-token claims.

    Returns the verified claims dict (email, name, picture, ...).
    Raises AuthenticationError on any failure.
    """
    if not settings.google_client_id or not settings.google_client_secret:
        logger.error("Google OAuth is not configured (GOOGLE_CLIENT_ID/SECRET missing)")
        raise AuthenticationError("Sign-in is not configured on this server")

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                _GOOGLE_TOKEN_ENDPOINT,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    # The GIS popup code client uses the literal "postmessage"
                    # redirect_uri instead of a registered URL.
                    "redirect_uri": "postmessage",
                    "grant_type": "authorization_code",
                },
            )
        except httpx.HTTPError as exc:
            logger.warning("Google token endpoint unreachable", error=str(exc))
            raise AuthenticationError("Unable to reach Google to verify sign-in") from exc

    if resp.status_code != 200:
        logger.warning(
            "Google code exchange failed", status=resp.status_code, body=resp.text[:200]
        )
        raise AuthenticationError("Google sign-in failed")

    raw_id_token = resp.json().get("id_token")
    if not raw_id_token:
        raise AuthenticationError("Google sign-in failed")

    try:
        claims = google_id_token.verify_oauth2_token(
            raw_id_token, google_requests.Request(), settings.google_client_id
        )
    except ValueError as exc:
        logger.warning("Google ID token verification failed", error=str(exc))
        raise AuthenticationError("Google sign-in failed") from exc

    if not claims.get("email") or not claims.get("email_verified"):
        raise AuthenticationError("Google account email is not verified")

    return claims


def create_access_token(*, user_id: UUID, email: str) -> str:
    """Issue an application JWT for an authenticated user."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "iss": _JWT_ISSUER,
        "sub": str(user_id),
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and verify an app-issued JWT. Raises AuthenticationError on failure."""
    try:
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=[_JWT_ALGORITHM],
            issuer=_JWT_ISSUER,
        )
    except JWTError as exc:
        logger.warning("JWT decode failed", error=str(exc))
        raise AuthenticationError("Invalid or expired token") from exc
