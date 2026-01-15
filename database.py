from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

# Create SQLAlchemy instance - will be initialized with app in app.py
db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email_id = db.Column(db.String(200), unique=True)
    password = db.Column(db.String(255), nullable=True)  # Nullable for Google-only users
    google_id = db.Column(db.String(255), unique=True, nullable=True)  # For Google OAuth users

class Chat(db.Model):
    __tablename__ = "chats"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    title = db.Column(db.String(200))
    created_at = db.Column(db.DateTime)
    # Note: using existing table structure without updated_at

class Messages(db.Model):
    __tablename__ = "messages"
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer)
    content_text = db.Column(db.String(200))  # Using existing column name
    created_at = db.Column(db.DateTime)
    # Note: using existing table structure without role/model columns