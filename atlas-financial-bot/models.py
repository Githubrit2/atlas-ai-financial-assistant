# models.py
from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()

class UserProfile(Base):
    __tablename__ = "user_profiles"

    telegram_id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    
    # Profile & Onboarding Context
    role = Column(String, default="Unknown")  # e.g., Analyst, Investor, Founder
    watchlist = Column(JSON, default=[])      # e.g., ["AAPL", "NVDA", "TSLA"]
    topics_of_interest = Column(JSON, default=[]) # e.g., ["Semiconductors", "M&A"]
    briefing_time = Column(String, default="08:00") # Format "HH:MM" (UTC)
    onboarding_completed = Column(Boolean, default=False)
    
    # Auth & Tokens
    google_tokens = Column(JSON, nullable=True) # Gmail/Sheets Access & Refresh Tokens
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ConversationHistory(Base):
    __tablename__ = "conversation_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, index=True)
    role = Column(String)  # 'user', 'assistant', 'system'
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

class BriefingLog(Base):
    __tablename__ = "briefing_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, index=True)
    briefing_type = Column(String) # Morning, Evening, Breaking Alert
    content = Column(Text)
    sent_at = Column(DateTime, default=datetime.utcnow)

# DB Helper Setup
DATABASE_URL = "sqlite:///./atlas_financial.db" # Swap with PostgreSQL for production
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)