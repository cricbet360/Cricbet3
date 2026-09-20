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


class DepositRequest(Base):

    __tablename__ = "deposit_requests"

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

    utr_number = Column(
        String(100),
        nullable=False
    )

    payment_screenshot = Column(
        String(500),
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
        back_populates="deposit_requests"
    )

    # ------------------------------------------------------
    # EMPLOYEE
    # ------------------------------------------------------

    employee = relationship(
        "Employee",
        back_populates="deposit_requests"
    )