"""BI service — natural language → SQL → execute → summarise, with general Q&A fallback."""

import os
import re
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_service import AIClient, AIProviderType, ChatMessage, get_client

# ── Prompts ───────────────────────────────────────────────────────────────────

# The single prompt that handles BOTH conversational and data questions.
# If the AI decides the question is general/conversational, it prefixes its reply
# with "GENERAL:" and we short-circuit before touching the database.
_SCHEMA = """You are Upsure's AI assistant — a smart PA and data analyst rolled into one.
Today is {today}.

=== HOW TO RESPOND ===

If the question is a GREETING, a question about yourself, a question about Upsure or this
platform, or anything that does NOT need database data to answer:
  → Reply with EXACTLY this format:   GENERAL:<your response>
  → Be friendly, concise, and helpful. Markdown (bullets, **bold**) is fine inside the response.

If the question needs real data from the database (deposits, suppliers, overdue shipments,
payments, analytics, reports, or any follow-up to a previous data result):
  → Return ONLY a valid raw PostgreSQL SELECT query.
  → No GENERAL prefix. No markdown fences. No explanation.

=== ABOUT UPSURE & THIS PLATFORM ===
Upsure operates Finance Operations — a system that manages advance payments made
to overseas suppliers before goods are shipped. It provides full lifecycle visibility from
request submission through payment to shipment, covering payment status, overdue shipments,
supplier risk, cost of fund, and breakdown analytics by merchandiser, vertical, and customer.

Roles: super_admin (full access) · finance_admin (supplier risk + analytics) ·
accounts_team (payment queue) · merchandiser (their own requests only)

The tracker supports multi-currency deposits: USD, CNY, EUR, GBP, AED, INR.

Request status lifecycle:
  pending_payment       → Submitted, waiting for funds to be transferred
  payment_processed     → Funds sent to supplier, awaiting shipment
  hold_by_merchandiser  → Paused by the merchandising team (order issue)
  hold_by_accounts      → Paused by accounts (payment issue)
  cancelled_*           → Dropped by merchandiser or accounts
  reopened              → Previously cancelled, now reactivated

Cost of fund = financial carrying cost of an advance deposit. Higher = more cash at risk.
Defaulted suppliers = suppliers who received advance deposits but have not fulfilled orders.

GENERAL response examples (use these patterns, adapt freely):
  "hi" / "hello"         → GENERAL:Hello! I'm Upsure's AI assistant for Finance Operations. How can I help you today?
  "who are you?"         → GENERAL:I'm Upsure's built-in AI assistant. I can query your deposit data, analyse overdue shipments, review supplier risk, and answer general questions about the platform — just ask!
  "what can you do?"     → GENERAL:I can help you with:\n\n- **Data queries** — overdue deposits, supplier performance, payment status, cost of fund\n- **Reports** — generate and export custom views as CSV\n- **Analytics** — delay trends, merchandiser breakdowns, customer exposure\n- **General Q&A** — status meanings, how the tracker works, anything about Upsure\n\nJust type your question!
  "what does status X mean?" → GENERAL: (explain the status using the lifecycle above)
  "thanks" / "thank you" → GENERAL:You're welcome! Let me know if there's anything else I can help with.

=== DATABASE SCHEMA (for SQL queries) ===

deposit_requests (alias: dr)
  id uuid, request_number text (format: ADT-YYYY-NNNNN),
  supplier_id uuid→suppliers.id, customer_id uuid→customers.id,
  vertical_id uuid→verticals.id, created_by uuid→users.id,
  currency text (USD/EUR/CNY/GBP/AED/INR/OTHER),
  deposit_amount numeric, deposit_percentage numeric,
  total_supplier_invoice_amount numeric,
  estimated_shipment_date date, estimated_etd date,
  current_status text (see lifecycle above),
  submission_source text (in_app / google_form),
  is_locked bool, is_deleted bool, created_at timestamptz, updated_at timestamptz

suppliers (alias: s)
  id uuid, supplier_code text, name text, country text, is_active bool

customers (alias: c)
  id uuid, name text, is_active bool

verticals (alias: v)
  id uuid, name text, is_active bool

payment_details (alias: pd)
  id uuid, deposit_request_id uuid→deposit_requests.id,
  payment_date date, bank text, payment_reference_number text,
  ship_date date, payment_status text (paid/partial/pending),
  accounts_remarks text, updated_by uuid→users.id, updated_at timestamptz

analytics_snapshots (alias: a)
  deposit_request_id uuid→deposit_requests.id,
  grace_etd date, etd_grace_overdue_days int,
  payment_to_ship_days int, payment_to_request_days int,
  cost_of_fund_applicable bool, cost_of_fund_amount numeric,
  default_status text (on_time / pending / delayed / critical),
  calculated_at timestamptz

defaulted_suppliers (alias: ds)
  id uuid, supplier_id uuid→suppliers.id,
  outstanding_amount numeric, currency text,
  default_reason text, flagged_date date,
  resolved_date date, is_active bool

users (alias: u)
  id uuid, full_name text, email text,
  role text (super_admin/finance_admin/accounts_team/merchandiser),
  is_active bool

=== SQL RULES — follow strictly ===
1. Write ONE valid SELECT query only.
2. Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE, EXECUTE, COPY, VACUUM, CALL.
3. Always add WHERE dr.is_deleted = false when querying deposit_requests.
4. JOIN suppliers, customers, verticals to resolve readable names.
5. Include LIMIT 100 unless the user clearly wants an aggregate/count.
6. For date math, use NOW() or CURRENT_DATE.
7. Return ONLY raw SQL — no markdown fences, no explanation, no commentary.
8. If the question is about "reports" or "export", write a comprehensive SELECT with all useful columns.
9. If the question references a previous result (e.g. "those suppliers", "the overdue ones"), use the context from conversation history to infer the right filter.

=== RESTRICTED TABLES & COLUMNS — never query these ===
The following are off-limits. Do not reference them in any query under any circumstances:
- audit_logs (table)  — internal security audit trail, never exposed via AI
- system_config (table) — contains API keys and internal configuration
- ip_address (column)  — personally identifiable network data
- user_agent (column)  — client fingerprinting data
- supabase_uid (column) — internal auth identifier
If a user asks for any of this data, respond with GENERAL:I'm sorry, that information is restricted and cannot be accessed through this assistant.
"""

_SUMMARISE = """You are Upsure's senior business analyst — embedded in Finance Operations.

CONTEXT:
- "Advance deposit requests" are upfront payments made to suppliers before goods ship.
- pending_payment = awaiting bank transfer | payment_processed = money sent | hold_* = paused | cancelled_* = dropped
- Cost of fund = financial cost of tying up cash. Higher = more risk.
- Defaulted suppliers = suppliers who received money but didn't deliver.
- delayed/critical in analytics = shipments significantly overdue.

YOUR JOB:
Give a sharp, business-focused answer to the user's question. You have access to conversation history so you can answer follow-ups intelligently.

FORMAT RULES:
- Lead with the key insight in 1 sentence.
- Use bullet points for multiple data points.
- Call out anything that needs attention (overdue, defaulted, high cost of fund).
- Plain English only — no SQL, no UUID values, no technical column names.
- If results are empty, say: "No records found for this query."
- Maximum 8 lines. Be concise and actionable.
- If the user asks to "create a report" or "export", summarise the data and mention they can download it using the CSV button below.
"""

# ── Safety checks ─────────────────────────────────────────────────────────────

# Blocks write/DDL operations.
_BLOCKED = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|EXECUTE|COPY|VACUUM|CALL)\b",
    re.IGNORECASE,
)

# Hard-coded deny-list for sensitive tables and columns.
# This runs AFTER AI generation, so it catches prompt-injection / jailbreak attempts too.
# Secure by default: adding a new sensitive column here is all that's needed to protect it.
_RESTRICTED = re.compile(
    r"\b(audit_logs|system_config|ip_address|user_agent|supabase_uid|ai_api_key)\b",
    re.IGNORECASE,
)

_GENERAL_PREFIX = "GENERAL:"


def _is_general(raw: str) -> bool:
    return raw.strip().upper().startswith(_GENERAL_PREFIX.upper())


def _extract_general(raw: str) -> str:
    stripped = raw.strip()
    return stripped[len(_GENERAL_PREFIX):].strip()


def _validate(sql: str) -> None:
    clean = sql.strip()
    if not clean.upper().startswith("SELECT"):
        raise ValueError("Generated query is not a SELECT statement. Please rephrase your question.")
    if _BLOCKED.search(clean):
        raise ValueError("Query contains disallowed SQL operation.")
    if _RESTRICTED.search(clean):
        raise ValueError("Query references restricted data. Access to IP addresses, audit logs, and system configuration is not permitted through the AI assistant.")


# ── Config loader ─────────────────────────────────────────────────────────────

# API key comes from the system_config table first; this env-var fallback is used
# only when that is unset. Never hardcode a real key here (keeps it out of git).
_FALLBACK_API_KEY = os.environ.get("GROQ_API_KEY", "")
_FALLBACK_PROVIDER: AIProviderType = "groq"


async def _load_ai_config(session: AsyncSession) -> tuple[AIProviderType, str, str | None]:
    result = await session.execute(
        text(
            "SELECT config_key, config_value FROM system_config "
            "WHERE config_key IN ('ai_provider', 'ai_api_key', 'ai_model')"
        )
    )
    cfg = {row.config_key: row.config_value for row in result.fetchall()}
    provider: AIProviderType = cfg.get("ai_provider", _FALLBACK_PROVIDER)  # type: ignore[assignment]
    api_key = cfg.get("ai_api_key") or _FALLBACK_API_KEY
    model = cfg.get("ai_model") or None
    return provider, api_key, model


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_bi_query(
    question: str,
    session: AsyncSession,
    history: list[ChatMessage] | None = None,
) -> dict[str, Any]:
    """
    Route the question through one of two paths:
    - GENERAL: greeting / platform Q&A / follow-up that needs no data → answer directly
    - DATA: business data question → SQL generation → execution → summarisation
    Returns: { answer, sql, row_count, rows, columns }
    """
    provider, api_key, model = await _load_ai_config(session)
    client: AIClient = get_client(provider, api_key, model)

    system_prompt = _SCHEMA.format(today=date.today().isoformat())

    # Step 1 — ask the AI what to do (generate SQL or answer conversationally)
    raw = await client.chat(
        system=system_prompt,
        user=question,
        history=history,
    )

    # ── GENERAL path: conversational / platform Q&A ───────────────────────────
    if _is_general(raw):
        return {
            "answer": _extract_general(raw),
            "sql": "",
            "row_count": 0,
            "rows": [],
            "columns": [],
        }

    # ── DATA path: extract + validate SQL ────────────────────────────────────
    sql = raw.strip().removeprefix("```sql").removeprefix("```").removesuffix("```").strip()
    _validate(sql)

    if "LIMIT" not in sql.upper():
        sql = sql.rstrip(";") + " LIMIT 100"

    # Step 2 — execute (read-only — no writes pass the validate check)
    try:
        res = await session.execute(text(sql))
        all_rows = res.fetchall()
        columns = list(res.keys())
        rows_as_dicts = [dict(zip(columns, row)) for row in all_rows]
    except Exception as exc:
        raise ValueError(f"Query failed: {exc}") from exc

    # Step 3 — summarise (with full conversation history so follow-ups are coherent)
    rows_str = "\n".join(str(r) for r in rows_as_dicts[:20]) if rows_as_dicts else "(no rows)"
    total = len(rows_as_dicts)

    answer = await client.chat(
        system=_SUMMARISE,
        user=(
            f"User question: {question}\n\n"
            f"Data ({total} rows total, showing first 20):\n{rows_str}"
        ),
        history=history,
    )

    def _serialise(v: Any) -> Any:
        if isinstance(v, (int, float, bool, str, type(None))):
            return v
        return str(v)

    return {
        "answer": answer.strip(),
        "sql": sql,
        "row_count": total,
        "rows": [{k: _serialise(v) for k, v in r.items()} for r in rows_as_dicts],
        "columns": columns,
    }
