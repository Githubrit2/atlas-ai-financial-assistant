# main.py
import os
import io
import base64
from dotenv import load_dotenv
from fastapi import FastAPI, Request, BackgroundTasks, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import requests
import openai

# Load environment variables
load_dotenv()

from models import init_db, SessionLocal, UserProfile
from agent import run_agent
from briefings import generate_and_dispatch_daily_briefings

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "mock_client_id")

groq_client = None
if GROQ_API_KEY and not GROQ_API_KEY.startswith("YOUR"):
    groq_client = openai.OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1"
    )

app = FastAPI(title="Atlas Financial Assistant Engine")
@app.get("/")
def home():
    return {"status": "online", "message": "Atlas AI Financial Assistant Engine is Live 24/7!"}
@app.on_event("startup")
def startup():
    init_db()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def download_telegram_file(file_id: str) -> bytes:
    file_info = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}").json()
    file_path = file_info['result']['file_path']
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    response = requests.get(file_url)
    return response.content

# --- GOOGLE OAUTH INTEGRATION ENDPOINTS ---

@app.get("/auth/google/{telegram_id}")
def auth_google(telegram_id: int, request: Request):
    redirect_uri = f"{request.base_url}auth/google/callback"
    scopes = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/spreadsheets.readonly"
    ]
    
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={GOOGLE_CLIENT_ID}&"
        f"response_type=code&"
        f"scope={'%20'.join(scopes)}&"
        f"redirect_uri={redirect_uri}&"
        f"access_type=offline&"
        f"state={telegram_id}"
    )
    
    return HTMLResponse(content=f"""
    <html>
        <body style="font-family: Arial; text-align: center; padding-top: 50px;">
            <h2>Atlas Google Workspace Integration</h2>
            <p>Click below to connect Gmail & Google Sheets securely:</p>
            <a href="{auth_url}" style="background-color: #4285F4; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; font-weight: bold;">Connect Google Workspace</a>
        </body>
    </html>
    """)

@app.get("/auth/google/callback")
def google_callback(code: str = None, state: str = None, db: Session = Depends(get_db)):
    if state:
        telegram_id = int(state)
        user = db.query(UserProfile).filter(UserProfile.telegram_id == telegram_id).first()
        if user:
            user.google_tokens = {"status": "connected", "code": code}
            db.commit()
            
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": telegram_id, 
                    "text": "✅ **Google Workspace Connected!** I can now read your Google Sheets models and search financial emails in Gmail upon request."
                }
            )
            
    return HTMLResponse(content="<h3>Google Workspace Connected Successfully! You can close this tab and return to Telegram.</h3>")

# --- TELEGRAM WEBHOOK HANDLER ---

@app.post("/telegram-webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    data = await request.json()
    
    if "message" not in data:
        return {"status": "ok"}

    message = data["message"]
    chat_id = message["chat"]["id"]
    
    text_content = message.get("text", "")
    image_url = None

    print(f"\n📩 Incoming Message from Chat {chat_id}: {text_content}")

    # Voice Handling
    if "voice" in message and groq_client:
        try:
            file_id = message["voice"]["file_id"]
            audio_bytes = download_telegram_file(file_id)
            
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "voice.ogg"
            
            transcript = groq_client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio_file
            )
            text_content = transcript.text
            print(f"🎙️ Voice Transcribed: {text_content}")
        except Exception as e:
            print(f"❌ Error transcribing voice: {e}")

    # Photo Handling with Base64 Encoding
    if "photo" in message:
        try:
            file_id = message["photo"][-1]["file_id"]
            image_bytes = download_telegram_file(file_id)
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            image_url = f"data:image/jpeg;base64,{base64_image}"
            text_content = message.get("caption", "Analyze this financial image or document.")
            print("🖼️ Photo received and Base64 encoded successfully!")
        except Exception as e:
            print(f"❌ Error downloading image: {e}")

    # Process through Agent Orchestrator
    try:
        base_url = str(request.base_url).rstrip("/")
        assistant_reply = run_agent(db, chat_id, text_content, image_url, base_url)
        print(f"🤖 Assistant Reply: {assistant_reply[:120]}...")
    except Exception as e:
        print(f"❌ Agent Error: {e}")
        assistant_reply = "I apologize, I ran into an issue processing that query. Could you try asking again?"

    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": assistant_reply}
    )

    return {"status": "ok"}

@app.post("/trigger-briefing")
def trigger_briefing(background_tasks: BackgroundTasks):
    background_tasks.add_task(generate_and_dispatch_daily_briefings)
    return {"status": "Briefing job dispatched."}