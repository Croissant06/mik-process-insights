from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String
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
