from dotenv import load_dotenv
load_dotenv(".env.local")

import psycopg2
import os

conn = psycopg2.connect(
    host=os.environ["POSTGRES_HOST"],
    port=os.environ["POSTGRES_PORT"],
    dbname=os.environ["INVESTIGATOR_DB"],
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
)
cur = conn.cursor()

# Delete all agent-generated incidents (keep only SEED-* records)
cur.execute("DELETE FROM incidents WHERE incident_id NOT LIKE 'SEED-%'")
print(f"Deleted {cur.rowcount} agent-generated incidents")

conn.commit()
cur.close()
conn.close()