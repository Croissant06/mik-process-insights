"""Owner-run retention review (PROVISIONAL pilot policy: 90 days from submission, RETENTION_DAYS to change).

Reports (named) and their attachments expire `RETENTION_DAYS` calendar days after `submitted_at` (the time of
submission, not the work date). Nothing is ever deleted automatically. This script:

    python scripts/retention_review.py                      # DRY RUN (default): counts only, changes nothing
    python scripts/retention_review.py --days 120           # dry run with another period
    RETENTION_DELETION_APPROVED=1 python scripts/retention_review.py --delete --i-am-the-operator

Deletion needs ALL of: --delete, --i-am-the-operator, and RETENTION_DELETION_APPROVED=1 in the environment
(set only after the company's data owner has confirmed the policy and the operator reviewed the dry-run).
Run it with the DATABASE OWNER role (the web application's role cannot delete reports or audit rows), e.g. through
the `migrate` service of docker-compose.hosted.yml. Output never contains names, answers or file names.
Backups and downloaded exports are NOT touched: they must expire under the company's own schedule.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select  # noqa: E402

from app import admin_auth as auth  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import make_engine, make_session_factory  # noqa: E402
from app.models import AdminAudit, ReportAttachment, Submission  # noqa: E402


def review(db, days: int, now: datetime | None = None) -> dict:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    expired = select(Submission.id).where(Submission.submitted_at < cutoff)
    reports = db.scalar(select(func.count()).select_from(expired.subquery()))
    files = db.scalar(select(func.count()).select_from(ReportAttachment).where(ReportAttachment.submission_id.in_(expired)))
    size = db.scalar(select(func.coalesce(func.sum(func.length(ReportAttachment.content)), 0))
                     .where(ReportAttachment.submission_id.in_(expired)))
    oldest, newest = db.execute(select(func.min(Submission.submitted_at), func.max(Submission.submitted_at))
                                .where(Submission.submitted_at < cutoff)).one()
    return {"cutoff": cutoff, "reports": reports, "attachments": files, "bytes": int(size or 0),
            "oldest": oldest, "newest": newest}


def purge(db, days: int, now: datetime | None = None) -> dict:
    result = review(db, days, now)
    expired = select(Submission.id).where(Submission.submitted_at < result["cutoff"])
    db.execute(delete(ReportAttachment).where(ReportAttachment.submission_id.in_(expired)))
    db.execute(delete(Submission).where(Submission.submitted_at < result["cutoff"]))
    db.add(AdminAudit(user_id=None, action="retention_deleted",
                      detail=f"reports={result['reports']} attachments={result['attachments']} days={days}"))
    db.commit()
    return result


def main(argv: list[str] | None = None, env: dict | None = None) -> int:
    env = os.environ if env is None else env
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, help="retention period in days (default: RETENTION_DAYS, provisional 90)")
    ap.add_argument("--delete", action="store_true", help="actually delete (otherwise dry run)")
    ap.add_argument("--i-am-the-operator", action="store_true", help="second confirmation required with --delete")
    args = ap.parse_args(argv)
    settings = Settings.from_env(web=False)
    days = args.days if args.days is not None else settings.retention_days
    if days < 7:
        print("Refusing: the retention period must be at least 7 days.")
        return 2
    if args.delete and not (args.i_am_the_operator and env.get("RETENTION_DELETION_APPROVED") == "1"):
        print("Refusing to delete: needs --i-am-the-operator and RETENTION_DELETION_APPROVED=1 "
              "(set only after the data owner confirmed the policy and the dry run was reviewed).")
        return 2
    with make_session_factory(make_engine(settings.database_url))() as db:
        r = purge(db, days) if args.delete else review(db, days)
    verb = "DELETED" if args.delete else "DRY RUN - would delete"
    print(f"{verb}: {r['reports']} reports and {r['attachments']} attachments ({r['bytes'] / 1048576:.1f} MiB) "
          f"submitted before {r['cutoff']:%Y-%m-%d %H:%M} UTC ({days} days).")
    if r["reports"]:
        print(f"Oldest submission: {auth.aware(r['oldest']):%Y-%m-%d}; newest affected: {auth.aware(r['newest']):%Y-%m-%d}.")
    if not args.delete:
        print("Nothing was changed. Backups and exported files must be expired separately by the company.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
