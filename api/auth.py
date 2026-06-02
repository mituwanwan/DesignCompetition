import hashlib
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session
from .decorators import login_required, admin_required
from .database import get_db, format_db_error, db_operation
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import log_action

# 紧急配置：是否启用登录锁定策略
ENABLE_LOGIN_LOCKOUT = True  # 恢复启用锁定策略
MAX_LOGIN_ATTEMPTS = 5       # 增加到5次，更友好一些
LOCKOUT_MINUTES = 10
PASSWORD_EXPIRY_DAYS = 90    # 密码有效期90天

# 安全配置：操作频率限制
UNLOCK_RATE_LIMIT = 3        # 每分钟最多解锁次数
UNLOCK_RATE_WINDOW = 60      # 频率限制窗口（秒）
# 用于记录解锁操作的临时存储
unlock_operations = {}

def validate_password_complexity(password):
    """验证密码复杂度：至少8位，包含大小写字母和数字"""
    if len(password) < 8:
        return False, "密码至少需要8位"
    if not any(c.islower() for c in password):
        return False, "密码必须包含小写字母"
    if not any(c.isupper() for c in password):
        return False, "密码必须包含大写字母"
    if not any(c.isdigit() for c in password):
        return False, "密码必须包含数字"
    return True, ""

def is_password_expired(updated_at_str):
    """检查密码是否已过期"""
    if not updated_at_str:
        return False
    try:
        updated_at = datetime.fromisoformat(updated_at_str)
        expiry_date = updated_at + timedelta(days=PASSWORD_EXPIRY_DAYS)
        return datetime.now() > expiry_date
    except Exception:
        return False


def check_unlock_rate_limit(user_id):
    """
    检查解锁操作频率限制
    返回: (是否允许, 剩余次数, 等待秒数)
    """
    now = datetime.now()
    user_ops = unlock_operations.get(user_id, [])
    
    # 清理过期记录
    cutoff = now - timedelta(seconds=UNLOCK_RATE_WINDOW)
    user_ops = [op for op in user_ops if op > cutoff]
    unlock_operations[user_id] = user_ops
    
    if len(user_ops) >= UNLOCK_RATE_LIMIT:
        # 计算等待时间
        oldest_op = min(user_ops)
        wait_seconds = int((oldest_op + timedelta(seconds=UNLOCK_RATE_WINDOW) - now).total_seconds())
        return False, 0, max(1, wait_seconds)
    
    # 记录本次操作
    user_ops.append(now)
    return True, UNLOCK_RATE_LIMIT - len(user_ops), 0


def is_production_environment():
    """判断是否为生产环境"""
    env = os.getenv('FLASK_ENV', 'development').lower()
    return env in ['production', 'prod']

# 创建一个"蓝图"，相当于给应用分模块。所有的登录相关请求都走 /api/v1/auth 前缀
auth_bp = Blueprint('auth', __name__, url_prefix='/api/v1/auth')


def log_login_to_db(conn, user_id, username, login_status, failure_reason=None):
    """记录登录日志到数据库"""
    try:
        conn.execute('''
            INSERT INTO login_logs (user_id, username, ip_address, user_agent, login_status, failure_reason)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            username,
            request.remote_addr,
            request.user_agent.string,
            login_status,
            failure_reason
        ))
    except Exception as e:
        pass


# 核心登录接口：当前端发送 POST 请求到 /api/v1/auth/login 时，触发这个函数
@auth_bp.route('/login', methods=['POST'])
@db_operation
def login():
    # 1. 接收前端页面传来的账号和密码
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    # 2. 验证输入
    if not username or not password:
        return jsonify({"code": 400, "msg": "用户名和密码不能为空", "data": None}), 400

    try:
        with get_db() as conn:
            # 3. 去数据库里寻找这个用户名
            user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

            # 4. 检查账号是否存在
            if not user:
                # 记录失败日志（用户不存在）
                log_login_to_db(conn, 0, username, 'failed', '用户名不存在')
                return jsonify({"code": 400, "msg": "用户名或密码错误", "data": None}), 400

            # 5. 检查账号是否被锁定（如果策略启用）
            if ENABLE_LOGIN_LOCKOUT and user['locked_until']:
                try:
                    locked_until = datetime.fromisoformat(user['locked_until'])
                except (ValueError, TypeError):
                    locked_until = None
                if locked_until and locked_until > datetime.utcnow():
                    log_login_to_db(conn, user['id'], username, 'locked', '账号已锁定')
                    remaining_minutes = (locked_until - datetime.utcnow()).seconds // 60
                    return jsonify({
                        "code": 403,
                        "msg": f"账号已锁定，请{remaining_minutes+1}分钟后重试",
                        "data": None
                    }), 403
                else:
                    # 锁定时间已过，重置锁定状态
                    conn.execute('UPDATE users SET login_failed_count = 0, locked_until = NULL WHERE id = ?', (user['id'],))
            elif user['locked_until'] and not ENABLE_LOGIN_LOCKOUT:
                # 如果策略关闭，自动解锁所有被锁定账号
                conn.execute('UPDATE users SET login_failed_count = 0, locked_until = NULL WHERE id = ?', (user['id'],))

            # 6. 验证密码
            salt = user['salt']
            pwd_hash = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
            
            # 验证密码
            password_matched = pwd_hash == user['password_hash']
            
            if password_matched:
                # 检查密码是否过期
                if is_password_expired(user['password_updated_at']):
                    return jsonify({
                        "code": 401,
                        "msg": "您的密码已过期（超过90天），请修改密码后再登录",
                        "data": {"require_password_change": True}
                    }), 401

                # 密码正确！重置失败计数
                conn.execute('UPDATE users SET login_failed_count = 0, locked_until = NULL WHERE id = ?', (user['id'],))

                # 记录成功登录日志
                log_login_to_db(conn, user['id'], username, 'success')

                # 把用户信息存进 session
                session['user_id'] = user['id']
                session['role'] = user['role']
                session['name'] = user['name']

                # 记录登录日志
                log_action(
                    user_id=user['id'],
                    user_name=user['name'],
                    action='login',
                    module='auth',
                    description='用户登录',
                    ip_address=request.remote_addr
                )

                # 告诉前端：登录成功
                return jsonify({
                    "code": 200,
                    "msg": "登录成功",
                    "data": {
                        "role": user['role']
                    }
                })
            else:
                # 密码错误，增加失败计数（仅策略启用时）
                failed_count = user['login_failed_count'] + 1
                failure_reason = f"密码错误，第{failed_count}次尝试"
                
                if ENABLE_LOGIN_LOCKOUT:
                    if failed_count >= MAX_LOGIN_ATTEMPTS:
                        # 锁定账号10分钟
                        locked_until = datetime.now() + timedelta(minutes=LOCKOUT_MINUTES)
                        conn.execute('UPDATE users SET login_failed_count = ?, locked_until = ? WHERE id = ?',
                                    (failed_count, locked_until.isoformat(), user['id']))
                        failure_reason = "密码错误次数过多，账号已锁定"
                        msg = "密码错误次数过多，账号已锁定10分钟"
                        log_login_to_db(conn, user['id'], username, 'locked', failure_reason)
                    else:
                        conn.execute('UPDATE users SET login_failed_count = ? WHERE id = ?', (failed_count, user['id']))
                        msg = f"用户名或密码错误，还剩{MAX_LOGIN_ATTEMPTS-failed_count}次尝试机会"
                        log_login_to_db(conn, user['id'], username, 'failed', failure_reason)
                else:
                    # 策略关闭时，不记录失败计数
                    msg = "用户名或密码错误"
                    log_login_to_db(conn, user['id'], username, 'failed', failure_reason)

                return jsonify({"code": 400, "msg": msg, "data": None}), 400
    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# 安全退出接口
@auth_bp.route('/logout', methods=['POST'])
def logout():
    # 记录登出日志
    user_id = session.get('user_id')
    user_name = session.get('name')
    if user_id:
        log_action(
            user_id=user_id,
            user_name=user_name,
            action='logout',
            module='auth',
            description='用户退出',
            ip_address=request.remote_addr
        )

    # 清除session中的所有数据
    session.clear()
    return jsonify({
        "code": 200,
        "msg": "退出成功",
        "data": None
    })


# 修改密码接口
@auth_bp.route('/change-password', methods=['PUT'])
@login_required
@db_operation
def change_password():
    try:
        # 获取请求数据
        data = request.get_json()
        old_password = data.get('old_password')
        new_password = data.get('new_password')

        # 验证输入
        if not old_password or not new_password:
            return jsonify({"code": 400, "msg": "原密码和新密码不能为空", "data": None}), 400

        # 验证新密码复杂度
        is_valid, error_msg = validate_password_complexity(new_password)
        if not is_valid:
            return jsonify({"code": 400, "msg": error_msg, "data": None}), 400
        
        if old_password == new_password:
            return jsonify({"code": 400, "msg": "新密码不能与原密码相同", "data": None}), 400

        # 获取当前用户信息
        user_id = session['user_id']
        
        with get_db() as conn:
            user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

            if not user:
                return jsonify({"code": 400, "msg": "用户不存在", "data": None}), 400

            # 验证原密码
            salt = user['salt']
            old_pwd_hash = hashlib.sha256((old_password + salt).encode('utf-8')).hexdigest()
            if old_pwd_hash != user['password_hash']:
                return jsonify({"code": 400, "msg": "原密码错误", "data": None}), 400

            # 生成新密码哈希
            new_pwd_hash = hashlib.sha256((new_password + salt).encode('utf-8')).hexdigest()

            # 更新密码和更新时间
            conn.execute('UPDATE users SET password_hash = ?, password_updated_at = CURRENT_TIMESTAMP WHERE id = ?', (new_pwd_hash, user_id))

        # 记录修改密码日志
        log_action(
            user_id=user_id,
            user_name=session.get('name'),
            action='update',
            module='auth',
            description='修改密码',
            ip_address=request.remote_addr
        )

        return jsonify({
            "code": 200,
            "msg": "密码修改成功",
            "data": None
        })
    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# 解锁API：单个用户解锁
@auth_bp.route('/unlock/<int:user_id>', methods=['PUT'])
@admin_required
@db_operation
def unlock_user(user_id):
    """
    解锁指定用户 - 仅管理员可用
    需要提供解锁原因
    """
    try:
        current_user_id = session.get('user_id')
        
        # 检查频率限制
        allowed, remaining, wait_time = check_unlock_rate_limit(current_user_id)
        if not allowed:
            return jsonify({
                "code": 429, 
                "msg": f"操作过于频繁，请等待 {wait_time} 秒后重试", 
                "data": None
            }), 429
        
        # 验证解锁原因
        data = request.get_json() or {}
        reason = data.get('reason', '').strip()
        if not reason or len(reason) < 5:
            return jsonify({"code": 400, "msg": "请提供有效的解锁原因（至少5个字符）", "data": None}), 400
        
        with get_db() as conn:
            # 检查要解锁的用户
            user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
            if not user:
                return jsonify({"code": 404, "msg": "用户不存在", "data": None}), 404
            
            # 执行解锁
            conn.execute('UPDATE users SET login_failed_count = 0, locked_until = NULL WHERE id = ?', (user_id,))
            
            # 确保审计表存在并记录详细日志
            conn.execute('''
                CREATE TABLE IF NOT EXISTS unlock_audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operator_id INTEGER NOT NULL,
                    operator_name TEXT NOT NULL,
                    operator_role TEXT NOT NULL,
                    unlocked_user_id INTEGER NOT NULL,
                    unlocked_user_name TEXT NOT NULL,
                    unlocked_user_username TEXT NOT NULL,
                    unlocked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    reason TEXT NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    FOREIGN KEY (operator_id) REFERENCES users(id),
                    FOREIGN KEY (unlocked_user_id) REFERENCES users(id)
                )
            ''')
            conn.execute('''
                INSERT INTO unlock_audit_logs 
                (operator_id, operator_name, operator_role, unlocked_user_id, unlocked_user_name, unlocked_user_username, reason, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                current_user_id,
                session.get('name', ''),
                session.get('role', ''),
                user_id,
                user['name'],
                user['username'],
                reason,
                request.remote_addr,
                request.user_agent.string if request.user_agent else ''
            ))
            
            # 记录操作日志
            log_action(
                user_id=current_user_id,
                user_name=session.get('name'),
                action='unlock',
                module='auth',
                description=f'解锁用户 {user["name"]}，原因：{reason}',
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string if request.user_agent else '',
                is_sensitive=True
            )
        
        return jsonify({
            "code": 200, 
            "msg": f"用户 {user['name']} 解锁成功", 
            "data": {"remaining_unlocks": remaining}
        })
    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# 批量解锁API
@auth_bp.route('/unlock/batch', methods=['POST'])
@admin_required
@db_operation
def batch_unlock_users():
    """
    批量解锁用户 - 仅管理员可用
    每次最多解锁5个用户
    """
    try:
        current_user_id = session.get('user_id')
        data = request.get_json()
        user_ids = data.get('user_ids', [])
        reason = data.get('reason', '').strip()
        
        if not user_ids:
            return jsonify({"code": 400, "msg": "请选择要解锁的用户", "data": None}), 400
        
        if not reason or len(reason) < 5:
            return jsonify({"code": 400, "msg": "请提供有效的解锁原因（至少5个字符）", "data": None}), 400
        
        # 限制每次批量解锁的数量
        MAX_BATCH_SIZE = 5
        if len(user_ids) > MAX_BATCH_SIZE:
            return jsonify({
                "code": 400, 
                "msg": f"每次最多解锁 {MAX_BATCH_SIZE} 个用户", 
                "data": None
            }), 400
        
        # 检查频率限制
        allowed, remaining, wait_time = check_unlock_rate_limit(current_user_id)
        if not allowed:
            return jsonify({
                "code": 429, 
                "msg": f"操作过于频繁，请等待 {wait_time} 秒后重试", 
                "data": None
            }), 429
        
        with get_db() as conn:
            # 创建审计表（如果不存在）
            conn.execute('''
                CREATE TABLE IF NOT EXISTS unlock_audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operator_id INTEGER NOT NULL,
                    operator_name TEXT NOT NULL,
                    operator_role TEXT NOT NULL,
                    unlocked_user_id INTEGER NOT NULL,
                    unlocked_user_name TEXT NOT NULL,
                    unlocked_user_username TEXT NOT NULL,
                    unlocked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    reason TEXT NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    FOREIGN KEY (operator_id) REFERENCES users(id),
                    FOREIGN KEY (unlocked_user_id) REFERENCES users(id)
                )
            ''')
            
            unlocked_count = 0
            user_names = []
            
            for user_id in user_ids:
                user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
                if user:
                    conn.execute('UPDATE users SET login_failed_count = 0, locked_until = NULL WHERE id = ?', (user_id,))
                    user_names.append(user['name'])
                    unlocked_count += 1
                    
                    # 记录每个解锁操作的审计
                    conn.execute('''
                        INSERT INTO unlock_audit_logs 
                        (operator_id, operator_name, operator_role, unlocked_user_id, unlocked_user_name, unlocked_user_username, reason, ip_address, user_agent)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        current_user_id,
                        session.get('name', ''),
                        session.get('role', ''),
                        user_id,
                        user['name'],
                        user['username'],
                        reason,
                        request.remote_addr,
                        request.user_agent.string if request.user_agent else ''
                    ))
            
            # 记录操作日志
            log_action(
                user_id=current_user_id,
                user_name=session.get('name'),
                action='batch_unlock',
                module='auth',
                description=f'批量解锁 {unlocked_count} 个用户: {", ".join(user_names)}，原因：{reason}',
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string if request.user_agent else '',
                is_sensitive=True
            )
        
        return jsonify({
            "code": 200, 
            "msg": f"成功解锁 {unlocked_count} 个用户", 
            "data": {"count": unlocked_count, "users": user_names, "remaining_unlocks": remaining}
        })
    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# 获取锁定用户列表API
@auth_bp.route('/locked-users', methods=['GET'])
@login_required
@db_operation
def get_locked_users():
    """
    获取当前被锁定的用户列表
    管理员可以查看所有锁定用户，其他角色只能查看自己的锁定状态
    """
    try:
        with get_db() as conn:
            current_role = session.get('role')
            
            if current_role == 'admin':
                # 管理员查看所有锁定用户
                users = conn.execute('''
                    SELECT id, username, name, role, phone, login_failed_count, locked_until
                    FROM users 
                    WHERE locked_until IS NOT NULL
                    ORDER BY locked_until DESC
                ''').fetchall()
            else:
                # 其他角色只能查看自己
                current_user_id = session.get('user_id')
                users = conn.execute('''
                    SELECT id, username, name, role, phone, login_failed_count, locked_until
                    FROM users 
                    WHERE id = ? AND locked_until IS NOT NULL
                ''', (current_user_id,)).fetchall()
            
            result = []
            for user in users:
                user_dict = dict(user)
                if user_dict['locked_until']:
                    locked_until = datetime.fromisoformat(user_dict['locked_until'])
                    user_dict['is_locked'] = locked_until > datetime.now()
                    user_dict['locked_until_readable'] = locked_until.strftime('%Y-%m-%d %H:%M:%S')
                    if user_dict['is_locked']:
                        remaining = locked_until - datetime.now()
                        user_dict['remaining_minutes'] = max(0, int(remaining.total_seconds() / 60))
                result.append(user_dict)
        
        return jsonify({
            "code": 200, 
            "msg": "获取成功", 
            "data": {
                "locked_count": sum(1 for u in result if u['is_locked']),
                "users": result
            }
        })
    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# 解锁所有人API - 已禁用
# 此接口过于危险，已移除
@auth_bp.route('/unlock-all', methods=['PUT'])
@admin_required
@db_operation
def unlock_all_users():
    """
    解锁所有被锁定的用户 - 已废弃
    此接口过于危险，请使用批量解锁功能
    """
    return jsonify({
        "code": 410, 
        "msg": "此接口已废弃，请使用批量解锁功能", 
        "data": None
    }), 410


# 重置所有用户密码测试接口 - 已移除
# 此接口在生产环境中禁用，存在严重安全隐患
@auth_bp.route('/reset-all-passwords', methods=['POST'])
@admin_required
@db_operation
def reset_all_passwords():
    """
    重置所有用户密码测试接口 - 已禁用
    此接口仅在开发环境可用，生产环境禁用
    包含测试账号密码泄露风险，已禁用
    """
    # 在生产环境中完全禁用此接口
    if is_production_environment():
        # 记录尝试访问的行为
        log_action(
            user_id=session.get('user_id'),
            user_name=session.get('name'),
            action='forbidden_api_access',
            module='auth',
            description='尝试访问已禁用的测试接口 reset-all-passwords',
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string if request.user_agent else '',
            is_sensitive=True
        )
        return jsonify({
            "code": 403, 
            "msg": "此接口在生产环境中已禁用", 
            "data": None
        }), 403
    
    # 在开发环境中也禁止使用，或进行严格限制
    log_action(
        user_id=session.get('user_id'),
        user_name=session.get('name'),
        action='deprecated_api_access',
        module='auth',
        description='尝试访问已废弃的测试接口 reset-all-passwords',
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else '',
        is_sensitive=True
    )
    return jsonify({
        "code": 410, 
        "msg": "此接口已废弃，存在安全风险", 
        "data": None
    }), 410


# 切换锁定策略API
@auth_bp.route('/toggle-lockout', methods=['PUT'])
@login_required
def toggle_lockout_policy():
    """切换登录失败锁定策略"""
    # 只有管理员可以操作
    if session.get('role') != 'admin':
        return jsonify({"code": 403, "msg": "无权操作", "data": None}), 403
    
    global ENABLE_LOGIN_LOCKOUT
    data = request.get_json()
    enable = data.get('enable', False)
    
    ENABLE_LOGIN_LOCKOUT = enable
    
    # 记录操作
    log_action(
        user_id=session.get('user_id'),
        user_name=session.get('name'),
        action='toggle_lockout_policy',
        module='auth',
        description=f'{"启用" if enable else "禁用"}登录失败锁定策略',
        ip_address=request.remote_addr,
        is_sensitive=True
    )
    
    return jsonify({
        "code": 200, 
        "msg": f"登录失败锁定策略已{'启用' if enable else '禁用'}", 
        "data": {"enabled": ENABLE_LOGIN_LOCKOUT}
    })


# 获取锁定策略状态API
@auth_bp.route('/lockout-status', methods=['GET'])
@login_required
def get_lockout_status():
    """获取锁定策略状态"""
    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "enabled": ENABLE_LOGIN_LOCKOUT,
            "max_attempts": MAX_LOGIN_ATTEMPTS,
            "lockout_minutes": LOCKOUT_MINUTES
        }
    })


# 获取解锁审计日志
@auth_bp.route('/unlock-audit', methods=['GET'])
@admin_required
@db_operation
def get_unlock_audit():
    """获取解锁审计日志 - 仅管理员可访问"""
    try:
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        
        with get_db() as conn:
            # 检查表是否存在
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='unlock_audit_logs'")
            if not cursor.fetchone():
                return jsonify({"code": 200, "msg": "审计表不存在", "data": {"list": [], "total": 0}})
            
            # 获取总数
            total = conn.execute('SELECT COUNT(*) FROM unlock_audit_logs').fetchone()[0]
            
            # 获取分页数据
            offset = (page - 1) * page_size
            logs = conn.execute('''
                SELECT * FROM unlock_audit_logs 
                ORDER BY unlocked_at DESC 
                LIMIT ? OFFSET ?
            ''', (page_size, offset)).fetchall()
            
            result = []
            for log in logs:
                log_dict = dict(log)
                log_dict['unlocked_at_readable'] = datetime.fromisoformat(log_dict['unlocked_at']).strftime('%Y-%m-%d %H:%M:%S')
                result.append(log_dict)
        
        return jsonify({
            "code": 200,
            "msg": "获取成功",
            "data": {
                "list": result,
                "total": total,
                "page": page,
                "page_size": page_size
            }
        })
    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500
