"""Manage the people who may open the admin panel. Run inside the web container:

    docker compose exec web python scripts/admin_users.py create --login martin --name "Име Фамилия"
    docker compose exec web python scripts/admin_users.py list
    docker compose exec web python scripts/admin_users.py set-password --login martin
    docker compose exec web python scripts/admin_users.py deactivate --login martin

Passwords are typed at a hidden prompt (never on the command line, never printed or logged).
At most 4 active admins (see app/admin_auth.py MAX_ADMINS).
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import admin_auth as auth  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import make_engine, make_session_factory  # noqa: E402
from app.models import AdminUser  # noqa: E402


def ask_password() -> str:
    p1 = getpass.getpass("Password (min %d characters): " % auth.MIN_PASSWORD_LENGTH)
    if p1 != getpass.getpass("Repeat password: "):
        raise auth.AdminError("Passwords do not match.")
    return p1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--login", required=True)
    c.add_argument("--name", required=True, help="display name shown in the panel")
    sub.add_parser("list")
    for name in ("set-password", "deactivate", "activate"):
        sub.add_parser(name).add_argument("--login", required=True)
    args = ap.parse_args(argv)

    session_factory = make_session_factory(make_engine(Settings.from_env(web=False).database_url))
    try:
        with session_factory() as db:
            if args.cmd == "list":
                for u in db.scalars(select(AdminUser).order_by(AdminUser.id)):
                    last = u.last_login_at.strftime("%Y-%m-%d %H:%M UTC") if u.last_login_at else "never"
                    print(f"{u.login:20} {'active' if u.is_active else 'INACTIVE':9} last login: {last:22} {u.display_name}")
                return 0
            if args.cmd == "create":
                u = auth.create_admin(db, args.login, args.name, ask_password())
                print(f"Created admin '{u.login}'.")
                return 0
            user = auth.get_by_login(db, args.login)
            if user is None:
                raise auth.AdminError("No such login.")
            if args.cmd == "set-password":
                pw = ask_password()
                auth.check_password_strength(pw)
                user.password_hash = auth.hash_password(pw)
                auth.end_all_sessions(db, user.id)
                auth.audit(db, "password_changed", user.id)
                print("Password changed; the person was signed out everywhere.")
            elif args.cmd == "deactivate":
                user.is_active = False
                auth.end_all_sessions(db, user.id)
                auth.audit(db, "admin_deactivated", user.id)
                print("Deactivated and signed out.")
            elif args.cmd == "activate":
                active = len(db.scalars(select(AdminUser).where(AdminUser.is_active.is_(True))).all())
                if active >= auth.MAX_ADMINS:
                    raise auth.AdminError(f"Already {active} active admins (limit {auth.MAX_ADMINS}).")
                user.is_active = True
                auth.audit(db, "admin_activated", user.id)
                print("Activated.")
            db.commit()
        return 0
    except auth.AdminError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
