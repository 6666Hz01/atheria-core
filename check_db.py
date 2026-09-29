import sqlite3
import os

db_path = os.path.expanduser("~/atheria_live/atheria.db")

try:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cursor = con.cursor()
    print(f"--- بررسی ساختار دیتابیس: {db_path} ---")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    for table in tables:
        table_name = table[0]
        print(f"\nجدول: {table_name}")
        cursor.execute(f"PRAGMA table_info('{table_name}');")
        columns = cursor.fetchall()
        for col in columns:
            print(f"  ستون: {col[1]} ({col[2]})")
    con.close()
except Exception as e:
    print(f"خطا در خواندن دیتابیس: {e}")
