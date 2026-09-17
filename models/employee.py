from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from database.database import Base


class Employee(Base):

    __tablename__ = "employees"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    employee_id = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True
    )

    password = Column(
        String(255),
        nullable=False
    )

    status = Column(
        String(20),
        default="Active",
        nullable=False
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    deposit_requests = relationship(
        "DepositRequest",
        back_populates="employee"
    )

    withdrawal_requests = relationship(
        "WithdrawalRequest",
        back_populates="employee"
    )