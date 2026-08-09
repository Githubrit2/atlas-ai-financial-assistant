# briefings.py
import requests
import os
from sqlalchemy.orm import Session
from models import UserProfile, BriefingLog, SessionLocal
from tools import get_financial_summary
import openai

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def send_telegram_message(telegram_id: int, text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": telegram_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

def generate_and_dispatch_daily_briefings():
    """Triggered by cron/scheduler. Inspects profiles and sends customized daily updates."""
    db: Session = SessionLocal()
    try:
        users = db.query(UserProfile).filter(UserProfile.watchlist != []).all()
        for user in users:
            # Aggregate updates across user's watchlist
            data_points = []
            for symbol in user.watchlist[:3]:  # Top 3 assets for conciseness
                summary = get_financial_summary(symbol)
                data_points.append(summary)

            prompt = f"""
            You are drafting a daily concise morning briefing for a user whose role is '{user.role}'.
            
            Watchlist Market Data:
            {chr(10).join(data_points)}
            
            Instructions:
            - Provide a concise summary on what matters most today for their watchlist.
            - Focus on 'WHY' it matters.
            - Maximum 3 bullet points total. Keep it brief.
            """

            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}]
            )

            briefing_text = "🌅 **Morning Intelligence Briefing**\n\n" + response.choices[0].message.content
            
            # Send proactive message to user
            send_telegram_message(user.telegram_id, briefing_text)

            # Log briefing
            db.add(BriefingLog(telegram_id=user.telegram_id, briefing_type="Morning", content=briefing_text))
            db.commit()
    finally:
        db.close()