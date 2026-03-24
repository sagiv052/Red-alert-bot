# -*- coding: utf-8 -*-
"""
בוט התרעות אזעקות - גרסה עם Socket.IO (API רשמי)
"""

import sqlite3
import requests
import time
import threading
import asyncio
import logging
import os
import socketio
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ============= לוגים =============
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ============= טוקן =============
TOKEN = os.environ.get('TOKEN', '7668475816:AAEt2Yajc_Q25sxiu1SGkSuOjPM-z5Q6yVk')
RED_ALERT_API_KEY = os.environ.get('RED_ALERT_API_KEY', 'pr_rmwozxvWHMlSVhbVlxZkyqNdmIfGhTsTRuBONQIoOwjgYeiBJidJDnNrxzhKRzqg')

# ============= Socket.IO =============
sio = socketio.Client(logger=False, engineio_logger=False)

# ============= מסד נתונים =============
conn = sqlite3.connect('alerts_bot.db', check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL")
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    alert_mode TEXT DEFAULT 'all'
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS user_cities (
    user_id INTEGER,
    city TEXT,
    PRIMARY KEY (user_id, city)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS user_language (
    user_id INTEGER PRIMARY KEY,
    lang TEXT DEFAULT 'he'
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    night_mode INTEGER DEFAULT 0,
    night_start TEXT DEFAULT '23:00',
    night_end TEXT DEFAULT '07:00'
)
''')

# יצירת טבלת ערים אם לא קיימת
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settlements'")
if not cursor.fetchone():
    logger.info("📦 יוצר טבלת ערים...")
    try:
        from cities_data import ALL_CITIES
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            zone_name TEXT UNIQUE
        )
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS settlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            settlement_name TEXT UNIQUE,
            zone_id INTEGER,
            FOREIGN KEY (zone_id) REFERENCES zones(id)
        )
        ''')
        
        zones_dict = {}
        for city, zone in ALL_CITIES:
            if zone not in zones_dict:
                cursor.execute('INSERT OR IGNORE INTO zones (zone_name) VALUES (?)', (zone,))
                conn.commit()
                cursor.execute('SELECT id FROM zones WHERE zone_name = ?', (zone,))
                result = cursor.fetchone()
                if result:
                    zones_dict[zone] = result[0]
        
        for city, zone in ALL_CITIES:
            zone_id = zones_dict.get(zone)
            if zone_id:
                cursor.execute('INSERT OR IGNORE INTO settlements (settlement_name, zone_id) VALUES (?, ?)', (city, zone_id))
        conn.commit()
        logger.info("✅ מאגר הערים נוצר בהצלחה")
    except Exception as e:
        logger.error(f"שגיאה ביצירת מאגר ערים: {e}")

conn.commit()

# ============= מילון שפות =============
TEXTS = {
    'he': {
        'welcome': "ברוכים הבאים לבוט התרעות אזעקות! 🚨\n\nבחר שפה:",
        'main_menu': "תפריט ראשי:",
        'settings': "🔔 הגדרות התראות",
        'info': "ℹ️ מידע",
        'help': "🆘 סיוע",
        'change_lang': "🌐 שנה שפה",
        'back': "🔙 חזרה",
        'all_israel': "🌍 כל הארץ",
        'my_areas': "🎯 איזור ספציפי בלבד",
        'surroundings': "🌍✨ איזורך והסביבה",
        'manage_cities': "📝 ניהול ישובים",
        'my_cities': "📋 הישובים שלי",
        'add_city': "➕ הוסף ישוב",
        'remove_city': "❌ הסר ישוב",
        'help_text': "🆘 **סיוע נפשי:**\nנט\"ל: 1-800-363-363\nער\"ן: 1201",
        'info_text': "🤖 **בוט התרעות ואזעקות**\n\nנוצר על ידי אלוף\nמנהל אתר נושמים מזרחית\nתהנו 🚀",
        'alert_message': "🔴 **אזעקה!** 🔴\n\n{areas}\n\n🕒 {time}\n⚠️ היכנסו למרחב מוגן!",
        'long_range_alert': "🔴 **אזעקה - שיגור ארוך טווח!** 🔴\n\n{areas}\n\n🕒 {time}\n⚠️ היכנסו למרחב מוגן!\n⏱️ זמן תגובה: 5-10 דקות",
        'city_added': "✅ {city} נוסף בהצלחה!",
        'city_removed': "✅ {city} הוסר",
        'city_exists': "❌ {city} כבר קיים",
        'city_limit': "❌ מקסימום 5 ישובים",
        'no_cities': "📭 אין לך ישובים",
        'mode_updated_all': "✅ תקבל התראות מכל הארץ",
        'mode_updated_only': "✅ תקבל התראות רק עבור:\n{areas}",
        'mode_updated_surroundings': "✅ תקבל התראות עבור:\n{areas}",
        'mode_no_cities': "⚠️ בחרת איזור ספציפי אבל אין לך ישובים!\n\nלחץ על 📝 ניהול ישובים והוסף ישובים",
        'enter_city': "📝 **הוסף ישוב**\n\nהזן שם ישוב:",
        'enter_city_remove': "📝 **הסר ישוב**\n\nהישובים שלך:\n{cities}\n\nהזן שם ישוב להסרה:",
        'cancelled': "❌ בוטל",
        'cancel': "❌ ביטול",
        'night_mode': "🌙 מצב לילה",
        'night_status_on': "🌙 מצב לילה: ✅ פעיל",
        'night_status_off': "🌙 מצב לילה: ❌ לא פעיל",
        'night_current': "🌙 **מצב לילה אישי**\n\nסטטוס: {status}\nשעות: {start} - {end}",
        'night_activate': "✅ הפעל מצב לילה",
        'night_deactivate': "❌ כבה מצב לילה",
        'night_set_hours': "⏰ הגדר שעות חדשות",
        'night_ask': "⏰ **הגדר שעות מצב לילה אישיות**\n\nשלח בפורמט: התחלה-סיום\nלדוגמה: 23:00-07:00",
        'night_updated': "✅ שעות מצב לילה עודכנו: {start} - {end}",
        'night_activated': "✅ מצב לילה הופעל עבורך",
        'night_deactivated': "❌ מצב לילה כובה עבורך",
        'night_format_error': "❌ פורמט לא תקין!\n\nשלח בפורמט: 23:00-07:00"
    },
    'en': {
        'welcome': "Welcome to the Emergency Alert Bot! 🚨\n\nSelect language:",
        'main_menu': "Main Menu:",
        'settings': "🔔 Alert Settings",
        'info': "ℹ️ Info",
        'help': "🆘 Help",
        'change_lang': "🌐 Change Language",
        'back': "🔙 Back",
        'all_israel': "🌍 All Israel",
        'my_areas': "🎯 Specific Area Only",
        'surroundings': "🌍✨ Your Area and Surroundings",
        'manage_cities': "📝 Manage Cities",
        'my_cities': "📋 My Cities",
        'add_city': "➕ Add City",
        'remove_city': "❌ Remove City",
        'help_text': "🆘 **Mental Health Support:**\nNATAL: 1-800-363-363\nERAN: 1201",
        'info_text': "🤖 **Alert Bot**\n\nCreated by Aluf\nManager of Noshim Mizrahit website\nEnjoy 🚀",
        'alert_message': "🔴 **Alert!** 🔴\n\n{areas}\n\n🕒 {time}\n⚠️ Enter protected area!",
        'long_range_alert': "🔴 **Long Range Alert!** 🔴\n\n{areas}\n\n🕒 {time}\n⚠️ Enter protected area!\n⏱️ Response time: 5-10 minutes",
        'city_added': "✅ {city} added successfully!",
        'city_removed': "✅ {city} removed",
        'city_exists': "❌ {city} already exists",
        'city_limit': "❌ Maximum 5 cities",
        'no_cities': "📭 No cities added",
        'mode_updated_all': "✅ You will receive alerts from all Israel",
        'mode_updated_only': "✅ You will receive alerts only for:\n{areas}",
        'mode_updated_surroundings': "✅ You will receive alerts for:\n{areas}",
        'mode_no_cities': "⚠️ You selected 'Specific Area' but you have no cities!\n\nClick 📝 Manage Cities and add cities",
        'enter_city': "📝 **Add City**\n\nEnter city name:",
        'enter_city_remove': "📝 **Remove City**\n\nYour cities:\n{cities}\n\nEnter city name to remove:",
        'cancelled': "❌ Cancelled",
        'cancel': "❌ Cancel",
        'night_mode': "🌙 Night Mode",
        'night_status_on': "🌙 Night Mode: ✅ Active",
        'night_status_off': "🌙 Night Mode: ❌ Inactive",
        'night_current': "🌙 **Personal Night Mode**\n\nStatus: {status}\nHours: {start} - {end}",
        'night_activate': "✅ Activate Night Mode",
        'night_deactivate': "❌ Deactivate Night Mode",
        'night_set_hours': "⏰ Set New Hours",
        'night_ask': "⏰ **Set Personal Night Mode Hours**\n\nSend format: start-end\nExample: 23:00-07:00",
        'night_updated': "✅ Night mode hours updated: {start} - {end}",
        'night_activated': "✅ Night mode activated for you",
        'night_deactivated': "❌ Night mode deactivated for you",
        'night_format_error': "❌ Invalid format!\n\nSend format: 23:00-07:00"
    },
    'ru': {
        'welcome': "Добро пожаловать в бот экстренных оповещений! 🚨\n\nВыберите язык:",
        'main_menu': "Главное меню:",
        'settings': "🔔 Настройки оповещений",
        'info': "ℹ️ Информация",
        'help': "🆘 Помощь",
        'change_lang': "🌐 Сменить язык",
        'back': "🔙 Назад",
        'all_israel': "🌍 Вся страна",
        'my_areas': "🎯 Только конкретный район",
        'surroundings': "🌍✨ Ваш район и окрестности",
        'manage_cities': "📝 Управление городами",
        'my_cities': "📋 Мои города",
        'add_city': "➕ Добавить город",
        'remove_city': "❌ Удалить город",
        'help_text': "🆘 **Психологическая поддержка:**\nНАТАЛ: 1-800-363-363\nЭРАН: 1201",
        'info_text': "🤖 **Бот оповещений**\n\nСоздано Алуфом\nМенеджер сайта Noshim Mizrahit\nНаслаждайтесь 🚀",
        'alert_message': "🔴 **Тревога!** 🔴\n\n{areas}\n\n🕒 {time}\n⚠️ Зайдите в укрытие!",
        'long_range_alert': "🔴 **Тревога - дальний запуск!** 🔴\n\n{areas}\n\n🕒 {time}\n⚠️ Зайдите в укрытие!\n⏱️ Время реакции: 5-10 минут",
        'city_added': "✅ {city} успешно добавлен!",
        'city_removed': "✅ {city} удален",
        'city_exists': "❌ {city} уже существует",
        'city_limit': "❌ Максимум 5 городов",
        'no_cities': "📭 Нет добавленных городов",
        'mode_updated_all': "✅ Вы будете получать оповещения по всей стране",
        'mode_updated_only': "✅ Вы будете получать оповещения только для:\n{areas}",
        'mode_updated_surroundings': "✅ Вы будете получать оповещения для:\n{areas}",
        'mode_no_cities': "⚠️ Вы выбрали 'Только конкретный район', но у вас нет городов!\n\nНажмите 📝 Управление городами и добавьте города",
        'enter_city': "📝 **Добавить город**\n\nВведите название города:",
        'enter_city_remove': "📝 **Удалить город**\n\nВаши города:\n{cities}\n\nВведите название города для удаления:",
        'cancelled': "❌ Отменено",
        'cancel': "❌ Отмена",
        'night_mode': "🌙 Ночной режим",
        'night_status_on': "🌙 Ночной режим: ✅ Активен",
        'night_status_off': "🌙 Ночной режим: ❌ Не активен",
        'night_current': "🌙 **Личный ночной режим**\n\nСтатус: {status}\nЧасы: {start} - {end}",
        'night_activate': "✅ Включить ночной режим",
        'night_deactivate': "❌ Выключить ночной режим",
        'night_set_hours': "⏰ Установить новые часы",
        'night_ask': "⏰ **Установите личные часы ночного режима**\n\nОтправьте формат: начало-конец\nНапример: 23:00-07:00",
        'night_updated': "✅ Часы ночного режима обновлены: {start} - {end}",
        'night_activated': "✅ Ночной режим активирован для вас",
        'night_deactivated': "❌ Ночной режим деактивирован для вас",
        'night_format_error': "❌ Неверный формат!\n\nОтправьте формат: 23:00-07:00"
    }
}

# ============= פונקציות עזר =============
def get_user_lang(user_id):
    c = conn.cursor()
    c.execute('SELECT lang FROM user_language WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    return result[0] if result else 'he'

def set_user_lang(user_id, lang):
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO user_language (user_id, lang) VALUES (?, ?)', (user_id, lang))
    conn.commit()

def get_text(user_id, key, **kwargs):
    lang = get_user_lang(user_id)
    text = TEXTS.get(lang, TEXTS['he']).get(key, TEXTS['he'][key])
    if kwargs:
        return text.format(**kwargs)
    return text

def get_user_mode(user_id):
    c = conn.cursor()
    c.execute('SELECT alert_mode FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    return result[0] if result else 'all'

def set_user_mode(user_id, mode):
    c = conn.cursor()
    c.execute('UPDATE users SET alert_mode = ? WHERE user_id = ?', (mode, user_id))
    conn.commit()

def get_user_cities(user_id):
    c = conn.cursor()
    c.execute('SELECT city FROM user_cities WHERE user_id = ?', (user_id,))
    return [row[0] for row in c.fetchall()]

def add_city(user_id, city):
    city = city.strip()
    if not city:
        return False, "שם ישוב לא תקין"
    
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM user_cities WHERE user_id = ?', (user_id,))
    if c.fetchone()[0] >= 5:
        return False, get_text(user_id, 'city_limit')
    
    try:
        c.execute('INSERT INTO user_cities (user_id, city) VALUES (?, ?)', (user_id, city))
        conn.commit()
        return True, get_text(user_id, 'city_added', city=city)
    except sqlite3.IntegrityError:
        return False, get_text(user_id, 'city_exists', city=city)
    except Exception as e:
        logger.error(f"שגיאה בהוספת עיר: {e}")
        return False, "❌ שגיאה"

def remove_city(user_id, city):
    city = city.strip()
    c = conn.cursor()
    c.execute('DELETE FROM user_cities WHERE user_id = ? AND city = ?', (user_id, city))
    conn.commit()
    if c.rowcount > 0:
        return True, get_text(user_id, 'city_removed', city=city)
    return False, get_text(user_id, 'city_exists', city=city)

def register_user(user_id, username):
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (user_id, username, alert_mode) VALUES (?, ?, ?)', (user_id, username, 'all'))
    c.execute('INSERT OR IGNORE INTO user_settings (user_id, night_mode, night_start, night_end) VALUES (?, 0, "23:00", "07:00")', (user_id,))
    conn.commit()

def get_expanded_cities(city_name):
    """מחזיר רשימה מורחבת של ערים לפי אזור ממסד הנתונים"""
    c = conn.cursor()
    try:
        c.execute('''
            SELECT z.zone_name FROM settlements s 
            JOIN zones z ON s.zone_id = z.id 
            WHERE s.settlement_name = ? OR s.settlement_name LIKE ?
        ''', (city_name, f'%{city_name}%'))
        zone = c.fetchone()
        if zone:
            c.execute('''
                SELECT settlement_name FROM settlements s 
                JOIN zones z ON s.zone_id = z.id 
                WHERE z.zone_name = ?
            ''', (zone[0],))
            return [row[0] for row in c.fetchall()]
    except Exception as e:
        logger.error(f"שגיאה בחיפוש ערים: {e}")
    return [city_name]

# ============= פונקציות מצב לילה =============
def get_user_night_mode(user_id):
    c = conn.cursor()
    c.execute('SELECT night_mode FROM user_settings WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    return result[0] == 1 if result else False

def set_user_night_mode(user_id, enabled):
    c = conn.cursor()
    c.execute('UPDATE user_settings SET night_mode = ? WHERE user_id = ?', (1 if enabled else 0, user_id))
    conn.commit()

def get_user_night_hours(user_id):
    c = conn.cursor()
    c.execute('SELECT night_start, night_end FROM user_settings WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    return (result[0] if result else '23:00'), (result[1] if result else '07:00')

def set_user_night_hours(user_id, start, end):
    c = conn.cursor()
    c.execute('UPDATE user_settings SET night_start = ?, night_end = ? WHERE user_id = ?', (start, end, user_id))
    conn.commit()

def is_night_time_for_user(user_id):
    if not get_user_night_mode(user_id):
        return False
    now = datetime.now().strftime('%H:%M')
    start, end = get_user_night_hours(user_id)
    if start < end:
        return start <= now < end
    else:
        return now >= start or now < end

# ============= פונקציות API (Socket.IO) =============
def get_alert_area(alert):
    """מחזיר את שם האזור מהתראה (מבנה של Socket.IO)"""
    # מבנה של redalert.orielhaim.com
    if 'cities' in alert and alert['cities']:
        return alert['cities'][0] if isinstance(alert['cities'], list) else alert['cities']
    if 'city' in alert and alert['city']:
        return alert['city']
    if 'area' in alert and alert['area']:
        return alert['area']
    return None

def is_long_range_alert(alert):
    threat = alert.get('threat', 0)
    area = get_alert_area(alert) or ""
    area_lower = area.lower()
    # threat = 4 מציין שיגור ארוך טווח
    if threat == 4:
        return True
    long_range_zones = ['מרכז', 'דרום', 'אילת', 'ים המלח', 'הערבה', 'ממשית', 'יטבתה']
    for zone in long_range_zones:
        if zone in area_lower:
            return True
    return False

def should_send_alert(user_id, alert_area):
    mode = get_user_mode(user_id)
    
    if mode == 'all':
        return True
    elif mode == 'only_city':
        cities = get_user_cities(user_id)
        if not cities:
            return False
        alert_lower = alert_area.lower()
        for city in cities:
            if city.lower() in alert_lower or alert_lower in city.lower():
                return True
        return False
    elif mode == 'city_and_surroundings':
        cities = get_user_cities(user_id)
        if not cities:
            return False
        alert_lower = alert_area.lower()
        for city in cities:
            expanded = get_expanded_cities(city)
            for exp_city in expanded:
                if exp_city.lower() in alert_lower or alert_lower in exp_city.lower():
                    return True
        return False
    
    return False

# ============= שליחת הודעות =============
application = None

async def send_msg(chat_id, text, keyboard=None):
    try:
        await application.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown', reply_markup=keyboard)
        return True
    except Exception as e:
        logger.error(f"שגיאה בשליחה: {e}")
        return False

def send_safe(chat_id, text, keyboard=None):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(send_msg(chat_id, text, keyboard))
        loop.close()
        return result
    else:
        return asyncio.create_task(send_msg(chat_id, text, keyboard))

# ============= אזעקות (Socket.IO) =============
processed_alerts = set()
pending_alerts = []
pending_lock = threading.Lock()
send_timer = None
SEND_DELAY = 8

def send_batch():
    global pending_alerts, send_timer
    with pending_lock:
        if not pending_alerts:
            return
        alerts = pending_alerts.copy()
        pending_alerts = []
        send_timer = None

    areas = []
    threat_type = 0
    alert_time = time.time()
    
    for a in alerts:
        area = get_alert_area(a)
        if area:
            areas.append(area)
            threat_type = max(threat_type, a.get('threat', 0))
            alert_time = a.get('date', alert_time)
        else:
            areas.append("אזור לא ידוע")

    unique_areas = []
    for area in areas:
        if area not in unique_areas:
            unique_areas.append(area)

    c = conn.cursor()
    c.execute('SELECT user_id FROM users')
    users = c.fetchall()

    for (uid,) in users:
        if not should_send_alert(uid, unique_areas[0] if unique_areas else ""):
            continue
        
        if is_night_time_for_user(uid):
            continue
        
        is_long = is_long_range_alert({'city': unique_areas[0] if unique_areas else '', 'threat': threat_type})
        time_str = datetime.fromtimestamp(alert_time).strftime('%H:%M:%S')
        areas_text = "\n".join([f"• {a}" for a in unique_areas])
        
        if is_long:
            msg = get_text(uid, 'long_range_alert', areas=areas_text, time=time_str)
        else:
            msg = get_text(uid, 'alert_message', areas=areas_text, time=time_str)
        
        send_safe(uid, msg)

def add_alert(alert):
    global send_timer
    alert_id = alert.get('id')
    if alert_id and alert_id in processed_alerts:
        return
    area = get_alert_area(alert)
    if not area:
        return
    if alert_id:
        processed_alerts.add(alert_id)
    logger.info(f"➕ אזעקה: {area}")
    with pending_lock:
        pending_alerts.append(alert)
    if send_timer:
        send_timer.cancel()
    send_timer = threading.Timer(SEND_DELAY, send_batch)
    send_timer.start()

# ============= Socket.IO Events =============
@sio.on('connect')
def on_connect():
    logger.info("✅ התחבר ל-Socket.IO של RedAlert")
    # שלח API key לאימות
    sio.emit('authenticate', {'api_key': RED_ALERT_API_KEY})

@sio.on('authenticated')
def on_authenticated(data):
    logger.info(f"✅ אושר: {data}")

@sio.on('alert')
def on_alert(data):
    logger.info(f"🔴 התראה: {data}")
    # עיבוד ההתראה
    alert_time = data.get('time', time.time())
    if isinstance(alert_time, str):
        try:
            alert_time = time.mktime(datetime.strptime(alert_time, '%Y-%m-%d %H:%M:%S').timetuple())
        except:
            alert_time = time.time()
    
    alert = {
        'id': data.get('id', f"alert_{alert_time}"),
        'city': data.get('cities', ['אזור לא ידוע'])[0] if data.get('cities') else 'אזור לא ידוע',
        'date': alert_time,
        'threat': data.get('threat', 0)
    }
    add_alert(alert)

@sio.on('rockets')
def on_rockets(data):
    logger.info(f"🚀 התראת רקטות: {data}")
    alert_time = data.get('time', time.time())
    if isinstance(alert_time, str):
        try:
            alert_time = time.mktime(datetime.strptime(alert_time, '%Y-%m-%d %H:%M:%S').timetuple())
        except:
            alert_time = time.time()
    
    alert = {
        'id': data.get('id', f"rockets_{alert_time}"),
        'city': data.get('cities', ['אזור לא ידוע'])[0] if data.get('cities') else 'אזור לא ידוע',
        'date': alert_time,
        'threat': data.get('threat', 0)
    }
    add_alert(alert)

@sio.on('hostileAircraftIntrusion')
def on_aircraft(data):
    logger.info(f"✈️ חדירת כלי טיס: {data}")
    alert_time = data.get('time', time.time())
    if isinstance(alert_time, str):
        try:
            alert_time = time.mktime(datetime.strptime(alert_time, '%Y-%m-%d %H:%M:%S').timetuple())
        except:
            alert_time = time.time()
    
    alert = {
        'id': data.get('id', f"aircraft_{alert_time}"),
        'city': data.get('cities', ['אזור לא ידוע'])[0] if data.get('cities') else 'אזור לא ידוע',
        'date': alert_time,
        'threat': data.get('threat', 1)
    }
    add_alert(alert)

@sio.on('disconnect')
def on_disconnect():
    logger.warning("⚠️ נותק מ-Socket.IO, מנסה להתחבר מחדש...")

def start_socketio():
    """מתחבר ל-Socket.IO ומקשיב להתראות"""
    while True:
        try:
            sio.connect('https://redalert.orielhaim.com', transports=['websocket'])
            sio.wait()
        except Exception as e:
            logger.error(f"שגיאת Socket.IO: {e}")
            time.sleep(5)

# ============= תפריטים =============
def main_keyboard(user_id):
    return ReplyKeyboardMarkup([
        [get_text(user_id, 'settings')],
        [get_text(user_id, 'info'), get_text(user_id, 'help')],
        [get_text(user_id, 'change_lang')]
    ], resize_keyboard=True)

def settings_keyboard(user_id):
    mode = get_user_mode(user_id)
    if mode == 'all':
        return ReplyKeyboardMarkup([
            [get_text(user_id, 'all_israel') + ' ✅'],
            [get_text(user_id, 'my_areas')],
            [get_text(user_id, 'surroundings')],
            [get_text(user_id, 'manage_cities')],
            [get_text(user_id, 'night_mode')],
            [get_text(user_id, 'back')]
        ], resize_keyboard=True)
    elif mode == 'only_city':
        return ReplyKeyboardMarkup([
            [get_text(user_id, 'all_israel')],
            [get_text(user_id, 'my_areas') + ' ✅'],
            [get_text(user_id, 'surroundings')],
            [get_text(user_id, 'manage_cities')],
            [get_text(user_id, 'night_mode')],
            [get_text(user_id, 'back')]
        ], resize_keyboard=True)
    else:
        return ReplyKeyboardMarkup([
            [get_text(user_id, 'all_israel')],
            [get_text(user_id, 'my_areas')],
            [get_text(user_id, 'surroundings') + ' ✅'],
            [get_text(user_id, 'manage_cities')],
            [get_text(user_id, 'night_mode')],
            [get_text(user_id, 'back')]
        ], resize_keyboard=True)

def cities_keyboard(user_id):
    return ReplyKeyboardMarkup([
        [get_text(user_id, 'add_city'), get_text(user_id, 'remove_city')],
        [get_text(user_id, 'my_cities')],
        [get_text(user_id, 'back')]
    ], resize_keyboard=True)

def night_keyboard(user_id):
    status = get_text(user_id, 'night_status_on') if get_user_night_mode(user_id) else get_text(user_id, 'night_status_off')
    start, end = get_user_night_hours(user_id)
    return ReplyKeyboardMarkup([
        [status],
        [get_text(user_id, 'night_activate'), get_text(user_id, 'night_deactivate')],
        [get_text(user_id, 'night_set_hours')],
        [get_text(user_id, 'back')]
    ], resize_keyboard=True)

def cancel_keyboard(user_id):
    return ReplyKeyboardMarkup([[get_text(user_id, 'cancel')]], resize_keyboard=True)

def lang_keyboard():
    return ReplyKeyboardMarkup([['🇮🇱 עברית', '🇬🇧 English', '🇷🇺 Русский']], resize_keyboard=True)

# ============= Handlers =============
async def start(update: Update, context):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    register_user(user_id, username)
    await update.message.reply_text("🌐 ברוכים הבאים! / Welcome! / Добро пожаловать!\n\nבחר שפה / Choose language / Выберите язык:", reply_markup=lang_keyboard())

async def handle_message(update: Update, context):
    user_id = update.effective_user.id
    text = update.message.text

    # בחירת שפה
    if text in ['🇮🇱 עברית', '🇬🇧 English', '🇷🇺 Русский']:
        lang = {'🇮🇱 עברית': 'he', '🇬🇧 English': 'en', '🇷🇺 Русский': 'ru'}[text]
        set_user_lang(user_id, lang)
        await update.message.reply_text(get_text(user_id, 'welcome'), reply_markup=main_keyboard(user_id))
        return

    # טיפול בהקלדת ישוב
    if context.user_data.get('waiting_for_city'):
        if text == get_text(user_id, 'cancel'):
            context.user_data.pop('waiting_for_city', None)
            context.user_data.pop('city_action', None)
            await update.message.reply_text(get_text(user_id, 'cancelled'), reply_markup=cities_keyboard(user_id))
            return
        action = context.user_data.pop('city_action')
        city = text.strip()
        if action == 'add':
            success, msg = add_city(user_id, city)
            await update.message.reply_text(msg, reply_markup=cities_keyboard(user_id))
            if success:
                cities = get_user_cities(user_id)
                if cities:
                    await update.message.reply_text(get_text(user_id, 'my_cities') + f"\n\n" + "\n".join([f"• {c}" for c in cities]), reply_markup=cities_keyboard(user_id))
        else:
            success, msg = remove_city(user_id, city)
            await update.message.reply_text(msg, reply_markup=cities_keyboard(user_id))
            cities = get_user_cities(user_id)
            if cities:
                await update.message.reply_text(get_text(user_id, 'my_cities') + f"\n\n" + "\n".join([f"• {c}" for c in cities]), reply_markup=cities_keyboard(user_id))
        context.user_data.pop('waiting_for_city', None)
        return

    # טיפול בהקלדת שעות מצב לילה
    if context.user_data.get('waiting_night_hours'):
        hours = text.strip()
        context.user_data.pop('waiting_night_hours')
        try:
            if '-' not in hours:
                raise ValueError()
            start, end = hours.split('-')
            datetime.strptime(start, '%H:%M')
            datetime.strptime(end, '%H:%M')
            set_user_night_hours(user_id, start, end)
            await update.message.reply_text(get_text(user_id, 'night_updated', start=start, end=end), reply_markup=night_keyboard(user_id))
        except:
            await update.message.reply_text(get_text(user_id, 'night_format_error'), reply_markup=night_keyboard(user_id))
        return

    # תפריט ראשי
    if text == get_text(user_id, 'settings'):
        await update.message.reply_text(get_text(user_id, 'settings'), reply_markup=settings_keyboard(user_id))
    elif text == get_text(user_id, 'info'):
        await update.message.reply_text(get_text(user_id, 'info_text'), reply_markup=main_keyboard(user_id))
    elif text == get_text(user_id, 'help'):
        await update.message.reply_text(get_text(user_id, 'help_text'), reply_markup=main_keyboard(user_id))
    elif text == get_text(user_id, 'change_lang'):
        await update.message.reply_text("🌐 בחר שפה / Choose language / Выберите язык:", reply_markup=lang_keyboard())
    elif text == get_text(user_id, 'back'):
        await update.message.reply_text(get_text(user_id, 'main_menu'), reply_markup=main_keyboard(user_id))
    
    # הגדרות התראות
    elif text == get_text(user_id, 'all_israel') or text == get_text(user_id, 'all_israel') + ' ✅':
        set_user_mode(user_id, 'all')
        await update.message.reply_text(get_text(user_id, 'mode_updated_all'), reply_markup=settings_keyboard(user_id))
    elif text == get_text(user_id, 'my_areas') or text == get_text(user_id, 'my_areas') + ' ✅':
        set_user_mode(user_id, 'only_city')
        cities = get_user_cities(user_id)
        if cities:
            await update.message.reply_text(get_text(user_id, 'mode_updated_only', areas="\n".join([f"📍 {c}" for c in cities])), reply_markup=settings_keyboard(user_id))
        else:
            await update.message.reply_text(get_text(user_id, 'mode_no_cities'), reply_markup=settings_keyboard(user_id))
    elif text == get_text(user_id, 'surroundings') or text == get_text(user_id, 'surroundings') + ' ✅':
        set_user_mode(user_id, 'city_and_surroundings')
        cities = get_user_cities(user_id)
        if cities:
            all_cities = []
            for city in cities:
                all_cities.extend(get_expanded_cities(city))
            all_cities = list(dict.fromkeys(all_cities))
            await update.message.reply_text(get_text(user_id, 'mode_updated_surroundings', areas="\n".join([f"📍 {c}" for c in all_cities[:10]]) + (f"\n... ועוד {len(all_cities)-10} ישובים" if len(all_cities) > 10 else "")), reply_markup=settings_keyboard(user_id))
        else:
            await update.message.reply_text(get_text(user_id, 'mode_no_cities'), reply_markup=settings_keyboard(user_id))
    elif text == get_text(user_id, 'manage_cities'):
        cities = get_user_cities(user_id)
        if cities:
            msg = get_text(user_id, 'my_cities') + f"\n\n" + "\n".join([f"• {c}" for c in cities])
        else:
            msg = get_text(user_id, 'no_cities')
        await update.message.reply_text(msg, reply_markup=cities_keyboard(user_id))
    
    # ניהול ישובים
    elif text == get_text(user_id, 'add_city'):
        context.user_data['waiting_for_city'] = True
        context.user_data['city_action'] = 'add'
        await update.message.reply_text(get_text(user_id, 'enter_city'), reply_markup=cancel_keyboard(user_id))
    elif text == get_text(user_id, 'remove_city'):
        cities = get_user_cities(user_id)
        if not cities:
            await update.message.reply_text(get_text(user_id, 'no_cities'), reply_markup=cities_keyboard(user_id))
        else:
            context.user_data['waiting_for_city'] = True
            context.user_data['city_action'] = 'remove'
            await update.message.reply_text(get_text(user_id, 'enter_city_remove', cities="\n".join([f"• {c}" for c in cities])), reply_markup=cancel_keyboard(user_id))
    elif text == get_text(user_id, 'my_cities'):
        cities = get_user_cities(user_id)
        if cities:
            await update.message.reply_text(get_text(user_id, 'my_cities') + f"\n\n" + "\n".join([f"• {c}" for c in cities]), reply_markup=cities_keyboard(user_id))
        else:
            await update.message.reply_text(get_text(user_id, 'no_cities'), reply_markup=cities_keyboard(user_id))
    
    # מצב לילה
    elif text == get_text(user_id, 'night_mode'):
        status = get_text(user_id, 'night_status_on') if get_user_night_mode(user_id) else get_text(user_id, 'night_status_off')
        start, end = get_user_night_hours(user_id)
        await update.message.reply_text(get_text(user_id, 'night_current', status=status, start=start, end=end), reply_markup=night_keyboard(user_id))
    elif text == get_text(user_id, 'night_activate'):
        set_user_night_mode(user_id, True)
        await update.message.reply_text(get_text(user_id, 'night_activated'), reply_markup=night_keyboard(user_id))
    elif text == get_text(user_id, 'night_deactivate'):
        set_user_night_mode(user_id, False)
        await update.message.reply_text(get_text(user_id, 'night_deactivated'), reply_markup=night_keyboard(user_id))
    elif text == get_text(user_id, 'night_set_hours'):
        context.user_data['waiting_night_hours'] = True
        await update.message.reply_text(get_text(user_id, 'night_ask'), reply_markup=ReplyKeyboardRemove())
    
    else:
        await update.message.reply_text("אנא השתמש בכפתורים", reply_markup=main_keyboard(user_id))

# ============= הרצה =============
def main():
    global application
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # הפעלת Socket.IO בת'רד נפרד
    socketio_thread = threading.Thread(target=start_socketio, daemon=True)
    socketio_thread.start()

    print("=" * 50)
    print("🚀 בוט התרעות אזעקות עלה בהצלחה!")
    print("🔌 מתחבר ל-API הרשמי של RedAlert...")
    print("=" * 50)
    print("📜 איך להשתמש:")
    print("1. שלח /start")
    print("2. לחץ על 🔔 הגדרות התראות")
    print("3. בחר מצב: כל הארץ / איזור ספציפי בלבד / איזורך והסביבה")
    print("4. לחץ על 📝 ניהול ישובים")
    print("5. לחץ על ➕ הוסף ישוב")
    print("6. הקלד שם ישוב - תקבל אישור")
    print("=" * 50)

    application.run_polling()

if __name__ == '__main__':
    main()
