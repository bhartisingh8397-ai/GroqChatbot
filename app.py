from flask import Flask, render_template, request, jsonify,send_file
import os
from datetime import datetime
from dotenv import load_dotenv
from groq_client import GroqClient
from gemini_client import GeminiClient
from openrouter_client import OpenRouterClient
import secrets

load_dotenv()

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

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

# In-memory storage for chat history (session only)
chat_history = []

@app.route('/')
def index():
    """Render the main chat interface"""
    return render_template('index.html')

@app.route('/exportchat', methods =['GET'])
def export_chat():
    with open ("chat.txt","w",encoding="utf-8") as file: 
        for msg in chat_history:
            file.write(f"{msg['role']}:{msg['content']}\n")
    return send_file("chat.txt",as_attachment=True)     



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
    """Handle chat messages"""
    global chat_history
    
    try:
        data = request.json
        user_message = data.get('message')
        selected_model = data.get('model', 'mixtral-8x7b-32768')
        provider = (data.get('provider') or 'groq').lower()
        if provider == 'groq' and groq_client is None and gemini_client is not None:
            # Fallback to Gemini if Groq is not configured
            provider = 'gemini'
        
        if not user_message:
            return jsonify({
                'success': False,
                'error': 'Message is required'
            }), 400
        
        # Add user message to in-memory history
        chat_history.append({
            'role': 'user',
            'content': user_message,
            'timestamp': datetime.now().isoformat(),
            'model': selected_model
        })
        
        # Prepare messages for provider API (includes the latest user message)
        messages = [{'role': msg['role'], 'content': msg['content']} for msg in chat_history]
        
        # Get response from selected provider
        if provider == 'gemini':
            if not gemini_client:
                return jsonify({'success': False, 'error': 'Gemini client not configured. Set GEMINI_API_KEY.'}), 400
            assistant_message = gemini_client.chat(messages, model=selected_model)
        elif provider == 'openrouter':
            if not openrouter_client:
                return jsonify({'success': False, 'error': 'OpenRouter client not configured. Set OPENROUTER_API_KEY.'}), 400
            assistant_message = openrouter_client.chat(messages, model=selected_model)
        else:
            if not groq_client:
                return jsonify({'success': False, 'error': 'Groq client not configured. Set GROQ_API_KEY.'}), 400
            assistant_message = groq_client.chat(messages, model=selected_model)
        
        # Add assistant message to in-memory history
        timestamp = datetime.now().isoformat()
        chat_history.append({
            'role': 'assistant',
            'content': assistant_message,
            'timestamp': timestamp,
            'model': selected_model
        })
        
        return jsonify({
            'success': True,
            'message': assistant_message,
            'timestamp': timestamp
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get chat history for current session (in-memory)"""
    return jsonify({
        'success': True,
        'history': chat_history
    })

@app.route('/api/clear', methods=['POST'])
def clear_history():
    """Clear chat history"""
    global chat_history
    chat_history = []
    
    return jsonify({
        'success': True,
        'message': 'Chat history cleared'
    })

@app.route('/api/new-chat', methods=['POST'])
def newchat():
    """Start a new chat (clear history)"""
    global chat_history
    chat_history = []
    
    return jsonify({
        'success': True,
        'message': 'New chat started'
    })
    

@app.route('/api/sessions', methods=['GET'])
def get_sessions():
    """Get all chat sessions - disabled for no-database mode"""
    return jsonify({
        'success': True,
        'sessions': []  # No sessions in memory-only mode
    })

@app.route('/api/switch-session', methods=['POST'])
def switch_session():
    """Switch to a different session - disabled for no-database mode"""
    return jsonify({
        'success': False,
        'error': 'Sessions not available in memory-only mode'
    }), 501

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get statistics"""
    return jsonify({
        'success': True,
        'stats': {
            'total_messages': len(chat_history),
            'user_messages': sum(1 for msg in chat_history if msg['role'] == 'user'),
            'assistant_messages': sum(1 for msg in chat_history if msg['role'] == 'assistant')
        }
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for container orchestration"""
    try:
        # Check any available provider API (simple model list)
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

        return jsonify({'status': 'healthy', 'api': provider, 'messages': len(chat_history)}), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 503
        
#newchat 
def create_new_chat():
    return "chat_1"

@app.route('/newChat', methods =['GET'])

def newChat():
    global chat_history
    chat_history = []
    chat_id = create_new_chat()
    return jsonify({
        "status":"success",
        "chat_id":chat_id
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
        
        # Limit text length (Groq supports max 10K characters)
        if len(text) > 10000:
            text = text[:10000]
        
        # Call Groq TTS API
        audio_content = groq_client.text_to_speech(
            text=text,
            model=model,
            voice=voice
        )
        
        # Return audio as WAV file
        from flask import Response
        return Response(
            audio_content,
            mimetype='audio/wav',
            headers={
                'Content-Disposition': 'inline; filename="speech.wav"'
            }
        )
        
    except Exception as e:
        error_msg = str(e)
        
        # Check for terms acceptance error
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


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
