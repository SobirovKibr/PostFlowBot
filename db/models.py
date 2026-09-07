"""
SQLAlchemy Async ORM Database Models for Multi-User Telegram Userbot SaaS.
"""

from datetime import datetime
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from db.database import Base


class User(Base):
    """Represents an onboarded Telegram user possessing a userbot instance."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    phone = Column(String(512), nullable=False)  # Fernet encrypted string
    api_key_index = Column(Integer, default=0, nullable=False)  # 0: primary, 1: fallback
    is_active = Column(Boolean, default=True, nullable=False)
    is_banned = Column(Boolean, default=False, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    groups = relationship("Group", back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    state = relationship("State", back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="selectin")


class Group(Base):
    """Target groups or channels configured by the user."""
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    group_identifier = Column(String(255), nullable=False)  # @username, channel_id, or t.me link
    title = Column(String(255), default="", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    user = relationship("User", back_populates="groups")


class Message(Base):
    """Rotating message templates configured by the user."""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    position = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    user = relationship("User", back_populates="messages")


class State(Base):
    """Per-user runtime configuration and scheduler state."""
    __tablename__ = "states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    is_sending = Column(Boolean, default=False, nullable=False)
    interval_minutes = Column(Integer, default=60, nullable=False)
    start_time = Column(String(10), default="09:00", nullable=False)
    end_time = Column(String(10), default="21:00", nullable=False)
    timezone = Column(String(50), default="Asia/Tashkent", nullable=False)
    send_sticker = Column(Boolean, default=False, nullable=False)
    current_message_index = Column(Integer, default=0, nullable=False)
    current_sticker_index = Column(Integer, default=0, nullable=False)
    sticker_set_name = Column(String(255), nullable=True)

    user = relationship("User", back_populates="state")
