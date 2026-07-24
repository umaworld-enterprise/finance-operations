# Deployment — AWS single instance (Docker Compose + Caddy)

Quick reference for standing the app up on one EC2 host. The full step-by-step
runbook (EC2 provisioning, security group, DNS, backups, auto-recovery) is in
**`docs/Finance Operations - AWS Deployment Runbook (Developer).pdf`**.

The app runs as three containers on one box. **Supabase stays external and unchanged.**

```
Internet (443)
      │
   Caddy  ──/api/*──►  backend   (FastAPI  :8000)
          ──/health─►  backend
          ──else────►  frontend  (Next.js  :3000)
                          └──────►  Supabase (Postgres · Auth · RLS)  [external]
```

## Files in this repo
| File | Purpose |
|---|---|
| `docker-compose.prod.yml` | The three services (backend, frontend, caddy) |
| `Caddyfile` | HTTPS + request routing — **replace the domain** |
| `backend/Dockerfile`, `frontend/Dockerfile` | Container images |

## Prerequisites
- EC2 **t3.large** (2 vCPU / 8 GB) + T3 Unlimited, Ubuntu 24.04, **ap-south-1 (Mumbai)** — same region as Supabase
- Docker + the Docker Compose plugin
- A domain/subdomain whose **A-record points at the instance's Elastic IP**

## 1. Backend secrets (never commit)
Create `secrets/backend.env` (the `secrets/` folder is gitignored) using
`backend/.env.example` as the key list, with the REAL values. Set `APP_ENV=production`.

Four values live **only in the current Railway deployment** — pull them with
`railway variables --service backend`:
`GOOGLE_SERVICE_ACCOUNT_JSON`, `VAPID_PRIVATE_KEY`, the `SMTP_*` set, and a real `SECRET_KEY`.
Without the first two, Google Drive uploads and web-push stop working.

## 2. Frontend build variables
`NEXT_PUBLIC_*` are compiled into the bundle at **build time**. Put them in a root
`.env` (gitignored; see `frontend/.env.local.example`) with the production domain:

```
NEXT_PUBLIC_API_URL=https://DOMAIN/api/v1
NEXT_PUBLIC_APP_URL=https://DOMAIN
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
NEXT_PUBLIC_VAPID_PUBLIC_KEY=...
NEXT_PUBLIC_ADMIN_EMAIL=...
```

## 3. Set the domain
Replace `finance.yourcompany.com` in **`Caddyfile`** with the real domain (and make
sure the `NEXT_PUBLIC_API_URL` / `NEXT_PUBLIC_APP_URL` above use the same one).

## 4. Deploy
```
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f backend   # watch migrations, then uvicorn
```
Database migrations run automatically on backend start (`alembic upgrade head`, via the
direct `MIGRATION_DATABASE_URL`). The app uses the Supabase **transaction pooler** at
runtime (`DATABASE_URL`, port 6543) — leave that as-is.

> The Next.js build peaks near ~3 GB RAM; on t3.large (8 GB) it is safe. For later
> updates prefer building the image separately (or in CI) so a rebuild never competes
> with live traffic.

## 5. Post-deploy (or sign-in breaks)
Update **Supabase → Authentication** redirect URLs and the **Google OAuth** authorised
origins to the new domain. Then smoke-test:
- `https://DOMAIN/health` → 200
- sign in with Google as a super-admin
- submit a request via the public form; confirm it saves and appears in the dashboard
