from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session, Response
import os
from datetime import datetime
from datetime import timedelta
from dotenv import load_dotenv
from groq_client import GroqClient
from gemini_client import GeminiClient
from openrouter_client import OpenRouterClient
import secrets
from flask_sqlalchemy import SQLAlchemy
from database import db, User, Messages, Chat
from werkzeug.security import generate_password_hash, check_password_hash
from authlib.integrations.flask_client import OAuth
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:bharti@localhost:5432/db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
if 'sqlalchemy' not in app.extensions:
    db.init_app(app)
# Use fixed secret key from env or default (don't regenerate on every restart)
app.secret_key = os.getenv('SECRET_KEY', 'your-fixed-secret-key-change-in-production')

# Configure session lifetime (Instagram-like persistence)
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=365)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)

# Initialize OAuth
oauth = OAuth(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Configure Google OAuth
google = oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

# Create tables if they don't exist
try:
    with app.app_context():
        db.create_all()
        print("[INFO] Database tables created successfully!")
except Exception as e:
    print(f"[ERROR] Database connection failed: {e}")
    print("[ERROR] Make sure PostgreSQL is running and accessible!")

# Initialize Groq client (optional)
try:
    groq_client = GroqClient(api_key=os.getenv('GROQ_API_KEY'))
except Exception as e:
    print(f"Warning: Groq client initialization failed: {e}")
    groq_client = None

# Initialize Gemini client if available
try:
    gemini_client = GeminiClient(api_key=os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY'))
except Exception as e:
    print(f"Warning: Gemini client initialization failed: {e}")
    gemini_client = None

# Initialize OpenRouter client if available
try:
    openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
    if openrouter_api_key:
        print(f"[INFO] Initializing OpenRouter client...")
        openrouter_client = OpenRouterClient(api_key=openrouter_api_key)
        print(f"[INFO] OpenRouter client initialized successfully")
    else:
        print(f"[WARNING] OPENROUTER_API_KEY not found in environment")
        openrouter_client = None
except Exception as e:
    print(f"[ERROR] OpenRouter client initialization failed: {e}")
    import traceback
    traceback.print_exc()
    openrouter_client = None


# Helper function to get current user - REMOVED, use current_user instead
# def get_current_user():
#     """Get the currently logged in user from session"""
#     user_id = session.get('user_id')
#     if user_id:
#         return User.query.get(user_id)
#     return None


# Helper function to get or create current chat
def get_or_create_chat(user_id):
    """Get current chat from session or create a new one"""
    chat_id = session.get('current_chat_id')
    
    if chat_id:
        chat = Chat.query.get(chat_id)
        if chat and chat.user_id == user_id:
            return chat
    
    # Create new chat
    new_chat = Chat(
        user_id=user_id,
        title="New Chat",
        created_at=datetime.utcnow()
    )
    db.session.add(new_chat)
    db.session.commit()
    session['current_chat_id'] = new_chat.id
    return new_chat


@app.route('/send', methods=['POST'])
def send_msg():
    data = request.json
    
    if current_user.is_authenticated:
        chat = get_or_create_chat(current_user.id)
        new_message = Messages(
            chat_id=chat.id,
            content_text=data.get("messages"),
            created_at=datetime.utcnow()
        )
        db.session.add(new_message)
        db.session.commit()
    
    return jsonify({"status": "success"})


@app.route('/history_page')
@login_required
def history_page():
    chats = []
    
    # Only show chats for the logged-in user
    if current_user.is_authenticated:
        user_chats = Chat.query.filter_by(user_id=current_user.id).order_by(Chat.created_at.desc()).all()
        print(f"[DEBUG] history_page - found {len(user_chats)} chats for user {current_user.id}")
        
        for chat in user_chats:
            chat_data = {
                'id': chat.id,
                'title': chat.title,
                'created_at': chat.created_at.isoformat() if chat.created_at else None,
                'messages': []
            }
            msgs = Messages.query.filter_by(chat_id=chat.id).order_by(Messages.created_at).all()
            for msg in msgs:
                text = msg.content_text or ''
                role = 'assistant' if text.startswith('[ASSISTANT]') else 'user'
                content = text.replace('[USER] ', '').replace('[ASSISTANT] ', '')
                chat_data['messages'].append({
                    'role': role,
                    'content': content,
                    'time': msg.created_at.isoformat() if msg.created_at else None
                })
            chats.append(chat_data)
    else:
        print("[DEBUG] history_page - no user logged in, showing empty history")
    
    return render_template('history.html', chats=chats)


@app.route("/history", methods=["GET"])
@login_required
def history():
    try:
        formatted = []
        
        if current_user.is_authenticated:
            chat_id = session.get('current_chat_id')
            if chat_id:
                messages = Messages.query.filter_by(chat_id=chat_id).order_by(Messages.created_at).all()
                for msg in messages:
                    formatted.append({
                        "messages": msg.content,
                        "time": msg.created_at.isoformat() if msg.created_at else datetime.now().isoformat(),
                        "role": msg.role or "user"
                    })
        
        return jsonify(formatted)
    except Exception as e:
        print("History route error:", e)
        return jsonify({"error": str(e)}), 500


@app.route('/exportchat', methods=['GET'])
@login_required
def export_chat():
    chat_id = session.get('current_chat_id')
    
    with open("chat.txt", "w", encoding="utf-8") as file:
        if current_user.is_authenticated and chat_id:
            messages = Messages.query.filter_by(chat_id=chat_id).order_by(Messages.created_at).all()
            for msg in messages:
                file.write(f"{msg.role}:{msg.content}\n")
    
    return send_file("chat.txt", as_attachment=True)


@app.route('/api/models', methods=['GET'])
def get_models():
    """Get list of available models from selected provider."""
    try:
        provider = request.args.get('provider', 'groq').lower()
        print(f"[DEBUG] /api/models called with provider: {provider}")

        if provider == 'gemini':
            if not gemini_client:
                print(f"[DEBUG] Gemini client not configured")
                return jsonify({'success': False, 'error': 'Gemini client not configured. Set GEMINI_API_KEY.'}), 400
            models = gemini_client.list_models()
            print(f"[DEBUG] Gemini models loaded: {len(models)}")
            return jsonify({'success': True, 'models': models})

        if provider == 'openrouter':
            if not openrouter_client:
                print(f"[DEBUG] OpenRouter client not configured")
                return jsonify({'success': False, 'error': 'OpenRouter client not configured. Set OPENROUTER_API_KEY.'}), 400
            print(f"[DEBUG] Fetching OpenRouter models...")
            models = openrouter_client.list_models()
            print(f"[DEBUG] OpenRouter models loaded: {len(models)}")
            return jsonify({'success': True, 'models': models})

        if provider == 'all':
            models = []
            try:
                groq_models = groq_client.list_models()
                for m in groq_models:
                    m_copy = dict(m)
                    m_copy['provider'] = 'groq'
                    models.append(m_copy)
            except Exception:
                pass
            try:
                if gemini_client:
                    gem_models = gemini_client.list_models()
                    for m in gem_models:
                        m_copy = dict(m)
                        m_copy['provider'] = 'gemini'
                        models.append(m_copy)
            except Exception:
                pass
            try:
                if openrouter_client:
                    or_models = openrouter_client.list_models()
                    for m in or_models:
                        m_copy = dict(m)
                        m_copy['provider'] = 'openrouter'
                        models.append(m_copy)
            except Exception:
                pass
            return jsonify({'success': True, 'models': models})

        # Default to groq provider
        models = groq_client.list_models()
        return jsonify({'success': True, 'models': models})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chat messages - saves to database for permanent storage"""
    try:
        data = request.json
        user_message = data.get('message')
        selected_model = data.get('model', 'mixtral-8x7b-32768')
        provider = (data.get('provider') or 'groq').lower()
        
        print(f"[DEBUG] /api/chat - message: {user_message[:50] if user_message else 'None'}...")
        print(f"[DEBUG] /api/chat - model: {selected_model}, provider: {provider}")
        
        if provider == 'groq' and groq_client is None and gemini_client is not None:
            provider = 'gemini'
            print(f"[DEBUG] /api/chat - Switched to gemini (groq not available)")
        
        if not user_message:
            return jsonify({
                'success': False,
                'error': 'Message is required'
            }), 400
        
        chat_history = []
        
        print(f"[DEBUG] /api/chat - user logged in: {current_user.is_authenticated}")
        
        # Get or create chat (works with or without login)
        chat_id = session.get('current_chat_id')
        chat_obj = None
        
        if chat_id:
            chat_obj = Chat.query.get(chat_id)
        
        if not chat_obj:
            # Create new chat (for guest users, user_id will be None)
            chat_obj = Chat(
                user_id=current_user.id if current_user.is_authenticated else None,
                title="New Chat",
                created_at=datetime.utcnow()
            )
            db.session.add(chat_obj)
            db.session.commit()
            session['current_chat_id'] = chat_obj.id
            print(f"[DEBUG] /api/chat - Created new chat_id: {chat_obj.id}")
        
        print(f"[DEBUG] /api/chat - Using chat_id: {chat_obj.id}")
        
        # Save user message to database
        user_msg = Messages(
            chat_id=chat_obj.id,
            content_text=f"[USER] {user_message}",
            created_at=datetime.utcnow()
        )
        db.session.add(user_msg)
        db.session.commit()
        
        # Update chat title if it's the first message
        msg_count = Messages.query.filter_by(chat_id=chat_obj.id).count()
        if chat_obj.title == "New Chat" and msg_count == 1:
            chat_obj.title = user_message[:50] + "..." if len(user_message) > 50 else user_message
            db.session.commit()
        
        # Load chat history from database for context
        db_messages = Messages.query.filter_by(chat_id=chat_obj.id).order_by(Messages.created_at).all()
        chat_history = []
        for msg in db_messages:
            text = msg.content_text or ''
            if text.startswith('[USER] '):
                chat_history.append({'role': 'user', 'content': text[7:]})
            elif text.startswith('[ASSISTANT] '):
                chat_history.append({'role': 'assistant', 'content': text[12:]})
        
        print(f"[DEBUG] /api/chat - chat_history length: {len(chat_history)}")
        
        # Get response from selected provider
        print(f"[DEBUG] /api/chat - Calling {provider} API...")
        
        if provider == 'gemini':
            if not gemini_client:
                print(f"[DEBUG] /api/chat - Gemini client not configured!")
                return jsonify({'success': False, 'error': 'Gemini client not configured. Set GEMINI_API_KEY.'}), 400
            assistant_message = gemini_client.chat(chat_history, model=selected_model)
        elif provider == 'openrouter':
            if not openrouter_client:
                print(f"[DEBUG] /api/chat - OpenRouter client not configured!")
                return jsonify({'success': False, 'error': 'OpenRouter client not configured. Set OPENROUTER_API_KEY.'}), 400
            assistant_message = openrouter_client.chat(chat_history, model=selected_model)
        else:
            if not groq_client:
                print(f"[DEBUG] /api/chat - Groq client not configured!")
                return jsonify({'success': False, 'error': 'Groq client not configured. Set GROQ_API_KEY.'}), 400
            assistant_message = groq_client.chat(chat_history, model=selected_model)
        
        print(f"[DEBUG] /api/chat - Got response: {assistant_message[:50] if assistant_message else 'None'}...")
        
        timestamp = datetime.utcnow()
        
        # Save assistant message to database (always, not just when logged in)
        if chat_obj:
            assistant_msg = Messages(
                chat_id=chat_obj.id,
                content_text=f"[ASSISTANT] {assistant_message}",
                created_at=timestamp
            )
            db.session.add(assistant_msg)
            db.session.commit()
            print(f"[DEBUG] /api/chat - Saved assistant message to database")
        
        return jsonify({
            'success': True,
            'message': assistant_message,
            'timestamp': timestamp.isoformat()
        })
        
    except Exception as e:
        import traceback
        print(f"[ERROR] /api/chat - Exception: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/history', methods=['GET'])
@login_required
def get_history():
    """Get chat history for current session from database"""
    chat_id = session.get('current_chat_id')
    
    if current_user.is_authenticated and chat_id:
        messages = Messages.query.filter_by(chat_id=chat_id).order_by(Messages.created_at).all()
        history = [{
            'role': msg.role,
            'content': msg.content,
            'timestamp': msg.created_at.isoformat() if msg.created_at else None,
            'model': msg.model
        } for msg in messages]
        return jsonify({
            'success': True,
            'history': history
        })
    
    return jsonify({
        'success': True,
        'history': []
    })


@app.route('/api/clear', methods=['POST'])
@login_required
def clear_history():
    """Clear chat history for current chat"""
    chat_id = session.get('current_chat_id')
    
    if current_user.is_authenticated and chat_id:
        Messages.query.filter_by(chat_id=chat_id).delete()
        db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Chat history cleared'
    })


@app.route('/api/new-chat', methods=['POST'])
@login_required
def newchat():
    """Start a new chat - creates new chat in database"""
    
    if current_user.is_authenticated:
        new_chat = Chat(
            user_id=current_user.id,
            title="New Chat",
            created_at=datetime.utcnow()
        )
        db.session.add(new_chat)
        db.session.commit()
        session['current_chat_id'] = new_chat.id
        
        return jsonify({
            'success': True,
            'message': 'New chat started',
            'chat_id': new_chat.id
        })
    
    return jsonify({
        'success': True,
        'message': 'New chat started'
    })


@app.route('/api/sessions', methods=['GET'])
@login_required
def get_sessions():
    """Get all chat sessions for the current user"""
    
    if current_user.is_authenticated:
        chats = Chat.query.filter_by(user_id=current_user.id).order_by(Chat.updated_at.desc()).all()
        sessions = [{
            'id': chat.id,
            'title': chat.title,
            'created_at': chat.created_at.isoformat() if chat.created_at else None,
            'updated_at': chat.updated_at.isoformat() if chat.updated_at else None,
            'message_count': len(chat.messages)
        } for chat in chats]
        
        return jsonify({
            'success': True,
            'sessions': sessions
        })
    
    return jsonify({
        'success': True,
        'sessions': []
    })


@app.route('/api/switch-session', methods=['POST'])
@login_required
def switch_session():
    """Switch to a different chat session"""
    data = request.json
    chat_id = data.get('chat_id')
    
    if current_user.is_authenticated and chat_id:
        chat = Chat.query.get(chat_id)
        if chat and chat.user_id == current_user.id:
            session['current_chat_id'] = chat.id
            return jsonify({
                'success': True,
                'message': f'Switched to chat: {chat.title}'
            })
        return jsonify({
            'success': False,
            'error': 'Chat not found or access denied'
        }), 404
    
    return jsonify({
        'success': False,
        'error': 'User not logged in or chat_id not provided'
    }), 400


@app.route('/api/delete-chat', methods=['POST'])
@login_required
def delete_chat():
    """Delete a chat and all its messages"""
    data = request.json
    chat_id = data.get('chat_id')
    
    if not chat_id:
        return jsonify({
            'success': False,
            'error': 'chat_id not provided'
        }), 400
    
    chat = Chat.query.get(chat_id)
    if not chat:
        return jsonify({
            'success': False,
            'error': 'Chat not found'
        }), 404
    
    # Delete all messages first, then the chat
    Messages.query.filter_by(chat_id=chat_id).delete()
    db.session.delete(chat)
    db.session.commit()
    
    # If deleting current chat, clear session
    if session.get('current_chat_id') == chat_id:
        session.pop('current_chat_id', None)
    
    return jsonify({
        'success': True,
        'message': 'Chat deleted successfully'
    })


@app.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    """Get statistics"""
    
    if current_user.is_authenticated:
        total_chats = Chat.query.filter_by(user_id=current_user.id).count()
        total_messages = Messages.query.join(Chat).filter(Chat.user_id == current_user.id).count()
        user_messages = Messages.query.join(Chat).filter(Chat.user_id == current_user.id, Messages.role == 'user').count()
        assistant_messages = Messages.query.join(Chat).filter(Chat.user_id == current_user.id, Messages.role == 'assistant').count()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_chats': total_chats,
                'total_messages': total_messages,
                'user_messages': user_messages,
                'assistant_messages': assistant_messages
            }
        })
    
    return jsonify({
        'success': True,
        'stats': {
            'total_messages': 0,
            'user_messages': 0,
            'assistant_messages': 0
        }
    })


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for container orchestration"""
    try:
        if groq_client is not None:
            _ = groq_client.list_models()
            provider = 'groq'
        elif gemini_client is not None:
            _ = gemini_client.list_models()
            provider = 'gemini'
        elif openrouter_client is not None:
            _ = openrouter_client.list_models()
            provider = 'openrouter'
        else:
            return jsonify({'status': 'unhealthy', 'error': 'No AI provider configured'}), 503

        return jsonify({'status': 'healthy', 'api': provider}), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 503


@app.route('/newChat', methods=['GET'])
def newChat():
    # user = get_current_user() # Handled by current_user now
    
    if current_user.is_authenticated:
        new_chat = Chat(
            user_id=current_user.id,
            title="New Chat",
            created_at=datetime.utcnow()
        )
        db.session.add(new_chat)
        db.session.commit()
        session['current_chat_id'] = new_chat.id
        
        return jsonify({
            "status": "success",
            "chat_id": new_chat.id
        })
    
    return jsonify({
        "status": "success",
        "chat_id": "guest_chat"
    })


@app.route('/api/tts', methods=['POST'])
def text_to_speech():
    """Convert text to speech using Groq TTS API"""
    try:
        data = request.get_json()
        text = data.get('text', '')
        model = data.get('model', 'playai-tts')
        voice = data.get('voice', 'Fritz-PlayAI')
        
        if not text:
            return jsonify({
                'success': False,
                'error': 'Text is required'
            }), 400
        
        if len(text) > 10000:
            text = text[:10000]
        
        audio_content = groq_client.text_to_speech(
            text=text,
            model=model,
            voice=voice
        )
        
        return Response(
            audio_content,
            mimetype='audio/wav',
            headers={
                'Content-Disposition': 'inline; filename="speech.wav"'
            }
        )
        
    except Exception as e:
        error_msg = str(e)
        
        if 'terms acceptance' in error_msg.lower():
            return jsonify({
                'success': False,
                'error': 'TTS requires terms acceptance. Please visit https://console.groq.com/playground?model=playai-tts to accept terms.',
                'error_type': 'terms_required'
            }), 403
        
        return jsonify({
            'success': False,
            'error': error_msg
        }), 500


@app.route('/')
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == "POST":
        email_id = request.form.get("email_id")
        password = request.form.get("password")
        remember = True if request.form.get("remember") else False

        print(f"[DEBUG] Login attempt - email: {email_id}")
        
        user = User.query.filter_by(email_id=email_id).first()
        
        if not user:
            print(f"[DEBUG] Login failed - User not found: {email_id}")
            return "User not found. Please sign up first."
        
        print(f"[DEBUG] User found - id: {user.id}, name: {user.name}")
        print(f"[DEBUG] Stored password hash: {user.password[:20] if user.password else 'None'}...")
        
        # Check if password is hashed (starts with typical hash prefixes)
        is_hashed = user.password and (user.password.startswith('pbkdf2:') or user.password.startswith('scrypt:') or user.password.startswith('$'))
        
        if not is_hashed:
            print(f"[DEBUG] Password is NOT hashed! Checking plain text...")
            # For old users with unhashed passwords - direct comparison
            if user.password == password:
                print(f"[DEBUG] Plain text password matched! Updating to hashed...")
                # Update to hashed password
                user.password = generate_password_hash(password)
                db.session.commit()
                
                
                login_user(user, remember=remember)
                # session['user_id'] = user.id
                # session['user_name'] = user.name
                
                latest_chat = Chat.query.filter_by(user_id=user.id).order_by(Chat.created_at.desc()).first()
                if latest_chat:
                    session['current_chat_id'] = latest_chat.id
                
                return redirect(url_for('index'))
            else:
                print(f"[DEBUG] Plain text password did NOT match")
                return "Invalid password"
        
        # Normal hashed password check
        if check_password_hash(user.password, password):
            print(f"[DEBUG] Login successful!")
            login_user(user, remember=remember)
            # session['user_id'] = user.id
            # session['user_name'] = user.name
            
            latest_chat = Chat.query.filter_by(user_id=user.id).order_by(Chat.created_at.desc()).first()
            if latest_chat:
                session['current_chat_id'] = latest_chat.id
            
            return redirect(url_for('index'))
        else:
            print(f"[DEBUG] Hashed password did NOT match")
            return "Invalid password"

    return render_template("login.html")


@app.route('/login/google')
def google_login():
    """Initiate Google OAuth login"""
    redirect_uri = url_for('google_callback', _external=True)
    # prompt='select_account' forces Google to show account chooser every time
    return google.authorize_redirect(redirect_uri, prompt='select_account')


@app.route('/callback')
def google_callback():
    """Handle Google OAuth callback"""
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        
        if not user_info:
            # Fallback: fetch user info from Google
            resp = google.get('https://openidconnect.googleapis.com/v1/userinfo')
            user_info = resp.json()
        
        google_id = user_info.get('sub')
        email = user_info.get('email')
        name = user_info.get('name', email.split('@')[0] if email else 'User')
        
        print(f"[DEBUG] Google OAuth - google_id: {google_id}, email: {email}, name: {name}")
        
        # Check if user exists by google_id
        user = User.query.filter_by(google_id=google_id).first()
        
        if not user:
            # Check if user exists by email (link accounts)
            user = User.query.filter_by(email_id=email).first()
            if user:
                # Link Google account to existing user
                user.google_id = google_id
                db.session.commit()
                print(f"[DEBUG] Linked Google account to existing user: {user.id}")
            else:
                # Create new user
                user = User(
                    name=name,
                    email_id=email,
                    google_id=google_id,
                    password=None  # No password for Google-only users
                )
                db.session.add(user)
                db.session.commit()
                print(f"[DEBUG] Created new user via Google: {user.id}")
        
        # Log the user in
        login_user(user)
        # session['user_id'] = user.id
        # session['user_name'] = user.name
        
        # Get or create latest chat
        latest_chat = Chat.query.filter_by(user_id=user.id).order_by(Chat.created_at.desc()).first()
        if latest_chat:
            session['current_chat_id'] = latest_chat.id
        
        print(f"[DEBUG] Google OAuth login successful for user: {user.id}")
        return redirect(url_for('index'))
        
    except Exception as e:
        print(f"[ERROR] Google OAuth callback failed: {e}")
        import traceback
        traceback.print_exc()
        return f"Google authentication failed: {str(e)}. <a href='/login'>Try again</a>"


@app.route('/logout')
@login_required
def logout():
    """Logout user and clear session"""
    logout_user()
    session.clear()
    return redirect(url_for('login_page'))


@app.route('/index')
@login_required
def index():
    user_name = current_user.name if current_user.is_authenticated else "Guest User"
    return render_template('index.html', user_name=user_name)


@app.route('/signup', methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == "POST":
        id = request.form.get("userid")
        name = request.form.get("name")
        email_id = request.form.get("email")
        password = request.form.get("password")
        hashed_password = generate_password_hash(password)
        
        existing_user = User.query.filter_by(email_id=email_id).first()
        if existing_user:
            return "User already exists"

        new_user = User(
            name=name,
            email_id=email_id,
            password=hashed_password
        )

        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for("login"))

    return render_template('signup.html')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
