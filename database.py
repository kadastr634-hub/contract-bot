import aiosqlite
import json
from datetime import datetime

DB_PATH = "bot.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                role TEXT DEFAULT NULL,
                created_at TEXT,
                agreed_at TEXT DEFAULT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT,
                doc_type TEXT,
                doc_text TEXT,
                verdict TEXT,
                score INTEGER,
                free_result TEXT,
                pro_result TEXT DEFAULT NULL,
                is_paid INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                analysis_id INTEGER,
                payment_id TEXT UNIQUE,
                amount INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                paid_at TEXT DEFAULT NULL
            )
        """)
        await db.commit()


async def get_or_create_user(user_id: int, username: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, created_at) VALUES (?, ?, ?)",
            (user_id, username or "", datetime.now().isoformat())
        )
        await db.commit()


async def set_user_role(user_id: int, role: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET role = ? WHERE user_id = ?",
            (role, user_id)
        )
        await db.commit()


async def get_user_role(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT role FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def save_analysis(user_id, role, doc_type, doc_text, verdict, score, free_result):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO analyses
               (user_id, role, doc_type, doc_text, verdict, score, free_result, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, role, doc_type, doc_text, verdict, score,
             json.dumps(free_result, ensure_ascii=False),
             datetime.now().isoformat())
        )
        await db.commit()
        return cur.lastrowid


async def save_pro_result(analysis_id: int, pro_result: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE analyses SET pro_result = ?, is_paid = 1 WHERE id = ?",
            (json.dumps(pro_result, ensure_ascii=False), analysis_id)
        )
        await db.commit()


async def get_analysis(analysis_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM analyses WHERE id = ?", (analysis_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))


async def create_payment_record(user_id, analysis_id, payment_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO payments
               (user_id, analysis_id, payment_id, amount, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, analysis_id, payment_id, amount, datetime.now().isoformat())
        )
        await db.commit()


async def update_payment_status(payment_id: str, status: str):
    paid_at = datetime.now().isoformat() if status == "succeeded" else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE payments SET status = ?, paid_at = ? WHERE payment_id = ?",
            (status, paid_at, payment_id)
        )
        await db.commit()


async def get_payment_by_id(payment_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM payments WHERE payment_id = ?", (payment_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))


async def get_user_agreement(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT agreed_at FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return False
            return row[0] is not None


async def save_user_agreement(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET agreed_at = ? WHERE user_id = ?",
            (datetime.now().isoformat(), user_id)
        )
        await db.commit()