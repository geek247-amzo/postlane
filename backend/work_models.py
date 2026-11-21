"""Additive Work tables; no existing mail schema is modified."""

from sqlalchemy import String, Text, Integer, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base, uid, now


class WorkConnection(Base):
    __tablename__ = "work_connections"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(100))
    secret: Mapped[str] = mapped_column(Text, default="")
    settings: Mapped[str] = mapped_column(Text, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[int] = mapped_column(Integer, default=now)


class WorkChat(Base):
    __tablename__ = "work_chats"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    provider_id: Mapped[str] = mapped_column(ForeignKey("work_connections.id"))
    connection_ids: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[int] = mapped_column(Integer, default=now)


class WorkEntry(Base):
    __tablename__ = "work_entries"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    chat_id: Mapped[str] = mapped_column(ForeignKey("work_chats.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[int] = mapped_column(Integer, default=now)


class WorkAction(Base):
    __tablename__ = "work_actions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    chat_id: Mapped[str] = mapped_column(ForeignKey("work_chats.id"), index=True)
    connection_id: Mapped[str] = mapped_column(ForeignKey("work_connections.id"))
    connection_version: Mapped[int] = mapped_column(Integer)
    operation: Mapped[str] = mapped_column(String(60))
    arguments: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    result: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[int] = mapped_column(Integer, default=now)


class WorkOAuth(Base):
    __tablename__ = "work_oauth"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    connection_id: Mapped[str] = mapped_column(ForeignKey("work_connections.id"))
    verifier: Mapped[str] = mapped_column(Text)
    expires: Mapped[int] = mapped_column(Integer)
