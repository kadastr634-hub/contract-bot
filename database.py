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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS risk_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id INTEGER,
                doc_type TEXT,
                role TEXT,
                risk_title TEXT,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                user_id INTEGER DEFAULT NULL,
                used_count INTEGER DEFAULT 0,
                max_uses INTEGER DEFAULT 1,
                created_at TEXT,
                used_at TEXT DEFAULT NULL
            )
        """)
        # Добавляем колонки если их нет
        for col in ["agreed_at TEXT DEFAULT NULL"]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col}")
            except Exception:
                pass
        await db.commit()

        # Создаём промокоды при первом запуске
        await _init_promo_codes(db)


async def _init_promo_codes(db):
    codes = [
        ("OWNER2025", 999),
        ("PILOT001", 1),
        ("PILOT002", 1),
        ("PILOT003", 1),
        ("PILOT004", 1),
        ("PILOT005", 1),
        ("PILOT006", 1),
        ("PILOT007", 1),
        ("PILOT008", 1),
        ("PILOT009", 1),
        ("PILOT010", 1),
    ]
    for code, max_uses in codes:
        try:
            await db.execute(
                "INSERT OR IGNORE INTO promo_codes (code, max_uses, created_at) VALUES (?, ?, ?)",
                (code, max_uses, datetime.now().isoformat())
            )
        except Exception:
            pass
    await db.commit()


async def check_promo_code(code: str) -> bool:
    """Проверяет валидность промокода"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT used_count, max_uses FROM promo_codes WHERE code = ?",
            (code.upper(),)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return False
            used, max_uses = row
            return used < max_uses


async def use_promo_code(code: str, user_id: int):
    """Фиксирует использование промокода"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE promo_codes
               SET used_count = used_count + 1,
                   user_id = ?,
                   used_at = ?
               WHERE code = ?""",
            (user_id, datetime.now().isoformat(), code.upper())
        )
        await db.commit()


async def save_risk_stats(analysis_id: int, doc_type: str, role: str, risk_titles: list):
    """Сохраняет заголовки рисков для статистики"""
    async with aiosqlite.connect(DB_PATH) as db:
        for title in risk_titles:
            await db.execute(
                """INSERT INTO risk_stats (analysis_id, doc_type, role, risk_title, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (analysis_id, doc_type, role, title, datetime.now().isoformat())
            )
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


async def save_analysis(user_id, role, doc_type, doc_text, verdict, score,
                        free_result, pro_result=None):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO analyses
               (user_id, role, doc_type, doc_text, verdict, score, free_result,
                pro_result, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, role, doc_type, doc_text, verdict, score,
             json.dumps(free_result, ensure_ascii=False),
             json.dumps(pro_result, ensure_ascii=False) if pro_result else None,
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
