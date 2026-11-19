# Company server deployment

## Server call checklist

- Confirm a Linux host with Docker Engine and Compose v2, the person who can operate them, and how the host can pull the private repository and container images.
- Confirm a private HTTPS hostname and trusted certificate, access over the office network or company VPN, and whether the existing proxy can send requests to a loopback port on the same host. The app uses a hostname at the root path.
- Confirm available RAM and persistent disk space for PostgreSQL and ClamAV. ClamAV recommends 3 GiB minimum and 4 GiB preferred for its container alone. Agree how the scanner receives signature updates and how the proxy will rate-limit sign-in and uploads. [ClamAV Docker requirements](https://docs.clamav.net/manual/Installing/Docker.html#memory-ram-requirements)
- Agree who owns PostgreSQL backups, off-host storage, and restore checks. Reports and file bytes are in the same database and backup.
- Agree whether employee devices can reach the private hostname. Confirm how the four admins will get their personal credentials through an approved channel.

## Synthetic deployment

The hosted stack gives the app its own PostgreSQL role, no published DB or scanner port, and a loopback web port. Use a private HTTPS proxy for all browser access. It must keep the original Host, set the forwarded scheme to HTTPS, and overwrite inbound forwarding headers. If it runs in a container or on another host, the server administrator should adapt the private upstream without publishing the app port publicly. The form itself relies on the company access boundary.

Create `.env.hosted` outside version control with permissions restricted to the operator. Generate two independent strong database passwords. Set the peer address the app actually sees from the trusted proxy (often the Docker bridge gateway for a host-based proxy). Check this on the host before rollout.

```dotenv
MIK_APP_ENV=staging
MIK_PUBLIC_ORIGIN=https://reports.example.com
MIK_BIND_PORT=8000
MIK_DB_OWNER_PASSWORD=<generated-owner-password>
MIK_DB_APP_PASSWORD=<different-generated-app-password>
MIK_TRUSTED_PROXY_IPS=<trusted-proxy-peer-ip>
MIK_QUESTIONNAIRE_VERSION=3
```

```sh
docker compose --env-file .env.hosted -f docker-compose.hosted.yml config --quiet
docker compose --env-file .env.hosted -f docker-compose.hosted.yml up -d --build
docker compose --env-file .env.hosted -f docker-compose.hosted.yml ps
curl --fail http://127.0.0.1:8000/healthz
docker compose --env-file .env.hosted -f docker-compose.hosted.yml exec web \
  python scripts/admin_users.py create --login pilot-test --name "Тестов администратор"
```

### Admin accounts and export rights

All four admins (Пресиян, Мартин, Росица, Миглена) see full reports with names, download attachments and export **PDF and Excel**. **CSV** is limited to Пресиян and Мартин and is enforced on the server per account:

```sh
docker compose --env-file .env.hosted -f docker-compose.hosted.yml exec web python scripts/admin_users.py create --login <login> --name "<име>" --csv   # Пресиян, Мартин
docker compose --env-file .env.hosted -f docker-compose.hosted.yml exec web python scripts/admin_users.py create --login <login> --name "<име>"         # Росица, Миглена
docker compose --env-file .env.hosted -f docker-compose.hosted.yml exec web python scripts/admin_users.py allow-csv --login <login>   # or deny-csv later
```

The web application's database role cannot delete audit rows. To trim old failed/throttled sign-in noise, run `scripts/purge_audit_noise.py --days 90` through the `migrate` service (owner role).

Verify via the actual private HTTPS hostname. Submit a synthetic report with and without attachments and download the files as the test admin. Check the Secure cookie, scanner readiness and blocked access outside the approved network. The proxy must allow at least **67 MiB** (we recommend 72 MiB) request bodies on `/api/submissions/with-attachments` only: ten 5 MiB files become about 66.9 MiB of base64 JSON. Keep the proxy's body limit on every other path small (the app itself caps the ordinary API at 256 KiB and the admin forms at 4 KiB). One full upload needs roughly 350 MiB of RAM in the web container while it is processed, and at most two uploads run at once; a further one gets a retryable 503. Plan at least 4 GiB of free RAM for the whole stack (ClamAV alone wants 3-4 GiB). The app keeps a 256 KiB cap on the ordinary API route. Wait for ClamAV to load signatures. If it is unavailable, file submissions return a retryable error and save no report. An external scanner, if used later, belongs on a trusted private connection.

## Production switch

- Management approved the questionnaire and the participant list (as reported by Presiyan, 19 Nov; no written confirmation is in the repository). Still confirm the employee notice, named collection, four-admin access, and the **retention period including attachments** (no automatic deletion is configured until the retention period is confirmed).
- The approved questionnaire is **version 3** (`questionnaire/daily_report.v3.yaml`, `status: approved`). Version 2 stays as the draft snapshot; production refuses drafts at startup and refuses submissions to older draft versions. `MIK_QUESTIONNAIRE_VERSION=3`.
- Use a production Compose project and volume separate from the synthetic demo if staging was run on the host. Give production its own private origin or proxy route and a separate port if both stacks will coexist.
- Create the real admin accounts on production only. Run the host smoke checks and verify a restored backup before enabling employee access.

## Backup and restore

From the deployment directory, use the database owner for backups. Keep files in protected company storage and transfer backups off the server under the agreed policy.

```sh
umask 077
docker compose --env-file .env.hosted -f docker-compose.hosted.yml exec -T db \
  pg_dump -U mik_owner -d mik_insights -Fc > mik-insights.dump
```

For a restore drill, create a fresh, isolated database and restore with `pg_restore --exit-on-error`. Restore verification should include reports, attachment downloads and migration version. In a new cluster recreate the app role or restore without ACLs and rerun the grants. Never restore over the live database as a test. The Compose database volume persists through normal restarts and shutdowns.
