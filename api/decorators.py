"""
权限装饰器模块
提供用于Flask路由的权限检查装饰器
"""

from functools import wraps
from flask import session, jsonify, request
import sqlite3
import os


def get_db_connection():
    """获取数据库连接"""
    current_dir = os.path.dirname(__file__)
    db_path = os.path.join(current_dir, '..', 'instance', 'nursing_home.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def login_required(f):
    """
    登录检查装饰器
    验证用户是否已登录，未登录返回401错误
    同时检查账号是否被锁定
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"code": 401, "msg": "请先登录", "data": None}), 401

        from datetime import datetime
        user_id = session.get('user_id')
        conn = get_db_connection()
        try:
            user = conn.execute('SELECT locked_until, status FROM users WHERE id = ?', (user_id,)).fetchone()
            if user:
                if user['status'] == 'disabled':
                    conn.close()
                    session.clear()
                    return jsonify({"code": 403, "msg": "账号已被禁用，请联系管理员", "data": None}), 403
                if user['locked_until']:
                    try:
                        locked_until = datetime.fromisoformat(user['locked_until'])
                        if locked_until > datetime.utcnow():
                            conn.close()
                            session.clear()
                            return jsonify({"code": 403, "msg": "账号已被锁定，请稍后再试", "data": None}), 403
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass
        finally:
            conn.close()

        return f(*args, **kwargs)
    return decorated_function


def role_required(required_role):
    """
    角色检查装饰器
    验证用户是否具有指定角色，权限不足返回403错误

    Args:
        required_role: 要求的角色 ('admin', 'caregiver', 'family')
    """
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if session.get('role') != required_role:
                return jsonify({"code": 403, "msg": "权限不足", "data": None}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def caregiver_elder_access_required(f):
    """
    护工访问老人数据权限检查装饰器
    确保护工只能操作自己负责的老人数据
    需要从请求参数或URL路径中获取elder_id
    """
    @wraps(f)
    @role_required('caregiver')
    def decorated_function(*args, **kwargs):
        caregiver_id = session.get('user_id')
        
        # 尝试从不同位置获取elder_id
        elder_id = None
        if 'elder_id' in kwargs:
            elder_id = kwargs['elder_id']
        elif request.is_json:
            data = request.get_json()
            if data and 'elder_id' in data:
                elder_id = data['elder_id']
        elif request.args.get('elder_id'):
            elder_id = int(request.args.get('elder_id'))
        
        # 如果没有elder_id参数，允许访问（可能是列表页面）
        if not elder_id:
            return f(*args, **kwargs)
        
        # 检查护工是否分配了该老人
        conn = get_db_connection()
        assignment = conn.execute('''
            SELECT * FROM caregiver_elder_assignments 
            WHERE caregiver_id = ? AND elder_id = ?
        ''', (caregiver_id, elder_id)).fetchone()
        conn.close()
        
        if not assignment:
            return jsonify({"code": 403, "msg": "您无权操作该老人数据", "data": None}), 403
        
        return f(*args, **kwargs)
    return decorated_function


def family_elder_access_required(f):
    """
    家属访问老人数据权限检查装饰器
    确保家属只能查看自己绑定的老人数据
    """
    @wraps(f)
    @role_required('family')
    def decorated_function(*args, **kwargs):
        family_id = session.get('user_id')
        
        # 尝试从不同位置获取elder_id
        elder_id = None
        if 'elder_id' in kwargs:
            elder_id = kwargs['elder_id']
        elif request.is_json:
            data = request.get_json()
            if data and 'elder_id' in data:
                elder_id = data['elder_id']
        elif request.args.get('elder_id'):
            elder_id = int(request.args.get('elder_id'))
        
        # 如果没有elder_id参数，允许访问
        if not elder_id:
            return f(*args, **kwargs)
        
        # 检查家属是否绑定了该老人
        conn = get_db_connection()
        binding = conn.execute('''
            SELECT * FROM family_elder_bindings 
            WHERE family_user_id = ? AND elder_id = ?
        ''', (family_id, elder_id)).fetchone()
        conn.close()
        
        if not binding:
            return jsonify({"code": 403, "msg": "您无权查看该老人数据", "data": None}), 403
        
        return f(*args, **kwargs)
    return decorated_function


# 快捷装饰器
admin_required = role_required('admin')
caregiver_required = role_required('caregiver')
family_required = role_required('family')
