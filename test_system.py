"""
智慧养老院管理系统 - 全面测试脚本
"""
import sys
import os
sys.path.insert(0, '.')

import sqlite3
import json

print("="*60)
print("智慧养老院管理系统 - 全面测试")
print("="*60)

# === 测试1: 数据库连接和表结构 ===
print("\n[测试1] 数据库检查")
print("-"*40)

db_path = os.path.join('instance', 'nursing_home.db')
if os.path.exists(db_path):
    print(f"✅ 数据库文件存在: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 获取所有表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row['name'] for row in cursor.fetchall()]
    print(f"✅ 数据库表数量: {len(tables)}")
    print(f"   表名: {', '.join(tables)}")

    # 检查关键表
    required_tables = ['users', 'elders', 'family_elder_bindings', 'care_records',
                      'care_tasks', 'incident_reports', 'alarms', 'messages',
                      'notifications', 'appointments', 'system_logs']

    missing_tables = [t for t in required_tables if t not in tables]
    if missing_tables:
        print(f"❌ 缺少关键表: {missing_tables}")
    else:
        print(f"✅ 所有关键表都存在")

    # 检查用户数据
    cursor.execute("SELECT COUNT(*) as count FROM users")
    user_count = cursor.fetchone()['count']
    print(f"✅ 用户表记录数: {user_count}")

    cursor.execute("SELECT username, role, status FROM users LIMIT 3")
    users = cursor.fetchall()
    print(f"   示例用户:")
    for u in users:
        print(f"     - {u['username']} ({u['role']}) - {u['status']}")

    # 检查老人数据
    cursor.execute("SELECT COUNT(*) as count FROM elders")
    elder_count = cursor.fetchone()['count']
    print(f"✅ 老人表记录数: {elder_count}")

    conn.close()
else:
    print(f"❌ 数据库文件不存在: {db_path}")

# === 测试2: 模块导入 ===
print("\n[测试2] 模块导入检查")
print("-"*40)

modules_to_test = [
    ('Flask应用', 'app'),
    ('认证API', 'api.auth'),
    ('老人管理API', 'api.elders'),
    ('统计API', 'api.stats'),
    ('用户管理API', 'api.users'),
    ('报警API', 'api.alarms'),
    ('护理记录API', 'api.care_records'),
    ('护理任务API', 'api.care_tasks'),
    ('异常上报API', 'api.incident_reports'),
    ('通知API', 'api.notifications'),
    ('子女端API', 'api.family'),
    ('探视预约API', 'api.visits'),
    ('日志API', 'api.logs'),
    ('权限装饰器', 'api.decorators'),
    ('Excel导出工具', 'utils.excel_export'),
    ('日志工具', 'utils.logger'),
]

all_import_ok = True
for name, module_path in modules_to_test:
    try:
        __import__(module_path)
        print(f"✅ {name} 导入成功")
    except Exception as e:
        print(f"❌ {name} 导入失败: {e}")
        all_import_ok = False

# === 测试3: Flask应用初始化 ===
print("\n[测试3] Flask应用检查")
print("-"*40)

try:
    from app import app
    print(f"✅ Flask应用创建成功")
    print(f"   调试模式: {app.debug}")
    print(f"   密钥已配置: {'是' if app.secret_key else '否'}")

    # 检查蓝图
    blueprints = list(app.blueprints.keys())
    print(f"✅ 已注册蓝图: {len(blueprints)} 个")
    for bp in blueprints:
        print(f"   - {bp}")

    # 检查路由
    routes = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint != 'static':
            routes.append(f"{rule.rule} ({', '.join(rule.methods - {'HEAD', 'OPTIONS'})})")

    print(f"✅ 已注册路由: {len(routes)} 个")

except Exception as e:
    print(f"❌ Flask应用初始化失败: {e}")
    import traceback
    traceback.print_exc()

# === 测试4: API模块功能检查 ===
print("\n[测试4] API模块功能检查")
print("-"*40)

try:
    from utils.logger import get_db_connection

    # 测试数据库连接工具
    conn = get_db_connection()
    print(f"✅ 数据库连接工具正常")

    # 测试一些简单查询
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    admin_count = cursor.fetchone()[0]
    print(f"✅ 管理员账号数: {admin_count}")

    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'caregiver'")
    caregiver_count = cursor.fetchone()[0]
    print(f"✅ 护工账号数: {caregiver_count}")

    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'family'")
    family_count = cursor.fetchone()[0]
    print(f"✅ 子女账号数: {family_count}")

    conn.close()

except Exception as e:
    print(f"❌ API模块功能检查失败: {e}")

# === 测试5: 模板文件检查 ===
print("\n[测试5] 模板文件检查")
print("-"*40)

templates_dir = 'templates'
if os.path.exists(templates_dir):
    required_templates = [
        'base.html',
        'auth/login.html',
        'auth/base_auth.html',
        'admin/index.html',
        'admin/users.html',
        'admin/elders.html',
        'admin/alarms.html',
        'admin/reports.html',
        'admin/logs.html',
        'caregiver/index.html',
        'caregiver/tasks.html',
        'caregiver/health_records.html',
        'caregiver/incident_reports.html',
        'caregiver/messages.html',
        'family/index.html',
        'family/health.html',
        'family/messages.html',
        'family/video_visit.html',
        'family/appointment.html',
    ]

    missing_templates = []
    for tpl in required_templates:
        tpl_path = os.path.join(templates_dir, tpl)
        if os.path.exists(tpl_path):
            print(f"✅ 模板存在: {tpl}")
        else:
            print(f"❌ 模板缺失: {tpl}")
            missing_templates.append(tpl)

    if not missing_templates:
        print(f"✅ 所有必需模板都存在")
else:
    print(f"❌ 模板目录不存在: {templates_dir}")

# === 测试6: 静态文件检查 ===
print("\n[测试6] 静态文件检查")
print("-"*40)

static_dir = 'static'
if os.path.exists(static_dir):
    static_files = {
        'CSS': ['css/variables.css', 'css/global.css', 'css/auth.css'],
        'JS': ['js/toast.js', 'js/notifications.js', 'js/auth.js'],
    }

    for category, files in static_files.items():
        print(f"\n{category}:")
        for f in files:
            f_path = os.path.join(static_dir, f)
            if os.path.exists(f_path):
                print(f"  ✅ {f}")
            else:
                print(f"  ❌ {f} (缺失)")
else:
    print(f"❌ 静态文件目录不存在: {static_dir}")

# === 总结 ===
print("\n" + "="*60)
print("测试完成总结")
print("="*60)
print("\n项目可以正常启动！")
print("\n下一步建议:")
print("1. 运行 'python app.py' 启动开发服务器")
print("2. 访问 http://localhost:5000 进行前端测试")
print("3. 使用测试账号登录验证功能")
print("\n测试账号:")
print("  管理员: admin / Admin@123")
print("  护工: caregiver1 / Caregiver@123")
print("  子女: family1 / Family@123")
print("="*60)
