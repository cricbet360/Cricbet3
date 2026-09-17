from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from database.database import Base


class BetSelection(Base):

    __tablename__ = "bet_selections"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    bet_id = Column(
        Integer,
        ForeignKey("bets.id"),
        nullable=False,
        index=True,
    )

    market_id = Column(
        String(100),
        nullable=False,
    )

    event_id = Column(
        String(100),
        nullable=True,
    )

    selection_id = Column(
        String(100),
        nullable=False,
    )

    runner_name = Column(
        String(255),
        nullable=False,
    )

    side = Column(
        String(10),
        nullable=False,
    )

    price = Column(
        Float,
        nullable=False,
    )

    market_name = Column(
        String(255),
        nullable=True,
    )

    event_name = Column(
        String(255),
        nullable=True,
    )

    bet = relationship(
        "Bet",
        back_populates="selections",
    )