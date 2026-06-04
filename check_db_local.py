
from database_operations.db_connection import engine
from sqlalchemy import text
import pandas as pd
import os

def check_db():
    query = "SELECT channel_id, channel_name, thumbnail_url, subscribers FROM channels LIMIT 10"
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
            print("--- DATABASE CHECK ---")
            print(df)
            df.to_csv("db_check_info.csv", index=False)
            print(f"Results saved to {os.path.abspath('db_check_info.csv')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_db()
