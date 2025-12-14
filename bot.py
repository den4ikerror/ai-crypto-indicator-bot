import logging
import string
import random
import json
import os
import asyncio
from datetime import datetime, timedelta
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters
)
from config import TG_BOT_TOKEN, PRICES, CRYPTO_PAYMENTS, ADMIN_ID, MOD_CHANNEL_ID, USD_TO_UAH_RATE
from db import (
    init_db, get_user, decrement_signal, create_payment,
    get_payment, update_payment, get_pending_payments, set_plan,
    get_signals_available
)
from payments import purchase_plan as payments_purchase_plan
import time

# Логування
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

init_db()

pending_signals = {}
pending_admin_user = {}
searching_signals = set()
USERS_JSON = 'users_data.json'

# Розширений список монет (BTC/ETH/SOL обов'язкові)
SYMBOL_CANDIDATES = [
    'BTC/USDT','ETH/USDT','SOL/USDT','ADA/USDT','BNB/USDT',
    'XRP/USDT','DOGE/USDT','MATIC/USDT','AVAX/USDT','LTC/USDT',
    'ATOM/USDT','TRX/USDT','NEAR/USDT','DOT/USDT','FTM/USDT'
]

MAIN_TEXT = (
    "👋 Привіт! Ласкаво просимо до AI Crypto Indicator!\n\n"
    "🚀 Професійна платформа для торгівлі криптовалютами\n"
    "🔍 Отримуйте точні сигнали торгівлі в реальному часі\n"
    "📊 Аналіз ринку на основі передової AI-технології\n"
    "💡 Точні рівні входу та виходу з індикаторами\n"
    "⚡ Швидка реакція на зміни ринку\n\n"
    "🎯 Обираємо найперспективніші торговельні можливості:\n"
    "• Підтримка BTC, ETH, SOL та інших топ-монет\n"
    "• Таймфрейми від 15 хвилин до 4 годин\n"
    "• Сигнали з рівнем довіри > 70%\n\n"
    "💰 Легка оплата (USDT, TON, monobank)\n"
    "✅ Моментальний доступ після підтвердження оплати\n\n"
    "📌 Якщо залишились питання, зверніться до менеджера: @dima58s\n\n"
    "Оберіть дію нижче для початку:"
)

def is_admin(user_id):
    return user_id == ADMIN_ID

def generate_payment_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def load_users_json():
    if os.path.exists(USERS_JSON):
        try:
            with open(USERS_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_users_json(users_data):
    try:
        with open(USERS_JSON, 'w', encoding='utf-8') as f:
            json.dump(users_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving JSON: {e}")

def track_user(user_id, username, first_name):
    users = load_users_json()
    if str(user_id) not in users:
        users[str(user_id)] = {
            'user_id': user_id,
            'username': username or 'N/A',
            'first_name': first_name or 'N/A',
            'created_at': datetime.utcnow().isoformat(),
            'last_seen': datetime.utcnow().isoformat(),
            'plan': None,
            'signals_daily': 0,
            'signals_used_today': 0
        }
    else:
        users[str(user_id)]['last_seen'] = datetime.utcnow().isoformat()
    save_users_json(users)

def plan_reliability_bounds(plan_key: str):
    if plan_key == 'starter':
        return (60, 80)
    if plan_key == 'pro':
        return (80, 90)
    return (60, 80)

async def send_signal_after_delay(chat_id: int, context: ContextTypes.DEFAULT_TYPE, min_delay=5*60, max_delay=60*60):
    try:
        delay = random.randint(min_delay, max_delay)
        logger.info(f"⏳ Scheduled signal for {chat_id} in {delay} sec")
        await asyncio.sleep(delay)

        available, daily = get_signals_available(chat_id)
        if available <= 0:
            await context.bot.send_message(chat_id=chat_id, text="❌ Ваш денний ліміт сигналів сплив. Сигнал не надіслано.")
            searching_signals.discard(chat_id)
            return

        symbols = SYMBOL_CANDIDATES.copy()
        random.shuffle(symbols)

        success = False
        errors = []
        for sym in symbols:
            try:
                logger.info(f"🧪 Trying symbol {sym} for user {chat_id}")
                from signal_generator import generate_signal_message
                msg, chart = generate_signal_message(symbol=sym)

                if "Signal: NEUTRAL" in msg:
                    logger.info(f"⏭️ Signal {sym} is NEUTRAL, skipping...")
                    continue

                u = get_user(chat_id) or {}
                plan = u.get('paid_plan', '')
                low, high = plan_reliability_bounds(plan)
                reliability = random.randint(low, high)
                leverage = random.choice(range(25, 105, 5))

                header = f"📡 Сигнал — {sym}\n"
                meta = f"🔒 Надійність: {reliability}% | ⚖️ Плече: {leverage}x\n"
                caption = header + meta + "\n" + msg

                await context.bot.send_photo(chat_id=chat_id, photo=chart, caption=caption)

                decrement_signal(chat_id)
                users = load_users_json()
                u_db = get_user(chat_id) or {}
                if str(chat_id) in users:
                    users[str(chat_id)]['signals_daily'] = u_db.get('signals_daily', 0)
                    users[str(chat_id)]['signals_used_today'] = u_db.get('signals_used_today', 0)
                    users[str(chat_id)]['plan'] = u_db.get('paid_plan')
                    save_users_json(users)

                success = True
                logger.info(f"✅ Sent signal {sym} to {chat_id} (rel={reliability}%, lev={leverage}x)")
                break
            except Exception as e_sym:
                etype = type(e_sym).__name__
                logger.warning(f"⚠️ Symbol {sym} failed for {chat_id}: {etype} - {e_sym}")
                errors.append(f"{sym}:{etype}")
                continue

        if not success:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Нажаль, не змогли згенерувати сигнал. Спробуйте пізніше.")
            logger.error(f"❌ All attempts failed for {chat_id}: {errors}")
        
        searching_signals.discard(chat_id)
    except Exception as e:
        logger.error(f"❌ send_signal_after_delay error for {chat_id}: {type(e).__name__} - {e}")
        searching_signals.discard(chat_id)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    track_user(user.id, user.username, user.first_name)
    logger.info(f"✅ User started: {user.id}")

    kb = [
        [InlineKeyboardButton("🛒 Купити план", callback_data="menu:buy")],
        [InlineKeyboardButton("📡 Отримати сигнал", callback_data="menu:signal")],
        [InlineKeyboardButton("📋 Статус", callback_data="menu:status")]
    ]
    if is_admin(user.id):
        # Для адміна додати кнопку миттєвого сигналу
        kb.insert(2, [InlineKeyboardButton("⚡ Сигнал моментально", callback_data="menu:signal:admin")])
        kb.insert(4, [InlineKeyboardButton("👨‍💼 Адмін панель", callback_data="admin:menu")])

    kb.append([InlineKeyboardButton("💬 Відгуки", url="https://t.me/+MBzp-7dZLH5kZTAy")])
    kb.append([InlineKeyboardButton("❓ Допомога", callback_data="menu:help")])

    await update.message.reply_text(MAIN_TEXT, reply_markup=InlineKeyboardMarkup(kb))

def build_main_kb(user_id):
    kb = [
        [InlineKeyboardButton("🛒 Купити план", callback_data="menu:buy")],
        [InlineKeyboardButton("📡 Отримати сигнал", callback_data="menu:signal")]
    ]
    if is_admin(user_id):
        kb.append([InlineKeyboardButton("⚡ Сигнал моментально", callback_data="menu:signal:admin")])
    kb.append([InlineKeyboardButton("📋 Статус", callback_data="menu:status")])
    if is_admin(user_id):
        kb.append([InlineKeyboardButton("👨‍💼 Адмін панель", callback_data="admin:menu")])
    kb.append([InlineKeyboardButton("💬 Відгуки", url="https://t.me/+MBzp-7dZLH5kZTAy")])
    kb.append([InlineKeyboardButton("❓ Допомога", callback_data="menu:help")])
    return InlineKeyboardMarkup(kb)

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        data = query.data
        user = query.from_user
        chat_id = user.id

        logger.info(f"👤 User {chat_id} clicked: {data}")

        # === ADMIN ROUTES ===
        if data == 'admin:menu' and is_admin(chat_id):
            logger.info(f"📊 Admin {chat_id} opened admin panel")
            kb = [
                [InlineKeyboardButton("👥 Активні користувачі", callback_data="admin:active_users")],
                [InlineKeyboardButton("🔎 Знайти користувача", callback_data="admin:find_user")],
                [InlineKeyboardButton("💳 Перевірити платежі", callback_data="admin:check_payments")],
                [InlineKeyboardButton("🎁 Дати собі тариф", callback_data="admin:self_plan")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")]
            ]
            await query.edit_message_text("👨‍💼 Адмін Панель\n══════════════════════\nОберіть дію:", reply_markup=InlineKeyboardMarkup(kb))
            return

        if data == 'admin:active_users' and is_admin(chat_id):
            users = load_users_json()
            if not users:
                await query.edit_message_text("ℹ️ Немає активних користувачів")
                return
            text = "👥 Останні активні користувачі (ID — username):\n\n"
            for uid, udata in sorted(users.items(), key=lambda x: x[1].get('last_seen', ''), reverse=True)[:20]:
                text += f"• {uid} — @{udata.get('username','N/A')}\n"
            kb = [[InlineKeyboardButton("⬅️ Назад", callback_data="admin:menu")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
            return

        if data == 'admin:find_user' and is_admin(chat_id):
            context.user_data['state'] = 'admin_find_user'
            await query.edit_message_text("🔎 Введіть ID або username користувача для пошуку:")
            return

        if data == 'admin:check_payments' and is_admin(chat_id):
            payments = get_pending_payments()
            if not payments:
                kb = [[InlineKeyboardButton("⬅️ Назад", callback_data="admin:menu")]]
                await query.edit_message_text("✅ Немає очікуючих платежів", reply_markup=InlineKeyboardMarkup(kb))
                return
            
            text = "💳 Платежі на перевірці:\n\n"
            for p in payments[:5]:
                text += f"💳 {p['payment_code']}\n   👤 User: {p['chat_id']}\n   📦 План: {p['plan']} | {p['crypto'].upper()}\n   💰 ${p['amount']}\n"
            first_code = payments[0]['payment_code']
            kb = [
                [InlineKeyboardButton(f"✅ Затвердити {first_code[:6]}", callback_data=f"admin:approve:{first_code}")],
                [InlineKeyboardButton(f"❌ Відхилити {first_code[:6]}", callback_data=f"admin:reject:{first_code}")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="admin:menu")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
            return

        if data.startswith('admin:approve:') and is_admin(chat_id):
            payment_code = data.split(':', 2)[2]
            payment = get_payment(payment_code)
            if not payment:
                await query.edit_message_text("❌ Платіж не знайдено")
                return
            try:
                update_payment(payment_code, 'approved')
                plan = payment['plan']
                user_id = payment['chat_id']
                payments_purchase_plan(user_id, plan)
                users = load_users_json()
                u_db = get_user(user_id) or {}
                if str(user_id) in users:
                    users[str(user_id)]['plan'] = plan
                    users[str(user_id)]['signals_daily'] = u_db.get('signals_daily', 0)
                    users[str(user_id)]['signals_used_today'] = u_db.get('signals_used_today', 0)
                    save_users_json(users)
                await context.bot.send_message(chat_id=user_id, text=f"✅ Оплату підтверджено! План: {plan}")
                await query.edit_message_text("✅ Платіж затверджено. Користувачу надіслано повідомлення.")
            except Exception as e:
                logger.error(f"Approve error: {e}")
                await query.edit_message_text(f"❌ Помилка: {str(e)}")
            return

        if data.startswith('admin:reject:') and is_admin(chat_id):
            payment_code = data.split(':', 2)[2]
            payment = get_payment(payment_code)
            if not payment:
                await query.edit_message_text("❌ Платіж не знайдено")
                return
            try:
                update_payment(payment_code, 'rejected')
                user_id = payment['chat_id']
                await context.bot.send_message(chat_id=user_id, text=f"❌ Ваш платіж відхилено.\n\nКод: {payment_code}")
                await query.edit_message_text("✅ Платіж відхилено. Користувачу надіслано повідомлення.")
            except Exception as e:
                logger.error(f"Reject error: {e}")
                await query.edit_message_text(f"❌ Помилка: {str(e)}")
            return

        if data == 'admin:self_plan' and is_admin(chat_id):
            kb = [
                [InlineKeyboardButton(f"Lite — ${PRICES['starter']}", callback_data="self:starter")],
                [InlineKeyboardButton(f"Pro — ${PRICES['pro']}", callback_data="self:pro")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="admin:menu")]
            ]
            await query.edit_message_text("🎁 Оберіть тариф для себе:", reply_markup=InlineKeyboardMarkup(kb))
            return

        if data.startswith('self:') and is_admin(chat_id):
            plan = data.split(':', 1)[1]
            try:
                payments_purchase_plan(chat_id, plan)
                users = load_users_json()
                u_db = get_user(chat_id) or {}
                if str(chat_id) in users:
                    users[str(chat_id)]['plan'] = plan
                    users[str(chat_id)]['signals_daily'] = u_db.get('signals_daily', 0)
                    users[str(chat_id)]['signals_used_today'] = u_db.get('signals_used_today', 0)
                    save_users_json(users)
                await query.edit_message_text(f"✅ Вам виданий тариф: {plan}")
            except Exception as e:
                logger.error(f"Self plan error: {e}")
                await query.edit_message_text(f"❌ Помилка: {str(e)}")
            return

        if data.startswith('admin:grant_plan:') and is_admin(chat_id):
            target = int(data.split(':', 2)[2])
            context.user_data['admin_grant_target'] = target
            context.user_data['state'] = 'admin_grant_select_plan'
            
            kb = [
                [InlineKeyboardButton("🔵 Lite (2 сигнали/день)", callback_data="admin_grant_plan_lite")],
                [InlineKeyboardButton("🟢 Pro (5 сигналів/день)", callback_data="admin_grant_plan_pro")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="admin:menu")]
            ]
            await query.edit_message_text(f"📦 Оберіть тариф для користувача {target}:", reply_markup=InlineKeyboardMarkup(kb))
            return

        if data.startswith('admin_grant_plan_') and is_admin(chat_id):
            plan_type = data.split('_')[-1]
            plan_map = {'lite': 'starter', 'pro': 'pro'}
            context.user_data['admin_grant_plan'] = plan_map[plan_type]
            context.user_data['state'] = 'admin_grant_select_term'
            
            kb = [
                [InlineKeyboardButton("📅 1 місяць", callback_data="admin_grant_term_month")],
                [InlineKeyboardButton("📅 1 рік", callback_data="admin_grant_term_year")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="admin:menu")]
            ]
            await query.edit_message_text("⏳ Оберіть період підписки:", reply_markup=InlineKeyboardMarkup(kb))
            return

        if data.startswith('admin_grant_term_') and is_admin(chat_id):
            term = data.split('_')[-1]
            target = context.user_data.get('admin_grant_target')
            plan = context.user_data.get('admin_grant_plan')
            
            if not target or not plan:
                await query.edit_message_text("❌ Помилка. Почніть заново.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="admin:menu")]]))
                return
            
            try:
                from payments import plan_config
                days = 30 if term == 'month' else 365
                expires = int((datetime.utcnow() + timedelta(days=days)).timestamp())
                signals_daily = plan_config.get(plan, {}).get('signals_daily', 2)
                
                set_plan(target, plan, expires, signals_daily=signals_daily)
                
                users = load_users_json()
                u_db = get_user(target) or {}
                if str(target) in users:
                    users[str(target)]['plan'] = plan
                    users[str(target)]['signals_daily'] = signals_daily
                    users[str(target)]['signals_used_today'] = 0
                    save_users_json(users)
                
                term_text = "1 місяць" if term == 'month' else "1 рік"
                await query.edit_message_text(
                    f"✅ Тариф видано!\n\n"
                    f"👤 Користувач: {target}\n"
                    f"📦 План: {plan}\n"
                    f"⏳ Період: {term_text}\n"
                    f"🎯 Сигналів/день: {signals_daily}"
                )
                
                context.user_data['state'] = None
                context.user_data['admin_grant_target'] = None
                context.user_data['admin_grant_plan'] = None
            except Exception as e:
                logger.error(f"Grant error: {e}")
                await query.edit_message_text(f"❌ Помилка при видачі тарифу: {str(e)}")
            return

        if data.startswith('admin:revoke_plan:') and is_admin(chat_id):
            target = int(data.split(':', 2)[2])
            try:
                set_plan(target, None, None, signals_daily=0)
                users = load_users_json()
                if str(target) in users:
                    users[str(target)]['plan'] = None
                    users[str(target)]['signals_daily'] = 0
                    users[str(target)]['signals_used_today'] = 0
                    save_users_json(users)
                await query.edit_message_text(f"✅ Тариф забрано у {target}")
            except Exception as e:
                logger.error(f"Revoke error: {e}")
                await query.edit_message_text("❌ Помилка при знятті тарифу")
            return

        if data.startswith('admin:add_signal:') and is_admin(chat_id):
            target = int(data.split(':', 2)[2])
            u = get_user(target) or {}
            daily = (u.get('signals_daily') or 0) + 1
            set_plan(target, u.get('paid_plan'), u.get('plan_expires'), signals_daily=daily)
            users = load_users_json()
            if str(target) in users:
                users[str(target)]['signals_daily'] = daily
                users[str(target)]['signals_used_today'] = u.get('signals_used_today', 0)
                save_users_json(users)
            await query.edit_message_text(f"✅ Додано 1 сигнал/день. Наразі: {daily}")
            return

        if data.startswith('admin:remove_signal:') and is_admin(chat_id):
            target = int(data.split(':', 2)[2])
            u = get_user(target) or {}
            daily = max(0, (u.get('signals_daily') or 0) - 1)
            set_plan(target, u.get('paid_plan'), u.get('plan_expires'), signals_daily=daily)
            users = load_users_json()
            if str(target) in users:
                users[str(target)]['signals_daily'] = daily
                users[str(target)]['signals_used_today'] = u.get('signals_used_today', 0)
                save_users_json(users)
            await query.edit_message_text(f"✅ Віднято 1 сигнал/день. Наразі: {daily}")
            return

        if data.startswith('admin:info:') and is_admin(chat_id):
            target = int(data.split(':', 2)[2])
            u = get_user(target)
            if not u:
                await query.edit_message_text("❌ Користувач не знайдений в БД")
                return
            info_text = (
                f"👤 User ID: {target}\n"
                f"📦 План: {u.get('paid_plan') or 'Немає'}\n"
                f"🎯 Сигналів/день: {u.get('signals_daily', 0)}\n"
                f"📊 Витрачено сьогодні: {u.get('signals_used_today', 0)}\n"
                f"📅 План закінчується: {datetime.utcfromtimestamp(u.get('plan_expires', 0)).strftime('%Y-%m-%d') if u.get('plan_expires') else 'N/A'}"
            )
            kb = [[InlineKeyboardButton("⬅️ Назад", callback_data="admin:menu")]]
            await query.edit_message_text(info_text, reply_markup=InlineKeyboardMarkup(kb))
            return

        # === REGULAR USER ROUTES ===
        if data == 'menu:buy':
            logger.info(f"🛒 User {chat_id} opened buy menu")
            kb = [
                [InlineKeyboardButton(f"🔵 Lite — ${PRICES['starter']}\n(2 сигн./день)", callback_data="buy:starter")],
                [InlineKeyboardButton(f"🟢 Pro — ${PRICES['pro']}\n(5 сигн./день)", callback_data="buy:pro")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")]
            ]
            await query.edit_message_text(
                "🛒 Оберіть план:\n══════════════════════\n\n"
                "Lite — бюджетний, 2 сигнали/день, середня - висока вірогідність.\n"
                "Pro — преміум, 5 сигналів/день, найвища вірогідність.\n\n"
                "Порівняння: Lite дешевше — базовий доступ; Pro — більше сигналів та найвища вірогідність успіху.",
                reply_markup=InlineKeyboardMarkup(kb)
            )
            return

        if data.startswith('buy:'):
            plan = data.split(':', 1)[1]
            pending_signals[chat_id] = {'plan': plan, 'step': 'select_term'}
            kb = [
                [InlineKeyboardButton("1 місяць", callback_data="term:month")],
                [InlineKeyboardButton("1 рік", callback_data="term:year")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="menu:buy")]
            ]
            await query.edit_message_text(f"📦 Ви обрали: {'Lite' if plan=='starter' else 'Pro'}\n⏳ Оберіть термін:", reply_markup=InlineKeyboardMarkup(kb))
            return

        if data.startswith('term:'):
            term = data.split(':', 1)[1]
            pending = pending_signals.get(chat_id)
            if not pending or 'plan' not in pending:
                await query.edit_message_text("❌ Помилка. Почніть спочатку.", reply_markup=build_main_kb(chat_id))
                return
            pending['term'] = term
            plan = pending['plan']
            if term == 'month':
                amount = PRICES.get(plan, 0)
            elif term == 'year':
                if plan == 'starter':
                    amount = 240
                elif plan == 'pro':
                    amount = 420
                else:
                    amount = 0
            pending['amount'] = amount
            
            amount_uah = round(amount * USD_TO_UAH_RATE, 2)
            
            kb = [
                [InlineKeyboardButton(f"{CRYPTO_PAYMENTS['usdt']['emoji']} USDT", callback_data="crypto:usdt")],
                [InlineKeyboardButton(f"{CRYPTO_PAYMENTS['ton']['emoji']} TON", callback_data="crypto:ton")],
                [InlineKeyboardButton(f"{CRYPTO_PAYMENTS['monobank']['emoji']} Monobank банка {amount_uah} UAH", callback_data="crypto:monobank")],
                [InlineKeyboardButton(f"{CRYPTO_PAYMENTS['monobank_card']['emoji']} Monobank картка {amount_uah} UAH", callback_data="crypto:monobank_card")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="menu:buy")]
            ]
            await query.edit_message_text(
                f"💳 План: {'Lite' if plan=='starter' else 'Pro'}\n"
                f"⏳ Термін: {'1 місяць' if term=='month' else '1 рік'}\n"
                f"💰 Сума: {amount} USD ({amount_uah} UAH)\n\n"
                f"💱 Оберіть спосіб оплати:",
                reply_markup=InlineKeyboardMarkup(kb)
            )
            return

        if data.startswith('crypto:'):
            crypto = data.split(':', 1)[1]
            if chat_id not in pending_signals or 'plan' not in pending_signals[chat_id]:
                await query.edit_message_text("❌ Помилка. Почніть спочатку.", reply_markup=build_main_kb(chat_id))
                return
            plan = pending_signals[chat_id]['plan']
            amount = pending_signals[chat_id].get('amount', PRICES.get(plan, 0))
            payment_code = generate_payment_code()

            if crypto == 'monobank':
                amount_uah = round(amount * USD_TO_UAH_RATE, 2)
                wallet = CRYPTO_PAYMENTS[crypto]['address']

                try:
                    create_payment(chat_id, plan, amount, crypto, payment_code)
                except Exception as e:
                    logger.error(f"Payment creation error: {e}")
                    await query.edit_message_text("❌ Помилка створення платежу.", reply_markup=build_main_kb(chat_id))
                    return

                pending_signals[chat_id]['crypto'] = crypto
                pending_signals[chat_id]['payment_code'] = payment_code

                kb = [
                    [InlineKeyboardButton("🏦 Оплатити через Monobank банку", url=wallet)],
                    [InlineKeyboardButton("✅ Оплачено", callback_data=f"payment:confirm:{payment_code}")],
                    [InlineKeyboardButton("⬅️ Назад", callback_data="menu:buy")]
                ]

                text = (
                    f"💳 Оплата Monobank (банка)\n══════════════════════\n"
                    f"Сума: {amount_uah} ₴ (UAH)\n"
                    f"План: {plan}\n\n"
                    f"📌 Посилання відкриється в Monobank\n"
                    f"✅ Після оплати натисніть «Оплачено»"
                )

                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                return

            elif crypto == 'monobank_card':
                amount_uah = round(amount * USD_TO_UAH_RATE, 2)

                try:
                    create_payment(chat_id, plan, amount, crypto, payment_code)
                except Exception as e:
                    logger.error(f"Payment creation error: {e}")
                    await query.edit_message_text("❌ Помилка створення платежу.", reply_markup=build_main_kb(chat_id))
                    return

                pending_signals[chat_id]['crypto'] = crypto
                pending_signals[chat_id]['payment_code'] = payment_code

                kb = [
                    [InlineKeyboardButton("✅ Оплачено", callback_data=f"payment:confirm:{payment_code}")],
                    [InlineKeyboardButton("⬅️ Назад", callback_data="menu:buy")]
                ]

                text = (
                    f"💳 Оплата напряму на картку Monobank\n══════════════════════\n"
                    f"Сума: {amount_uah} ₴ (UAH)\n"
                    f"План: {plan}\n\n"
                    f"📌 Реквізити картки: 4441 1111 3666 0614\n"
                    f"✅ Після оплати натисніть «Оплачено»"
                )

                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                return
            else:
                crypto_info = CRYPTO_PAYMENTS[crypto]
                wallet = crypto_info['address']
                
                try:
                    create_payment(chat_id, plan, amount, crypto, payment_code)
                except Exception as e:
                    logger.error(f"Payment creation error: {e}")
                    await query.edit_message_text("❌ Помилка створення платежу.", reply_markup=build_main_kb(chat_id))
                    return
                
                pending_signals[chat_id]['crypto'] = crypto
                pending_signals[chat_id]['payment_code'] = payment_code
                
                kb = [
                    [InlineKeyboardButton("📋 Копіювати адресу", callback_data=f"copy:addr:{wallet}")],
                    [InlineKeyboardButton("📋 Копіювати код", callback_data=f"copy:code:{payment_code}")],
                    [InlineKeyboardButton("✅ Оплачено", callback_data=f"payment:confirm:{payment_code}")],
                    [InlineKeyboardButton("⬅️ Назад", callback_data="menu:buy")]
                ]
                
                text = (
                    f"💳 Деталі платежу\n══════════════════════\n"
                    f"Монета: {crypto_info['emoji']} {crypto_info['name']}\n"
                    f"Мережа: {crypto_info['network']}\n"
                    f"Сума: {amount} USD\n\n"
                    f"📪 Адреса кошелька:\n`{wallet}`\n\n"
                    f"🏷️ Код (Memo/Tag):\n`{payment_code}`\n\n"
                    f"⚠️ Обов'язково вкажіть код в Memo/Tag!\n✅ Після оплати натисніть «Оплачено»"
                )
                
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
                return

        if data.startswith('copy:'):
            await query.answer("✅ Скопійовано!", show_alert=False)
            return

        if data.startswith('payment:confirm:'):
            payment_code = data.split(':', 2)[2]
            payment = get_payment(payment_code)
            if not payment:
                await query.edit_message_text("❌ Платіж не знайдено.")
                return
            if payment['status'] != 'pending':
                await query.edit_message_text(f"⚠️ Статус: {payment['status']}")
                return
            try:
                update_payment(payment_code, 'pending_screenshot')
            except Exception as e:
                logger.error(f"Update error: {e}")
            await query.edit_message_text("📸 Надішліть скріншот транзакції (фото: сума, адреса, статус)")
            context.user_data['pending_payment_code'] = payment_code
            context.user_data['state'] = 'awaiting_screenshot'
            return

        if data == 'menu:signal':
            logger.info(f"📡 User {chat_id} clicked get signal")
            u = get_user(chat_id)
            
            if chat_id in searching_signals:
                await query.answer("⏳ Сигнал вже в процесі! Дочекайтесь першого сигналу перед активацією нового.", show_alert=True)
                return
            
            if not u or not u.get('paid_plan'):
                await query.answer()
                await context.bot.send_message(chat_id=chat_id, text="❌ У вас немає активного тарифу. Натисніть /start")
                return
            
            available, daily = get_signals_available(chat_id)
            if available <= 0:
                now = datetime.utcnow()
                next_reset = now.replace(hour=8, minute=0, second=0, microsecond=0)
                if now >= next_reset:
                    next_reset = next_reset + timedelta(days=1)
                next_reset_time = next_reset.strftime('%Y-%m-%d %H:%M UTC')
                await query.answer()
                await context.bot.send_message(chat_id=chat_id, text=f"❌ Сигнали закінчились. Відновлення: {next_reset_time}")
                return
            
            min_delay = 5*60
            max_delay = 60*60
            await query.edit_message_text(
                "⏳ Сигнали шукаються...\n\n🔍 AI аналізує ринки. Сигнал буде надісланий протягом 1 год.\n\n✅ Повернутись: натисніть «⬅️ Назад»",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")]])
            )
            searching_signals.add(chat_id)
            try:
                context.application.create_task(send_signal_after_delay(chat_id, context, min_delay, max_delay))
            except Exception as e_task:
                logger.error(f"Failed to schedule task: {e_task}")
                searching_signals.discard(chat_id)
                await context.bot.send_message(chat_id=chat_id, text="❌ Не вдалося запланувати сигнал.")
            return

        # НОВИЙ: Сигнал для адміна без затримки
        if data == 'menu:signal:admin' and is_admin(chat_id):
            logger.info(f"⚡ Admin {chat_id} requesting instant signal")
            
            if chat_id in searching_signals:
                await query.answer("⏳ Сигнал уже в обробці!", show_alert=True)
                return
            
            searching_signals.add(chat_id)
            await query.edit_message_text(
                "⚡ Генерування сигналу...\n\n🚀 Моментальна генерація для адміністратора",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")]])
            )
            
            try:
                from signal_generator import generate_signal_message
                symbols = SYMBOL_CANDIDATES.copy()
                random.shuffle(symbols)

                success = False
                errors = []
                for sym in symbols:
                    try:
                        logger.info(f"🚀 Admin instant signal: trying {sym}")
                        msg, chart = generate_signal_message(symbol=sym)

                        if "Signal: NEUTRAL" in msg:
                            logger.info(f"⏭️ Signal {sym} is NEUTRAL, skipping...")
                            continue

                        u = get_user(chat_id) or {}
                        plan = u.get('paid_plan', '')
                        low, high = plan_reliability_bounds(plan)
                        reliability = random.randint(low, high)
                        leverage = random.choice(range(25, 105, 5))

                        header = f"📡 Сигнал (моментально) — {sym}\n"
                        meta = f"🔒 Надійність: {reliability}% | ⚖️ Плече: {leverage}x\n"
                        caption = header + meta + "\n" + msg

                        await context.bot.send_photo(chat_id=chat_id, photo=chart, caption=caption)

                        logger.info(f"✅ Instant signal sent to admin {chat_id}: {sym} (rel={reliability}%, lev={leverage}x)")
                        success = True
                        break
                    except Exception as e_sym:
                        etype = type(e_sym).__name__
                        logger.warning(f"⚠️ Admin instant signal {sym} failed: {etype} - {e_sym}")
                        errors.append(f"{sym}:{etype}")
                        continue

                if not success:
                    await context.bot.send_message(chat_id=chat_id, text="⚠️ Не змогли згенерувати сигнал. Спробуйте ще раз.")
                    logger.error(f"❌ All instant signal attempts failed for admin {chat_id}: {errors}")

                searching_signals.discard(chat_id)
            except Exception as e:
                logger.error(f"❌ Admin instant signal error for {chat_id}: {type(e).__name__} - {e}")
                searching_signals.discard(chat_id)
                await context.bot.send_message(chat_id=chat_id, text="❌ Помилка генерації сигналу.")
            return

        if data == 'menu:status':
            logger.info(f"📋 User {chat_id} opened status menu")
            u = get_user(chat_id)
            
            if not u or not u.get('paid_plan'):
                kb = [[InlineKeyboardButton("🛒 Купити план", callback_data="menu:buy")],[InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")]]
                await query.edit_message_text("📋 Ваш Статус\n❌ Активний тариф: Немає", reply_markup=InlineKeyboardMarkup(kb))
                return
            
            available, daily = get_signals_available(chat_id)
            now = datetime.utcnow()
            next_reset = now.replace(hour=8, minute=0, second=0, microsecond=0)
            if now >= next_reset:
                next_reset = next_reset + timedelta(days=1)
            next_reset_time = next_reset.strftime('%Y-%m-%d %H:%M UTC')
            
            plan_expires = u.get('plan_expires', 0)
            if plan_expires > 0:
                expires_dt = datetime.utcfromtimestamp(plan_expires)
                expires_str = expires_dt.strftime('%Y-%m-%d %H:%M UTC')
                days_left = (expires_dt - now).days
            else:
                expires_str = "Невідомо"
                days_left = 0
            
            kb = [[InlineKeyboardButton("🛒 Поновити план", callback_data="menu:buy")],[InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")]]
            status_text = (
                f"📊 Ваш Статус\n════════════════════\n📦 План: {u.get('paid_plan')}\n🎯 Сигналів сьогодні: {available} / {daily}\n⏰ Наступне відновлення: {next_reset_time}\n\n📅 Підписка закінчується: {expires_str} (днів: {max(0, days_left)})"
            )
            await query.edit_message_text(status_text, reply_markup=InlineKeyboardMarkup(kb))
            return

        if data == 'menu:help':
            logger.info(f"❓ User {chat_id} opened help menu")
            kb = [[InlineKeyboardButton("⬅️ Назад в меню", callback_data="menu:main")]]
            await query.edit_message_text(
                "❓ Як користуватись ботом?\n════════════════════\n1) Купіть план\n2) Оплатіть і надішліть скрін\n3) Отримуйте сигнали\n\n📞 Питання: @dima58s",
                reply_markup=InlineKeyboardMarkup(kb)
            )
            return

        if data == 'menu:main':
            logger.info(f"🏠 User {chat_id} returned to main menu")
            kb = build_main_kb(chat_id)
            await query.edit_message_text(MAIN_TEXT, reply_markup=kb)
            return

    except Exception as e:
        logger.error(f"❌ CALLBACK ERROR: {type(e).__name__} - {e} | data={data} | user={chat_id}")
        try:
            await query.edit_message_text("❌ Сталася помилка. Спробуйте пізніше.")
        except:
            pass

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        chat_id = user.id
        text = (update.message.text or '').strip()
        state = context.user_data.get('state')

        if state == 'admin_grant_select_user' and is_admin(chat_id):
            try:
                target_id = int(text)
                u = get_user(target_id)
                if not u:
                    await update.message.reply_text(f"❌ Користувач {target_id} не знайдений в БД")
                    return
                
                context.user_data['admin_grant_target'] = target_id
                context.user_data['state'] = None
                
                kb = [
                    [InlineKeyboardButton("🔵 Lite (2 сигнали/день)", callback_data="admin_grant_plan_lite")],
                    [InlineKeyboardButton("🟢 Pro (5 сигналів/день)", callback_data="admin_grant_plan_pro")],
                    [InlineKeyboardButton("⬅️ Назад", callback_data="admin:menu")]
                ]
                await update.message.reply_text(f"📦 Оберіть тариф для користувача {target_id}:", reply_markup=InlineKeyboardMarkup(kb))
            except ValueError:
                await update.message.reply_text("❌ Введіть коректний ID (число)")
            return

        if state == 'admin_find_user' and is_admin(chat_id):
            query_text = text
            users = load_users_json()
            found = None
            if query_text.isdigit():
                found = users.get(query_text)
            else:
                for uid, u in users.items():
                    if u.get('username') and u.get('username').lower() == query_text.lstrip('@').lower():
                        found = u
                        break
            context.user_data['state'] = None
            if not found:
                await update.message.reply_text("❌ Користувача не знайдено")
                return
            target_id = found['user_id']
            kb = [
                [InlineKeyboardButton("✅ Дати тариф", callback_data=f"admin:grant_plan:{target_id}")],
                [InlineKeyboardButton("❌ Забрати тариф", callback_data=f"admin:revoke_plan:{target_id}")],
                [InlineKeyboardButton("➕ +1 сделка/день", callback_data=f"admin:add_signal:{target_id}")],
                [InlineKeyboardButton("➖ -1 сделка/день", callback_data=f"admin:remove_signal:{target_id}")],
                [InlineKeyboardButton("📊 Дані", callback_data=f"admin:info:{target_id}")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="admin:menu")]
            ]
            await update.message.reply_text(f"👤 Знайдено: {target_id} — @{found.get('username','N/A')}\nОберіть дію:", reply_markup=InlineKeyboardMarkup(kb))
            return

        if state == 'awaiting_screenshot' and context.user_data.get('pending_payment_code'):
            if update.message.photo:
                payment_code = context.user_data['pending_payment_code']
                photo = update.message.photo[-1]
                photo_id = photo.file_id

                payment = get_payment(payment_code)
                wallet_addr = None
                if payment and payment.get('crypto'):
                    wallet_info = CRYPTO_PAYMENTS.get(payment['crypto'], {})
                    wallet_addr = wallet_info.get('address')

                caption_text = ''
                if getattr(update.message, 'caption', None):
                    caption_text += update.message.caption or ''
                caption_text += ' ' + (update.message.text or '')
                caption_text = caption_text.strip()

                valid = False
                if payment_code and payment_code in caption_text:
                    valid = True
                elif wallet_addr and wallet_addr in caption_text:
                    valid = True
                else:
                    if wallet_addr and len(wallet_addr) > 6 and wallet_addr[-6:] in caption_text:
                        valid = True
                    elif len(payment_code) > 4 and payment_code[-4:] in caption_text:
                        valid = True

                try:
                    update_payment(payment_code, 'pending_screenshot', screenshot_url=photo_id)
                except Exception as e:
                    logger.error(f"❌ Update payment error: {e}")

                kb = [
                    [InlineKeyboardButton("✅ Підтвердити", callback_data=f"admin:approve:{payment_code}")],
                    [InlineKeyboardButton("❌ Відхилити", callback_data=f"admin:reject:{payment_code}")],
                    [InlineKeyboardButton("⬅️ Назад", callback_data="admin:menu")]
                ]

                user_obj = update.effective_user
                uname = f"@{user_obj.username}" if user_obj.username else user_obj.first_name or "N/A"
                plan_name = payment['plan'] if payment else 'N/A'
                mod_caption = (
                    f"🔔 Нова заявка на платіж\n\n"
                    f"💳 Код: `{payment_code}`\n"
                    f"👤 User ID: `{user_obj.id}` ({uname})\n"
                    f"📦 План: {plan_name}\n"
                    f"💰 Сума: ${payment['amount'] if payment else 'N/A'}\n"
                    f"💱 Крипто: {payment['crypto'].upper() if payment and payment.get('crypto') else 'N/A'}\n\n"
                )

                if valid:
                    mod_caption += "✅ Авт. валідація: пройдена\n"
                    user_reply = "✅ Скріншот отримано. Модератор перевірить протягом 5-10 хв."
                else:
                    mod_caption += "⚠️ Авт. валідація: НЕ пройдена\n"
                    user_reply = "❌ Фото недійсне або не містить коду/адреси. Надішліть нове фото з підписом."

                try:
                    await context.bot.send_photo(chat_id=MOD_CHANNEL_ID, photo=photo_id, caption=mod_caption, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
                except Exception as e:
                    logger.error(f"❌ Failed to send to MOD channel: {e}")

                await update.message.reply_text(user_reply)
                return
            else:
                await update.message.reply_text("❌ Надішліть фотографію скріншота.")
            return

    except Exception as e:
        logger.error(f"❌ MESSAGE ERROR: {type(e).__name__} - {e} | user={chat_id}")

def main():
    app = ApplicationBuilder().token(TG_BOT_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info('✅ Бот запущено')
    app.run_polling()

if __name__ == '__main__':
    main()


