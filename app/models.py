from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, LargeBinary, String, false as sa_false
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QuestionnaireVersion(Base):
    """Immutable snapshot of a questionnaire definition.

    Submissions point at a version, so old answers stay interpretable
    (question wording, option labels, department labels) after changes.
    """

    __tablename__ = "questionnaire_versions"

    version: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    definition: Mapped[dict] = mapped_column(JsonType, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (Index("uq_submissions_idempotency_key", "idempotency_key", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    questionnaire_version: Mapped[int] = mapped_column(
        ForeignKey("questionnaire_versions.version"), nullable=False, index=True
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)  # Europe/Sofia calendar day
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False  # UTC
    )
    respondent_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    department_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    answers: Mapped[dict] = mapped_column(JsonType, nullable=False)
    # One key per form fill: a retry with the same key and content never creates a second report.
    idempotency_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ReportAttachment(Base):
    __tablename__ = "report_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class AdminUser(Base):
    """A person allowed to open the admin panel (max a handful; created only with scripts/admin_users.py)."""

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    login: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # lowercase
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # CSV export is allowed only for explicitly named accounts (Presiyan and Martin); PDF/Excel are open to all admins.
    can_export_csv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_false())


class AdminSession(Base):
    """Server-side session. `id` is the SHA-256 of the cookie token, so a database leak does not leak live sessions."""

    __tablename__ = "admin_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AdminAudit(Base):
    """Who did what in the admin panel. Never stores passwords or attempted login names."""

    __tablename__ = "admin_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[str] = mapped_column(String(255), nullable=False, default="")
