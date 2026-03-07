# AI Betting Intelligence System 🎯

A fully autonomous, self-hosted, personal betting intelligence platform. It tracks bankroll, scrapes live odds, calculates expected value (EV) and Kelly criteria margins using machine learning and Poisson models, and orchestrates reasoning with free-tier AI APIs.

> **Disclaimer:** This software is for **personal, educational use only**. It does not place bets automatically. Always check local laws and bet responsibly. The developer assumes no liability.

---

## Features 🚀
- **Automated Odds Scraping:** The Odds API (primary) + Playwright Headless fallback (SportyBet).
- **ML Probability Engine:** Scikit-Learn Logistic Regression + Dixon-Coles Poisson + ELO with Monte Carlo simulations.
- **AI Intelligence Layer:** Anthropic Claude (strategy), Google Gemini (data extraction), DeepSeek (sentiment).
- **Automated Value Alerts:** Identifies positive EV and sends Telegram alerts.
- **Personal Dashboard:** React JS, Glassmorphism UI, real-time WebSocket alerts, Chart.js ROI tracking.
- **Reporting:** Daily PDF/Markdown performance reports.

---

## 1. Quickstart (Docker — Recommended) 🐳

The easiest way to run the entire backend + Redis cache.

1. **Clone the repo** into `ai-betting-system`.
2. **Set up `.env`**:
   Copy the example and fill in your keys (API-Football, The Odds API, Gemini, Telegram etc.):
   ```bash
   cp .env.example .env
   # Edit .env with your favorite editor
   ```
3. **Start the Backend Stack**:
   ```bash
   docker-compose up -d --build
   ```
   The FastAPI backend will now run on `http://localhost:8000` and it will automatically apply migrations.

4. **Start the Dashboard**:
   You need Node.js installed locally.
   ```bash
   cd dashboard
   npm install
   cp .env.example .env
   npm start
   ```
   The dashboard runs on `http://localhost:3000`. Log in with username: `admin`, password: `changeme` (or whatever you set in `.env`).

---

## 2. Local Development (No Docker) 💻

If you prefer running everything natively:

### Backend
1. **Python version**: Python 3.10 or 3.11 recommended.
2. **Install deps**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   playwright install chromium --with-deps
   ```
3. **Set up SQLite DB**:
   ```bash
   python -m backend.db_init
   ```
4. **Run Server**:
   ```bash
   uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
   ```

### Frontend
```bash
cd dashboard
npm install
npm start
```

---

## 3. Usage & System Workflows ⚙️

- **06:00 UTC**: The backend APScheduler automatically fetches new fixtures from `API-Football`, triggers the `odds_scraper.py`, computes models, and saves value bets.
- **Hourly**: Line movement checker runs. If odds shift > 10%, a Telegram alert is sent.
- **23:00 UTC**: Daily PDF report is generated containing your day's ROI, hit rate, and new EV opportunities.

### Manual Actions via Dashboard:
- **Scan Value Bets**: Click *"Scan"* on the dashboard to force an immediate odds fetch and model re-evaluation.
- **Bankroll**: Log your daily balance. The Kelly Criterion stake suggestions will automatically adjust.
- **Bet Tracker**: Manually input your placed bets so the analytics engine can calculate your real-world ROI and Yield.

---

## 4. API Documentation 📖
When the backend is running, visit:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

---

## 5. Security & Deployment 🔐
- **Auth**: This is a personal tool. It uses a single hardcoded Admin JWT login (from `.env`). Do not expose the backend publicly without changing the default password and enabling HTTPS.
- **Vercel / Render**:
  - Frontend can be built with `npm run build` and published to Vercel/Netlify.
  - Backend can be deployed to a VPS (DigitalOcean, AWS EC2) using Docker. Change `DATABASE_URL` to a PostgreSQL instance for production.

---

## Technical Stack
- **Backend**: Python, FastAPI, SQLAlchemy (Async), APScheduler, Playwright, Scikit-Learn.
- **Frontend**: React, React Router, Chart.js, Axios, Socket.IO.
- **AI**: LangChain (Gemini, Claude, DeepSeek).
- **DB/Cache**: SQLite + Redis.
