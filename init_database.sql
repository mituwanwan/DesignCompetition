-- 智慧养老院管理系统 - 数据库初始化脚本
-- 数据库类型：SQLite
-- 执行前请确保已安装SQLite3

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- 1. 用户表 (users)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'caregiver', 'family')),
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    status TEXT DEFAULT 'enabled' CHECK(status IN ('enabled', 'disabled')),
    login_failed_count INTEGER DEFAULT 0,
    locked_until DATETIME,
    password_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 2. 老人表 (elders)
CREATE TABLE IF NOT EXISTS elders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    gender TEXT NOT NULL CHECK(gender IN ('male', 'female')),
    age INTEGER NOT NULL CHECK(age > 0 AND age < 150),
    room_number TEXT NOT NULL,
    bed_number TEXT NOT NULL,
    emergency_contact TEXT DEFAULT '',
    emergency_contact_name TEXT DEFAULT '',
    emergency_contact_phone TEXT DEFAULT '',
    medical_history TEXT,
    care_level TEXT DEFAULT 'standard' CHECK(care_level IN ('special', 'enhanced', 'standard')),
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'discharged')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 3. 子女-老人绑定表 (family_elder_bindings)
CREATE TABLE IF NOT EXISTS family_elder_bindings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    family_user_id INTEGER NOT NULL,
    elder_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (family_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (elder_id) REFERENCES elders(id) ON DELETE CASCADE,
    UNIQUE(family_user_id, elder_id)
);

-- 4. 护理记录表 (care_records)
CREATE TABLE IF NOT EXISTS care_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    elder_id INTEGER NOT NULL,
    caregiver_id INTEGER NOT NULL,
    record_date TEXT NOT NULL,
    -- 健康数据 (JSON格式存储)
    health_data TEXT,
    -- 饮食数据 (JSON格式存储)
    diet TEXT,
    -- 睡眠数据 (JSON格式存储)
    sleep TEXT,
    -- 情绪数据 (JSON格式存储)
    emotion TEXT,
    -- 备注
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (elder_id) REFERENCES elders(id) ON DELETE CASCADE,
    FOREIGN KEY (caregiver_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 5. 护理任务表 (care_tasks)
CREATE TABLE IF NOT EXISTS care_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL,
    caregiver_id INTEGER NOT NULL,
    elder_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    due_time DATETIME NOT NULL,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'completed')),
    completed_at DATETIME,
    completed_by INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (caregiver_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (elder_id) REFERENCES elders(id) ON DELETE CASCADE,
    FOREIGN KEY (completed_by) REFERENCES users(id) ON DELETE SET NULL
);

-- 6. 异常情况上报 (incident_reports)
CREATE TABLE IF NOT EXISTS incident_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    elder_id INTEGER NOT NULL,
    caregiver_id INTEGER NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('fall', 'discomfort', 'agitation', 'other')),
    note TEXT,
    images TEXT, -- JSON数组存储图片路径
    alarm_id INTEGER, -- 关联的报警记录ID
    status TEXT DEFAULT 'unhandled' CHECK(status IN ('unhandled', 'processing', 'resolved')), -- 同步报警状态
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (elder_id) REFERENCES elders(id) ON DELETE CASCADE,
    FOREIGN KEY (caregiver_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (alarm_id) REFERENCES alarms(id) ON DELETE SET NULL
);

-- 7. 报警表 (alarms)
CREATE TABLE IF NOT EXISTS alarms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    elder_id INTEGER NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('auto_health', 'manual_incident', 'other')),
    trigger_source TEXT, -- 自动报警规则ID或手动上报ID
    trigger_note TEXT, -- 报警触发说明
    status TEXT DEFAULT 'unhandled' CHECK(status IN ('unhandled', 'processing', 'resolved')),
    handler_id INTEGER,
    result TEXT,
    triggered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    processing_at DATETIME,
    resolved_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (elder_id) REFERENCES elders(id) ON DELETE CASCADE,
    FOREIGN KEY (handler_id) REFERENCES users(id) ON DELETE SET NULL
);

-- 8. 留言表 (messages)
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    elder_id INTEGER NOT NULL,
    sender_id INTEGER NOT NULL,
    sender_role TEXT NOT NULL CHECK(sender_role IN ('caregiver', 'family')),
    content TEXT NOT NULL,
    is_read INTEGER DEFAULT 0 CHECK(is_read IN (0, 1)),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (elder_id) REFERENCES elders(id) ON DELETE CASCADE,
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 9. 系统消息表 (notifications)
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('alarm', 'task', 'message')),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    related_id INTEGER, -- 关联的报警/任务/消息ID
    is_read INTEGER DEFAULT 0 CHECK(is_read IN (0, 1)),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 10. 探视预约表（appointments）
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    elder_id INTEGER NOT NULL,
    family_user_id INTEGER NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('video', 'in_person')),
    appointment_date TEXT NOT NULL,
    notes TEXT,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'completed', 'cancelled')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (elder_id) REFERENCES elders(id) ON DELETE CASCADE,
    FOREIGN KEY (family_user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 11. 护工-老人分配表（caregiver_elder_assignments）
CREATE TABLE IF NOT EXISTS caregiver_elder_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caregiver_id INTEGER NOT NULL,
    elder_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (caregiver_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (elder_id) REFERENCES elders(id) ON DELETE CASCADE,
    UNIQUE(caregiver_id, elder_id)
);

-- 12. 登录日志表（login_logs）
CREATE TABLE IF NOT EXISTS login_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    login_status TEXT NOT NULL CHECK(login_status IN ('success', 'failed', 'locked')),
    failure_reason TEXT,
    login_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 13. 报警规则配置表（alarm_rules）
CREATE TABLE IF NOT EXISTS alarm_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_key TEXT UNIQUE NOT NULL, -- 规则标识
    rule_name TEXT NOT NULL, -- 规则名称
    rule_type TEXT NOT NULL CHECK(rule_type IN ('blood_pressure', 'heart_rate', 'sleep', 'temperature', 'blood_sugar')), -- 规则类型
    is_enabled INTEGER DEFAULT 1 CHECK(is_enabled IN (0, 1)), -- 是否启用
    threshold_min REAL, -- 最小值阈值
    threshold_max REAL, -- 最大值阈值
    duration_threshold INTEGER, -- 持续时长（天数，用于睡眠规则）
    description TEXT, -- 规则描述
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 14. 报警处理记录表（alarm_action_logs）
CREATE TABLE IF NOT EXISTS alarm_action_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alarm_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('process', 'resolve')),
    note TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (alarm_id) REFERENCES alarms(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 15. 预约时间段配置表（visit_config）
CREATE TABLE IF NOT EXISTS visit_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_type TEXT NOT NULL CHECK(visit_type IN ('video', 'in_person', 'all')),
    day_of_week INTEGER, -- 0=周日, 1=周一, ..., 6=周六, NULL=所有天
    start_time TEXT NOT NULL, -- 开始时间，格式如 "09:00"
    end_time TEXT NOT NULL, -- 结束时间，格式如 "11:00"
    max_appointments INTEGER DEFAULT 5, -- 该时间段最大预约数
    is_enabled INTEGER DEFAULT 1 CHECK(is_enabled IN (0, 1)),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 16. 亲情留言表（family_messages）
CREATE TABLE IF NOT EXISTS family_messages (
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
);

-- 17. 节日祝福模板表（festival_templates）
CREATE TABLE IF NOT EXISTS festival_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    festival_type TEXT NOT NULL,
    is_active INTEGER DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_elders_name ON elders(name);
CREATE INDEX IF NOT EXISTS idx_elders_room ON elders(room_number);
CREATE INDEX IF NOT EXISTS idx_care_records_elder_date ON care_records(elder_id, record_date);
CREATE INDEX IF NOT EXISTS idx_care_tasks_caregiver_status ON care_tasks(caregiver_id, status);
CREATE INDEX IF NOT EXISTS idx_alarms_status ON alarms(status);
CREATE INDEX IF NOT EXISTS idx_messages_elder ON messages(elder_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_caregiver_assignments_caregiver ON caregiver_elder_assignments(caregiver_id);
CREATE INDEX IF NOT EXISTS idx_caregiver_assignments_elder ON caregiver_elder_assignments(elder_id);
CREATE INDEX IF NOT EXISTS idx_login_logs_user ON login_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_login_logs_time ON login_logs(login_time);
CREATE INDEX IF NOT EXISTS idx_family_messages_elder ON family_messages(elder_id);
CREATE INDEX IF NOT EXISTS idx_family_messages_sender ON family_messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_family_messages_receiver ON family_messages(receiver_id);
CREATE INDEX IF NOT EXISTS idx_family_messages_created ON family_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_family_messages_read ON family_messages(is_read);

-- 插入默认报警规则
INSERT INTO alarm_rules (rule_key, rule_name, rule_type, is_enabled, threshold_min, threshold_max, description)
VALUES 
    ('bp_high', '高血压', 'blood_pressure', 1, NULL, 140, '收缩压＞140mmHg触发报警'),
    ('bp_low', '低血压', 'blood_pressure', 1, 90, NULL, '舒张压＜90mmHg触发报警'),
    ('hr_high', '心动过速', 'heart_rate', 1, NULL, 100, '心率＞100bpm触发报警'),
    ('hr_low', '心动过缓', 'heart_rate', 1, 60, NULL, '心率＜60bpm触发报警'),
    ('sleep_deficit', '睡眠不足', 'sleep', 1, NULL, 5, '连续3天睡眠少于5小时触发报警'),
    ('temp_high', '体温过高', 'temperature', 1, NULL, 37.5, '体温＞37.5℃触发报警'),
    ('temp_low', '体温过低', 'temperature', 1, 35, NULL, '体温＜35℃触发报警'),
    ('bs_high', '血糖偏高', 'blood_sugar', 1, NULL, 11.1, '血糖＞11.1mmol/L触发报警'),
    ('bs_low', '血糖偏低', 'blood_sugar', 1, 3.9, NULL, '血糖＜3.9mmol/L触发报警')
ON CONFLICT(rule_key) DO NOTHING;

-- 插入默认预约时间段
INSERT INTO visit_config (visit_type, day_of_week, start_time, end_time, max_appointments)
VALUES 
    ('all', NULL, '09:00', '10:00', 5),
    ('all', NULL, '10:00', '11:00', 5),
    ('all', NULL, '15:00', '16:00', 5),
    ('all', NULL, '16:00', '17:00', 5)
ON CONFLICT(id) DO NOTHING;

-- 插入初始管理员账号 (用户名: admin, 密码: Admin@123)
-- 注意：实际部署时请修改默认密码
INSERT INTO users (username, password_hash, salt, role, name)
VALUES (
    'admin',
    'be5624e96818304b7a011880e1eb567691524134951edc60cf89b55816fa430b',
    'random_salt_123456',
    'admin',
    '系统管理员'
) ON CONFLICT(username) DO NOTHING;

-- 插入测试护工账号 (用户名: caregiver1, 密码: Caregiver@123)
INSERT INTO users (username, password_hash, salt, role, name, phone)
VALUES (
    'caregiver1',
    '0e142adf2ced13951eb85d6513c7552a1791ea0ca786cd9841cc6b70ba83a7ff',
    'random_salt_654321',
    'caregiver',
    '张护工',
    '13800138001'
) ON CONFLICT(username) DO NOTHING;

-- 插入测试子女账号 (用户名: family1, 密码: Family@123)
INSERT INTO users (username, password_hash, salt, role, name, phone)
VALUES (
    'family1',
    '59b0c92c3c4c1378b69dd657ca83650efaa4d1ec387bed1f6f60e499366abd9a',
    'random_salt_112233',
    'family',
    '李女士',
    '13900139001'
) ON CONFLICT(username) DO NOTHING;

-- 插入测试老人数据
INSERT INTO elders (name, gender, age, room_number, bed_number, emergency_contact, status)
VALUES 
('王大爷', 'male', 78, '101', 'A01', '13800000001', 'active'),
('张奶奶', 'female', 82, '101', 'A02', '13800000002', 'active'),
('李爷爷', 'male', 75, '102', 'B01', '13800000003', 'active'),
('刘奶奶', 'female', 79, '102', 'B02', '13800000004', 'active'),
('陈大爷', 'male', 85, '103', 'C01', '13800000005', 'active')
ON CONFLICT(id) DO NOTHING;

-- 插入初始绑定关系：将老人1-3分配给护工1，将老人1-2绑定给子女1
INSERT OR IGNORE INTO caregiver_elder_assignments (caregiver_id, elder_id)
SELECT 2, id FROM elders WHERE id <=3;

INSERT OR IGNORE INTO family_elder_bindings (family_user_id, elder_id)
SELECT 3, id FROM elders WHERE id <=2;

-- 插入一条测试护理记录
INSERT OR IGNORE INTO care_records (elder_id, caregiver_id, record_date, health_data, notes)
VALUES (
    1,
    2,
    date('now'),
    '{"temperature": 36.5, "heart_rate": 72, "systolic_pressure": 120, "diastolic_pressure": 80}',
    '老人今日状态良好'
);

-- 插入一条测试护理任务
INSERT OR IGNORE INTO care_tasks (admin_id, caregiver_id, elder_id, content, due_time, status)
VALUES (
    1,
    2,
    1,
    '日常健康检查',
    datetime('now'),
    'pending'
);

-- 插入默认节日祝福模板
INSERT INTO festival_templates (name, content, festival_type, is_active) VALUES
    ('春节祝福', '亲爱的爸爸/妈妈，新春快乐！愿您在新的一年里身体健康，万事如意！我们永远爱您！', 'spring_festival', 1),
    ('元宵节祝福', '元宵佳节到，愿您团团圆圆，甜甜蜜蜜！记得吃汤圆哦，想您了！', 'lantern_festival', 1),
    ('母亲节祝福', '亲爱的妈妈，母亲节快乐！感谢您一直以来的付出和关爱，愿您永远健康快乐！', 'mothers_day', 1),
    ('父亲节祝福', '亲爱的爸爸，父亲节快乐！您是我心中最伟大的英雄，愿您身体健康，笑口常开！', 'fathers_day', 1),
    ('中秋节祝福', '月圆人团圆，中秋佳节到！愿您在这美好的日子里，感受到我们满满的爱和思念！', 'mid_autumn', 1),
    ('重阳节祝福', '重阳登高望远，愿您福寿安康！我们虽不在身边，但心中时刻牵挂着您！', 'double_ninth', 1),
    ('生日祝福', '祝您生日快乐！愿您岁岁平安，健康长寿！我们爱您！', 'birthday', 1),
    ('日常问候', '今天过得好吗？记得按时吃饭，多注意休息，我们一直惦记着您！', 'daily', 1);
