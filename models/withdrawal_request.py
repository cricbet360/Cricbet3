from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    ForeignKey
)

from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from database.database import Base


class WithdrawalRequest(Base):

    __tablename__ = "withdrawal_requests"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    amount = Column(
        Float,
        nullable=False
    )

    account_holder_name = Column(
        String(150),
        nullable=False
    )

    bank_name = Column(
        String(150),
        nullable=False
    )

    account_number = Column(
        String(50),
        nullable=False
    )

    ifsc_code = Column(
        String(11),
        nullable=False
    )

    status = Column(
        String(20),
        default="Pending",
        nullable=False,
        index=True
    )

    processed_by = Column(
        Integer,
        ForeignKey("employees.id"),
        nullable=True
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    completed_at = Column(
        DateTime,
        nullable=True
    )

    # ------------------------------------------------------
    # USER
    # ------------------------------------------------------

    user = relationship(
        "User",
        back_populates="withdrawal_requests"
    )

    # ------------------------------------------------------
    # EMPLOYEE
    # ------------------------------------------------------

    employee = relationship(
        "Employee",
        back_populates="withdrawal_requests"
    )