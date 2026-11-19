# Remediation checklist — remaining audit findings

Source: `docs/audit/TECHNICAL_AUDIT_2026-11-17.md`. Rule: **no real employee data until batches B, C and D are done.** Nothing is deployed publicly.

## Done (batch A)
- [x] H1 PostgreSQL limits vs questionnaire config
- [x] H3 Malformed Unicode → 422
- [x] H4 No silent SQLite; DB-aware `/healthz`
- [x] H5 Locked, hash-pinned dependencies
- [x] M6 Database credential configuration and docs
- [x] T1/T2 PostgreSQL integration + regression tests

## P1 — Decisions and non-code blockers (batch D, before any real data)
- [ ] **C1** Privacy notice, legal basis, retention period; confirm with DPO/lawyer (draft: `docs/business/EMPLOYEE_NOTICE_BG.md`); render a short notice link on the form
- [ ] **C2** Exposure decision: internal network/VPN only, never public (provisional plan recorded in DECISIONS; confirm with Martin); record that names are self-declared until auth exists
- [ ] **M11** Named vs anonymous vs employee code/list — decide before collection; affects the de-identified export and erasure requests
- [ ] **M2** Backdating policy and floor date (audit suggests `MAX_BACKDATE_DAYS=7`, floor = pilot start); management decision
- [ ] Real department list, participants, device access (questions for Martin)

## Added from the ChatGPT review (pre-pilot)
- [ ] Production must require PostgreSQL even if an explicit SQLite `DATABASE_URL` is supplied (e.g. `APP_ENV=production` rejects `sqlite:`)
- [ ] Fail closed for a draft/placeholder questionnaire in production; reject unapproved versions (needs an `approved` flag in the YAML)
- [ ] M1 detail: same idempotency key + different payload must not silently succeed (409)
- [ ] Do not treat LAN membership or self-declared names as verified identity
- [ ] Exports: aggregate/de-identified by default; pseudonyms are not anonymity; review free text; no external AI sharing without approved governance
- [x] Pre-merge: form fails closed without JavaScript; destructive-test guard; build-context exclusions tightened; filled materials kept out of Git

## Admin panel follow-ups
- [ ] Create the four admin accounts (Presiyan, Martin, Росица, Миглена) — with Presiyan
- [x] (19 Nov) Login form has a double-submit CSRF token; logout has a session token. Every future state-changing admin form must carry one.
- [x] (19 Nov) scrypt n=2^17 (OWASP), re-hash on login; production start refuses non-HTTPS cookies / missing exact `ALLOWED_ORIGINS`; admin forms 4 KB; throttle memory bounded; audit noise limited (purge with `scripts/purge_audit_noise.py` as the DB owner)
- [ ] Confirm with Presiyan/Martin whether all four admins may see all report detail (names included) before real data
- [ ] Let admins change their own password; consider a stored (DB) login throttle if more than one worker is ever run
- [ ] Per-IP rate limit at the proxy; HTTPS + `COOKIE_SECURE=1` before any non-local use
- [ ] Export (Phase 2 in `docs/NEXT_STEPS_PLAN.md`)

## P2 — Hardening before pilot (batch B)
- [x] **H2** (18 Nov) `Content-Type: application/json` required on `/api/*` (415); foreign `Origin`/`Sec-Fetch-Site: cross-site` rejected (403); body cap 256 KB (413). Still open: per-IP rate limit at the proxy, and CSRF tokens once admin cookies exist
- [ ] **M1** Idempotency key per form fill (UUID as PK, `ON CONFLICT DO NOTHING`)
- [ ] **M3** Logging and exception handler (log error type + request id, never payloads)
- [ ] **M5** Non-root container user; split prod Compose (no bind mounts, `restart: unless-stopped`) from dev override
- [ ] **M7** Least-privilege DB role for the app; migrations with the owner role
- [ ] **M9** Security headers (CSP with hash for the inline theme script), `openapi_url=None`
- [ ] **M10** Accessibility: focus/announce success, one live error region, `aria-invalid`, conditional `aria-required`; test on real devices and Safari/Firefox
- [ ] **M12** Run questionnaire sync once after migrations or use `ON CONFLICT DO NOTHING` (needed if more than one worker)
- [ ] **L10** Mention/handle uvicorn access logs (IP, path) in the privacy notice or retention plan

## P3 — Operations (batch C)
- [ ] **M8** Nightly `pg_dump -Fc` to a gitignored, off-host location with retention, plus a **tested restore**
- [ ] Hosting setup on the chosen machine: HTTPS on the internal network, VPN access for admin, host updates

## P4 — With the admin/auth/export work (Wed/Thu)
- [ ] **M4** Do not copy the async-route-with-sync-DB pattern into admin pages
- [ ] **L9** Neutralise `=`, `+`, `-`, `@` prefixes on CSV export only
- [ ] **T3** End-to-end browser tests; **T4** edge-case tests (L1–L3 inputs)

## P5 — Low priority
- [ ] L1 strict ISO date · L2 reject `true` as version · L3 strip zero-width/RTL characters · L4 limit accepted old versions · L5 stale "today" on long-open tab · L6 version key per questionnaire code · L7 `server_default=now()` · L8 seed script uses Sofia date
