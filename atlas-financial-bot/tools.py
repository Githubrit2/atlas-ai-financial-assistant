# tools.py
import yfinance as yf
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import json

def format_number(val, suffix="", is_currency=False):
    """Safely format numeric values without throwing ValueError on None or strings."""
    if val is None or val == "N/A":
        return "N/A"
    try:
        num = float(val)
        if suffix == "%":
            return f"{num * 100:.2f}%" if abs(num) < 1 else f"{num:.2f}%"
        if is_currency:
            if abs(num) >= 1e12:
                return f"${num / 1e12:.2f} Trillion"
            elif abs(num) >= 1e9:
                return f"${num / 1e9:.2f} Billion"
            elif abs(num) >= 1e6:
                return f"${num / 1e6:.2f} Million"
            return f"${num:,.2f}"
        return f"{num:.2f}"
    except Exception:
        return str(val)

def get_financial_summary(symbol) -> str:
    """Fetch real-time financial metrics, revenue growth, profitability, and valuation for stock tickers."""
    try:
        # Handle list of symbols e.g. ["MSFT", "GOOGL"]
        if isinstance(symbol, list):
            results = [get_financial_summary(s) for s in symbol[:3]]
            return "\n\n".join(results)
            
        # Handle comma-separated string e.g. "MSFT, GOOGL"
        if isinstance(symbol, str) and "," in symbol:
            symbols = [s.strip() for s in symbol.split(",")]
            results = [get_financial_summary(s) for s in symbols[:3]]
            return "\n\n".join(results)

        clean_symbol = str(symbol).upper().strip()
        
        # Name aliases mapping
        ALIASES = {
            "MICROSOFT": "MSFT", "GOOGLE": "GOOGL", "ALPHABET": "GOOGL",
            "APPLE": "AAPL", "TESLA": "TSLA", "NVIDIA": "NVDA", "AMAZON": "AMZN"
        }
        if clean_symbol in ALIASES:
            clean_symbol = ALIASES[clean_symbol]

        ticker = yf.Ticker(clean_symbol)
        info = ticker.info or {}
        hist = ticker.history(period="5d")
        
        if hist is None or hist.empty or 'Close' not in hist:
            return f"Could not locate active market data for ticker '{clean_symbol}'."
            
        latest_close = hist['Close'].iloc[-1]
        prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else latest_close
        pct_change = ((latest_close - prev_close) / prev_close) * 100 if prev_close else 0
        
        mcap = format_number(info.get('marketCap'), is_currency=True)
        rev_growth = format_number(info.get('revenueGrowth'), suffix="%")
        profit_margin = format_number(info.get('profitMargins'), suffix="%")
        fwd_pe = format_number(info.get('forwardPE'))
        trail_pe = format_number(info.get('trailingPE'))
        roe = format_number(info.get('returnOnEquity'), suffix="%")
        
        company_name = info.get('shortName') or info.get('longName') or clean_symbol

        summary = (
            f"**{company_name} ({clean_symbol})**\n"
            f"• Current Price: ${latest_close:.2f} ({pct_change:+.2f}%)\n"
            f"• Market Cap: {mcap}\n"
            f"• Revenue Growth (YoY): {rev_growth}\n"
            f"• Profit Margin: {profit_margin}\n"
            f"• Valuation (Trailing P/E / Forward P/E): {trail_pe} / {fwd_pe}\n"
            f"• Return on Equity (ROE): {roe}\n"
            f"• Sector: {info.get('sector', 'N/A')}"
        )
        return summary
    except Exception as e:
        return f"Notice: Metrics for ticker '{symbol}' unavailable: {str(e)}"

def search_gmail_messages(user_tokens: dict, query: str) -> str:
    """Search user's integrated Gmail inbox for specific finance/company emails."""
    if not user_tokens:
        return "Gmail integration is not connected for this user yet."
    try:
        creds = Credentials.from_authorized_user_info(user_tokens)
        service = build('gmail', 'v1', credentials=creds)
        results = service.users().messages().list(userId='me', q=query, maxResults=3).execute()
        messages = results.get('messages', [])
        
        if not messages:
            return f"No recent emails found matching query: '{query}'"
            
        summaries = []
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
            snippet = msg_data.get('snippet', '')
            summaries.append(f"- Email snippet: {snippet}")
            
        return "\n".join(summaries)
    except Exception as e:
        return f"Error searching Gmail: {str(e)}"

def read_google_sheet(user_tokens: dict, spreadsheet_id: str, range_name: str) -> str:
    """Read context or numbers from a target Google Sheet / Model."""
    if not user_tokens:
        return "Google Workspace integration is not connected for this user yet."
    try:
        creds = Credentials.from_authorized_user_info(user_tokens)
        service = build('sheets', '4', credentials=creds)
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        rows = result.get('values', [])
        return f"Sheet Data extracted:\n{json.dumps(rows)}"
    except Exception as e:
        return f"Error reading sheet: {str(e)}"

def get_company_news(symbol: str) -> str:
    """Fetch real-time news headlines and catalyst events for a stock ticker."""
    try:
        clean_symbol = str(symbol).upper().strip()
        ALIASES = {"MICROSOFT": "MSFT", "GOOGLE": "GOOGL", "APPLE": "AAPL", "TESLA": "TSLA", "NVIDIA": "NVDA"}
        if clean_symbol in ALIASES:
            clean_symbol = ALIASES[clean_symbol]

        ticker = yf.Ticker(clean_symbol)
        news_items = ticker.news or []
        
        if not news_items:
            return f"No recent breaking news found for {clean_symbol}."
            
        headlines = []
        for item in news_items[:5]: # Top 5 headlines
            title = item.get("title") or item.get("content", {}).get("title", "")
            publisher = item.get("publisher") or item.get("content", {}).get("provider", {}).get("displayName", "Finance News")
            if title:
                headlines.append(f"• **[{publisher}]** {title}")
                
        return f"**Recent Breaking News & Catalysts for {clean_symbol}:**\n" + "\n".join(headlines)
    except Exception as e:
        return f"News lookup unavailable for {symbol}: {str(e)}"