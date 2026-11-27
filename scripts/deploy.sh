#!/usr/bin/env bash
# One-command, manually approved deploy of the hosted pilot.
#
# Run on the VM from the repository folder:
#   sudo bash scripts/deploy.sh            # show what changes, ask, back up, update, check
#   sudo bash scripts/deploy.sh --check    # only show what would change; touches nothing
#
# Steps:
#   1. fetch origin/<branch> and show the commits and files that would change
#   2. ask for the word "deploy" before changing anything
#   3. pg_dump -Fc backup to /root/mik-backups (mode 600) and verify it with pg_restore --list
#   4. fast-forward the checkout, rebuild the image, run migrations, restart web
#   5. health check: /healthz on the app, the public form through the local proxy, and the
#      Alembic version; on failure the code is put back to the previous commit and restarted.
#
# It never runs `docker compose down`, never removes volumes and never deletes data.
# A failed migration is NOT undone automatically: the script prints the backup path and the
# restore command for the operator instead.
set -euo pipefail

BRANCH="${MIK_DEPLOY_BRANCH:-development}"
PROJECT="${MIK_COMPOSE_PROJECT:-mik-process-insights-hosted}"
ENV_FILE="${MIK_ENV_FILE:-.env.hosted}"
BACKUP_DIR="${MIK_BACKUP_DIR:-/root/mik-backups}"
APP_URL="${MIK_APP_HEALTH_URL:-http://127.0.0.1:8000/healthz}"
PROXY_URL="${MIK_PROXY_HEALTH_URL:-http://127.0.0.1:8080/}"
HEALTH_TIMEOUT="${MIK_HEALTH_TIMEOUT:-120}"

CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

say()  { printf '\n== %s\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

cd "$(dirname "$0")/.."
REPO_DIR="$(pwd)"

[[ -f "$ENV_FILE" ]] || fail "$ENV_FILE not found in $REPO_DIR"
COMPOSE=(docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f docker-compose.hosted.yml)
# The VM keeps its own private overrides (admin origin, port binding) outside git.
for extra in private/compose.*.yml; do
  [[ -f "$extra" ]] && COMPOSE+=(-f "$extra")
done

if [[ $CHECK_ONLY -eq 0 && $EUID -ne 0 ]]; then
  fail "run with sudo (needed for docker and $BACKUP_DIR)"
fi

# Run git as the repository owner so fetch uses their credentials and files keep their owner.
OWNER="$(stat -c %U "$REPO_DIR")"
g() {
  if [[ $EUID -eq 0 && "$OWNER" != "root" ]]; then sudo -u "$OWNER" git -C "$REPO_DIR" "$@"
  else git -C "$REPO_DIR" "$@"; fi
}

if ! g diff --quiet || ! g diff --cached --quiet; then
  g status --short
  fail "tracked files have local changes; commit or discard them first"
fi

say "Fetching origin/$BRANCH"
g fetch --quiet origin "$BRANCH"
OLD="$(g rev-parse HEAD)"
NEW="$(g rev-parse FETCH_HEAD)"
echo "running now: $(g log -1 --format='%h %s' "$OLD")"
echo "on GitHub:   $(g log -1 --format='%h %s' "$NEW")"

if [[ "$OLD" == "$NEW" ]]; then
  say "Already up to date. Nothing to deploy."
  exit 0
fi
if ! g merge-base --is-ancestor "$OLD" "$NEW"; then
  fail "the VM checkout is not an ancestor of origin/$BRANCH (local commits?); resolve by hand"
fi

say "Commits that would be deployed"
g log --oneline --no-decorate "$OLD..$NEW"
say "Files that would change"
g diff --stat "$OLD" "$NEW"
MIGRATIONS="$(g diff --name-only "$OLD" "$NEW" -- migrations/ || true)"
if [[ -n "$MIGRATIONS" ]]; then
  say "This update includes DATABASE MIGRATIONS:"
  echo "$MIGRATIONS"
fi

if [[ $CHECK_ONLY -eq 1 ]]; then
  say "--check: nothing was changed."
  exit 0
fi

printf '\nType "deploy" to back up the database and deploy %s: ' "$(g rev-parse --short "$NEW")"
read -r answer
[[ "$answer" == "deploy" ]] || fail "not confirmed; nothing was changed"

say "Backing up the database"
install -d -m 700 "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$BACKUP_DIR/mik_insights-$STAMP-before-$(g rev-parse --short "$NEW").dump"
( umask 077; "${COMPOSE[@]}" exec -T db pg_dump -U mik_owner -d mik_insights -Fc > "$BACKUP" )
[[ -s "$BACKUP" ]] || fail "backup is empty: $BACKUP"
"${COMPOSE[@]}" exec -T db pg_restore --list < "$BACKUP" | grep -q "TABLE DATA public submissions" \
  || fail "backup could not be read back: $BACKUP"
echo "backup OK: $BACKUP ($(du -h "$BACKUP" | cut -f1))"

health() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT))
  until curl -fsS -o /dev/null --max-time 5 "$APP_URL"; do
    (( SECONDS < deadline )) || return 1
    sleep 3
  done
  curl -fsS -o /dev/null --max-time 5 "$PROXY_URL" || return 1
}

restart_stack() {
  "${COMPOSE[@]}" build web
  # `up -d` reruns migrate (alembic upgrade head) before web starts; db and scanner keep running.
  "${COMPOSE[@]}" up -d
}

say "Updating code to $(g rev-parse --short "$NEW")"
g merge --ff-only --quiet "$NEW"

say "Rebuilding and restarting"
if restart_stack && health; then
  say "Health check passed"
  "${COMPOSE[@]}" exec -T db psql -U mik_owner -d mik_insights -tAc \
    "SELECT 'alembic version: ' || version_num FROM alembic_version"
  "${COMPOSE[@]}" ps
  say "Deployed $(g log -1 --format='%h %s')"
  echo "backup kept at $BACKUP"
  exit 0
fi

say "Health check FAILED. Putting the code back to $(g rev-parse --short "$OLD")"
"${COMPOSE[@]}" logs --tail=40 migrate web || true
g reset --hard --quiet "$OLD"
if restart_stack && health; then
  echo "previous version is running again."
else
  echo "previous version did not come back healthy either."
fi
cat <<EOF

The database was NOT restored automatically. If a migration ran and must be undone,
restore the backup taken just before this deploy:
  ${COMPOSE[*]} stop web
  ${COMPOSE[*]} exec -T db pg_restore -U mik_owner -d mik_insights --clean --if-exists --exit-on-error < $BACKUP
  ${COMPOSE[*]} up -d
EOF
exit 1
