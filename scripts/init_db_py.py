import sqlite3
import os

db_path = 'db/betting.db'
schema_path = 'db/schema.sql'

if not os.path.exists('db'):
    os.makedirs('db')

conn = sqlite3.connect(db_path)
with open(schema_path, 'r') as f:
    schema = f.read()
    conn.executescript(schema)
conn.commit()
conn.close()
print("Database initialized successfully.")
