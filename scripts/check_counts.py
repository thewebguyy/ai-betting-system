import sqlite3
conn = sqlite3.connect('db/betting.db')
cursor = conn.cursor()
print(f'Matches: {cursor.execute("SELECT count(*) FROM matches").fetchone()[0]}')
print(f'Teams: {cursor.execute("SELECT count(*) FROM teams").fetchone()[0]}')
print(f'Stats: {cursor.execute("SELECT count(*) FROM team_match_stats").fetchone()[0]}')
conn.close()
