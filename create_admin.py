from database.database import SessionLocal
from models.admin import Admin
from auth.password import hash_password


db = SessionLocal()

username = "Cricbet"
password = "Cricbet@360"


existing_admin = db.query(Admin).filter(
    Admin.username == username
).first()


if existing_admin:
    print("Admin already exists.")

else:
    admin = Admin(
        username=username,
        password=hash_password(password),
        status="Active"
    )

    db.add(admin)
    db.commit()

    print("Admin created successfully.")
    print("Username:", username)
    print("Password:", password)


db.close()