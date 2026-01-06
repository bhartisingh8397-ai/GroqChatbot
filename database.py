from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app=Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI']= 'postgresql://postgres:bharti@localhost:5432/db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS']= False

db= SQLAlchemy(app)

class User(db.Model):
    __table__= "User"
    id = db.Column(db.Integer , primary_key=True)
    name = db.Column(db.String(100))
    email_id = db.Column(db.String(200),unique=True)
    password = db.Column(db.String(120))

class Messages(db.Model):
    id = db.Column(db.Integer,primary_key=True)
    chat_id = db.Column(db.Integer)
    content_text = db.Column(db.String(200))
    created_at= db.Column(db.DateTime)

class Chat(db.Model):
    id = db.Column(db.Integer,primary_key=True)
    user_id = db.Column(db.Integer)
    title= db.Column(db.String(200))
    created_at= db.Column(db.DateTime)

with app.app_context():
    db.create_all()
    
@app.route('/')
def home():
    return "database connected."

if __name__=='__main__':
    app.run(debug=True)