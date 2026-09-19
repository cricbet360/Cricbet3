from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from database.database import Base


class User(Base):

    __tablename__ = "users"

    # ======================================================
    # BASIC USER INFORMATION
    # ======================================================

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    username = Column(
        String(50),
        unique=True,
        nullable=False
    )

    email = Column(
        String(100),
        unique=True,
        nullable=False
    )

    phone = Column(
        String(20),
        unique=True,
        nullable=False
    )

    password = Column(
        String(255),
        nullable=False
    )

    balance = Column(
        Float,
        default=0.00,
        nullable=False
    )

    status = Column(
        String(20),
        default="Active"
    )

    # ======================================================
    # REFERRAL SYSTEM
    # ======================================================

    referral_code = Column(
        String(20),
        unique=True,
        nullable=True,
        index=True
    )

    referred_by_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
        index=True
    )

    # True once this user has had their first approved deposit.
    first_deposit_completed = Column(
        Boolean,
        default=False,
        nullable=False
    )

    # True once the one-time referral bonus for this user
    # has been paid to their referrer.
    referral_bonus_paid = Column(
        Boolean,
        default=False,
        nullable=False
    )

    # ======================================================
    # REFERRAL RELATIONSHIPS
    # ======================================================

    referrer = relationship(
        "User",
        remote_side=[id],
        foreign_keys=[referred_by_user_id],
        back_populates="referred_users",
    )

    referred_users = relationship(
        "User",
        foreign_keys=[referred_by_user_id],
        back_populates="referrer",
    )

    # ======================================================
    # WALLET
    # ======================================================

    wallet = relationship(
        "Wallet",
        back_populates="user",
        uselist=False
    )

    # ======================================================
    # TRANSACTIONS
    # ======================================================

    transactions = relationship(
        "Transaction",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Transaction.created_at.desc()",
    )

    # ======================================================
    # BETS
    # ======================================================

    bets = relationship(
        "Bet",
        back_populates="user",
        order_by="Bet.created_at.desc()",
        cascade="all, delete-orphan",
    )

    # ======================================================
    # DEPOSITS
    # ======================================================

    deposit_requests = relationship(
        "DepositRequest",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="DepositRequest.created_at.desc()",
    )

    # ======================================================
    # WITHDRAWALS
    # ======================================================

    withdrawal_requests = relationship(
        "WithdrawalRequest",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="WithdrawalRequest.created_at.desc()",
    )