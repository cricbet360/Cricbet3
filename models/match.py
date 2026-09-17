from sqlalchemy import Column, Integer, String

from database.database import Base


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True)

    sport = Column(String)

    league = Column(String)

    team1 = Column(String)

    team2 = Column(String)

    status = Column(String)

    score = Column(String)