import asyncio
import logging
import sqlite3
import json
from datetime import datetime, date
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiohttp import web
import os

TOKEN = "7686179892:AAFzLrkYLMSuLsi3S51Rq3HgTwrTQIBmXaA"
WEBAPP_URL = "https://unimpeded-tableful-strained.ngrok-free.dev"

# ===== БАЗА ДАННЫХ =====
def init_db():
    conn = sqlite3.connect("cortex.db")
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 0,
            total_taps INTEGER DEFAULT 0,
            energy INTEGER DEFAULT 1000,
            multiplier INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)
    
    # Таблица рефералов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            referred_name TEXT,
            earned INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY (referrer_id) REFERENCES users(user_id)
        )
    """)
    
    # Таблица активированных промокодов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS used_promocodes (
            user_id INTEGER,
            promo_code TEXT,
            used_at TEXT,
            PRIMARY KEY (user_id, promo_code)
        )
    """)
    
    # Таблица ежедневных бонусов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_bonus (
            user_id INTEGER PRIMARY KEY,
            last_claim TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

def get_user(user_id):
    conn = sqlite3.connect("cortex.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance, total_taps, energy, multiplier FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def create_user(user_id, username, first_name, referrer_id=None):
    conn = sqlite3.connect("cortex.db")
    cursor = conn.cursor()
    
    # Проверяем, существует ли пользователь
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    exists = cursor.fetchone()
    
    if not exists:
        # Создаём пользователя
        cursor.execute("""
            INSERT INTO users (user_id, username, first_name, balance, total_taps, energy, multiplier, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username, first_name, 0, 0, 1000, 1, datetime.now().isoformat()))
        
        # Если есть реферер — записываем реферала и начисляем бонус
        if referrer_id and referrer_id != user_id:
            cursor.execute("SELECT * FROM referrals WHERE referrer_id = ? AND referred_id = ?", (referrer_id, user_id))
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO referrals (referrer_id, referred_id, referred_name, earned, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (referrer_id, user_id, first_name, 0, datetime.now().isoformat()))
                
                # Начисляем бонус рефереру (100 монет)
                cursor.execute("UPDATE users SET balance = balance + 100 WHERE user_id = ?", (referrer_id,))
                print(f"✅ Рефереру {referrer_id} начислено 100 монет за приглашение {first_name}")
    
    conn.commit()
    conn.close()

def update_user_stats(user_id, taps, balance, energy):
    conn = sqlite3.connect("cortex.db")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users 
        SET balance = ?, total_taps = total_taps + ?, energy = ?
        WHERE user_id = ?
    """, (balance, taps, energy, user_id))
    conn.commit()
    conn.close()

def get_referral_stats(user_id):
    conn = sqlite3.connect("cortex.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(earned) FROM referrals WHERE referrer_id = ?", (user_id,))
    earned = cursor.fetchone()[0] or 0
    conn.close()
    return count, earned

def get_referrals_list(user_id):
    conn = sqlite3.connect("cortex.db")
    cursor = conn.cursor()
    cursor.execute("SELECT referred_name, created_at, earned FROM referrals WHERE referrer_id = ? ORDER BY created_at DESC", (user_id,))
    result = cursor.fetchall()
    conn.close()
    return result

def get_ref_link(user_id):
    return f"https://t.me/dsadddsdasd_bot?start=ref_{user_id}"

def apply_promocode(user_id, code):
    promocodes = {
        'CRYSTAL500': {'coins': 500, 'energy': 0},
        'ENERGY200': {'coins': 0, 'energy': 200},
        'WELCOME100': {'coins': 100, 'energy': 0},
        'PHANTOM': {'coins': 250, 'energy': 100}
    }
    
    if code not in promocodes:
        return None, "Неверный промокод!"
    
    conn = sqlite3.connect("cortex.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM used_promocodes WHERE user_id = ? AND promo_code = ?", (user_id, code))
    if cursor.fetchone():
        conn.close()
        return None, "Вы уже активировали этот промокод!"
    
    reward = promocodes[code]
    cursor.execute("INSERT INTO used_promocodes (user_id, promo_code, used_at) VALUES (?, ?, ?)",
                   (user_id, code, datetime.now().isoformat()))
    
    if reward['coins'] > 0 or reward['energy'] > 0:
        cursor.execute("UPDATE users SET balance = balance + ?, energy = energy + ? WHERE user_id = ?",
                       (reward['coins'], reward['energy'], user_id))
    
    conn.commit()
    conn.close()
    
    return reward, "Промокод активирован!"

def claim_daily_bonus(user_id):
    conn = sqlite3.connect("cortex.db")
    cursor = conn.cursor()
    
    today = date.today().isoformat()
    cursor.execute("SELECT last_claim FROM daily_bonus WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    if result and result[0] == today:
        conn.close()
        return False, "Бонус уже получен сегодня!"
    
    bonus = 500
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (bonus, user_id))
    cursor.execute("INSERT OR REPLACE INTO daily_bonus (user_id, last_claim) VALUES (?, ?)", (user_id, today))
    
    conn.commit()
    conn.close()
    return True, bonus

def get_top_players(limit=10):
    conn = sqlite3.connect("cortex.db")
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, total_taps, balance FROM users ORDER BY total_taps DESC LIMIT ?", (limit,))
    result = cursor.fetchall()
    conn.close()
    return result

# ===== БОТ =====
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

init_db()

@dp.message(CommandStart())
async def start_command(message: types.Message):
    user = message.from_user
    args = message.text.split()
    
    referrer_id = None
    if len(args) > 1 and 'ref_' in args[0]:
        try:
            referrer_id = int(args[0].split('ref_')[1])
            print(f"📎 Реферальная ссылка от {referrer_id} для {user.id}")
        except:
            pass
    
    # Создаём пользователя (с реферером если есть)
    create_user(user.id, user.username, user.first_name, referrer_id)
    
    # Получаем актуальные данные
    user_data = get_user(user.id)
    balance = user_data[0] if user_data else 0
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Открыть игру", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text="💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals")],
        [InlineKeyboardButton(text="🏆 Топ", callback_data="top")]
    ])
    
    await message.answer(
        f"🚀 <b>Добро пожаловать, {user.first_name}!</b>\n\n"
        f"💎 <b>Твой баланс:</b> {balance} кристаллов\n\n"
        f"✨ <b>Что тебя ждёт:</b>\n"
        f"• Тапай по кристаллу — зарабатывай монеты\n"
        f"• Приглашай друзей — получай +100💎 за каждого\n"
        f"• Забирай ежедневный бонус — 500💎\n"
        f"• Покупай усилители x2 и авто-тап\n\n"
        f"👇 Нажми на кнопку ниже, чтобы начать!",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data == "balance")
async def show_balance(callback: types.CallbackQuery):
    user_data = get_user(callback.from_user.id)
    if user_data:
        balance, total_taps, energy, multiplier = user_data
        await callback.message.edit_text(
            f"👤 <b>Твой профиль</b>\n\n"
            f"💎 <b>Баланс:</b> {balance} кристаллов\n"
            f"🖱️ <b>Всего тапов:</b> {total_taps}\n"
            f"⚡ <b>Энергия:</b> {energy}/1000\n"
            f"⚡ <b>Множитель:</b> x{multiplier}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎮 Играть", web_app=WebAppInfo(url=WEBAPP_URL))],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
            ])
        )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "referrals")
async def show_referrals(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    count, earned = get_referral_stats(user_id)
    ref_link = get_ref_link(user_id)
    referrals_list = get_referrals_list(user_id)
    
    text = f"👥 <b>Реферальная программа</b>\n\n"
    text += f"🔗 <b>Твоя ссылка:</b>\n<code>{ref_link}</code>\n\n"
    text += f"📊 <b>Статистика:</b>\n"
    text += f"• Приглашено друзей: {count}\n"
    text += f"• Заработано: {earned} 💎\n\n"
    text += f"🎁 <b>Бонус:</b> +100💎 за каждого друга + 10% от его дохода!\n\n"
    
    if referrals_list:
        text += "📋 <b>Твои рефералы:</b>\n"
        for name, created, earned in referrals_list[:5]:
            text += f"• {name} — {earned}💎\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Играть", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
        ])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "top")
async def show_top(callback: types.CallbackQuery):
    top = get_top_players(10)
    
    text = "🏆 <b>Топ игроков</b>\n\n"
    if top:
        for i, (name, taps, bal) in enumerate(top):
            text += f"{i+1}. {name} — {taps} тапов | {bal} 💎\n"
    else:
        text += "Пока нет игроков\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Играть", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
        ])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back")
async def back_to_menu(callback: types.CallbackQuery):
    user_data = get_user(callback.from_user.id)
    balance = user_data[0] if user_data else 0
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Открыть игру", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text="💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals")],
        [InlineKeyboardButton(text="🏆 Топ", callback_data="top")]
    ])
    
    await callback.message.edit_text(
        f"🚀 <b>Главное меню</b>\n\n"
        f"💎 <b>Твой баланс:</b> {balance} кристаллов\n\n"
        f"👇 Нажми на кнопку ниже, чтобы продолжить игру!",
        reply_markup=keyboard
    )
    await callback.answer()

# ===== WEBHOOK ДЛЯ MINIAPP =====
async def handle_webapp_data(request):
    try:
        data = await request.json()
        user_id = data.get("user_id")
        taps = data.get("taps", 0)
        balance = data.get("balance", 0)
        energy = data.get("energy", 1000)
        
        if user_id:
            update_user_stats(user_id, taps, balance, energy)
            return web.json_response({"status": "ok", "synced": taps})
        return web.json_response({"status": "error"}, status=400)
    except Exception as e:
        print(f"Error: {e}")
        return web.json_response({"status": "error"}, status=500)

async def handle_promo(request):
    try:
        data = await request.json()
        user_id = data.get("user_id")
        code = data.get("code", "").upper()
        
        reward, msg = apply_promocode(user_id, code)
        if reward:
            return web.json_response({"status": "ok", "reward": reward, "message": msg})
        return web.json_response({"status": "error", "message": msg}, status=400)
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def handle_daily(request):
    try:
        data = await request.json()
        user_id = data.get("user_id")
        
        success, result = claim_daily_bonus(user_id)
        if success:
            return web.json_response({"status": "ok", "bonus": result})
        return web.json_response({"status": "error", "message": result}, status=400)
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def handle_user_data(request):
    try:
        data = await request.json()
        user_id = data.get("user_id")
        
        conn = sqlite3.connect("cortex.db")
        cursor = conn.cursor()
        cursor.execute("SELECT balance, total_taps, energy, multiplier FROM users WHERE user_id = ?", (user_id,))
        user_data = cursor.fetchone()
        
        ref_count, ref_earned = get_referral_stats(user_id)
        
        conn.close()
        
        if user_data:
            return web.json_response({
                "status": "ok",
                "balance": user_data[0],
                "total_taps": user_data[1],
                "energy": user_data[2],
                "multiplier": user_data[3],
                "ref_count": ref_count,
                "ref_earned": ref_earned,
                "ref_link": get_ref_link(user_id)
            })
        return web.json_response({"status": "error"}, status=404)
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def main():
    app = web.Application()
    app.router.add_post("/webapp-data", handle_webapp_data)
    app.router.add_post("/promo", handle_promo)
    app.router.add_post("/daily", handle_daily)
    app.router.add_post("/user-data", handle_user_data)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    
    print("🤖 Бот запущен!")
    print("📡 Сервер на порту 8080")
    print("✅ Реферальная система активна: 100💎 за друга + 10% от его дохода")
    print("✅ База данных синхронизирована")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())