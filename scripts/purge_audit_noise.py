"""Delete old failed/throttled sign-in rows from the admin audit log (they are noise and otherwise grow forever).

The web application's database role deliberately cannot delete audit rows, so run this with the DATABASE OWNER role:

    docker compose --env-file .env.hosted -f docker-compose.hosted.yml run --rm migrate \
        python scripts/purge_audit_noise.py --days 90

Other audit rows (successful sign-ins, report views, downloads, exports, account changes) are never touched.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import admin_auth as auth  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import make_engine, make_session_factory  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=90)
    args = ap.parse_args(argv)
    if args.days < 7:
        print("Refusing to purge rows younger than 7 days.")
        return 1
    with make_session_factory(make_engine(Settings.from_env(web=False).database_url))() as db:
        print(f"Deleted {auth.purge_old_audit(db, args.days)} old failed/throttled sign-in rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
