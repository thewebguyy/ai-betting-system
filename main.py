from fastapi import FastAPI
from automation.state_manager import StateManager
import uvicorn
import os

app = FastAPI(title="AI Betting Local Dashboard")
db = StateManager()

@app.get("/")
def home():
    accounts = db.get_all_accounts()
    return {
        "status": "ONLINE",
        "mode": os.environ.get("MODE", "DEVELOPMENT"),
        "accounts": accounts
    }

@app.get("/stats")
def stats():
    import sqlite3
    with sqlite3.connect(db.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM signals")
        total_signals = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM bets")
        total_bets = cursor.fetchone()[0]
        
    return {
        "total_signals": total_signals,
        "total_bets": total_bets
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="127.0.0.1", port=port)
