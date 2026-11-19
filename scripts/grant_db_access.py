"""Provision the app's PostgreSQL privileges after running the hosted migrations."""
import os

import psycopg
from psycopg import sql


def main():
    password = os.environ["MIK_DB_APP_PASSWORD"]
    owner_password = os.environ["POSTGRES_PASSWORD"]
    if not password or password == owner_password:
        raise SystemExit("Use a separate password for the app database role.")

    with psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=owner_password,
    ) as db:
        exists = db.execute("SELECT 1 FROM pg_roles WHERE rolname = 'mik_app'").fetchone()
        if not exists:
            db.execute("CREATE ROLE mik_app LOGIN")
        db.execute(sql.SQL("ALTER ROLE mik_app PASSWORD {}").format(sql.Literal(password)))
        db.execute("GRANT USAGE ON SCHEMA public TO mik_app")
        db.execute("GRANT SELECT, INSERT ON questionnaire_versions, submissions, report_attachments TO mik_app")
        db.execute("GRANT SELECT, INSERT, UPDATE ON admin_users TO mik_app")
        db.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON admin_sessions TO mik_app")
        db.execute("GRANT INSERT, SELECT (id) ON admin_audit TO mik_app")
        db.execute("GRANT USAGE ON SEQUENCE admin_users_id_seq, admin_audit_id_seq TO mik_app")


if __name__ == "__main__":
    main()
