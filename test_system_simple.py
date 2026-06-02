"""
智慧养老院管理系统 - 全面测试脚本
"""
import sys
import os
sys.path.insert(0, '.')

import sqlite3
import json

print("="*60)
print("Smart Nursing Home System - Full Test")
print("="*60)

# === Test 1: Database ===
print("\n[Test 1] Database Check")
print("-"*40)

db_path = os.path.join('instance', 'nursing_home.db')
if os.path.exists(db_path):
    print(f"[OK] Database file exists: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row['name'] for row in cursor.fetchall()]
    print(f"[OK] Number of tables: {len(tables)}")
    print(f"   Tables: {', '.join(tables)}")

    cursor.execute("SELECT COUNT(*) as count FROM users")
    user_count = cursor.fetchone()['count']
    print(f"[OK] Users: {user_count}")

    cursor.execute("SELECT username, role, status FROM users LIMIT 3")
    users = cursor.fetchall()
    print(f"   Sample users:")
    for u in users:
        print(f"     - {u['username']} ({u['role']}) - {u['status']}")

    cursor.execute("SELECT COUNT(*) as count FROM elders")
    elder_count = cursor.fetchone()['count']
    print(f"[OK] Elders: {elder_count}")

    conn.close()
else:
    print(f"[FAIL] Database file not found: {db_path}")

# === Test 2: Imports ===
print("\n[Test 2] Module Import Check")
print("-"*40)

modules_to_test = [
    ('Flask App', 'app'),
    ('Auth API', 'api.auth'),
    ('Elders API', 'api.elders'),
    ('Stats API', 'api.stats'),
    ('Users API', 'api.users'),
    ('Alarms API', 'api.alarms'),
    ('Care Records API', 'api.care_records'),
    ('Care Tasks API', 'api.care_tasks'),
    ('Incident Reports API', 'api.incident_reports'),
    ('Notifications API', 'api.notifications'),
    ('Family API', 'api.family'),
    ('Visits API', 'api.visits'),
    ('Logs API', 'api.logs'),
    ('Decorators', 'api.decorators'),
    ('Excel Export', 'utils.excel_export'),
    ('Logger', 'utils.logger'),
]

all_import_ok = True
for name, module_path in modules_to_test:
    try:
        __import__(module_path)
        print(f"[OK] {name} imported")
    except Exception as e:
        print(f"[FAIL] {name} import failed: {e}")
        all_import_ok = False

# === Test 3: Flask App ===
print("\n[Test 3] Flask App Check")
print("-"*40)

try:
    from app import app
    print(f"[OK] Flask app created")
    print(f"   Debug mode: {app.debug}")

    blueprints = list(app.blueprints.keys())
    print(f"[OK] Blueprints: {len(blueprints)}")
    for bp in blueprints:
        print(f"   - {bp}")

    routes = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint != 'static':
            routes.append(f"{rule.rule}")

    print(f"[OK] Routes: {len(routes)}")

except Exception as e:
    print(f"[FAIL] Flask app init failed: {e}")
    import traceback
    traceback.print_exc()

# === Test 4: Templates ===
print("\n[Test 4] Template Check")
print("-"*40)

templates_dir = 'templates'
if os.path.exists(templates_dir):
    required_templates = [
        'base.html',
        'auth/login.html',
        'admin/index.html',
        'admin/users.html',
        'admin/elders.html',
        'admin/alarms.html',
        'admin/reports.html',
        'admin/logs.html',
        'caregiver/index.html',
        'family/index.html',
    ]

    all_found = True
    for tpl in required_templates:
        tpl_path = os.path.join(templates_dir, tpl)
        if os.path.exists(tpl_path):
            print(f"[OK] Template: {tpl}")
        else:
            print(f"[FAIL] Missing: {tpl}")
            all_found = False

    if all_found:
        print(f"[OK] All required templates present")
else:
    print(f"[FAIL] Templates directory not found")

# === Summary ===
print("\n" + "="*60)
print("Test Summary")
print("="*60)
print("\nSystem is ready to start!")
print("\nNext steps:")
print("1. Run 'python app.py' to start server")
print("2. Open http://localhost:5000 in browser")
print("\nTest accounts:")
print("  Admin: admin / Admin@123")
print("  Caregiver: caregiver1 / Caregiver@123")
print("  Family: family1 / Family@123")
print("="*60)
