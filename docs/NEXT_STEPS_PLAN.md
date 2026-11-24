# Next steps — draft plan (for Presiyan and ChatGPT to review)

Status: **DRAFT, 18 Nov 2026.** Facts below come from Presiyan's notes of the meeting with Martin; nothing is confirmed in writing by management yet. Items marked **Decision** need Presiyan/management. Nothing here is built unless marked *done*.

## Scope boundaries (from Presiyan, 18 Nov)
- **This app = day-to-day questionnaire.** Role-based order entry (isolated, each person sees only what they must) is a **separate future project**; the questionnaire may later plug into that dashboard. So: keep stable question ids, versioned questionnaires, a clean export/API and a nullable `employee_id` as integration seams; do **not** build role-based order entry here.
- Hosting research runs in another thread; this plan only states what the app needs from hosting.
- Department names and the example order table arrive "tomorrow" (19 Nov). Until then: no change to departments or questionnaire.

## Phase 0 — request protection (H2) — *done 18 Nov*
`Content-Type: application/json` required on `/api/*` (415), cross-site browser requests refused (403, `Origin`/`Sec-Fetch-Site`), body cap 256 KB (413, also while streaming), `ALLOWED_ORIGINS` for a future proxy/domain. Needed before uploads and admin cookies. Tests in `tests/test_request_protection.py`.

## Phase 1 — admin access for 4 people — *done 18 Nov (read-only view); decision: own password per person*
Requirement: only Presiyan, Martin, Росица and Миглена.
Recommended design (no external services, works with any hosting):
- Individual accounts in PostgreSQL (`admin_users`: name, login, password hash, `role` = `admin`), created only by a CLI script run by Presiyan; no self-registration, no shared login.
- Login page in the existing design system; session cookie `HttpOnly`, `SameSite=Strict`, `Secure` once HTTPS exists; CSRF protection = Origin check (done) + token on forms; rate-limited login; simple audit log (who opened/exported what).
- Read-only admin view first: list/filter by department and date, open a report. Export (Phase 2) after.
- **Decided by Presiyan (18 Nov): own password per person.** Built: `admin_users`/`admin_sessions`/`admin_audit` (migration 0002, additive), `scripts/admin_users.py`, login/logout, filtered list, report detail. **Still to do by Presiyan:** create the four accounts (Presiyan, Martin, Росица, Миглена) with the script — logins/names are not invented here. Not yet: CSRF token on future state-changing admin forms beyond logout (the Origin check covers browsers today), per-IP rate limit at a proxy, password change by the user themselves.

## Phase 2 — export (after Phase 1)
JSON, JSONL, CSV with filters (department, date range, questionnaire version), de-identified option, stable question ids + descriptions, UTF-8, metadata. CSV must neutralise `=`/`+`/`-`/`@` prefixes (audit L9). Per `docs/ADMIN_EXPORT_REQUIREMENTS.md`. Exports never go to Git.

## Phase 3 — file/photo attachments (needs decisions; design below)
Wanted by Martin. Sensitive: photos/files can contain people, customer data or metadata.
Recommended defaults (**Decision** on each):
- Optional, up to 10 files per report, 5 MiB each, any company file format (Presiyan, 19 Nov); every file is scanned with ClamAV before the report is saved.
- Upload as a separate step (`POST /api/attachments`, one file per request, size-capped, same Origin protection), then the report references the returned ids; orphaned uploads are deleted after 24 h.
- Stored in PostgreSQL (separate table, not in the submissions row) so one backup covers everything and "PostgreSQL is the single source of truth" still holds.
- Served only to logged-in admins, as a download (`Content-Disposition: attachment`, `nosniff`); no inline preview of PDFs; images re-encoded to strip EXIF/location (adds an image library dependency).
- Notice on the form (Bulgarian): do not photograph people, screens with passwords, or customer data.
- Retention = same as reports; deleted together with the report.
- Requires **questionnaire v2** (new optional "attachments" setting), so v1 stays immutable and management agrees first. Also needs the privacy notice (C1) to mention attachments.

## Phase 4 — hardening before any pilot (batch B/C in `docs/REMEDIATION_CHECKLIST.md`)
M1 idempotency (same key + different payload → 409), M3 logging, M5 non-root + production Compose, M7 least-privilege DB role, M9 security headers, M10 accessibility, M12 startup sync, production checks (PostgreSQL required, draft questionnaire refused), M8 backups with a tested restore.

## Phase 5 — hosting and rollout (waits for the hosting research and legal input)
"No internal server" means the earlier provisional plan (company computer/Linux server, internal network, VPN) no longer fits. What the app needs from any hosting option:
- Docker Compose or a container platform; a **persistent** PostgreSQL volume or managed PostgreSQL **with daily backups and a tested restore**.
- HTTPS; location in the EU; a data-processing agreement with the provider.
- Access control so the employee form is not open to the whole internet (options to compare: IP allowlist, VPN/tunnel, access gateway), and the admin area behind login (Phase 1).
- Cost per month and who maintains it.
Privacy notice, legal basis and retention (C1) must be settled before real data; external hosting makes this more important, not less.

## Decisions needed (priority order)
1. Admin sign-in method and the four admins' login ids (Phase 1).
2. Hosting option once the research is back (Phase 5) — gates any real data.
3. Attachments: the defaults above, and whether they ship in the first pilot or later (Phase 3).
4. Named vs "без име" vs employee code; backdating limit; retention; who sees identifiable data (unchanged from `docs/AI_HANDOFF.md` section 6).
5. Department names and example order table (arriving 19 Nov) → questionnaire v2.

## Review requests for ChatGPT (when its connection is back)
- Is the phase order right, given Thursday's deadline and that real data is gated on hosting + privacy?
- Phase 1 and 3 designs: security and privacy gaps? Is storing attachments in PostgreSQL acceptable at this scale?
- What should the integration seam to the future role-based dashboard look like (auth, ids, export format)?
