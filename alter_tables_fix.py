import sys
import os
sys.path.append(os.path.abspath(r"E:\InfosysVirtual"))

from database_operations.db_connection import engine
from sqlalchemy import text

def alter_schema():
    queries = [
        "ALTER TABLE channels MODIFY subscribers BIGINT;",
        "ALTER TABLE channels MODIFY views BIGINT;",
        "ALTER TABLE channels MODIFY total_videos BIGINT;",
        "ALTER TABLE video_statistics MODIFY view_count BIGINT;",
        "ALTER TABLE video_statistics MODIFY like_count BIGINT;",
        "ALTER TABLE video_statistics MODIFY comment_count BIGINT;"
    ]
    
    with engine.begin() as conn:
        for q in queries:
            try:
                conn.execute(text(q))
                print(f"Executed: {q}")
            except Exception as e:
                print(f"Error on {q}: {e}")

if __name__ == "__main__":
    alter_schema()
    print("Schema alteration complete.")
