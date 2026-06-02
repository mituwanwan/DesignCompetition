"""
用户管理接口模块
提供用户的CRUD、密码重置、老人绑定等功能
"""

import json
import secrets
import hashlib
from flask import Blueprint, request, jsonify, session
from .decorators import admin_required, caregiver_required
from .database import get_db, format_db_error, db_operation

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import log_action, is_sensitive_operation


users_bp = Blueprint('users', __name__, url_prefix='/api/v1/users')


VALID_ROLES = ['admin', 'caregiver', 'family']
ALLOWED_UPDATE_FIELDS = ['name', 'phone', 'email', 'status']


# ========== 1. 获取用户列表 ==========
@users_bp.route('', methods=['GET'])
@admin_required
@db_operation
def get_users():
    role = request.args.get('role', '').strip()
    status = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    with get_db() as conn:
        conditions = []
        params = []

        if role and role in VALID_ROLES:
            conditions.append("role = ?")
            params.append(role)

        if status:
            conditions.append("status = ?")
            params.append(status)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        total_count = conn.execute(
            f"SELECT COUNT(*) FROM users WHERE {where_clause}", params
        ).fetchone()[0]

        offset = (page - 1) * page_size
        users = conn.execute(
            f"SELECT id, username, role, name, phone, email, status, created_at, "
            f"login_failed_count, locked_until "
            f"FROM users WHERE {where_clause} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [page_size, offset]
        ).fetchall()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "list": [dict(u) for u in users],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_count,
                "total_pages": (total_count + page_size - 1) // page_size
            }
        }
    })


# ========== 2. 创建用户 ==========
@users_bp.route('', methods=['POST'])
@admin_required
@db_operation
def create_user():
    try:
        data = request.get_json()

        required_fields = ['username', 'password', 'role', 'name']
        for field in required_fields:
            if not data.get(field):
                return jsonify({"code": 400, "msg": f"{field}字段不能为空", "data": None}), 400

        role = data.get('role')
        if role not in VALID_ROLES:
            return jsonify({"code": 400, "msg": "角色必须是 admin/caregiver/family 之一", "data": None}), 400

        username = data.get('username').strip()
        password = data.get('password')
        name = data.get('name').strip()
        phone = data.get('phone', '').strip()
        email = data.get('email', '').strip()

        # 验证密码复杂度
        if len(password) < 8:
            return jsonify({"code": 400, "msg": "密码至少需要8位", "data": None}), 400
        if not any(c.islower() for c in password):
            return jsonify({"code": 400, "msg": "密码必须包含小写字母", "data": None}), 400
        if not any(c.isupper() for c in password):
            return jsonify({"code": 400, "msg": "密码必须包含大写字母", "data": None}), 400
        if not any(c.isdigit() for c in password):
            return jsonify({"code": 400, "msg": "密码必须包含数字", "data": None}), 400

        # 验证手机号格式
        if phone and not (phone.isdigit() and len(phone) == 11 and phone.startswith('1')):
            return jsonify({"code": 400, "msg": "手机号必须是11位数字且以1开头", "data": None}), 400

        # 验证邮箱格式
        if email and '@' not in email:
            return jsonify({"code": 400, "msg": "邮箱格式不正确", "data": None}), 400

        with get_db() as conn:
            # 检查用户名唯一性
            existing = conn.execute(
                'SELECT id FROM users WHERE username = ?', (username,)
            ).fetchone()
            if existing:
                return jsonify({"code": 400, "msg": "用户名已存在", "data": None}), 400

            salt = secrets.token_hex(16)
            pwd_hash = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()

            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (username, password_hash, salt, role, name, phone, email)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (username, pwd_hash, salt, role, name, phone, email))
            new_id = cursor.lastrowid

        # 记录创建用户操作日志
        log_action(
            user_id=session.get('user_id'),
            user_name=session.get('name'),
            action='create',
            module='users',
            description=f'创建用户: {name}, 角色: {role}',
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
            is_sensitive=is_sensitive_operation('create', 'users'),
            new_data=json.dumps({'username': username, 'name': name, 'role': role})
        )

        return jsonify({"code": 200, "msg": "创建成功", "data": {"id": new_id}})
    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# ========== 3. 更新用户信息 ==========
@users_bp.route('/<int:id>', methods=['PUT'])
@admin_required
@db_operation
def update_user(id):
    try:
        data = request.get_json()

        with get_db() as conn:
            user = conn.execute('SELECT * FROM users WHERE id = ?', (id,)).fetchone()
            if not user:
                return jsonify({"code": 404, "msg": "用户不存在", "data": None}), 404

            old_data = {'name': user['name'], 'phone': user['phone'], 'email': user['email'], 'status': user['status']}

            if 'username' in data or 'role' in data:
                return jsonify({"code": 400, "msg": "不能修改用户名和角色", "data": None}), 400

            if 'phone' in data and data['phone']:
                phone = data['phone']
                if not (phone.isdigit() and len(phone) == 11 and phone.startswith('1')):
                    return jsonify({"code": 400, "msg": "手机号必须是11位数字且以1开头", "data": None}), 400

            if 'email' in data and data['email'] and '@' not in data['email']:
                return jsonify({"code": 400, "msg": "邮箱格式不正确", "data": None}), 400

            update_fields = []
            update_values = []

            for field in ALLOWED_UPDATE_FIELDS:
                if field in data:
                    update_fields.append(f"{field} = ?")
                    update_values.append(data[field])

            if not update_fields:
                return jsonify({"code": 400, "msg": "没有提供更新数据", "data": None}), 400

            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            update_values.append(id)

            conn.execute(
                f"UPDATE users SET {', '.join(update_fields)} WHERE id = ?",
                update_values
            )

        log_action(
            user_id=session.get('user_id'),
            user_name=session.get('name'),
            action='update',
            module='users',
            description=f'更新用户: {old_data["name"]}',
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
            is_sensitive=is_sensitive_operation('update', 'users'),
            old_data=json.dumps(old_data),
            new_data=json.dumps(data)
        )

        return jsonify({"code": 200, "msg": "更新成功", "data": None})
    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# ========== 4. 重置密码 ==========
@users_bp.route('/<int:id>/reset-password', methods=['PUT'])
@admin_required
@db_operation
def reset_password(id):
    try:
        data = request.get_json()
        new_password = data.get('new_password')

        if not new_password:
            return jsonify({"code": 400, "msg": "新密码不能为空", "data": None}), 400

        if len(new_password) < 8:
            return jsonify({"code": 400, "msg": "密码至少需要8位", "data": None}), 400
        if not any(c.islower() for c in new_password):
            return jsonify({"code": 400, "msg": "密码必须包含小写字母", "data": None}), 400
        if not any(c.isupper() for c in new_password):
            return jsonify({"code": 400, "msg": "密码必须包含大写字母", "data": None}), 400
        if not any(c.isdigit() for c in new_password):
            return jsonify({"code": 400, "msg": "密码必须包含数字", "data": None}), 400

        with get_db() as conn:
            user = conn.execute('SELECT * FROM users WHERE id = ?', (id,)).fetchone()
            if not user:
                return jsonify({"code": 404, "msg": "用户不存在", "data": None}), 404

            salt = secrets.token_hex(16)
            pwd_hash = hashlib.sha256((new_password + salt).encode('utf-8')).hexdigest()

            conn.execute(
                'UPDATE users SET password_hash = ?, salt = ?, login_failed_count = 0, locked_until = NULL WHERE id = ?',
                (pwd_hash, salt, id)
            )

        log_action(
            user_id=session.get('user_id'),
            user_name=session.get('name'),
            action='password_reset',
            module='users',
            description=f'重置用户密码: {user["name"]}',
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
            is_sensitive=is_sensitive_operation('password_reset', 'users')
        )

        return jsonify({"code": 200, "msg": "密码重置成功", "data": None})
    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# ========== 5. 绑定老人 ==========
@users_bp.route('/<int:family_user_id>/bind-elder', methods=['POST'])
@admin_required
@db_operation
def bind_elder(family_user_id):
    try:
        data = request.get_json()
        elder_id = data.get('elder_id')

        if not elder_id:
            return jsonify({"code": 400, "msg": "老人ID不能为空", "data": None}), 400

        with get_db() as conn:
            family_user = conn.execute(
                'SELECT * FROM users WHERE id = ? AND role = ?',
                (family_user_id, 'family')
            ).fetchone()
            if not family_user:
                return jsonify({"code": 404, "msg": "子女用户不存在", "data": None}), 404

            elder = conn.execute('SELECT * FROM elders WHERE id = ?', (elder_id,)).fetchone()
            if not elder:
                return jsonify({"code": 404, "msg": "老人信息不存在", "data": None}), 404

            existing = conn.execute(
                'SELECT * FROM family_elder_bindings WHERE family_user_id = ? AND elder_id = ?',
                (family_user_id, elder_id)
            ).fetchone()
            if existing:
                return jsonify({"code": 400, "msg": "该老人已绑定此子女", "data": None}), 400

            conn.execute(
                'INSERT INTO family_elder_bindings (family_user_id, elder_id) VALUES (?, ?)',
                (family_user_id, elder_id)
            )

        log_action(
            user_id=session.get('user_id'),
            user_name=session.get('name'),
            action='create',
            module='elders',
            description=f'绑定子女 {family_user["name"]} 与老人 {elder["name"]}',
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )

        return jsonify({"code": 200, "msg": "绑定成功", "data": None})
    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# ========== 6. 获取子女已绑定的老人 ==========
@users_bp.route('/<int:family_user_id>/bound-elders', methods=['GET'])
@admin_required
@db_operation
def get_bound_elders(family_user_id):
    with get_db() as conn:
        family_user = conn.execute(
            'SELECT * FROM users WHERE id = ? AND role = ?',
            (family_user_id, 'family')
        ).fetchone()
        if not family_user:
            return jsonify({"code": 404, "msg": "子女用户不存在", "data": None}), 404

        bound_elders = conn.execute('''
            SELECT e.* FROM elders e
            JOIN family_elder_bindings feb ON e.id = feb.elder_id
            WHERE feb.family_user_id = ?
            ORDER BY e.name
        ''', (family_user_id,)).fetchall()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": [dict(e) for e in bound_elders]
    })


# ========== 7. 解绑老人 ==========
@users_bp.route('/<int:family_user_id>/bind-elder/<int:elder_id>', methods=['DELETE'])
@admin_required
@db_operation
def unbind_elder(family_user_id, elder_id):
    try:
        with get_db() as conn:
            family_user = conn.execute('SELECT * FROM users WHERE id = ?', (family_user_id,)).fetchone()
            elder = conn.execute('SELECT * FROM elders WHERE id = ?', (elder_id,)).fetchone()

            cursor = conn.cursor()
            cursor.execute(
                'DELETE FROM family_elder_bindings WHERE family_user_id = ? AND elder_id = ?',
                (family_user_id, elder_id)
            )
            if cursor.rowcount == 0:
                return jsonify({"code": 404, "msg": "绑定关系不存在", "data": None}), 404

        log_action(
            user_id=session.get('user_id'),
            user_name=session.get('name'),
            action='delete',
            module='elders',
            description=f'解绑子女 {family_user["name"]} 与老人 {elder["name"]}',
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
            is_sensitive=is_sensitive_operation('delete', 'elders')
        )

        return jsonify({"code": 200, "msg": "解绑成功", "data": None})
    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# ========== 8. 获取锁定账号列表 ==========
@users_bp.route('/locked', methods=['GET'])
@admin_required
@db_operation
def get_locked_accounts():
    with get_db() as conn:
        locked_users = conn.execute('''
            SELECT id, username, role, name, login_failed_count, locked_until, created_at 
            FROM users 
            WHERE locked_until IS NOT NULL AND locked_until > CURRENT_TIMESTAMP
            ORDER BY locked_until DESC
        ''').fetchall()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": [dict(u) for u in locked_users]
    })


# ========== 9. 解锁账号 ==========
@users_bp.route('/<int:id>/unlock', methods=['PUT'])
@admin_required
@db_operation
def unlock_account(id):
    try:
        with get_db() as conn:
            user = conn.execute('SELECT * FROM users WHERE id = ?', (id,)).fetchone()
            if not user:
                return jsonify({"code": 404, "msg": "用户不存在", "data": None}), 404

            conn.execute(
                'UPDATE users SET login_failed_count = 0, locked_until = NULL WHERE id = ?',
                (id,)
            )

        log_action(
            user_id=session.get('user_id'),
            user_name=session.get('name'),
            action='unlock',
            module='users',
            description=f'解锁账号: {user["name"]}',
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
            is_sensitive=is_sensitive_operation('unlock', 'users')
        )

        return jsonify({"code": 200, "msg": "账号解锁成功", "data": None})
    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# ========== 10. 锁定账号 ==========
@users_bp.route('/<int:id>/lock', methods=['PUT'])
@admin_required
@db_operation
def lock_account(id):
    try:
        data = request.get_json() if request.is_json else {}
        duration_minutes = data.get('duration_minutes', 10)

        if duration_minutes < 1:
            duration_minutes = 10

        with get_db() as conn:
            user = conn.execute('SELECT * FROM users WHERE id = ?', (id,)).fetchone()
            if not user:
                return jsonify({"code": 404, "msg": "用户不存在", "data": None}), 404

            if user['id'] == session.get('user_id'):
                return jsonify({"code": 400, "msg": "不能锁定自己的账号", "data": None}), 400

            conn.execute(f'''
                UPDATE users 
                SET login_failed_count = 5, locked_until = datetime(CURRENT_TIMESTAMP, '+{duration_minutes} minutes') 
                WHERE id = ?
            ''', (id,))

        log_action(
            user_id=session.get('user_id'),
            user_name=session.get('name'),
            action='lock',
            module='users',
            description=f'锁定账号: {user["name"]}, 时长: {duration_minutes}分钟',
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
            is_sensitive=is_sensitive_operation('lock', 'users')
        )

        return jsonify({"code": 200, "msg": f"账号已锁定{duration_minutes}分钟", "data": None})
    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# ========== 11. 护工分配老人 ==========
@users_bp.route('/<int:caregiver_id>/assign-elder', methods=['POST'])
@admin_required
@db_operation
def assign_elder_to_caregiver(caregiver_id):
    try:
        data = request.get_json()
        elder_id = data.get('elder_id')

        if not elder_id:
            return jsonify({"code": 400, "msg": "老人ID不能为空", "data": None}), 400

        with get_db() as conn:
            caregiver = conn.execute(
                'SELECT * FROM users WHERE id = ? AND role = ?',
                (caregiver_id, 'caregiver')
            ).fetchone()
            if not caregiver:
                return jsonify({"code": 404, "msg": "护工用户不存在", "data": None}), 404

            elder = conn.execute('SELECT * FROM elders WHERE id = ?', (elder_id,)).fetchone()
            if not elder:
                return jsonify({"code": 404, "msg": "老人信息不存在", "data": None}), 404

            existing = conn.execute(
                'SELECT * FROM caregiver_elder_assignments WHERE caregiver_id = ? AND elder_id = ?',
                (caregiver_id, elder_id)
            ).fetchone()
            if existing:
                return jsonify({"code": 400, "msg": "该老人已分配给此护工", "data": None}), 400

            conn.execute(
                'INSERT INTO caregiver_elder_assignments (caregiver_id, elder_id) VALUES (?, ?)',
                (caregiver_id, elder_id)
            )

        log_action(
            user_id=session.get('user_id'),
            user_name=session.get('name'),
            action='create',
            module='elders',
            description=f'分配老人 {elder["name"]} 给护工 {caregiver["name"]}',
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )

        return jsonify({"code": 200, "msg": "分配成功", "data": None})
    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# ========== 12. 获取护工已分配的老人 ==========
@users_bp.route('/<int:caregiver_id>/assigned-elders', methods=['GET'])
@admin_required
@db_operation
def get_assigned_elders(caregiver_id):
    with get_db() as conn:
        caregiver = conn.execute(
            'SELECT * FROM users WHERE id = ? AND role = ?',
            (caregiver_id, 'caregiver')
        ).fetchone()
        if not caregiver:
            return jsonify({"code": 404, "msg": "护工用户不存在", "data": None}), 404

        assigned_elders = conn.execute('''
            SELECT e.* FROM elders e
            JOIN caregiver_elder_assignments cea ON e.id = cea.elder_id
            WHERE cea.caregiver_id = ?
            ORDER BY e.name
        ''', (caregiver_id,)).fetchall()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": [dict(e) for e in assigned_elders]
    })


# ========== 13. 取消护工老人分配 ==========
@users_bp.route('/<int:caregiver_id>/assign-elder/<int:elder_id>', methods=['DELETE'])
@admin_required
@db_operation
def unassign_elder_from_caregiver(caregiver_id, elder_id):
    try:
        with get_db() as conn:
            caregiver = conn.execute('SELECT * FROM users WHERE id = ?', (caregiver_id,)).fetchone()
            elder = conn.execute('SELECT * FROM elders WHERE id = ?', (elder_id,)).fetchone()

            cursor = conn.cursor()
            cursor.execute(
                'DELETE FROM caregiver_elder_assignments WHERE caregiver_id = ? AND elder_id = ?',
                (caregiver_id, elder_id)
            )
            if cursor.rowcount == 0:
                return jsonify({"code": 404, "msg": "分配关系不存在", "data": None}), 404

        log_action(
            user_id=session.get('user_id'),
            user_name=session.get('name'),
            action='delete',
            module='elders',
            description=f'取消护工 {caregiver["name"]} 与老人 {elder["name"]} 的分配',
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
            is_sensitive=is_sensitive_operation('delete', 'elders')
        )

        return jsonify({"code": 200, "msg": "取消分配成功", "data": None})
    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# ========== 14. 获取所有老人，标记是否已分配给指定护工 ==========
@users_bp.route('/<int:caregiver_id>/all-elders-with-status', methods=['GET'])
@admin_required
@db_operation
def get_all_elders_with_assignment_status(caregiver_id):
    with get_db() as conn:
        caregiver = conn.execute(
            'SELECT * FROM users WHERE id = ? AND role = ?',
            (caregiver_id, 'caregiver')
        ).fetchone()
        if not caregiver:
            return jsonify({"code": 404, "msg": "护工用户不存在", "data": None}), 404

        elders = conn.execute('''
            SELECT e.*, 
                CASE WHEN cea.id IS NOT NULL THEN 1 ELSE 0 END as is_assigned
            FROM elders e
            LEFT JOIN caregiver_elder_assignments cea ON e.id = cea.elder_id AND cea.caregiver_id = ?
            ORDER BY e.name
        ''', (caregiver_id,)).fetchall()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": [dict(e) for e in elders]
    })


# ========== 获取当前护工负责的老人列表 ==========
@users_bp.route('/my-assigned-elders', methods=['GET'])
@caregiver_required
@db_operation
def get_my_assigned_elders():
    """获取当前登录护工负责的所有老人"""
    caregiver_id = session.get('user_id')

    with get_db() as conn:
        elders = conn.execute('''
            SELECT e.*
            FROM elders e
            INNER JOIN caregiver_elder_assignments cea ON e.id = cea.elder_id
            WHERE cea.caregiver_id = ? 
                AND e.status = 'active'
            ORDER BY e.room_number, e.bed_number
        ''', (caregiver_id,)).fetchall()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": [dict(e) for e in elders]
    })
