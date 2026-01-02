from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app=Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URL']= 'sqlite:///database.db'
app. config['SQLALCHEMY_TRACK_MODIFICATIONS']= False

db= SQLAlchemy(app)

class User(db.model):
    id = db.Column(db.integer,primary_key==True)
    name = db.Column(db.String(100))
    email_id = db.Column(db.String(200),unique==True)
    password = db.Column(db.String(120))

class Messages(db.model):
    id = db.Column(db.integer,primary_key==True)
    chat_id = db.Column(db.integer)
    content_text = db.Column(db.String(200))
    created_at= db.Column(db.datetime())

class Chat(db.model):
    id = db.Column(db.integer,primary_key==True)
    user_id = db.Column(db.integer)
    title= db.Column(db.String(200))
    created_at= db.Column(db.datetime())

with app.app_context():
    db.create_all()
    
@app.route('/check-db')
def home():
    return "database connected."

if __name__=='__main__':
    app.run(debug=True)