"""JWT validation against Supabase-issued tokens."""

import time
from typing import Any

import httpx
from jose import JWTError, jwt

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Legacy Supabase projects sign with HS256 (shared JWT secret).
# Modern projects sign with asymmetric keys (ES256/RS256) verified via JWKS.
_JWKS_TTL_SECONDS = 600.0
_jwks_cache: dict[str, Any] = {"keys": None, "fetched_at": 0.0}


def _jwks_url() -> str:
    base = str(settings.supabase_url).rstrip("/")
    return f"{base}/auth/v1/.well-known/jwks.json"


def _get_jwks(force_refresh: bool = False) -> list[dict[str, Any]]:
    """Fetch (and cache) Supabase's public JWKS for asymmetric token verification."""
    now = time.time()
    fresh = _jwks_cache["keys"] is not None and (now - _jwks_cache["fetched_at"]) < _JWKS_TTL_SECONDS
    if fresh and not force_refresh:
        return _jwks_cache["keys"]

    resp = httpx.get(_jwks_url(), timeout=5.0)
    resp.raise_for_status()
    keys = resp.json().get("keys", [])
    _jwks_cache["keys"] = keys
    _jwks_cache["fetched_at"] = now
    return keys


def _find_signing_key(kid: str) -> dict[str, Any] | None:
    """Locate a JWK by key id, refreshing once if not found (handles key rotation)."""
    for key in _get_jwks():
        if key.get("kid") == kid:
            return key
    for key in _get_jwks(force_refresh=True):
        if key.get("kid") == kid:
            return key
    return None


def decode_supabase_token(token: str) -> dict[str, Any]:
    """Decode and verify a Supabase-issued JWT. Raises AuthenticationError on failure."""
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "HS256")

        if alg == "HS256":
            # Legacy symmetric verification with the shared JWT secret
            return jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False},  # Supabase does not always set aud
            )

        # Asymmetric verification (ES256/RS256) against the project's public JWKS
        kid = header.get("kid")
        signing_key = _find_signing_key(kid) if kid else None
        if not signing_key:
            raise AuthenticationError("Token signing key not found in JWKS")

        return jwt.decode(
            token,
            signing_key,
            algorithms=[alg],
            options={"verify_aud": False},
        )
    except AuthenticationError:
        raise
    except JWTError as exc:
        logger.warning("JWT decode failed", error=str(exc))
        raise AuthenticationError("Invalid or expired token") from exc
    except httpx.HTTPError as exc:
        logger.warning("JWKS fetch failed", error=str(exc))
        raise AuthenticationError("Unable to verify token signing key") from exc
