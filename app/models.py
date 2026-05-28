from sqlalchemy import Column, Integer, String, Float, Text, Boolean, ForeignKey, DateTime, Index, CheckConstraint
from sqlalchemy.sql import func, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql.sqltypes import TIMESTAMP
from datetime import datetime
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, nullable=False)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)
    monthly_limit = Column(Float, server_default="0", nullable=False)
    
    # UPI Fields with proper validation
    upi_id = Column(String(50), unique=True, nullable=True)
    upi_verified = Column(Boolean, default=False, nullable=False)
    upi_verified_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Relationships
    expenses = relationship("Expense", back_populates="owner", cascade="all, delete")
    group_expenses = relationship("GroupExpense", back_populates="paid_by", cascade="all, delete")
    splits = relationship("Split", back_populates="user", cascade="all, delete")
    settlements_from = relationship("Settlement", foreign_keys='Settlement.from_user_id', back_populates="from_user", cascade="all, delete")
    settlements_to = relationship("Settlement", foreign_keys='Settlement.to_user_id', back_populates="to_user", cascade="all, delete")
    group_memberships = relationship("GroupMember", back_populates="user", cascade="all, delete")

    __table_args__ = (
        CheckConstraint('monthly_limit >= 0'),
    )


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint('amount > 0'),
        Index('idx_owner_created', 'owner_id', 'created_at'),
    )

    id = Column(Integer, primary_key=True, nullable=False)
    title = Column(String(100), nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String(50), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=True, index=True)

    owner = relationship("User", back_populates="expenses")
    group = relationship("Group", back_populates="individual_expenses")


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String(100), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)

    members = relationship("GroupMember", back_populates="group", cascade="all, delete")
    expenses = relationship("GroupExpense", back_populates="group", cascade="all, delete")
    individual_expenses = relationship("Expense", back_populates="group", cascade="all, delete")
    settlements = relationship("Settlement", back_populates="group", cascade="all, delete")


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (
        Index('idx_user_group', 'user_id', 'group_id'),
    )

    id = Column(Integer, primary_key=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), default="member", nullable=False)
    joined_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)

    user = relationship("User", back_populates="group_memberships")
    group = relationship("Group", back_populates="members")


class GroupExpense(Base):
    __tablename__ = "group_expenses"
    __table_args__ = (
        CheckConstraint('amount > 0'),
        Index('idx_group_created', 'group_id', 'created_at'),
    )

    id = Column(Integer, primary_key=True, nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    paid_by_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), onupdate=datetime.utcnow, nullable=False)

    group = relationship("Group", back_populates="expenses")
    paid_by = relationship("User", back_populates="group_expenses")
    splits = relationship("Split", back_populates="group_expense", cascade="all, delete")


class Split(Base):
    __tablename__ = "splits"
    __table_args__ = (
        CheckConstraint('amount > 0'),
        Index('idx_expense_user', 'group_expense_id', 'user_id'),
    )

    id = Column(Integer, primary_key=True, nullable=False)
    group_expense_id = Column(Integer, ForeignKey("group_expenses.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Float, nullable=False)

    group_expense = relationship("GroupExpense", back_populates="splits")
    user = relationship("User", back_populates="splits")


class Settlement(Base):
    __tablename__ = "settlements"
    __table_args__ = (
        CheckConstraint('amount > 0'),
        Index('idx_group_status', 'group_id', 'status'),
        Index('idx_from_to', 'from_user_id', 'to_user_id'),
    )

    id = Column(Integer, primary_key=True, nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    from_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    to_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    proof_url = Column(String(500), nullable=True)
    status = Column(String(20), default="pending", nullable=False)  # pending, confirmed, rejected
    
    # Timestamps for audit trail
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)
    confirmed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    rejected_at = Column(TIMESTAMP(timezone=True), nullable=True)

    group = relationship("Group", back_populates="settlements")
    from_user = relationship("User", foreign_keys=[from_user_id], back_populates="settlements_from")
    to_user = relationship("User", foreign_keys=[to_user_id], back_populates="settlements_to")

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(100), nullable=False)
    message = Column(String(500), nullable=False)
    type = Column(String(30), default="info", nullable=False)  # info, success, warning, danger
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)

    user = relationship("User", backref="notifications")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    description = Column(String(500), nullable=False)
    entity_type = Column(String(30), nullable=True)  # expense, group, settlement
    entity_id = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)

    user = relationship("User", backref="activity_logs")    