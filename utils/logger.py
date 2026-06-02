import sqlite3
import os
from datetime import datetime


def get_db_connection():
    """获取数据库连接"""
    current_dir = os.path.dirname(__file__)
    db_path = os.path.join(current_dir, '..', 'instance', 'nursing_home.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_logs_table():
    """初始化系统日志表"""
    conn = get_db_connection()

    # 创建系统日志表 - 增加字段
    conn.execute('''
        CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT,
            action TEXT NOT NULL,
            module TEXT NOT NULL,
            description TEXT,
            ip_address TEXT,
            user_agent TEXT,
            is_sensitive INTEGER DEFAULT 0,
            old_data TEXT,
            new_data TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    ''')

    conn.commit()
    conn.close()


def log_action(user_id, user_name, action, module, description='', ip_address='',
               user_agent='', is_sensitive=0, old_data='', new_data=''):
    """
    记录系统操作日志

    参数:
        user_id: 用户ID
        user_name: 用户名
        action: 操作类型 (login, logout, create, update, delete, etc.)
        module: 模块名称 (auth, elders, users, etc.)
        description: 详细描述
        ip_address: IP地址
        user_agent: 用户代理
        is_sensitive: 是否敏感操作 0/1
        old_data: 修改前数据(JSON)
        new_data: 修改后数据(JSON)
    """
    try:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO system_logs 
            (user_id, user_name, action, module, description, ip_address, 
             user_agent, is_sensitive, old_data, new_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, user_name, action, module, description, ip_address,
              user_agent, is_sensitive, old_data, new_data))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"记录日志失败: {e}")


def get_logs(limit=100, offset=0, module=None, action=None,
             user_id=None, start_time=None, end_time=None):
    """
    获取系统日志列表

    参数:
        limit: 每页数量
        offset: 偏移量
        module: 模块筛选
        action: 操作类型筛选
        user_id: 用户筛选
        start_time: 开始时间
        end_time: 结束时间
    """
    conn = get_db_connection()

    query = 'SELECT * FROM system_logs WHERE 1=1'
    params = []

    if module:
        query += ' AND module = ?'
        params.append(module)

    if action:
        query += ' AND action = ?'
        params.append(action)

    if user_id:
        query += ' AND user_id = ?'
        params.append(user_id)

    if start_time:
        query += ' AND created_at >= ?'
        params.append(start_time)

    if end_time:
        query += ' AND created_at <= ?'
        params.append(end_time)

    query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])

    logs = conn.execute(query, params).fetchall()

    # 获取总数
    count_query = 'SELECT COUNT(*) as total FROM system_logs WHERE 1=1'
    count_params = []

    if module:
        count_query += ' AND module = ?'
        count_params.append(module)

    if action:
        count_query += ' AND action = ?'
        count_params.append(action)

    if user_id:
        count_query += ' AND user_id = ?'
        count_params.append(user_id)

    if start_time:
        count_query += ' AND created_at >= ?'
        count_params.append(start_time)

    if end_time:
        count_query += ' AND created_at <= ?'
        count_params.append(end_time)

    total = conn.execute(count_query, count_params).fetchone()['total']

    conn.close()

    return {
        'logs': [dict(log) for log in logs],
        'total': total
    }


def get_users_list():
    """获取所有用户列表 - 用于筛选"""
    conn = get_db_connection()
    users = conn.execute('''
        SELECT DISTINCT user_id, user_name 
        FROM system_logs 
        WHERE user_id IS NOT NULL 
        ORDER BY user_name
    ''').fetchall()
    conn.close()
    return [dict(u) for u in users]


def is_sensitive_operation(action, module):
    """判断是否为敏感操作"""
    sensitive_actions = ['delete', 'unlock', 'lock', 'password_reset']
    sensitive_modules = ['users', 'alarms', 'system']
    return 1 if action in sensitive_actions or module in sensitive_modules else 0
