 -- =============================================================================
-- AI Betting Intelligence System — SQLite Schema
-- Run: sqlite3 db/betting.db < db/schema.sql
-- =============================================================================

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ── Leagues / Competitions ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS recommendations (
    id              INTEGER PRIMARY KEY AUTO_INCREMENT,
    match_id        INTEGER NOT NULL,
    value_bet_id    INTEGER NOT NULL,
    category        TEXT NOT NULL,
    score           REAL NOT NULL,
    reason          TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES matches(id),
    FOREIGN KEY (value_bet_id) REFERENCES value_bets(id)
);

CREATE TABLE IF NOT EXISTS leagues (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    api_id      TEXT UNIQUE,
    name        TEXT NOT NULL,
    country     TEXT,
    sport       TEXT DEFAULT 'football',
    season      TEXT,
    is_active   INTEGER DEFAULT 1,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ── Teams ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS teams (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    api_id      TEXT UNIQUE,
    name        TEXT NOT NULL,
    short_name  TEXT,
    country     TEXT,
    league_id   INTEGER REFERENCES leagues(id),
    elo_rating  REAL DEFAULT 1500.0,
    attack_strength REAL DEFAULT 1.0,
    defence_strength REAL DEFAULT 1.0,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);


-- ── Matches ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS matches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    api_id          TEXT UNIQUE,
    league_id       INTEGER REFERENCES leagues(id),
    home_team_id    INTEGER REFERENCES teams(id),
    away_team_id    INTEGER REFERENCES teams(id),
    match_date      DATETIME NOT NULL,
    status          TEXT DEFAULT 'scheduled',   -- scheduled|live|finished|cancelled
    home_score      INTEGER,
    away_score      INTEGER,
    -- Pre-match context
    home_form       TEXT,   -- JSON array last 5: W/D/L
    away_form       TEXT,
    home_injuries   TEXT,   -- JSON array of injured players
    away_injuries   TEXT,
    weather         TEXT,
    venue           TEXT,
    -- Model outputs
    model_home_prob REAL,
    model_draw_prob REAL,
    model_away_prob REAL,
    referee_avg_goals REAL,
    referee_avg_cards REAL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ── Odds History ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS odds_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER REFERENCES matches(id) ON DELETE CASCADE,
    bookmaker       TEXT NOT NULL,
    market          TEXT DEFAULT '1X2',  -- 1X2|BTTS|O/U|DNB|AH
    home_odds       REAL,
    draw_odds       REAL,
    away_odds       REAL,
    over_odds       REAL,
    under_odds      REAL,
    line            REAL,               -- for O/U or AH lines
    fetched_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_odds_match ON odds_history(match_id, bookmaker, fetched_at);

-- ── Value Bets ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS value_bets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER REFERENCES matches(id),
    bookmaker       TEXT NOT NULL,
    market          TEXT NOT NULL,
    selection       TEXT NOT NULL,      -- Home|Draw|Away|Over|Under
    decimal_odds    REAL NOT NULL,
    implied_prob    REAL NOT NULL,      -- 1/odds
    true_implied    REAL NOT NULL,      -- vig-normalised
    model_prob      REAL NOT NULL,
    edge            REAL NOT NULL,      -- model_prob - true_implied
    ev              REAL NOT NULL,      -- expected value
    kelly_fraction  REAL NOT NULL,
    suggested_stake REAL,
    status          TEXT DEFAULT 'pending',  -- pending|placed|won|lost|void
    detected_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_vb_match ON value_bets(match_id);
CREATE INDEX IF NOT EXISTS idx_vb_ev ON value_bets(ev DESC);

-- ── Placed Bets (Bankroll Tracker) ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    value_bet_id    INTEGER REFERENCES value_bets(id),
    match_id        INTEGER REFERENCES matches(id),
    bookmaker       TEXT NOT NULL,
    market          TEXT NOT NULL,
    selection       TEXT NOT NULL,
    decimal_odds    REAL NOT NULL,
    stake           REAL NOT NULL,
    potential_payout REAL NOT NULL,
    actual_payout   REAL DEFAULT 0,
    result          TEXT DEFAULT 'pending',  -- pending|won|lost|void|push
    placed_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    settled_at      DATETIME,
    notes           TEXT,
    closing_odds    REAL,
    clv             REAL
);


-- ── Bankroll Snapshots ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bankroll (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    balance         REAL NOT NULL,
    note            TEXT,
    snapshot_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ── Analytics Snapshots ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analytics_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    period_start    DATE,
    period_end      DATE,
    total_bets      INTEGER DEFAULT 0,
    won             INTEGER DEFAULT 0,
    lost            INTEGER DEFAULT 0,
    void            INTEGER DEFAULT 0,
    total_staked    REAL DEFAULT 0,
    total_profit    REAL DEFAULT 0,
    roi             REAL DEFAULT 0,
    yield_pct       REAL DEFAULT 0,
    hit_rate        REAL DEFAULT 0,
    avg_clv         REAL DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ── AI Prompt Cache ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_cache (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_key       TEXT UNIQUE NOT NULL,
    provider        TEXT NOT NULL,
    prompt_hash     TEXT NOT NULL,
    response        TEXT NOT NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at      DATETIME
);

-- ── Reports ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type     TEXT NOT NULL,  -- match|daily|weekly|performance
    title           TEXT NOT NULL,
    file_path       TEXT,
    content_md      TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ── Team Match Stats (xG Tracker) ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS team_match_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER REFERENCES matches(id) ON DELETE CASCADE,
    team_id         INTEGER REFERENCES teams(id) ON DELETE CASCADE,
    xg_for          REAL DEFAULT 0,
    xg_against      REAL DEFAULT 0,
    goals_for       INTEGER DEFAULT 0,
    goals_against   INTEGER DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ── System Configuration ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_config (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ── Seed initial bankroll snapshot ───────────────────────────────────────────
INSERT OR IGNORE INTO bankroll (balance, note)
VALUES (1000.0, 'Initial bankroll');

-- ── Seed default system config ─────────────────────────────────────────────
INSERT OR IGNORE INTO system_config (key, value) VALUES ('betting_paused', 'False');
INSERT OR IGNORE INTO system_config (key, value) VALUES ('kelly_fraction_multiplier', '1.0');

