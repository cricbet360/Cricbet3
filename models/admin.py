from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime
)

from sqlalchemy.sql import func

from database.database import Base


class Admin(Base):

    __tablename__ = "admins"


    id = Column(
        Integer,
        primary_key=True,
        index=True
    )


    username = Column(
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
        server_default=func.now(),
        nullable=False
    )