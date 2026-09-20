from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import relationship

from database.database import Base


class User(Base):

    __tablename__ = "users"

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
        default=10000.00
    )

    status = Column(
        String(20),
        default="Active"
    )

    # ------------------------------------------------------
    # WALLET
    # ------------------------------------------------------

    wallet = relationship(
        "Wallet",
        back_populates="user",
        uselist=False
    )

    # ------------------------------------------------------
    # TRANSACTIONS
    # ------------------------------------------------------

    transactions = relationship(
        "Transaction",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Transaction.created_at.desc()",
    )

    # ------------------------------------------------------
    # BETS
    # ------------------------------------------------------

    bets = relationship(
        "Bet",
        back_populates="user",
        order_by="Bet.created_at.desc()",
        cascade="all, delete-orphan",
    )

    # ------------------------------------------------------
    # DEPOSITS
    # ------------------------------------------------------

    deposit_requests = relationship(
        "DepositRequest",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="DepositRequest.created_at.desc()",
    )

    # ------------------------------------------------------
    # WITHDRAWALS
    # ------------------------------------------------------

    withdrawal_requests = relationship(
        "WithdrawalRequest",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="WithdrawalRequest.created_at.desc()",
    )