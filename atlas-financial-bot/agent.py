# agent.py
import json
import os
import re
import openai
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from models import UserProfile, ConversationHistory
from tools import get_financial_summary, search_gmail_messages, get_company_news, get_dcf_valuation
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Primary Text Client (Groq)
if GROQ_API_KEY and not GROQ_API_KEY.startswith("YOUR"):
    text_client = openai.OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1"
    )
    DEFAULT_TEXT_MODEL = "openai/gpt-oss-120b"
elif GEMINI_API_KEY:
    text_client = openai.OpenAI(
        api_key=GEMINI_API_KEY,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    )
    DEFAULT_TEXT_MODEL = "gemini-1.5-flash"
else:
    raise ValueError("Neither GROQ_API_KEY nor GEMINI_API_KEY found in .env file!")

# Dedicated Vision Client (Gemini 1.5 Flash)
vision_client = None
if GEMINI_API_KEY and not GEMINI_API_KEY.startswith("YOUR"):
    vision_client = openai.OpenAI(
        api_key=GEMINI_API_KEY,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    )

SYSTEM_PROMPT_TEMPLATE = """
You are "Atlas", an elite AI Financial Assistant operating inside Telegram.
Your primary objective is to build a personalized, high-value financial assistant experience for finance professionals.

CONVERSATIONAL ONBOARDING GUIDELINES:
1. Every interaction must feel welcoming, natural, and conversational. NEVER show rigid forms or mention commands/menus.
2. If onboarding is fresh or incomplete, gradually learn about the user across natural conversation turns:
   - What best describes their role? (Investor, Analyst, Founder, Student, Finance Professional, etc.)
   - Which companies, stocks, sectors, or markets do they actively follow?
   - What type of financial insights matter most to them? (Market news, earnings calls, SEC filings, analyst ratings, macro events, etc.)
   - When would they prefer to receive their daily morning/evening briefing?
3. Whenever the user shares any preference, invoke `update_user_profile` to save it to their persistent memory profile.

CURRENT USER PROFILE context:
- Role: {role}
- Watchlist: {watchlist}
- Topics/Sectors: {topics}
- Preferred Briefing Time: {briefing_time}
- Google Connected: {google_connected}

GENERAL RESEARCH GUIDELINES:
- When analyzing images, documents, or financial charts, provide concise financial insights.
- Speak concisely and professionally. NEVER output raw code or <function> tags in your final response.
"""

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_financial_summary",
            "description": "Fetch current stock price, fundamentals, and valuation metrics for one or more tickers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol or comma list e.g. AAPL or MSFT, GOOGL"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_company_news",
            "description": "Fetch real-time breaking market news, headlines, and catalyst events for a stock ticker.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol e.g. NVDA, TSLA"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_dcf_valuation",
            "description": "Estimate the intrinsic value per share of a stock using a discounted cash flow (DCF) model. Fetches free cash flow and shares outstanding automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol e.g. AAPL"},
                    "growth_rate": {"type": "number", "description": "Optional annual FCF growth as a decimal, e.g. 0.08 for 8%"},
                    "discount_rate": {"type": "number", "description": "Optional discount rate as a decimal, default 0.10"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_profile",
            "description": "Save or update user's role, watchlist, topics, or briefing preferences into long-term memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "description": "e.g. Investor, Analyst, Founder, Student"},
                    "add_to_watchlist": {"type": "array", "items": {"type": "string"}, "description": "Tickers e.g. ['TSLA', 'NVDA']"},
                    "topics": {"type": "array", "items": {"type": "string"}, "description": "Domains e.g. ['Technology', 'Healthcare']"},
                    "briefing_time": {"type": "string", "description": "e.g. '08:00 AM'"},
                    "onboarding_completed": {"type": "boolean"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_gmail_messages",
            "description": "Search user's integrated Gmail inbox for specific finance/company emails.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term e.g. 'Apple earnings'"}
                },
                "required": ["query"]
            }
        }
    }
]

def execute_tool_call(func_name: str, args: dict, user: UserProfile, db: Session) -> str:
    try:
        clean_func = func_name.strip().replace("function:", "").replace("function=", "").replace("function(", "").replace(")", "")
        print(f"🔧 Tool called: {func_name} {args}")
        
        if clean_func == "get_financial_summary":
            symbol = args.get("symbol") or args.get("ticker") or args.get("symbols")
            if not symbol or str(symbol).lower() in ["none", "null", "", "investment", "companies", "stocks"]:
                symbol = ["NVDA", "AAPL", "MSFT"]
            return get_financial_summary(symbol)
            
        elif clean_func == "get_company_news":
            symbol = args.get("symbol") or args.get("ticker") or "NVDA"
            return get_company_news(symbol)
        elif clean_func == "get_dcf_valuation":
            symbol = args.get("symbol") or args.get("ticker") or "AAPL"
            return get_dcf_valuation(
                symbol,
                growth_rate=args.get("growth_rate"),
                discount_rate=args.get("discount_rate") or 0.10,
            )
            
        elif clean_func == "update_user_profile":
            if "role" in args: user.role = args["role"]
            if "add_to_watchlist" in args:
                curr = set(user.watchlist or [])
                curr.update(args["add_to_watchlist"])
                user.watchlist = list(curr)
            if "topics" in args:
                curr_topics = set(user.topics_of_interest or [])
                curr_topics.update(args["topics"])
                user.topics_of_interest = list(curr_topics)
            if "briefing_time" in args: user.briefing_time = args["briefing_time"]
            if "onboarding_completed" in args: user.onboarding_completed = args["onboarding_completed"]
            db.commit()
            return "User profile updated successfully in memory."
            
        elif clean_func == "search_gmail_messages":
            return search_gmail_messages(user.google_tokens, args.get("query", ""))
            
        return "Tool execution complete."
    except Exception as e:
        return f"Notice: Tool {clean_func} encountered an issue: {str(e)}"

def run_agent(db: Session, telegram_id: int, user_message: str, image_url: str = None, base_url: str = "") -> str:
    user = db.query(UserProfile).filter(UserProfile.telegram_id == telegram_id).first()
    if not user:
        user = UserProfile(telegram_id=telegram_id)
        db.add(user)
        db.commit()
        db.refresh(user)

    google_auth_link = f"{base_url}/auth/google/{telegram_id}"
    google_connected = "Yes" if user.google_tokens else "No"

    clean_msg = (user_message or "").strip().lower()
    RESET_TRIGGERS = ["hi", "hello", "hey", "/start", "start", "restart"]

    # Select Vision Model (gemini-1.5-flash) vs Text Model (llama-3.3-70b)
    if image_url and vision_client:
        active_client = vision_client
        active_model = "gemini-1.5-flash"
    else:
        active_client = text_client
        active_model = DEFAULT_TEXT_MODEL

    if clean_msg in RESET_TRIGGERS:
        db.query(ConversationHistory).filter(ConversationHistory.telegram_id == telegram_id).delete()
        user.role = "Unknown"
        user.watchlist = []
        user.topics_of_interest = []
        user.briefing_time = "08:00 AM"
        user.onboarding_completed = False
        db.commit()

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            role="Unknown",
            watchlist="[]",
            topics="[]",
            briefing_time="08:00 AM",
            google_auth_link=google_auth_link,
            google_connected=google_connected
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
    else:
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            role=user.role,
            watchlist=json.dumps(user.watchlist or []),
            topics=json.dumps(user.topics_of_interest or []),
            briefing_time=user.briefing_time or "08:00 AM",
            google_auth_link=google_auth_link,
            google_connected=google_connected
        )

        history = db.query(ConversationHistory).filter(
            ConversationHistory.telegram_id == telegram_id
        ).order_by(ConversationHistory.timestamp.desc()).limit(8).all()
        
        messages = [{"role": "system", "content": system_prompt}]
        for msg in reversed(history):
            messages.append({"role": msg.role, "content": msg.content})

        if image_url:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": user_message or "Analyze this financial chart or document in detail."},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            })
        else:
            messages.append({"role": "user", "content": user_message})

    db.add(ConversationHistory(telegram_id=telegram_id, role="user", content=user_message or "[Image Received]"))
    db.commit()

    kwargs = {"model": active_model, "messages": messages}
    if not image_url:
        kwargs["tools"] = AGENT_TOOLS
        kwargs["tool_choice"] = "auto"

    try:
        response = active_client.chat.completions.create(**kwargs)
    except Exception as e:
        print(f"Notice: Vision completion error ({e}). Retrying with primary text client...")
        response = text_client.chat.completions.create(
            model=DEFAULT_TEXT_MODEL,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message or "Analyze this document."}]
        )

    response_msg = response.choices[0].message
    tool_results = []

    if response_msg.tool_calls:
        messages.append(response_msg)
        for tool_call in response_msg.tool_calls:
            func_name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except:
                args = {}
            res = execute_tool_call(func_name, args, user, db)
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": str(res)})

        try:
            final_response = active_client.chat.completions.create(model=active_model, messages=messages)
            final_text = final_response.choices[0].message.content
        except Exception:
            final_response = active_client.chat.completions.create(
                model=active_model,
                messages=[m for m in messages if m.get("role") != "tool"]
            )
            final_text = final_response.choices[0].message.content

    else:
        content = response_msg.content or ""
        matches = re.findall(r'<function[\(:=\s]*([a_zA_Z0-9_]+)[\)\s>]*?(.*?)(?:</function>|$)', content, re.DOTALL)
        
        if matches:
            for func_name, args_raw in matches:
                clean_func = func_name.strip()
                json_match = re.search(r'\{.*\}', args_raw, re.DOTALL)
                if json_match:
                    try:
                        args = json.loads(json_match.group(0))
                    except:
                        args = {}
                else:
                    args = {}
                    
                res = execute_tool_call(clean_func, args, user, db)
                tool_results.append(f"Tool {clean_func} output: {res}")

            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": f"System Tool Execution Results:\n{chr(10).join(tool_results)}\n\nNow respond clearly to the user without any function tags."})
            
            final_response = active_client.chat.completions.create(model=active_model, messages=messages)
            final_text = final_response.choices[0].message.content
        else:
            final_text = content

    cleaned_text = re.sub(r'<function.*?</function>', '', final_text, flags=re.DOTALL)
    cleaned_text = re.sub(r'<function.*?>', '', cleaned_text, flags=re.DOTALL).strip()

    # Safety Guard: Ensure response is never empty
    if not cleaned_text:
        cleaned_text = "I received your image and analyzed it. It appears to be a financial document or chart. Could you tell me what specific metrics or insights you'd like me to highlight from it?"

    db.add(ConversationHistory(telegram_id=telegram_id, role="assistant", content=cleaned_text))
    db.commit()

    return cleaned_text