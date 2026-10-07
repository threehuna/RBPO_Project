"""Начальная схема БД.

Таблицы пользователей, жалоб, решений и аудита создаются заранее, чтобы ограничения
целостности из D-02 существовали до появления изменяющих маршрутов. Маршрутов,
которые пишут в эти таблицы, в текущей версии нет.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

MATERIAL_STATUSES = ("visible", "hidden")
USER_ROLES = ("user", "moderator")
COMPLAINT_STATUSES = ("pending", "accepted", "rejected")
DECISION_RESULTS = ("accepted", "rejected")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_one_of("role", USER_ROLES), name="ck_users_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    login: Mapped[str] = mapped_column(String(64), unique=True)
    # Только Argon2id-хеш по D-01; открытый пароль в БД не хранится.
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))


class Material(Base):
    __tablename__ = "materials"
    __table_args__ = (
        CheckConstraint(_one_of("status", MATERIAL_STATUSES), name="ck_materials_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))


class Complaint(Base):
    __tablename__ = "complaints"
    __table_args__ = (
        CheckConstraint(_one_of("status", COMPLAINT_STATUSES), name="ck_complaints_status"),
        CheckConstraint("length(reason) BETWEEN 1 AND 2000", name="ck_complaints_reason"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        CheckConstraint(_one_of("result", DECISION_RESULTS), name="ck_decisions_result"),
        CheckConstraint("length(reason) BETWEEN 1 AND 2000", name="ck_decisions_reason"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # UNIQUE: по одной жалобе может существовать только одно решение (SR-06, D-02).
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), unique=True)
    moderator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    result: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    object_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
