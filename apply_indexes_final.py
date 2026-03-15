import sys
import os
from sqlalchemy import text

# Configure path for module imports
sys.path.append(os.path.dirname(os.getcwd()))

from database_operations.db_connection import engine

def apply_indexes():
    queries = [
        "CREATE INDEX idx_vstats_vid ON video_statistics(video_id);",
        "CREATE INDEX idx_vstats_cap ON video_statistics(captured_at);",
        "CREATE INDEX idx_vids_chid ON videos(channel_id);"
    ]
    with engine.connect() as conn:
        for q in queries:
            try:
                print(f"Executing: {q}")
                conn.execute(text(q))
                conn.commit()
                print("Success!")
            except Exception as e:
                print(f"Error (likely already exists): {e}")

if __name__ == "__main__":
    apply_indexes()
