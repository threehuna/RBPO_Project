"""Initial data schema; workflow and authorization are not implemented yet."""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'moderator')", name="user_role"),
        CheckConstraint("length(username) BETWEEN 1 AND 64", name="username_length"),
        CheckConstraint("length(password_hash) > 0", name="password_hash_present"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), default="user")


class Material(Base):
    __tablename__ = "materials"
    __table_args__ = (
        CheckConstraint("status IN ('visible', 'hidden')", name="material_status"),
        CheckConstraint("length(trim(title)) BETWEEN 1 AND 200", name="material_title"),
        CheckConstraint("length(body) BETWEEN 1 AND 10000", name="material_body"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="visible")


class Complaint(Base):
    __tablename__ = "complaints"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'accepted', 'rejected')", name="complaint_status"),
        CheckConstraint("length(trim(reason)) BETWEEN 1 AND 2000", name="complaint_reason"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        CheckConstraint("outcome IN ('accepted', 'rejected')", name="decision_outcome"),
        CheckConstraint("length(trim(reason)) BETWEEN 1 AND 2000", name="decision_reason"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), unique=True)
    moderator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    outcome: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    complaint_id: Mapped[int | None] = mapped_column(ForeignKey("complaints.id"))
    event_type: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
