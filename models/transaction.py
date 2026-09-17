from sqlalchemy import (
    Column,
    Integer,
    Numeric,
    String,
    DateTime,
    ForeignKey
)

from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database.database import Base


class Transaction(Base):

    __tablename__ = "transactions"


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
        Numeric(12, 2),
        nullable=False
    )


    transaction_type = Column(
        String(50),
        nullable=False,
        index=True
    )


    status = Column(
        String(30),
        nullable=False,
        default="Completed",
        index=True
    )


    reference_type = Column(
        String(50),
        nullable=True
    )


    reference_id = Column(
        Integer,
        nullable=True
    )


    description = Column(
        String(255),
        nullable=True
    )


    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )


    user = relationship(
        "User",
        back_populates="transactions"
    )