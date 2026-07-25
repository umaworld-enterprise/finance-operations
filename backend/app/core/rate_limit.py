"""Shared rate limiter instance (slowapi, keyed by client IP).

Uses slowapi's default in-memory storage. The backend runs 2 uvicorn worker
processes per container (see railway.toml / Dockerfile) with no shared cache,
so limits are enforced per-process — the effective ceiling across the
container is up to ~2x the configured value. Acceptable for now; move to a
Redis-backed storage if the deployment ever scales to multiple replicas or
per-worker precision becomes important.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
