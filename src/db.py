import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Table: posted_videos
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS posted_videos (
                    tiktok_id TEXT PRIMARY KEY,
                    youtube_id TEXT,
                    uploaded_at TEXT,
                    status TEXT,
                    format TEXT,
                    title TEXT
                )
            """)
            # Table: runs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    slot INTEGER,
                    status TEXT,
                    message TEXT
                )
            """)
            # Table: pending_retry
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_retry (
                    tiktok_id TEXT PRIMARY KEY,
                    retry_count INTEGER DEFAULT 0,
                    next_retry_date TEXT,
                    status TEXT
                )
            """)
            conn.commit()

    def is_video_posted(self, tiktok_id: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM posted_videos WHERE tiktok_id = ?", (tiktok_id,))
            return cursor.fetchone() is not None

    def record_posted_video(self, tiktok_id: str, youtube_id: str, status: str = "uploaded", video_format: str = "short", title: str = ""):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO posted_videos (tiktok_id, youtube_id, uploaded_at, status, format, title)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (tiktok_id, youtube_id, datetime.utcnow().isoformat(), status, video_format, title))
            conn.commit()

    def slot_already_ran_today(self, slot: int) -> bool:
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM runs 
                WHERE slot = ? AND status = 'success' AND timestamp LIKE ?
            """, (slot, f"{today_str}%"))
            return cursor.fetchone() is not None

    def record_run(self, slot: int, status: str, message: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO runs (timestamp, slot, status, message)
                VALUES (?, ?, ?, ?)
            """, (datetime.utcnow().isoformat(), slot, status, message))
            conn.commit()

    def get_all_posted_ids(self) -> List[str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT tiktok_id FROM posted_videos")
            return [row["tiktok_id"] for row in cursor.fetchall()]
