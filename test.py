from app import app
from database import db ,User

with app.app_context():
    fake_user =User (
            id = 101,
            name = "bharti",
            email_id= "bharti@gmail.com",
            password="bharti"   # (later hash karna)
        )

    db.session.add(fake_user)
    db.session.commit()
print("inserted successfully")