import sqlite3
from contextlib import closing
import logging
import time
import os

logger = logging.getLogger(__name__)

DB = 'bot_data.db'


def init_db():
    """Ініціалізує базу даних з таблицями користувачів і платежів."""
    try:
        with closing(sqlite3.connect(DB)) as conn:
            c = conn.cursor()
            
            # Перевірити чи існує стара таблиця з сигналами
            c.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in c.fetchall()]
            
            # Якщо старої таблиці немає — створити нову
            if not columns:
                c.execute('''CREATE TABLE IF NOT EXISTS users (
                    chat_id INTEGER PRIMARY KEY,
                    paid_plan TEXT,
                    plan_expires INTEGER,
                    signals_daily INTEGER,
                    signals_used_today INTEGER,
                    last_reset INTEGER
                )''')
            # Якщо таблиця має стару схему — мігрувати
            elif 'signals_daily' not in columns:
                logger.info("🔄 Мігрую БД на нову схему...")
                # Переймено вчення: видалити таблицю та пересоздать
                c.execute('DROP TABLE IF EXISTS users_old')
                c.execute('ALTER TABLE users RENAME TO users_old')
                
                c.execute('''CREATE TABLE users (
                    chat_id INTEGER PRIMARY KEY,
                    paid_plan TEXT,
                    plan_expires INTEGER,
                    signals_daily INTEGER,
                    signals_used_today INTEGER,
                    last_reset INTEGER
                )''')
                
                # Скопіювати дані з старої таблиці
                c.execute('''INSERT INTO users (chat_id, paid_plan, plan_expires, signals_daily, signals_used_today, last_reset)
                    SELECT chat_id, paid_plan, plan_expires, COALESCE(signals_left, 0), 0, ? FROM users_old''',
                    (int(time.time()),))
                
                c.execute('DROP TABLE users_old')
                logger.info("✅ Міграція завершена")
            
            c.execute('''CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                plan TEXT,
                amount REAL,
                crypto TEXT,
                payment_code TEXT UNIQUE,
                status TEXT,
                created_at INTEGER,
                screenshot_url TEXT,
                location TEXT
            )''')
            conn.commit()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ DB init error: {e}")
        raise


def set_plan(chat_id, plan, expires_ts=None, signals_daily=None):
    """Встановлює план та денну кількість сигналів"""
    try:
        with closing(sqlite3.connect(DB)) as conn:
            c = conn.cursor()
            c.execute('''REPLACE INTO users 
                (chat_id, paid_plan, plan_expires, signals_daily, signals_used_today, last_reset) 
                VALUES (?, ?, ?, ?, ?, ?)''',
                (chat_id, plan, expires_ts, signals_daily, 0, int(time.time())))
            conn.commit()
        logger.info(f"✅ Plan set: user={chat_id}, plan={plan}, daily_signals={signals_daily}")
    except Exception as e:
        logger.error(f"❌ Purchase plan error: {e}")
        raise


def decrement_signal(chat_id, amount: int = 1):
    """Віднімає сигнали витрачені сьогодні"""
    try:
        with closing(sqlite3.connect(DB)) as conn:
            c = conn.cursor()
            c.execute('''SELECT signals_daily, signals_used_today FROM users WHERE chat_id=?''', (chat_id,))
            row = c.fetchone()
            if not row:
                raise ValueError("User not found")
            
            daily = row[0] or 0
            used = (row[1] or 0) + amount
            
            c.execute('''UPDATE users SET signals_used_today=? WHERE chat_id=?''', (used, chat_id))
            conn.commit()
        
        logger.info(f"✅ Signal used: user={chat_id}, used={used}/{daily}")
        return used
    except Exception as e:
        logger.error(f"❌ Decrement error: {e}")
        raise


def reset_daily_signals():
    """Скидає щодобові сигнали о 8:00 UTC"""
    try:
        current_time = int(time.time())
        with closing(sqlite3.connect(DB)) as conn:
            c = conn.cursor()
            c.execute('''UPDATE users SET signals_used_today=0, last_reset=? WHERE signals_daily > 0''', 
                (current_time,))
            conn.commit()
        logger.info(f"✅ Daily signals reset for all users")
    except Exception as e:
        logger.error(f"❌ Reset error: {e}")
        raise


def get_user(chat_id):
    """Отримує дані користувача з бази даних за chat_id."""
    try:
        with closing(sqlite3.connect(DB)) as conn:
            c = conn.cursor()
            c.execute('''SELECT chat_id, paid_plan, plan_expires, signals_daily, signals_used_today, last_reset 
                FROM users WHERE chat_id=?''', (chat_id,))
            row = c.fetchone()
            if not row:
                return None
            
            return dict(
                chat_id=row[0],
                paid_plan=row[1],
                plan_expires=row[2],
                signals_daily=row[3] or 0,
                signals_used_today=row[4] or 0,
                last_reset=row[5] or 0
            )
    except Exception as e:
        logger.error(f"❌ Get user error: {e}")
        return None


def get_signals_available(chat_id):
    """Перевіряє скільки сигналів доступно сьогодні"""
    u = get_user(chat_id)
    if not u:
        return 0, 0
    daily = u.get('signals_daily', 0)
    used = u.get('signals_used_today', 0)
    available = max(0, daily - used)
    return available, daily


def create_payment(chat_id, plan, amount, crypto, payment_code):
    """Створює запис про платіж."""
    try:
        with closing(sqlite3.connect(DB)) as conn:
            c = conn.cursor()
            c.execute('''INSERT INTO payments 
                (chat_id, plan, amount, crypto, payment_code, status, created_at) 
                VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (chat_id, plan, amount, crypto, payment_code, 'pending', int(time.time())))
            conn.commit()
        logger.info(f"✅ Payment created: {payment_code}")
        return True
    except Exception as e:
        logger.error(f"❌ Create payment error: {e}")
        raise


def get_payment(payment_code):
    """Отримує дані платежу за кодом."""
    try:
        with closing(sqlite3.connect(DB)) as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM payments WHERE payment_code=?', (payment_code,))
            row = c.fetchone()
            if not row:
                return None
            return {
                'id': row[0],
                'chat_id': row[1],
                'plan': row[2],
                'amount': row[3],
                'crypto': row[4],
                'payment_code': row[5],
                'status': row[6],
                'created_at': row[7],
                'screenshot_url': row[8],
                'location': row[9]
            }
    except Exception as e:
        logger.error(f"❌ Get payment error: {e}")
        return None


def update_payment(payment_code, status, screenshot_url=None, location=None):
    """Оновлює статус платежу."""
    try:
        with closing(sqlite3.connect(DB)) as conn:
            c = conn.cursor()
            c.execute('''UPDATE payments 
                SET status=?, screenshot_url=?, location=? 
                WHERE payment_code=?''',
                (status, screenshot_url, location, payment_code))
            conn.commit()
        logger.info(f"✅ Payment updated: {payment_code} -> {status}")
        return True
    except Exception as e:
        logger.error(f"❌ Update payment error: {e}")
        raise


def get_pending_payments():
    """Отримує всі очікуючі платежі."""
    try:
        with closing(sqlite3.connect(DB)) as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM payments WHERE status=?', ('pending_screenshot',))
            rows = c.fetchall()
            return [
                {
                    'id': row[0],
                    'chat_id': row[1],
                    'plan': row[2],
                    'amount': row[3],
                    'crypto': row[4],
                    'payment_code': row[5],
                    'status': row[6],
                    'created_at': row[7],
                    'screenshot_url': row[8],
                    'location': row[9]
                } for row in rows
            ]
    except Exception as e:
        logger.error(f"❌ Get pending payments error: {e}")
        return []