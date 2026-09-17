from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from database.database import Base

# IMPORTANT:
# Import BetSelection so SQLAlchemy registers the model
# before it configures the Bet relationship.
from models.bet_selection import BetSelection


class Bet(Base):

    __tablename__ = "bets"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    stake = Column(
        Float,
        nullable=False,
    )

    total_odds = Column(
        Float,
        nullable=False,
    )

    potential_win = Column(
        Float,
        nullable=False,
    )

    status = Column(
        String(20),
        default="pending",
        nullable=False,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    # ------------------------------------------------------
    # USER
    # ------------------------------------------------------

    user = relationship(
        "User",
        back_populates="bets",
    )

    # ------------------------------------------------------
    # BET SELECTIONS
    # ------------------------------------------------------

    selections = relationship(
        "BetSelection",
        back_populates="bet",
        cascade="all, delete-orphan",
        order_by=BetSelection.id,
    )