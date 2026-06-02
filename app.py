from flask import Flask, render_template, redirect, url_for, session, send_from_directory
import sqlite3
import os
from api.auth import auth_bp
from api.stats import stats_bp
from api.elders import elders_bp
from api.notifications import notifications_bp
from api.care_records import care_records_bp
from api.users import users_bp
from api.care_tasks import care_tasks_bp
from api.incident_reports import incident_reports_bp
from api.alarms import alarms_bp
from api.family import family_bp, caregiver_msg_bp, admin_msg_bp
from api.visits import visits_bp
from api.logs import logs_bp
from api.alarm_rules import alarm_rules_bp
from api.visit_config import visit_config_bp
from api.caregiver import caregiver_bp
from api.family_messages import family_messages_bp
from api.database import init_database_pool, close_database_pool
from api.decorators import admin_required, caregiver_required, family_required, login_required
from utils.logger import init_logs_table

app = Flask(__name__)
# 配置 Session 密钥，这是启用登录状态管理的必要条件
app.secret_key = 'super_secret_key_for_nursing_home'

def init_database():
    """自动初始化数据库 - 确保所有表都存在"""
    try:
        instance_dir = os.path.join(os.path.dirname(__file__), 'instance')
        os.makedirs(instance_dir, exist_ok=True)
        db_path = os.path.join(instance_dir, 'nursing_home.db')
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查是否已有表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        is_first_init = not cursor.fetchone()
        
        if is_first_init:
            # 首次初始化 - 执行完整 SQL 脚本
            sql_path = os.path.join(os.path.dirname(__file__), 'init_database.sql')
            with open(sql_path, 'r', encoding='utf-8') as f:
                sql_script = f.read()
            cursor.executescript(sql_script)
            print("Database initialized successfully! All tables and test accounts created.")
        else:
            # 检查是否有新增的表
            # 检查 caregiver_elder_assignments 表
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='caregiver_elder_assignments'")
            if not cursor.fetchone():
                print("Creating missing caregiver_elder_assignments table...")
                cursor.execute("""
                CREATE TABLE caregiver_elder_assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    caregiver_id INTEGER NOT NULL,
                    elder_id INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (caregiver_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (elder_id) REFERENCES elders(id) ON DELETE CASCADE,
                    UNIQUE(caregiver_id, elder_id)
                )""")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_caregiver_assignments_caregiver ON caregiver_elder_assignments(caregiver_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_caregiver_assignments_elder ON caregiver_elder_assignments(elder_id)")
            
            # 检查 login_logs 表
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='login_logs'")
            if not cursor.fetchone():
                print("Creating missing login_logs table...")
                cursor.execute("""
                CREATE TABLE login_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    login_status TEXT NOT NULL CHECK(login_status IN ('success', 'failed', 'locked')),
                    failure_reason TEXT,
                    login_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )""")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_login_logs_user ON login_logs(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_login_logs_time ON login_logs(login_time)")

            # 检查 alarm_rules 表
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alarm_rules'")
            if not cursor.fetchone():
                print("Creating missing alarm_rules table...")
                cursor.execute("""
                CREATE TABLE alarm_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_key TEXT UNIQUE NOT NULL,
                    rule_name TEXT NOT NULL,
                    rule_type TEXT NOT NULL CHECK(rule_type IN ('blood_pressure', 'heart_rate', 'sleep', 'temperature')),
                    is_enabled INTEGER DEFAULT 1 CHECK(is_enabled IN (0, 1)),
                    threshold_min REAL,
                    threshold_max REAL,
                    duration_threshold INTEGER,
                    description TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )""")
                # 插入默认规则
                default_rules = [
                    ('bp_high', '高血压', 'blood_pressure', 1, None, 140, '收缩压＞140mmHg触发报警'),
                    ('bp_low', '低血压', 'blood_pressure', 1, 90, None, '舒张压＜90mmHg触发报警'),
                    ('hr_high', '心动过速', 'heart_rate', 1, None, 100, '心率＞100bpm触发报警'),
                    ('hr_low', '心动过缓', 'heart_rate', 1, 60, None, '心率＜60bpm触发报警'),
                    ('sleep_deficit', '睡眠不足', 'sleep', 1, None, 5, '连续3天睡眠少于5小时触发报警'),
                    ('temp_high', '体温过高', 'temperature', 1, None, 37.5, '体温＞37.5℃触发报警'),
                    ('temp_low', '体温过低', 'temperature', 1, 35, None, '体温＜35℃触发报警')
                ]
                for rule in default_rules:
                    cursor.execute("""
                        INSERT OR IGNORE INTO alarm_rules (rule_key, rule_name, rule_type, is_enabled, threshold_min, threshold_max, description)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, rule)
            
            # 检查 alarm_action_logs 表
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alarm_action_logs'")
            if not cursor.fetchone():
                print("Creating missing alarm_action_logs table...")
                cursor.execute("""
                CREATE TABLE alarm_action_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alarm_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    action TEXT NOT NULL CHECK(action IN ('process', 'resolve')),
                    note TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (alarm_id) REFERENCES alarms(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )""")

            # 迁移：修正已有 alarm_rules 的阈值和描述 + 添加血糖报警规则
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alarm_rules'")
            if cursor.fetchone():
                existing_rules = cursor.execute("SELECT rule_key, threshold_min, threshold_max, description FROM alarm_rules").fetchall()
                rule_fixes = {
                    'bp_high': {'threshold_min': None, 'threshold_max': 140, 'description': '收缩压＞140mmHg触发报警'},
                    'bp_low': {'threshold_min': 90, 'threshold_max': None, 'description': '舒张压＜90mmHg触发报警'},
                    'hr_high': {'threshold_min': None, 'threshold_max': 100, 'description': '心率＞100bpm触发报警'},
                    'hr_low': {'threshold_min': 60, 'threshold_max': None, 'description': '心率＜60bpm触发报警'},
                    'sleep_deficit': {'threshold_min': None, 'threshold_max': 5, 'description': '连续3天睡眠少于5小时触发报警'},
                    'temp_high': {'threshold_min': None, 'threshold_max': 37.5, 'description': '体温＞37.5℃触发报警'},
                    'temp_low': {'threshold_min': 35, 'threshold_max': None, 'description': '体温＜35℃触发报警'},
                }
                for rule in existing_rules:
                    rule_key = rule[0]
                    if rule_key in rule_fixes:
                        fix = rule_fixes[rule_key]
                        cursor.execute("""
                            UPDATE alarm_rules
                            SET threshold_min = ?, threshold_max = ?, description = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE rule_key = ?
                        """, (fix['threshold_min'], fix['threshold_max'], fix['description'], rule_key))

                # 迁移：重建 alarm_rules 表以支持 blood_sugar 规则类型
                existing_rule_keys = [r[0] for r in existing_rules]
                if 'bs_high' not in existing_rule_keys or 'bs_low' not in existing_rule_keys:
                    print("Migrating alarm_rules table to support blood_sugar rule type...")
                    cursor.execute("CREATE TABLE IF NOT EXISTS alarm_rules_backup AS SELECT * FROM alarm_rules")
                    cursor.execute("DROP TABLE IF EXISTS alarm_rules")
                    cursor.execute("""
                        CREATE TABLE alarm_rules (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            rule_key TEXT UNIQUE NOT NULL,
                            rule_name TEXT NOT NULL,
                            rule_type TEXT NOT NULL CHECK(rule_type IN ('blood_pressure', 'heart_rate', 'sleep', 'temperature', 'blood_sugar')),
                            is_enabled INTEGER DEFAULT 1 CHECK(is_enabled IN (0, 1)),
                            threshold_min REAL,
                            threshold_max REAL,
                            duration_threshold INTEGER,
                            description TEXT,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    cursor.execute("""
                        INSERT OR IGNORE INTO alarm_rules (id, rule_key, rule_name, rule_type, is_enabled, threshold_min, threshold_max, duration_threshold, description, created_at, updated_at)
                        SELECT id, rule_key, rule_name, rule_type, is_enabled, threshold_min, threshold_max, duration_threshold, description, created_at, updated_at
                        FROM alarm_rules_backup
                    """)
                    cursor.execute("INSERT OR IGNORE INTO alarm_rules (rule_key, rule_name, rule_type, is_enabled, threshold_min, threshold_max, description) VALUES ('bs_high', '血糖偏高', 'blood_sugar', 1, NULL, 11.1, '血糖＞11.1mmol/L触发报警')")
                    cursor.execute("INSERT OR IGNORE INTO alarm_rules (rule_key, rule_name, rule_type, is_enabled, threshold_min, threshold_max, description) VALUES ('bs_low', '血糖偏低', 'blood_sugar', 1, 3.9, NULL, '血糖＜3.9mmol/L触发报警')")
                    cursor.execute("DROP TABLE IF EXISTS alarm_rules_backup")
                    print("alarm_rules migration completed. Blood sugar rules added.")

            # 检查 visit_config 表
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='visit_config'")
            if not cursor.fetchone():
                print("📝 正在创建缺失的 visit_config 表...")
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS visit_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    visit_type TEXT NOT NULL CHECK(visit_type IN ('video', 'in_person', 'all')),
                    day_of_week INTEGER,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    max_appointments INTEGER DEFAULT 5,
                    is_enabled INTEGER DEFAULT 1 CHECK(is_enabled IN (0, 1)),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )""")
                # 插入默认时间段
                cursor.executemany("""
                    INSERT INTO visit_config (visit_type, day_of_week, start_time, end_time, max_appointments)
                    VALUES (?, ?, ?, ?, ?)
                """, [
                    ('all', None, '09:00', '10:00', 5),
                    ('all', None, '10:00', '11:00', 5),
                    ('all', None, '15:00', '16:00', 5),
                    ('all', None, '16:00', '17:00', 5)
                ])
            
            # 检查 care_records 表是否有 notes 列
            cursor.execute("PRAGMA table_info(care_records)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'notes' not in columns:
                print("Adding notes column to care_records table...")
                cursor.execute("ALTER TABLE care_records ADD COLUMN notes TEXT")

            # 检查 family_messages 表
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='family_messages'")
            if not cursor.fetchone():
                print("Creating family_messages table...")
                cursor.execute("""
                CREATE TABLE family_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    elder_id INTEGER NOT NULL,
                    sender_id INTEGER NOT NULL,
                    sender_type TEXT NOT NULL CHECK(sender_type IN ('family', 'caregiver')),
                    receiver_id INTEGER NOT NULL,
                    receiver_type TEXT NOT NULL CHECK(receiver_type IN ('family', 'caregiver')),
                    content TEXT,
                    message_type TEXT NOT NULL DEFAULT 'text' CHECK(message_type IN ('text', 'voice')),
                    voice_file_path TEXT,
                    is_read INTEGER DEFAULT 0 CHECK(is_read IN (0, 1)),
                    festival_template_id INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (elder_id) REFERENCES elders(id) ON DELETE CASCADE,
                    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE
                )""")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_family_messages_elder ON family_messages(elder_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_family_messages_sender ON family_messages(sender_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_family_messages_receiver ON family_messages(receiver_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_family_messages_created ON family_messages(created_at)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_family_messages_read ON family_messages(is_read)")

            # 检查 festival_templates 表
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='festival_templates'")
            if not cursor.fetchone():
                print("Creating festival_templates table...")
                cursor.execute("""
                CREATE TABLE festival_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    festival_type TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1 CHECK(is_active IN (0, 1)),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )""")
                cursor.executemany("""
                    INSERT INTO festival_templates (name, content, festival_type, is_active)
                    VALUES (?, ?, ?, 1)
                """, [
                    ('春节祝福', '亲爱的爸爸/妈妈，新春快乐！愿您在新的一年里身体健康，万事如意！我们永远爱您！', 'spring_festival'),
                    ('元宵节祝福', '元宵佳节到，愿您团团圆圆，甜甜蜜蜜！记得吃汤圆哦，想您了！', 'lantern_festival'),
                    ('母亲节祝福', '亲爱的妈妈，母亲节快乐！感谢您一直以来的付出和关爱，愿您永远健康快乐！', 'mothers_day'),
                    ('父亲节祝福', '亲爱的爸爸，父亲节快乐！您是我心中最伟大的英雄，愿您身体健康，笑口常开！', 'fathers_day'),
                    ('中秋节祝福', '月圆人团圆，中秋佳节到！愿您在这美好的日子里，感受到我们满满的爱和思念！', 'mid_autumn'),
                    ('重阳节祝福', '重阳登高望远，愿您福寿安康！我们虽不在身边，但心中时刻牵挂着您！', 'double_ninth'),
                    ('生日祝福', '祝您生日快乐！愿您岁岁平安，健康长寿！我们爱您！', 'birthday'),
                    ('日常问候', '今天过得好吗？记得按时吃饭，多注意休息，我们一直惦记着您！', 'daily')
                ])
            
            # 检查 elders 表是否有 emergency_contact_name 和 emergency_contact_phone 列
            cursor.execute("PRAGMA table_info(elders)")
            elder_columns = [col[1] for col in cursor.fetchall()]
            if 'emergency_contact_name' not in elder_columns:
                print("Adding emergency_contact_name column to elders table...")
                cursor.execute("ALTER TABLE elders ADD COLUMN emergency_contact_name TEXT DEFAULT ''")
            if 'emergency_contact_phone' not in elder_columns:
                print("Adding emergency_contact_phone column to elders table...")
                cursor.execute("ALTER TABLE elders ADD COLUMN emergency_contact_phone TEXT DEFAULT ''")
            if 'care_level' not in elder_columns:
                print("Adding care_level column to elders table...")
                cursor.execute("ALTER TABLE elders ADD COLUMN care_level TEXT DEFAULT 'standard' CHECK(care_level IN ('special', 'enhanced', 'standard'))")
            
            # 检查 alarms 表是否有 trigger_note 列
            cursor.execute("PRAGMA table_info(alarms)")
            alarm_columns = [col[1] for col in cursor.fetchall()]
            if 'trigger_note' not in alarm_columns:
                print("Adding trigger_note column to alarms table...")
                cursor.execute("ALTER TABLE alarms ADD COLUMN trigger_note TEXT")
            
            # 检查 incident_reports 表是否有 alarm_id 和 status 列
            cursor.execute("PRAGMA table_info(incident_reports)")
            ir_columns = [col[1] for col in cursor.fetchall()]
            if 'alarm_id' not in ir_columns:
                print("Adding alarm_id column to incident_reports table...")
                cursor.execute("ALTER TABLE incident_reports ADD COLUMN alarm_id INTEGER")
            if 'status' not in ir_columns:
                print("Adding status column to incident_reports table...")
                cursor.execute("ALTER TABLE incident_reports ADD COLUMN status TEXT DEFAULT 'unhandled'")
            
            # 迁移：为已有的 incident_reports 记录回填 alarm_id 和 status
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='incident_reports'")
            if cursor.fetchone():
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alarms'")
                if cursor.fetchone():
                    orphan_reports = cursor.execute(
                        "SELECT ir.id, a.id as alarm_id, a.status FROM incident_reports ir "
                        "LEFT JOIN alarms a ON a.type = 'manual_incident' AND a.trigger_source = CAST(ir.id AS TEXT) "
                        "WHERE ir.alarm_id IS NULL"
                    ).fetchall()
                    for row in orphan_reports:
                        if row[1]:
                            cursor.execute(
                                "UPDATE incident_reports SET alarm_id = ?, status = COALESCE(?, 'unhandled') WHERE id = ?",
                                (row[1], row[2], row[0])
                            )
            
            # 只在非首次初始化时才添加测试数据（首次初始化SQL脚本已经包含了测试数据）
            if not is_first_init:
                # 添加测试数据（如果不存在的话）
                # 检查是否有测试老人数据
                cursor.execute("SELECT COUNT(*) FROM elders")
                elder_count = cursor.fetchone()[0]
                if elder_count == 0:
                    print("Inserting test elders data...")
                    cursor.execute("""
                        INSERT INTO elders (name, gender, age, room_number, bed_number, emergency_contact, status)
                        VALUES 
                        ('王大爷', 'male', 78, '101', 'A01', '13800000001', 'active'),
                        ('张奶奶', 'female', 82, '101', 'A02', '13800000002', 'active'),
                        ('李爷爷', 'male', 75, '102', 'B01', '13800000003', 'active'),
                        ('刘奶奶', 'female', 79, '102', 'B02', '13800000004', 'active'),
                        ('陈大爷', 'male', 85, '103', 'C01', '13800000005', 'active')
                    """)
                
                # 检查是否有绑定关系
                cursor.execute("SELECT COUNT(*) FROM caregiver_elder_assignments")
                assign_count = cursor.fetchone()[0]
                if assign_count == 0:
                    print("Inserting caregiver-elder assignments...")
                    cursor.execute("""
                        INSERT OR IGNORE INTO caregiver_elder_assignments (caregiver_id, elder_id)
                        SELECT 2, id FROM elders WHERE id <= 3
                    """)
                
                cursor.execute("SELECT COUNT(*) FROM family_elder_bindings")
                bind_count = cursor.fetchone()[0]
                if bind_count == 0:
                    print("Inserting family-elder bindings...")
                    cursor.execute("""
                        INSERT OR IGNORE INTO family_elder_bindings (family_user_id, elder_id)
                        SELECT 3, id FROM elders WHERE id <= 2
                    """)
                
                # 检查是否有测试护理记录
                cursor.execute("SELECT COUNT(*) FROM care_records")
                rec_count = cursor.fetchone()[0]
                if rec_count == 0:
                    print("Inserting test care records...")
                    cursor.execute("""
                        INSERT INTO care_records (elder_id, caregiver_id, record_date, health_data, notes)
                        VALUES (
                            1,
                            2,
                            date('now'),
                            '{"temperature": 36.5, "heart_rate": 72, "systolic_pressure": 120, "diastolic_pressure": 80}',
                            '老人今日状态良好'
                        )
                    """)
                
                # 检查是否有测试护理任务
                cursor.execute("SELECT COUNT(*) FROM care_tasks")
                task_count = cursor.fetchone()[0]
                if task_count == 0:
                    print("Inserting test care tasks...")
                    cursor.execute("""
                        INSERT INTO care_tasks (admin_id, caregiver_id, elder_id, content, due_time, status)
                        VALUES (
                            1,
                            2,
                            1,
                            '日常健康检查',
                            datetime('now'),
                            'pending'
                        )
                    """)
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error: 数据库初始化失败: {e}")

# 注册认证接口的蓝图，将其接入大楼总控制台
app.register_blueprint(auth_bp)
app.register_blueprint(stats_bp)
app.register_blueprint(elders_bp)
app.register_blueprint(notifications_bp)
app.register_blueprint(care_records_bp)
app.register_blueprint(users_bp)
app.register_blueprint(care_tasks_bp)
app.register_blueprint(incident_reports_bp)
app.register_blueprint(alarms_bp)
app.register_blueprint(family_bp)
app.register_blueprint(caregiver_msg_bp)
app.register_blueprint(visits_bp)
app.register_blueprint(logs_bp)
app.register_blueprint(admin_msg_bp)
app.register_blueprint(alarm_rules_bp)
app.register_blueprint(visit_config_bp)
app.register_blueprint(caregiver_bp)
app.register_blueprint(family_messages_bp)

# 初始化数据库
init_database()

# 初始化日志表
init_logs_table()

# 初始化数据库连接池
print("Initializing database connection pool...")
init_database_pool()
print("Database connection pool initialized!")

@app.route('/')
def index():
    return redirect(url_for('login_page'))


@app.route('/login')
def login_page():
    return render_template('auth/login.html')


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """提供上传图片的静态文件服务"""
    uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)
    return send_from_directory(uploads_dir, filename)


# === 各角色前端路由页面及权限防线 ===

@app.route('/admin')
@admin_required
def admin_page():
    # 渲染管理员首页，并把登录者的名字传给页面展示
    return render_template('admin/index.html', user_name=session.get('name'))

@app.route('/admin/users')
@admin_required
def admin_users_page():
    return render_template('admin/users.html', user_name=session.get('name'), role=session.get('role'))

@app.route('/admin/alarms')
@admin_required
def admin_alarms_page():
    return render_template('admin/alarms.html', user_name=session.get('name'), role=session.get('role'))

@app.route('/admin/alarm-rules')
@admin_required
def admin_alarm_rules_page():
    return render_template('admin/alarm_rules.html', user_name=session.get('name'), role=session.get('role'))

@app.route('/admin/reports')
@admin_required
def admin_reports_page():
    return render_template('admin/reports.html', user_name=session.get('name'), role=session.get('role'))


@app.route('/admin/logs')
@admin_required
def admin_logs_page():
    return render_template('admin/logs.html', user_name=session.get('name'), role=session.get('role'))


@app.route('/admin/elders')
@admin_required
def admin_elders_page():
    # 渲染老人信息管理页面
    return render_template('admin/elders.html', user_name=session.get('name'))


@app.route('/admin/visits')
@admin_required
def admin_visits_page():
    # 渲染探视预约管理页面
    return render_template('admin/visits.html', user_name=session.get('name'), role=session.get('role'))

@app.route('/admin/messages')
@admin_required
def admin_messages_page():
    return render_template('admin/messages.html', user_name=session.get('name'), role=session.get('role'))

@app.route('/admin/unlock-management')
@admin_required
def admin_unlock_page():
    return render_template('admin/unlock-management.html', user_name=session.get('name'), role=session.get('role'))

@app.route('/admin/incident-reports')
@admin_required
def admin_incident_reports_page():
    return render_template('admin/incident_reports.html', user_name=session.get('name'), role=session.get('role'))

@app.route('/admin/family-messages')
@admin_required
def admin_family_messages_page():
    return render_template('admin/family_messages.html', user_name=session.get('name'), role=session.get('role'))

@app.route('/caregiver')
@caregiver_required
def caregiver_page():
    # 渲染护工首页，并把登录者的名字传给页面展示
    return render_template('caregiver/index.html', user_name=session.get('name'), role=session.get('role'))

@app.route('/caregiver/tasks')
@caregiver_required
def caregiver_tasks_page():
    return render_template('caregiver/tasks.html', user_name=session.get('name'), role=session.get('role'))

@app.route('/caregiver/health-records')
@caregiver_required
def caregiver_health_records_page():
    return render_template('caregiver/health_records.html', user_name=session.get('name'), role=session.get('role'))

@app.route('/caregiver/incident-reports')
@caregiver_required
def caregiver_incident_reports_page():
    return render_template('caregiver/incident_reports.html', user_name=session.get('name'), role=session.get('role'))

@app.route('/caregiver/messages')
@caregiver_required
def caregiver_messages_page():
    return render_template('caregiver/messages.html', user_name=session.get('name'), role=session.get('role'))

@app.route('/caregiver/family-messages')
@caregiver_required
def caregiver_family_messages_page():
    return render_template('caregiver/family_messages.html', user_name=session.get('name'), role=session.get('role'), user_id=session.get('user_id'))


@app.route('/family')
@family_required
def family_page():
    # 渲染子女首页，并把登录者的名字传给页面展示
    return render_template('family/index.html', user_name=session.get('name'), role=session.get('role'))

@app.route('/family/health')
@family_required
def family_health_page():
    return render_template('family/health.html', user_name=session.get('name'), role=session.get('role'))

@app.route('/family/messages')
@family_required
def family_messages_page():
    return render_template('family/messages.html', user_name=session.get('name'), role=session.get('role'))

@app.route('/family/alarms')
@family_required
def family_alarms_page():
    return render_template('family/alarms.html', user_name=session.get('name'), role=session.get('role'))

@app.route('/family/video-visit')
@family_required
def family_video_visit_page():
    return render_template('family/video_visit.html', user_name=session.get('name'), role=session.get('role'))

@app.route('/family/video-room/<token>')
def family_video_room_page(token):
    return render_template('family/video_room.html', token=token)

@app.route('/family/appointment')
@family_required
def family_appointment_page():
    return render_template('family/appointment.html', user_name=session.get('name'), role=session.get('role'))

@app.route('/family/family-messages')
@family_required
def family_family_messages_page():
    return render_template('family/family_messages.html', user_name=session.get('name'), role=session.get('role'), user_id=session.get('user_id'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)