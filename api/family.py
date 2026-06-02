"""
子女端 & 留言接口模块

包含两个Blueprint：
1. family_bp — 子女端接口（前缀 /api/v1/family）
2. caregiver_msg_bp — 护工回复留言（前缀 /api/v1/caregiver）
"""

import sqlite3
import json
import os
from flask import Blueprint, request, jsonify, session
from .decorators import admin_required, family_required, caregiver_required

family_bp = Blueprint('family', __name__, url_prefix='/api/v1/family')
caregiver_msg_bp = Blueprint('caregiver_msg', __name__, url_prefix='/api/v1/caregiver')


def get_db_connection():
    current_dir = os.path.dirname(__file__)
    db_path = os.path.join(current_dir, '..', 'instance', 'nursing_home.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def check_elder_binding(conn, family_user_id, elder_id):
    """检查子女是否绑定了指定老人，返回bool"""
    binding = conn.execute(
        'SELECT * FROM family_elder_bindings WHERE family_user_id = ? AND elder_id = ?',
        (family_user_id, elder_id)
    ).fetchone()
    return binding is not None


# ========== family_bp 接口 ==========

# 1. 获取绑定老人列表
@family_bp.route('/elders', methods=['GET'])
@family_required
def get_bound_elders():
    family_id = session['user_id']

    conn = get_db_connection()

    # 查询绑定老人
    elders = conn.execute(
        '''
        SELECT e.*
        FROM elders e
        JOIN family_elder_bindings feb ON e.id = feb.elder_id
        WHERE feb.family_user_id = ? AND e.status = 'active'
        ORDER BY e.id
        ''',
        (family_id,)
    ).fetchall()

    # 为每个老人获取最新健康数据
    result = []
    for elder in elders:
        elder_dict = dict(elder)

        latest_record = conn.execute(
            '''
            SELECT health_data FROM care_records
            WHERE elder_id = ?
            ORDER BY record_date DESC, created_at DESC
            LIMIT 1
            ''',
            (elder['id'],)
        ).fetchone()

        if latest_record and latest_record['health_data']:
            try:
                elder_dict['latest_health_data'] = json.loads(latest_record['health_data'])
            except json.JSONDecodeError:
                elder_dict['latest_health_data'] = None
        else:
            elder_dict['latest_health_data'] = None

        result.append(elder_dict)

    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": result
    })


# 1.1 获取绑定老人的护工信息
@family_bp.route('/elders/<int:elder_id>/caregivers', methods=['GET'])
@family_required
def get_elder_caregivers(elder_id):
    family_id = session['user_id']

    conn = get_db_connection()

    if not check_elder_binding(conn, family_id, elder_id):
        conn.close()
        return jsonify({"code": 403, "msg": "您没有权限查看该老人的护工信息", "data": None}), 403

    caregivers = conn.execute(
        '''
        SELECT u.id, u.name, u.phone
        FROM users u
        JOIN caregiver_elder_assignments cea ON u.id = cea.caregiver_id
        WHERE cea.elder_id = ? AND u.status = 'enabled'
        ORDER BY u.name
        ''',
        (elder_id,)
    ).fetchall()

    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": [dict(cg) for cg in caregivers]
    })


# 1.2 获取绑定老人列表（含未读消息数和护工信息）
@family_bp.route('/elders-with-messages', methods=['GET'])
@family_required
def get_bound_elders_with_messages():
    family_id = session['user_id']

    conn = get_db_connection()

    elders = conn.execute(
        '''
        SELECT e.id, e.name, e.gender, e.age, e.room_number, e.bed_number
        FROM elders e
        JOIN family_elder_bindings feb ON e.id = feb.elder_id
        WHERE feb.family_user_id = ? AND e.status = 'active'
        ORDER BY e.id
        ''',
        (family_id,)
    ).fetchall()

    result = []
    for elder in elders:
        elder_dict = dict(elder)

        unread = conn.execute('''
            SELECT COUNT(*) as count
            FROM messages
            WHERE elder_id = ?
              AND sender_role = 'caregiver'
              AND is_read = 0
        ''', (elder_dict['id'],)).fetchone()
        elder_dict['unread_count'] = unread['count'] or 0

        last_msg = conn.execute('''
            SELECT m.content, m.created_at, m.sender_role, m.sender_id, u.name as sender_name
            FROM messages m
            INNER JOIN users u ON m.sender_id = u.id
            WHERE m.elder_id = ?
            ORDER BY m.created_at DESC
            LIMIT 1
        ''', (elder_dict['id'],)).fetchone()

        if last_msg:
            elder_dict['last_message'] = last_msg['content']
            elder_dict['last_message_time'] = last_msg['created_at']
            elder_dict['last_message_sender_role'] = last_msg['sender_role']
            elder_dict['last_message_sender_name'] = last_msg['sender_name']
        else:
            elder_dict['last_message'] = None
            elder_dict['last_message_time'] = None
            elder_dict['last_message_sender_role'] = None
            elder_dict['last_message_sender_name'] = None

        caregivers = conn.execute('''
            SELECT u.id, u.name
            FROM users u
            JOIN caregiver_elder_assignments cea ON u.id = cea.caregiver_id
            WHERE cea.elder_id = ? AND u.status = 'enabled'
            ORDER BY u.name
        ''', (elder_dict['id'],)).fetchall()
        elder_dict['caregivers'] = [dict(cg) for cg in caregivers]

        result.append(elder_dict)

    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": result
    })


# 2. 获取绑定老人健康数据
@family_bp.route('/elders/<int:elder_id>/health', methods=['GET'])
@family_required
def get_elder_health(elder_id):
    family_id = session['user_id']
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    conn = get_db_connection()

    # 验证绑定
    if not check_elder_binding(conn, family_id, elder_id):
        conn.close()
        return jsonify({"code": 403, "msg": "您没有权限查看该老人的健康数据", "data": None}), 403

    # 查询总数
    total_count = conn.execute(
        'SELECT COUNT(*) FROM care_records WHERE elder_id = ?',
        (elder_id,)
    ).fetchone()[0]

    # 查询护理记录
    offset = (page - 1) * page_size
    records = conn.execute(
        '''
        SELECT cr.*, u.name as caregiver_name
        FROM care_records cr
        LEFT JOIN users u ON cr.caregiver_id = u.id
        WHERE cr.elder_id = ?
        ORDER BY cr.record_date DESC, cr.created_at DESC
        LIMIT ? OFFSET ?
        ''',
        (elder_id, page_size, offset)
    ).fetchall()

    conn.close()

    # 解析JSON字段
    records_list = []
    for row in records:
        record = dict(row)
        for field in ['health_data', 'diet', 'sleep', 'emotion']:
            if record.get(field):
                try:
                    record[field] = json.loads(record[field])
                except json.JSONDecodeError:
                    record[field] = None
        records_list.append(record)

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "list": records_list,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_count,
                "total_pages": (total_count + page_size - 1) // page_size
            }
        }
    })


# 3. 获取报警消息
@family_bp.route('/alarms', methods=['GET'])
@family_required
def get_family_alarms():
    family_id = session['user_id']
    status = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    conn = get_db_connection()

    # 构建查询 — 只查绑定老人的报警
    conditions = [
        "a.elder_id IN (SELECT elder_id FROM family_elder_bindings WHERE family_user_id = ?)"
    ]
    params = [family_id]

    if status:
        conditions.append("a.status = ?")
        params.append(status)

    where_clause = " AND ".join(conditions)

    total_count = conn.execute(
        f"SELECT COUNT(*) FROM alarms a WHERE {where_clause}", params
    ).fetchone()[0]

    offset = (page - 1) * page_size
    alarms = conn.execute(
        f'''
        SELECT a.*, e.name as elder_name, e.room_number
        FROM alarms a
        JOIN elders e ON a.elder_id = e.id
        WHERE {where_clause}
        ORDER BY a.triggered_at DESC
        LIMIT ? OFFSET ?
        ''',
        params + [page_size, offset]
    ).fetchall()
    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "list": [dict(a) for a in alarms],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_count,
                "total_pages": (total_count + page_size - 1) // page_size
            }
        }
    })


# 3.1 获取指定老人的报警消息
@family_bp.route('/elders/<int:elder_id>/alarms', methods=['GET'])
@family_required
def get_elder_alarms(elder_id):
    family_id = session['user_id']
    status = request.args.get('status', '').strip()

    conn = get_db_connection()

    if not check_elder_binding(conn, family_id, elder_id):
        conn.close()
        return jsonify({"code": 403, "msg": "您没有权限查看该老人的报警信息", "data": None}), 403

    conditions = ["a.elder_id = ?"]
    params = [elder_id]

    if status:
        conditions.append("a.status = ?")
        params.append(status)

    where_clause = " AND ".join(conditions)

    alarms = conn.execute(
        f'''
        SELECT a.*, e.name as elder_name, e.room_number
        FROM alarms a
        JOIN elders e ON a.elder_id = e.id
        WHERE {where_clause}
        ORDER BY a.triggered_at DESC
        LIMIT 50
        ''',
        params
    ).fetchall()
    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": [dict(a) for a in alarms]
    })


# 3.2 获取报警详情（含处理时间线）
@family_bp.route('/alarms/<int:alarm_id>', methods=['GET'])
@family_required
def get_alarm_detail(alarm_id):
    family_id = session['user_id']

    conn = get_db_connection()

    alarm = conn.execute('''
        SELECT a.*, e.name as elder_name, e.room_number,
            u.name as handler_name
        FROM alarms a
        JOIN elders e ON a.elder_id = e.id
        LEFT JOIN users u ON a.handler_id = u.id
        WHERE a.id = ?
    ''', (alarm_id,)).fetchone()

    if not alarm:
        conn.close()
        return jsonify({"code": 404, "msg": "报警记录不存在", "data": None}), 404

    binding = conn.execute(
        'SELECT 1 FROM family_elder_bindings WHERE family_user_id = ? AND elder_id = ?',
        (family_id, alarm['elder_id'])
    ).fetchone()
    if not binding:
        conn.close()
        return jsonify({"code": 403, "msg": "您没有权限查看该报警", "data": None}), 403

    alarm_dict = dict(alarm)

    response_duration = None
    if alarm_dict['status'] in ('processing', 'resolved') and alarm_dict.get('triggered_at') and alarm_dict.get('processing_at'):
        try:
            from datetime import datetime
            triggered = datetime.fromisoformat(alarm_dict['triggered_at'])
            processing = datetime.fromisoformat(alarm_dict['processing_at'])
            diff = processing - triggered
            if diff.total_seconds() > 0:
                hours = int(diff.total_seconds() // 3600)
                mins = int((diff.total_seconds() % 3600) // 60)
                secs = int(diff.total_seconds() % 60)
                if hours > 0:
                    response_duration = f"{hours}小时{mins}分钟"
                else:
                    response_duration = f"{mins}分钟{secs}秒"
        except Exception:
            pass
    alarm_dict['response_duration'] = response_duration

    resolve_duration = None
    if alarm_dict['status'] == 'resolved' and alarm_dict.get('processing_at') and alarm_dict.get('resolved_at'):
        try:
            from datetime import datetime
            processing = datetime.fromisoformat(alarm_dict['processing_at'])
            resolved = datetime.fromisoformat(alarm_dict['resolved_at'])
            diff = resolved - processing
            if diff.total_seconds() > 0:
                hours = int(diff.total_seconds() // 3600)
                mins = int((diff.total_seconds() % 3600) // 60)
                secs = int(diff.total_seconds() % 60)
                if hours > 0:
                    resolve_duration = f"{hours}小时{mins}分钟"
                else:
                    resolve_duration = f"{mins}分钟{secs}秒"
        except Exception:
            pass
    alarm_dict['resolve_duration'] = resolve_duration

    action_logs = conn.execute('''
        SELECT al.*, u.name as operator_name
        FROM alarm_action_logs al
        JOIN users u ON al.user_id = u.id
        WHERE al.alarm_id = ?
        ORDER BY al.created_at ASC
    ''', (alarm_id,)).fetchall()

    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "alarm": alarm_dict,
            "action_logs": [dict(log) for log in action_logs]
        }
    })


# 3.3 获取未处理报警数量
@family_bp.route('/alarms/unhandled-count', methods=['GET'])
@family_required
def get_unhandled_alarm_count():
    family_id = session['user_id']

    conn = get_db_connection()

    count = conn.execute('''
        SELECT COUNT(*) as count
        FROM alarms a
        WHERE a.elder_id IN (
            SELECT elder_id FROM family_elder_bindings WHERE family_user_id = ?
        ) AND a.status = 'unhandled'
    ''', (family_id,)).fetchone()

    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {"count": count['count'] or 0}
    })


# 4. 获取留言列表
@family_bp.route('/elders/<int:elder_id>/messages', methods=['GET'])
@family_required
def get_elder_messages(elder_id):
    family_id = session['user_id']
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    conn = get_db_connection()

    if not check_elder_binding(conn, family_id, elder_id):
        conn.close()
        return jsonify({"code": 403, "msg": "您没有权限查看该老人的留言", "data": None}), 403

    total_count = conn.execute(
        'SELECT COUNT(*) FROM messages WHERE elder_id = ?',
        (elder_id,)
    ).fetchone()[0]

    # 标记护工回复为已读
    conn.execute(
        'UPDATE messages SET is_read = 1 WHERE elder_id = ? AND sender_role = ? AND is_read = 0',
        (elder_id, 'caregiver')
    )
    conn.commit()

    offset = (page - 1) * page_size
    messages = conn.execute(
        '''
        SELECT m.*, u.name as sender_name
        FROM messages m
        LEFT JOIN users u ON m.sender_id = u.id
        WHERE m.elder_id = ?
        ORDER BY m.created_at ASC
        LIMIT ? OFFSET ?
        ''',
        (elder_id, page_size, offset)
    ).fetchall()
    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "list": [dict(m) for m in messages],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_count,
                "total_pages": (total_count + page_size - 1) // page_size
            }
        }
    })


# 5. 发送留言（子女端）
@family_bp.route('/messages', methods=['POST'])
@family_required
def send_message():
    family_id = session['user_id']
    data = request.get_json()

    elder_id = data.get('elder_id')
    content = data.get('content', '').strip()

    if not elder_id:
        return jsonify({"code": 400, "msg": "老人ID不能为空", "data": None}), 400
    if not content:
        return jsonify({"code": 400, "msg": "留言内容不能为空", "data": None}), 400
    if len(content) > 500:
        return jsonify({"code": 400, "msg": "留言内容不能超过500字", "data": None}), 400

    conn = get_db_connection()

    if not check_elder_binding(conn, family_id, elder_id):
        conn.close()
        return jsonify({"code": 403, "msg": "您没有权限给该老人留言", "data": None}), 403

    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO messages (elder_id, sender_id, sender_role, content)
            VALUES (?, ?, 'family', ?)
        ''', (elder_id, family_id, content))
        conn.commit()
        new_id = cursor.lastrowid
    except Exception as e:
        conn.close()
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}", "data": None}), 500

    # 创建消息通知（不影响主流程）
    try:
        from .notifications import create_notification
        # 通知该老人相关的护工
        caregivers = conn.execute(
            'SELECT DISTINCT caregiver_id FROM caregiver_elder_assignments WHERE elder_id = ?',
            (elder_id,)
        ).fetchall()
        for cg in caregivers:
            create_notification(cg['caregiver_id'], 'message', '新留言通知',
                                f'您负责的老人收到一条来自家属的新留言', new_id)
        # 通知所有管理员
        admins = conn.execute('SELECT id FROM users WHERE role = ?', ('admin',)).fetchall()
        for admin in admins:
            create_notification(admin['id'], 'message', '新留言通知',
                                f'收到一条来自家属的新留言（老人ID:{elder_id}）', new_id)
    except Exception:
        pass

    conn.close()

    return jsonify({
        "code": 200,
        "msg": "留言发送成功",
        "data": {"id": new_id}
    })


# 6. 标记消息为已读
@family_bp.route('/messages/mark-read', methods=['POST'])
@family_required
def mark_messages_read():
    family_id = session['user_id']
    data = request.get_json()
    elder_id = data.get('elder_id')
    
    if not elder_id:
        return jsonify({"code": 400, "msg": "老人ID不能为空", "data": None}), 400
    
    conn = get_db_connection()
    
    # 验证绑定
    if not check_elder_binding(conn, family_id, elder_id):
        conn.close()
        return jsonify({"code": 403, "msg": "您没有权限操作该老人的消息", "data": None}), 403
    
    # 标记护工发送的消息为已读
    conn.execute('''
        UPDATE messages 
        SET is_read = 1 
        WHERE elder_id = ? AND sender_role = ? AND is_read = 0
    ''', (elder_id, 'caregiver'))
    conn.commit()
    conn.close()
    
    return jsonify({"code": 200, "msg": "标记已读成功", "data": None})


# ========== caregiver_msg_bp 接口 ==========

# 6. 护工获取留言列表
@caregiver_msg_bp.route('/messages', methods=['GET'])
@caregiver_required
def caregiver_get_messages():
    caregiver_id = session['user_id']
    elder_id = request.args.get('elder_id', type=int)
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    conn = get_db_connection()

    # 只显示该护工负责的老人的留言
    conditions = ["m.elder_id IN (SELECT DISTINCT elder_id FROM care_tasks WHERE caregiver_id = ?)"]
    params = [caregiver_id]

    if elder_id:
        conditions.append("m.elder_id = ?")
        params.append(elder_id)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    total_count = conn.execute(
        f"SELECT COUNT(*) FROM messages m WHERE {where_clause}", params
    ).fetchone()[0]

    offset = (page - 1) * page_size
    messages = conn.execute(
        f'''
        SELECT m.*, e.name as elder_name, u.name as sender_name, u.role as sender_role
        FROM messages m
        JOIN elders e ON m.elder_id = e.id
        JOIN users u ON m.sender_id = u.id
        WHERE {where_clause}
        ORDER BY m.created_at DESC
        LIMIT ? OFFSET ?
        ''',
        params + [page_size, offset]
    ).fetchall()
    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "list": [dict(m) for m in messages],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_count,
                "total_pages": (total_count + page_size - 1) // page_size
            }
        }
    })


# 7. 护工回复留言
@caregiver_msg_bp.route('/messages', methods=['POST'])
@caregiver_required
def caregiver_reply():
    caregiver_id = session['user_id']
    data = request.get_json()

    elder_id = data.get('elder_id')
    content = data.get('content', '').strip()

    if not elder_id:
        return jsonify({"code": 400, "msg": "老人ID不能为空", "data": None}), 400
    if not content:
        return jsonify({"code": 400, "msg": "回复内容不能为空", "data": None}), 400
    if len(content) > 500:
        return jsonify({"code": 400, "msg": "回复内容不能超过500字", "data": None}), 400

    conn = get_db_connection()

    elder = conn.execute('SELECT * FROM elders WHERE id = ?', (elder_id,)).fetchone()
    if not elder:
        conn.close()
        return jsonify({"code": 404, "msg": "老人信息不存在", "data": None}), 404

    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO messages (elder_id, sender_id, sender_role, content)
            VALUES (?, ?, 'caregiver', ?)
        ''', (elder_id, caregiver_id, content))
        conn.commit()
        new_id = cursor.lastrowid
    except Exception as e:
        conn.close()
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}", "data": None}), 500

    # 创建消息通知（不影响主流程）
    try:
        from .notifications import create_notification
        # 通知绑定该老人的家属
        family_members = conn.execute(
            'SELECT DISTINCT family_user_id FROM family_elder_bindings WHERE elder_id = ?',
            (elder_id,)
        ).fetchall()
        for fm in family_members:
            create_notification(fm['family_user_id'], 'message', '新回复通知',
                                f'护工回复了关于老人的留言', new_id)
        # 通知所有管理员
        admins = conn.execute('SELECT id FROM users WHERE role = ?', ('admin',)).fetchall()
        for admin in admins:
            create_notification(admin['id'], 'message', '新回复通知',
                                f'护工回复了一条留言（老人ID:{elder_id}）', new_id)
    except Exception:
        pass

    conn.close()

    return jsonify({
        "code": 200,
        "msg": "回复成功",
        "data": {"id": new_id}
    })


# ========== admin_msg_bp 接口 ==========

admin_msg_bp = Blueprint('admin_msg', __name__, url_prefix='/api/v1/admin')


@admin_msg_bp.route('/messages', methods=['GET'])
@admin_required
def admin_get_messages():
    """管理员获取所有留言列表（支持分页、按老人筛选、按角色筛选）"""
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    elder_id = request.args.get('elder_id', type=int)
    sender_role = request.args.get('sender_role', '').strip()

    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    conn = get_db_connection()

    conditions = []
    params = []

    if elder_id:
        conditions.append("m.elder_id = ?")
        params.append(elder_id)

    if sender_role:
        conditions.append("m.sender_role = ?")
        params.append(sender_role)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    total_count = conn.execute(
        f"SELECT COUNT(*) FROM messages m WHERE {where_clause}", params
    ).fetchone()[0]

    offset = (page - 1) * page_size
    messages = conn.execute(
        f'''
        SELECT m.*, e.name as elder_name, e.room_number, u.name as sender_name
        FROM messages m
        JOIN elders e ON m.elder_id = e.id
        JOIN users u ON m.sender_id = u.id
        WHERE {where_clause}
        ORDER BY m.created_at DESC
        LIMIT ? OFFSET ?
        ''',
        params + [page_size, offset]
    ).fetchall()
    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "list": [dict(m) for m in messages],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_count,
                "total_pages": (total_count + page_size - 1) // page_size
            }
        }
    })


@admin_msg_bp.route('/messages/export', methods=['GET'])
@admin_required
def admin_export_messages():
    """导出消息记录 - Excel格式"""
    elder_id = request.args.get('elder_id', type=int)
    sender_role = request.args.get('sender_role', '').strip()

    conn = get_db_connection()

    conditions = []
    params = []

    if elder_id:
        conditions.append("m.elder_id = ?")
        params.append(elder_id)

    if sender_role:
        conditions.append("m.sender_role = ?")
        params.append(sender_role)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    messages = conn.execute(
        f'''
        SELECT m.*, e.name as elder_name, e.room_number, u.name as sender_name
        FROM messages m
        JOIN elders e ON m.elder_id = e.id
        JOIN users u ON m.sender_id = u.id
        WHERE {where_clause}
        ORDER BY m.created_at DESC
        LIMIT 10000
        ''',
        params
    ).fetchall()
    conn.close()

    try:
        import pandas as pd
        from datetime import datetime
        import io

        role_map = {'family': '家属', 'caregiver': '护工'}
        data_rows = []
        for msg in messages:
            data_rows.append({
                'ID': msg['id'],
                '老人姓名': msg['elder_name'],
                '房间号': msg['room_number'],
                '发送者': msg['sender_name'],
                '发送者角色': role_map.get(msg['sender_role'], msg['sender_role']),
                '消息内容': msg['content'],
                '已读': '是' if msg['is_read'] else '否',
                '发送时间': msg['created_at']
            })

        df = pd.DataFrame(data_rows)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='消息记录')
            worksheet = writer.sheets['消息记录']
            for idx, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max() if len(df) > 0 else 0, len(col))
                col_letter = chr(65 + idx) if idx < 26 else chr(64 + idx // 26) + chr(65 + idx % 26)
                worksheet.column_dimensions[col_letter].width = min(max_len + 4, 50)

        output.seek(0)
        filename = f'消息记录_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        from flask import send_file
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except ImportError:
        return jsonify({"code": 500, "msg": "导出功能依赖pandas库，请安装：pip install pandas openpyxl", "data": None}), 500
