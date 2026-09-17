from sqlalchemy import (
    Column,
    Integer,
    Numeric,
    ForeignKey,
    DateTime
)

from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database.database import Base


class Wallet(Base):

    __tablename__ = "wallets"


    id = Column(
        Integer,
        primary_key=True,
        index=True
    )


    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
        index=True
    )


    balance = Column(
        Numeric(12, 2),
        default=0.00,
        nullable=False
    )


    exposure = Column(
        Numeric(12, 2),
        default=0.00,
        nullable=False
    )


    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )


    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )


    user = relationship(
        "User",
        back_populates="wallet"
    )