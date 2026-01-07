from flask_sqlalchemy import SQLAlchemy

# Create SQLAlchemy instance - will be initialized with app in app.py
db = SQLAlchemy()

class User(db.Model):
    _tablename_ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email_id = db.Column(db.String(200), unique=True)
    password = db.Column(db.String(255))

class Messages(db.Model):
    _tablename_ = "messages"
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer)
    content_text = db.Column(db.String(200))
    created_at = db.Column(db.DateTime)

class Chat(db.Model):
    _tablename_ = "chats"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    title = db.Column(db.String(200))
    created_at = db.Column(db.DateTime)