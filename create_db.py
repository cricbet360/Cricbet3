from database.database import Base, engine
from models.user import User
from models.wallet import Wallet
from models.transaction import Transaction
from models.match import Match
from models.admin import Admin

Base.metadata.create_all(bind=engine)

print("✅ CrickBet Database Created Successfully")