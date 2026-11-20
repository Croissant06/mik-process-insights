# Host handoff — for the company server administrator

Short version of `docs/HOSTED_DEPLOYMENT.md`. Everything here was verified with **synthetic data** in a Docker sandbox; nothing has run on the company host yet. No employee data until the owners listed in `docs/REMEDIATION_CHECKLIST.md` have signed off.

## What you need to provide
| Item | Requirement |
|---|---|
| Server | Linux, Docker Engine + Compose v2, **≥ 4 GiB free RAM** (ClamAV alone wants 3–4 GiB), disk for PostgreSQL (reports **and** files are stored in the database) and the ClamAV signature volume |
| Name and certificate | A public HTTPS hostname with a trusted certificate for the submission form. Staff can open it from phones and computers on any network, including mobile data, without a VPN or sign-in. Suggested hostname `insights.mikltd.eu`, pending confirmation by company IT. The app runs at the root path. |
| Reverse proxy | Forward to `127.0.0.1:<MIK_BIND_PORT>` keeping the original `Host`, set the forwarded scheme to `https`, **overwrite** inbound `X-Forwarded-*`. Allow request bodies of **≥ 67 MiB (72 recommended) only on `POST /api/submissions/with-attachments`**; keep every other path small. Rate-limit `/admin/login` and both submission routes. Publish the form, its assets and submission routes. Restrict `/admin` and `/admin/*` to the approved admin network. |
| Trusted proxy address | Set `MIK_TRUSTED_PROXY_IPS` to the peer address the app sees from the proxy (check on the host; often the Docker bridge gateway) |
| Secrets | Two different strong database passwords in `.env.hosted` (mode 600, outside Git) |
| Backups | You own: nightly `pg_dump -Fc` to company storage, off-host copy, a restore drill (commands in `HOSTED_DEPLOYMENT.md`) |
| ClamAV updates | The container updates signatures itself; confirm it can reach `database.clamav.net` or provide an internal mirror |

## Bring-up (synthetic first)
1. `cp` the repo, create `.env.hosted` (template in `HOSTED_DEPLOYMENT.md`; `MIK_QUESTIONNAIRE_VERSION=3`, `MIK_PUBLIC_ORIGIN=https://<hostname>`).
2. `docker compose --env-file .env.hosted -f docker-compose.hosted.yml up -d --build`; wait for `ps` to show all services healthy (ClamAV needs a minute).
3. Create the four admins: Пресиян and Мартин with `--csv`, Росица and Миглена without (`scripts/admin_users.py create --login … --name …`). Passwords are typed at a hidden prompt.
4. Test the form from a phone on mobile data and a computer outside the office network without VPN. Submit a synthetic report with and without files. Verify that the admin routes are blocked there. On the approved admin network, confirm sign-in, the `Secure` cookie, downloads, and Excel/PDF exports for all four admins (CSV for the two).
5. Run a backup and restore it into a **separate, fresh** database. Never test a restore over the live database.

## Limits and behaviour to know
- Reports: name + department required, no sign-in (names are self-declared). Files optional: 10 per report, 5 MiB each, any format, virus-scanned; if the scanner is down a report with files gets a retryable 503 and nothing is saved, reports without files still work.
- One full upload uses roughly 350 MiB of RAM; at most two are processed at once (a third gets a retryable 503).
- **Retention is provisional: 90 days from submission, and nothing is deleted automatically.** Set `RETENTION_DAYS` in `.env.hosted` (default 90, minimum 7). Dry run: `docker compose --env-file .env.hosted -f docker-compose.hosted.yml run --rm retention`. Deleting needs the data owner's confirmation first, then `RETENTION_DELETION_APPROVED=1 docker compose … run --rm retention --delete --i-am-the-operator` (the service uses the owner database role). Backups and exported files are not touched; they expire on the company schedule.
- The web application's database role cannot delete reports or audit rows and cannot create objects. Old failed-sign-in audit noise: `scripts/purge_audit_noise.py --days 90` (owner role).
- Logs contain request id, method, path, error type and source line only; the hosted stack runs uvicorn with the access log off.

## Not verified (yours to check on the host)
Real proxy and certificate, employee submission from office and external networks (including phones on mobile data), admin network restriction, ClamAV signature updates, off-host backup copy and restore on your schedule, Safari/Firefox/real phones, large uploads over slow mobile links.
