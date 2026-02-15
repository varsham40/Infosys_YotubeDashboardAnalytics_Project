from database_operations.db_connection import init_db, SessionLocal

print("Testing database connection...")

init_db()

session = SessionLocal()

print("✅ SUCCESS — Connected to MySQL!")

session.close()
