# Remediation checklist — pre-pilot status (reconciled 19 Nov 2026 on `review/hosted-pilot`)

Source: `docs/audit/TECHNICAL_AUDIT_2026-11-17.md` plus the ChatGPT reviews in `docs/AI_HANDOFF.md`. Rule: **no real employee data until every open "owner" item below is closed.** Evidence references the test runs logged in `docs/AI_HANDOFF.md` section 3. Synthetic data only so far.

Legend: `[x]` done with evidence · `[ ]` open · **(owner)** = needs a person or the company, not repository code.

## Done — audit batch A
- [x] H1 PostgreSQL limits vs questionnaire config · H3 malformed Unicode → 422 · H4 no silent SQLite, DB-aware `/healthz` · H5 locked, hash-pinned dependencies · M6 DB credential configuration · T1/T2 PostgreSQL integration and regression tests

## Done — request, session and app hardening
- [x] **H2** JSON-only `/api/*` (415), cross-site browser requests refused (403), body caps: 256 KiB API, 4 KiB admin forms, ~67 MiB only on the upload route (413). Evidence: `tests/test_request_protection.py`, hosted smoke (cross-site Origin 403, other port 403, exact origin accepted)
- [x] **M1 Idempotency** (both routes): form sends one key per fill; same key + same content → one report (200, `duplicate: true`, no second virus scan); same key + changed content → 409; malformed key → 422; parallel retry resolved by the unique key. Migration 0005. Evidence: `tests/test_idempotency.py`, browser smoke (200 and 409). *Reports sent without a key (direct API calls) are not de-duplicated; the form always sends one.*
- [x] **M3 Sanitized errors**: unexpected exceptions return a generic 500 with a request id; the log line has request id, method, path (no query string), exception type and source line only — never the message, headers, cookies, bodies or answers; uvicorn access log is off in the hosted stack. Evidence: `tests/test_headers_and_errors.py`
- [x] **M9 Security headers**: CSP (own scripts + SHA-256 of the one inline theme script, no `unsafe-inline` for scripts, `frame-ancestors 'none'`, `object-src 'none'`), nosniff, frame deny, `Referrer-Policy: same-origin`, Permissions-Policy, COOP, HSTS when cookies are Secure; `/docs` and `/openapi.json` are off. Evidence: same test file, real-browser run with no console/CSP errors
- [x] **M5 Non-root runtime image** (`USER mik`); hosted Compose publishes only a loopback web port, no DB or scanner port, `restart: unless-stopped`, one worker. **M7 Least-privilege DB role**: app role cannot delete reports or audit rows, cannot create objects, timezone UTC (checked in the hosted stack, `has_table_privilege`)
- [x] **M12** one worker + migrations in a separate `migrate` service before the web service starts
- [x] Production requires PostgreSQL, HTTPS cookies, exact HTTPS origin; refuses draft/placeholder questionnaires (`tests/test_hosted.py`, `tests/test_config.py`)
- [x] Admin: personal accounts, scrypt 2^17 with re-hash, DB sessions, login CSRF token, throttle with bounded memory, audit log without secrets; all four admins view full reports; **CSV only for accounts with `can_export_csv`** (server-enforced, tested for four accounts); PDF/Excel for all four; **L9** formula injection neutralised in Excel and CSV
- [x] Attachments: optional, ≤10 files × 5 MiB, any format, ClamAV INSTREAM scan before saving (test virus file rejected; scanner down → 503 and nothing saved), admin-only audited download, atomic with the report
- [x] Employee form: required name + department, no sign-in, any valid past date (years 1 to today, picker and server aligned), future refused. Approved questionnaire = v3, draft v2 kept
- [x] **M8 (sandbox part)** `pg_dump -Fc` / `pg_restore --exit-on-error` into a fresh database restored reports, attachments (sizes) and migration version
- [x] **T3** real-browser smoke: `scripts/browser_smoke.js`; **T4** edge cases for dates and keys in the test suite
- [x] Pre-merge safeguards from the first review (no-JS fail-closed form, destructive-test guard, build-context exclusions)
- [x] **Retention (provisional)**: 90 calendar days from `submitted_at`, `RETENTION_DAYS` configurable, **no automatic deletion**; owner-run `scripts/retention_review.py` is a dry run by default, deletion needs `--delete --i-am-the-operator` and `RETENTION_DELETION_APPROVED=1` and the owner DB role (`tests/test_retention.py`)

## Open — owners
- [ ] **(data owner)** Confirm the retention period and who approves the first deletion run; **(company)** how exports and backup copies expire
- [ ] **(DPO / legal)** Employee notice wording, legal basis, controller, access, rights. Draft with the settled facts: `docs/business/EMPLOYEE_NOTICE_BG.md`. Form link is a placeholder until the host exists; do not publish before approval
- [ ] **(Presiyan)** Create the four admin accounts on the target host (`--csv` for Пресиян and Мартин only); distribute credentials through an approved channel
- [ ] **(server administrator)** Host, public HTTPS form without sign-in or VPN, restricted admin routes, proxy (body limit ≥ 67 MiB on `/api/submissions/with-attachments` only, rate limits on sign-in and both submission routes, overwrite forwarding headers), ≥ 4 GiB free RAM, employee access from mobile data and a computer outside the office network. Checklist: `docs/HOST_HANDOFF.md`
- [ ] **(server administrator)** ClamAV signature updates (the image ships signatures but the sandbox could not update them); off-host backups with a tested restore on the company schedule
- [ ] **(management)** Written confirmation of the questionnaire/participant approval (so far reported by Presiyan); MES/AI scope
- [ ] **(Presiyan/ChatGPT)** Day-one scope for a reviewed, de-identified export (pseudonyms are not anonymity; review free text; no external AI sharing without governance)

## Open — repository work, lower priority
- [ ] **M10** Accessibility pass (focus/announce success, one live error region, `aria-invalid`), real devices, Safari and Firefox
- [ ] Admins change their own password; stored (DB) login throttle if more than one worker is ever run
- [ ] **L10** Mention uvicorn access logs (IP, path) in the notice if the proxy or app logs them
- [ ] Per-IP rate limit at the proxy (owner item above) · L1–L8 low-priority items from the audit (strict ISO date, `true` as version, zero-width/RTL characters, old versions, stale "today" on a long-open tab, version key per code, `server_default=now()`, seed script)
- [ ] Not verified anywhere yet: Safari/Firefox/real phones, 50 MiB uploads over a slow mobile link, the company's real proxy and host
