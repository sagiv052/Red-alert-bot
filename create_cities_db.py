# -*- coding: utf-8 -*-
"""
יצירת מאגר הערים במסד הנתונים
"""

import sqlite3
from cities_data import ALL_CITIES

# חיבור למסד הנתונים
conn = sqlite3.connect('alerts_bot.db')
cursor = conn.cursor()

# יצירת טבלת אזורים
cursor.execute('''
CREATE TABLE IF NOT EXISTS zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_name TEXT UNIQUE
)
''')

# יצירת טבלת ישובים
cursor.execute('''
CREATE TABLE IF NOT EXISTS settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    settlement_name TEXT UNIQUE,
    zone_id INTEGER,
    FOREIGN KEY (zone_id) REFERENCES zones(id)
)
''')

# הוספת אזורים
zones_dict = {}
for city, zone in ALL_CITIES:
    if zone not in zones_dict:
        cursor.execute('INSERT OR IGNORE INTO zones (zone_name) VALUES (?)', (zone,))
        conn.commit()
        cursor.execute('SELECT id FROM zones WHERE zone_name = ?', (zone,))
        result = cursor.fetchone()
        if result:
            zones_dict[zone] = result[0]

# הוספת ישובים
for city, zone in ALL_CITIES:
    zone_id = zones_dict.get(zone)
    if zone_id:
        cursor.execute('INSERT OR IGNORE INTO settlements (settlement_name, zone_id) VALUES (?, ?)', (city, zone_id))
    else:
        print(f"⚠️ אזור לא נמצא: {zone} עבור {city}")

conn.commit()

# הצגת סטטיסטיקה
cursor.execute('SELECT COUNT(*) FROM settlements')
settlements_count = cursor.fetchone()[0]
cursor.execute('SELECT COUNT(*) FROM zones')
zones_count = cursor.fetchone()[0]

print("=" * 50)
print("✅ מאגר הערים נוצר בהצלחה!")
print(f"📊 סה\"כ ישובים: {settlements_count}")
print(f"📊 סה\"כ אזורים: {zones_count}")
print("=" * 50)

# הצגת דוגמה
print("\n📋 דוגמה לישובים:")
cursor.execute('SELECT s.settlement_name, z.zone_name FROM settlements s JOIN zones z ON s.zone_id = z.id LIMIT 10')
for settlement, zone in cursor.fetchall():
    print(f"   📍 {settlement} → {zone}")

conn.close()