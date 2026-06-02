"""
亲情留言板API模块
提供亲情留言的发送、拉取、标记已读、节日模板接口
数据完全独立于现有messages表，使用family_messages表
"""

import sqlite3
import os
import uuid
from flask import Blueprint, request, jsonify, session
from .decorators import family_required, caregiver_required, admin_required, login_required

family_messages_bp = Blueprint('family_messages', __name__, url_prefix='/api/v1/family-messages')

ALLOWED_VOICE_EXTENSIONS = {'mp3', 'wav'}
MAX_VOICE_SIZE = 10 * 1024 * 1024


def get_db_connection():
    current_dir = os.path.dirname(__file__)
    db_path = os.path.join(current_dir, '..', 'instance', 'nursing_home.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def check_family_binding(conn, family_user_id, elder_id):
    binding = conn.execute(
        'SELECT 1 FROM family_elder_bindings WHERE family_user_id = ? AND elder_id = ?',
        (family_user_id, elder_id)
    ).fetchone()
    return binding is not None


def check_caregiver_assignment(conn, caregiver_id, elder_id):
    assignment = conn.execute(
        'SELECT 1 FROM caregiver_elder_assignments WHERE caregiver_id = ? AND elder_id = ?',
        (caregiver_id, elder_id)
    ).fetchone()
    return assignment is not None


def get_voice_upload_dir():
    current_dir = os.path.dirname(__file__)
    upload_dir = os.path.join(current_dir, '..', 'uploads', 'voice_messages')
    upload_dir = os.path.abspath(upload_dir)
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def save_voice_file(file):
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_VOICE_EXTENSIONS:
        return None
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    if file_size > MAX_VOICE_SIZE:
        return None
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = get_voice_upload_dir()
    file_path = os.path.join(upload_dir, unique_name)
    file.save(file_path)
    relative_path = os.path.join('uploads', 'voice_messages', unique_name).replace('\\', '/')
    return relative_path


@family_messages_bp.route('/send', methods=['POST'])
@login_required
def send_message():
    user_id = session.get('user_id')
    user_role = session.get('role')

    if user_role not in ('family', 'caregiver'):
        return jsonify({"code": 403, "msg": "无权发送亲情留言", "data": None}), 403

    elder_id = request.form.get('elder_id', type=int) if request.content_type and 'multipart' in request.content_type else None
    message_type = request.form.get('message_type', 'text') if request.content_type and 'multipart' in request.content_type else None
    content = None
    voice_file = None
    receiver_id = None
    receiver_type = None
    festival_template_id = None

    if request.content_type and 'multipart' in request.content_type:
        content = request.form.get('content', '').strip()
        message_type = message_type or 'text'
        elder_id = elder_id
        receiver_id = request.form.get('receiver_id', type=int)
        receiver_type = request.form.get('receiver_type', '').strip()
        festival_template_id = request.form.get('festival_template_id', type=int)
        voice_file = request.files.get('voice_file')
    else:
        data = request.get_json()
        if not data:
            return jsonify({"code": 400, "msg": "请求数据不能为空", "data": None}), 400
        elder_id = data.get('elder_id')
        content = (data.get('content') or '').strip()
        message_type = data.get('message_type', 'text')
        receiver_id = data.get('receiver_id')
        receiver_type = data.get('receiver_type', '')
        festival_template_id = data.get('festival_template_id')

    if not elder_id:
        return jsonify({"code": 400, "msg": "老人ID不能为空", "data": None}), 400

    if message_type not in ('text', 'voice'):
        return jsonify({"code": 400, "msg": "消息类型无效", "data": None}), 400

    conn = get_db_connection()

    try:
        if user_role == 'family':
            if not check_family_binding(conn, user_id, elder_id):
                conn.close()
                return jsonify({"code": 403, "msg": "您没有权限给该老人留言", "data": None}), 403
            sender_type = 'family'
            if not receiver_id or not receiver_type:
                caregivers = conn.execute(
                    'SELECT caregiver_id FROM caregiver_elder_assignments WHERE elder_id = ? LIMIT 1',
                    (elder_id,)
                ).fetchone()
                if caregivers:
                    receiver_id = caregivers['caregiver_id']
                    receiver_type = 'caregiver'
                else:
                    conn.close()
                    return jsonify({"code": 400, "msg": "该老人暂无负责护工", "data": None}), 400
        else:
            if not check_caregiver_assignment(conn, user_id, elder_id):
                conn.close()
                return jsonify({"code": 403, "msg": "您没有权限给该老人留言", "data": None}), 403
            sender_type = 'caregiver'
            if not receiver_id or not receiver_type:
                family_member = conn.execute(
                    'SELECT family_user_id FROM family_elder_bindings WHERE elder_id = ? LIMIT 1',
                    (elder_id,)
                ).fetchone()
                if family_member:
                    receiver_id = family_member['family_user_id']
                    receiver_type = 'family'
                else:
                    conn.close()
                    return jsonify({"code": 400, "msg": "该老人暂无绑定家属", "data": None}), 400

        voice_file_path = None
        if message_type == 'voice':
            if not voice_file:
                conn.close()
                return jsonify({"code": 400, "msg": "语音文件不能为空", "data": None}), 400
            voice_file_path = save_voice_file(voice_file)
            if not voice_file_path:
                conn.close()
                return jsonify({"code": 400, "msg": "语音文件上传失败，仅支持mp3/wav格式，大小不超过10MB", "data": None}), 400
        else:
            if not content:
                conn.close()
                return jsonify({"code": 400, "msg": "留言内容不能为空", "data": None}), 400
            if len(content) > 500:
                conn.close()
                return jsonify({"code": 400, "msg": "留言内容不能超过500字", "data": None}), 400

        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO family_messages (elder_id, sender_id, sender_type, receiver_id, receiver_type, content, message_type, voice_file_path, is_read, festival_template_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        ''', (elder_id, user_id, sender_type, receiver_id, receiver_type, content, message_type, voice_file_path, festival_template_id))
        conn.commit()
        new_id = cursor.lastrowid

        try:
            from .notifications import create_notification
            elder_name_row = conn.execute('SELECT name FROM elders WHERE id = ?', (elder_id,)).fetchone()
            elder_name = elder_name_row['name'] if elder_name_row else ''
            sender_name_row = conn.execute('SELECT name FROM users WHERE id = ?', (user_id,)).fetchone()
            sender_name = sender_name_row['name'] if sender_name_row else ''
            role_label = '家属' if sender_type == 'family' else '护工'
            create_notification(
                receiver_id, 'message',
                '新亲情留言',
                f'{role_label}{sender_name}给老人{elder_name}发送了一条亲情留言',
                new_id
            )
        except Exception:
            pass

        conn.close()

        return jsonify({
            "code": 200,
            "msg": "留言发送成功",
            "data": {"id": new_id}
        })

    except Exception as e:
        conn.close()
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}", "data": None}), 500


@family_messages_bp.route('/list', methods=['GET'])
@login_required
def get_messages():
    user_id = session.get('user_id')
    user_role = session.get('role')

    if user_role not in ('family', 'caregiver', 'admin'):
        return jsonify({"code": 403, "msg": "无权访问", "data": None}), 403

    elder_id = request.args.get('elder_id', type=int)
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    is_read = request.args.get('is_read', '').strip()
    order = request.args.get('order', 'desc').strip()

    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    conn = get_db_connection()

    try:
        conditions = []
        params = []

        if user_role == 'family':
            conditions.append("fm.elder_id IN (SELECT elder_id FROM family_elder_bindings WHERE family_user_id = ?)")
            params.append(user_id)
            if elder_id:
                if not check_family_binding(conn, user_id, elder_id):
                    conn.close()
                    return jsonify({"code": 403, "msg": "您没有权限查看该老人的留言", "data": None}), 403
                conditions.append("fm.elder_id = ?")
                params.append(elder_id)
        elif user_role == 'caregiver':
            conditions.append("fm.elder_id IN (SELECT elder_id FROM caregiver_elder_assignments WHERE caregiver_id = ?)")
            params.append(user_id)
            if elder_id:
                if not check_caregiver_assignment(conn, user_id, elder_id):
                    conn.close()
                    return jsonify({"code": 403, "msg": "您没有权限查看该老人的留言", "data": None}), 403
                conditions.append("fm.elder_id = ?")
                params.append(elder_id)

        if is_read != '':
            conditions.append("fm.is_read = ?")
            params.append(int(is_read))

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        order_clause = "DESC" if order == "desc" else "ASC"

        total_count = conn.execute(
            f"SELECT COUNT(*) FROM family_messages fm WHERE {where_clause}", params
        ).fetchone()[0]

        offset = (page - 1) * page_size
        messages = conn.execute(
            f'''
            SELECT fm.*, e.name as elder_name, e.room_number,
                   su.name as sender_name, ru.name as receiver_name
            FROM family_messages fm
            JOIN elders e ON fm.elder_id = e.id
            JOIN users su ON fm.sender_id = su.id
            JOIN users ru ON fm.receiver_id = ru.id
            WHERE {where_clause}
            ORDER BY fm.created_at {order_clause}
            LIMIT ? OFFSET ?
            ''',
            params + [page_size, offset]
        ).fetchall()

        if user_role in ('family', 'caregiver') and elder_id:
            if user_role == 'family':
                conn.execute(
                    'UPDATE family_messages SET is_read = 1 WHERE elder_id = ? AND receiver_id = ? AND is_read = 0',
                    (elder_id, user_id)
                )
            else:
                conn.execute(
                    'UPDATE family_messages SET is_read = 1 WHERE elder_id = ? AND receiver_id = ? AND is_read = 0',
                    (elder_id, user_id)
                )
            conn.commit()

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

    except Exception as e:
        conn.close()
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}", "data": None}), 500


@family_messages_bp.route('/mark-read', methods=['POST'])
@login_required
def mark_read():
    user_id = session.get('user_id')
    user_role = session.get('role')

    if user_role not in ('family', 'caregiver'):
        return jsonify({"code": 403, "msg": "无权操作", "data": None}), 403

    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "msg": "请求数据不能为空", "data": None}), 400

    message_ids = data.get('message_ids', [])
    elder_id = data.get('elder_id')

    conn = get_db_connection()

    try:
        if message_ids:
            if isinstance(message_ids, list) and len(message_ids) > 0:
                placeholders = ','.join(['?' for _ in message_ids])
                if user_role == 'family':
                    conn.execute(
                        f'UPDATE family_messages SET is_read = 1 WHERE id IN ({placeholders}) AND receiver_id = ? AND sender_type = ?',
                        message_ids + [user_id, 'caregiver']
                    )
                else:
                    conn.execute(
                        f'UPDATE family_messages SET is_read = 1 WHERE id IN ({placeholders}) AND receiver_id = ? AND sender_type = ?',
                        message_ids + [user_id, 'family']
                    )
                conn.commit()
        elif elder_id:
            if user_role == 'family':
                if not check_family_binding(conn, user_id, elder_id):
                    conn.close()
                    return jsonify({"code": 403, "msg": "您没有权限操作该老人的留言", "data": None}), 403
                conn.execute(
                    'UPDATE family_messages SET is_read = 1 WHERE elder_id = ? AND receiver_id = ? AND is_read = 0',
                    (elder_id, user_id)
                )
            else:
                if not check_caregiver_assignment(conn, user_id, elder_id):
                    conn.close()
                    return jsonify({"code": 403, "msg": "您没有权限操作该老人的留言", "data": None}), 403
                conn.execute(
                    'UPDATE family_messages SET is_read = 1 WHERE elder_id = ? AND receiver_id = ? AND is_read = 0',
                    (elder_id, user_id)
                )
            conn.commit()
        else:
            conn.close()
            return jsonify({"code": 400, "msg": "请提供message_ids或elder_id", "data": None}), 400

        conn.close()
        return jsonify({"code": 200, "msg": "标记已读成功", "data": None})

    except Exception as e:
        conn.close()
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}", "data": None}), 500


@family_messages_bp.route('/festival-templates', methods=['GET'])
@login_required
def get_festival_templates():
    user_id = session.get('user_id')
    user_role = session.get('role')

    if user_role not in ('family', 'caregiver'):
        return jsonify({"code": 403, "msg": "无权访问", "data": None}), 403

    conn = get_db_connection()

    try:
        templates = conn.execute(
            'SELECT * FROM festival_templates WHERE is_active = 1 ORDER BY id'
        ).fetchall()

        conn.close()

        return jsonify({
            "code": 200,
            "msg": "获取成功",
            "data": [dict(t) for t in templates]
        })

    except Exception as e:
        conn.close()
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}", "data": None}), 500


@family_messages_bp.route('/unread-count', methods=['GET'])
@login_required
def get_unread_count():
    user_id = session.get('user_id')
    user_role = session.get('role')

    if user_role not in ('family', 'caregiver'):
        return jsonify({"code": 403, "msg": "无权访问", "data": None}), 403

    conn = get_db_connection()

    try:
        if user_role == 'family':
            count = conn.execute('''
                SELECT COUNT(*) as count FROM family_messages
                WHERE receiver_id = ? AND receiver_type = 'family' AND is_read = 0
                AND elder_id IN (SELECT elder_id FROM family_elder_bindings WHERE family_user_id = ?)
            ''', (user_id, user_id)).fetchone()
        else:
            count = conn.execute('''
                SELECT COUNT(*) as count FROM family_messages
                WHERE receiver_id = ? AND receiver_type = 'caregiver' AND is_read = 0
                AND elder_id IN (SELECT elder_id FROM caregiver_elder_assignments WHERE caregiver_id = ?)
            ''', (user_id, user_id)).fetchone()

        conn.close()

        return jsonify({
            "code": 200,
            "msg": "获取成功",
            "data": {"count": count['count'] or 0}
        })

    except Exception as e:
        conn.close()
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}", "data": None}), 500


@family_messages_bp.route('/elders-with-unread', methods=['GET'])
@login_required
def get_elders_with_unread():
    user_id = session.get('user_id')
    user_role = session.get('role')

    if user_role not in ('family', 'caregiver'):
        return jsonify({"code": 403, "msg": "无权访问", "data": None}), 403

    conn = get_db_connection()

    try:
        if user_role == 'family':
            elders = conn.execute('''
                SELECT e.id, e.name, e.gender, e.age, e.room_number, e.bed_number
                FROM elders e
                JOIN family_elder_bindings feb ON e.id = feb.elder_id
                WHERE feb.family_user_id = ? AND e.status = 'active'
                ORDER BY e.id
            ''', (user_id,)).fetchall()
        else:
            elders = conn.execute('''
                SELECT e.id, e.name, e.gender, e.age, e.room_number, e.bed_number
                FROM elders e
                JOIN caregiver_elder_assignments cea ON e.id = cea.elder_id
                WHERE cea.caregiver_id = ? AND e.status = 'active'
                ORDER BY e.room_number
            ''', (user_id,)).fetchall()

        result = []
        for elder in elders:
            elder_dict = dict(elder)

            unread = conn.execute('''
                SELECT COUNT(*) as count FROM family_messages
                WHERE elder_id = ? AND receiver_id = ? AND is_read = 0
            ''', (elder_dict['id'], user_id)).fetchone()
            elder_dict['unread_count'] = unread['count'] or 0

            last_msg = conn.execute('''
                SELECT fm.content, fm.created_at, fm.sender_type, fm.message_type,
                       su.name as sender_name
                FROM family_messages fm
                JOIN users su ON fm.sender_id = su.id
                WHERE fm.elder_id = ?
                ORDER BY fm.created_at DESC
                LIMIT 1
            ''', (elder_dict['id'],)).fetchone()

            if last_msg:
                elder_dict['last_message'] = last_msg['content']
                elder_dict['last_message_time'] = last_msg['created_at']
                elder_dict['last_message_sender_type'] = last_msg['sender_type']
                elder_dict['last_message_sender_name'] = last_msg['sender_name']
                elder_dict['last_message_type'] = last_msg['message_type']
            else:
                elder_dict['last_message'] = None
                elder_dict['last_message_time'] = None
                elder_dict['last_message_sender_type'] = None
                elder_dict['last_message_sender_name'] = None
                elder_dict['last_message_type'] = None

            if user_role == 'family':
                caregivers = conn.execute('''
                    SELECT u.id, u.name FROM users u
                    JOIN caregiver_elder_assignments cea ON u.id = cea.caregiver_id
                    WHERE cea.elder_id = ? AND u.status = 'enabled'
                ''', (elder_dict['id'],)).fetchall()
                elder_dict['caregivers'] = [dict(cg) for cg in caregivers]
            else:
                family_members = conn.execute('''
                    SELECT u.id, u.name FROM users u
                    JOIN family_elder_bindings feb ON u.id = feb.family_user_id
                    WHERE feb.elder_id = ?
                ''', (elder_dict['id'],)).fetchall()
                elder_dict['family_members'] = [dict(fm) for fm in family_members]

            result.append(elder_dict)

        conn.close()

        return jsonify({
            "code": 200,
            "msg": "获取成功",
            "data": result
        })

    except Exception as e:
        conn.close()
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}", "data": None}), 500


@family_messages_bp.route('/admin/list', methods=['GET'])
@admin_required
def admin_get_messages():
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    elder_id = request.args.get('elder_id', type=int)
    sender_type = request.args.get('sender_type', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()

    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    conn = get_db_connection()

    try:
        conditions = []
        params = []

        if elder_id:
            conditions.append("fm.elder_id = ?")
            params.append(elder_id)
        if sender_type:
            conditions.append("fm.sender_type = ?")
            params.append(sender_type)
        if start_date:
            conditions.append("fm.created_at >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("fm.created_at <= ?")
            params.append(end_date + ' 23:59:59')

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        total_count = conn.execute(
            f"SELECT COUNT(*) FROM family_messages fm WHERE {where_clause}", params
        ).fetchone()[0]

        offset = (page - 1) * page_size
        messages = conn.execute(
            f'''
            SELECT fm.*, e.name as elder_name, e.room_number,
                   su.name as sender_name, ru.name as receiver_name
            FROM family_messages fm
            JOIN elders e ON fm.elder_id = e.id
            JOIN users su ON fm.sender_id = su.id
            JOIN users ru ON fm.receiver_id = ru.id
            WHERE {where_clause}
            ORDER BY fm.created_at DESC
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

    except Exception as e:
        conn.close()
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}", "data": None}), 500


@family_messages_bp.route('/admin/stats', methods=['GET'])
@admin_required
def admin_get_stats():
    conn = get_db_connection()

    try:
        total = conn.execute('SELECT COUNT(*) as count FROM family_messages').fetchone()['count']
        family_count = conn.execute("SELECT COUNT(*) as count FROM family_messages WHERE sender_type = 'family'").fetchone()['count']
        caregiver_count = conn.execute("SELECT COUNT(*) as count FROM family_messages WHERE sender_type = 'caregiver'").fetchone()['count']
        unread = conn.execute('SELECT COUNT(*) as count FROM family_messages WHERE is_read = 0').fetchone()['count']
        voice_count = conn.execute("SELECT COUNT(*) as count FROM family_messages WHERE message_type = 'voice'").fetchone()['count']

        conn.close()

        return jsonify({
            "code": 200,
            "msg": "获取成功",
            "data": {
                "total": total,
                "family_count": family_count,
                "caregiver_count": caregiver_count,
                "unread_count": unread,
                "voice_count": voice_count
            }
        })

    except Exception as e:
        conn.close()
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}", "data": None}), 500
