"""
护理任务接口模块
提供护理任务的创建、查询、完成等功能
"""

import sqlite3
import os
from flask import Blueprint, request, jsonify, session
from .decorators import login_required, admin_required, caregiver_required
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import log_action

care_tasks_bp = Blueprint('care_tasks', __name__, url_prefix='/api/v1/care-tasks')


def get_db_connection():
    current_dir = os.path.dirname(__file__)
    db_path = os.path.join(current_dir, '..', 'instance', 'nursing_home.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


CARE_LEVEL_MAP = {
    'special': '特级护理',
    'enhanced': '加强护理',
    'standard': '标准护理'
}


# ========== 1. 创建护理任务 ==========
@care_tasks_bp.route('', methods=['POST'])
@admin_required
def create_care_task():
    data = request.get_json()

    required_fields = ['caregiver_id', 'elder_id', 'content', 'due_time']
    for field in required_fields:
        if not data.get(field):
            return jsonify({"code": 400, "msg": f"{field}字段不能为空", "data": None}), 400

    caregiver_id = data.get('caregiver_id')
    elder_id = data.get('elder_id')
    content = data.get('content').strip()
    due_time = data.get('due_time')
    admin_id = session['user_id']

    conn = get_db_connection()

    caregiver = conn.execute(
        'SELECT * FROM users WHERE id = ? AND role = ?',
        (caregiver_id, 'caregiver')
    ).fetchone()
    if not caregiver:
        conn.close()
        return jsonify({"code": 404, "msg": "护工用户不存在", "data": None}), 404

    elder = conn.execute('SELECT * FROM elders WHERE id = ?', (elder_id,)).fetchone()
    if not elder:
        conn.close()
        return jsonify({"code": 404, "msg": "老人信息不存在", "data": None}), 404

    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO care_tasks (admin_id, caregiver_id, elder_id, content, due_time)
            VALUES (?, ?, ?, ?, ?)
        ''', (admin_id, caregiver_id, elder_id, content, due_time))
        conn.commit()
        new_id = cursor.lastrowid

        try:
            from .notifications import create_notification
            caregiver_name = caregiver['name']
            elder_name = elder['name']
            create_notification(
                caregiver_id, 'task',
                '新护理任务',
                f'您有一个关于老人 {elder_name} 的新任务: {content}',
                new_id
            )
        except Exception:
            pass

        log_action(
            user_id=session.get('user_id'),
            user_name=session.get('name'),
            action='create',
            module='care_tasks',
            description=f'分配任务: 护工={caregiver["name"]}, 老人={elder["name"]}, 内容={content}',
            ip_address=request.remote_addr
        )

    except Exception as e:
        conn.close()
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}", "data": None}), 500

    conn.close()
    return jsonify({"code": 200, "msg": "任务创建成功", "data": {"id": new_id}})


# ========== 2. 获取任务列表 ==========
@care_tasks_bp.route('', methods=['GET'])
@login_required
def get_care_tasks():
    user_role = session.get('role')
    user_id = session.get('user_id')

    status = request.args.get('status', '').strip()
    elder_keyword = request.args.get('elder_keyword', '').strip()
    caregiver_id = request.args.get('caregiver_id', type=int)
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    conn = get_db_connection()

    conditions = []
    params = []

    if user_role == 'caregiver':
        conditions.append("ct.caregiver_id = ?")
        params.append(user_id)
    elif user_role == 'family':
        conn.close()
        return jsonify({"code": 403, "msg": "权限不足", "data": None}), 403
    elif user_role == 'admin' and caregiver_id:
        conditions.append("ct.caregiver_id = ?")
        params.append(caregiver_id)

    if status:
        conditions.append("ct.status = ?")
        params.append(status)

    if elder_keyword:
        conditions.append("(e.name LIKE ? OR CAST(e.id AS TEXT) LIKE ?)")
        kw = f'%{elder_keyword}%'
        params.append(kw)
        params.append(kw)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    total_count = conn.execute(
        f"SELECT COUNT(*) FROM care_tasks ct JOIN elders e ON ct.elder_id = e.id WHERE {where_clause}", params
    ).fetchone()[0]

    offset = (page - 1) * page_size
    tasks = conn.execute(
        f'''
        SELECT ct.*, e.name as elder_name, e.room_number, e.age as elder_age,
               e.care_level as elder_care_level, e.gender as elder_gender,
               u.name as caregiver_name
        FROM care_tasks ct
        JOIN elders e ON ct.elder_id = e.id
        JOIN users u ON ct.caregiver_id = u.id
        WHERE {where_clause}
        ORDER BY ct.created_at DESC
        LIMIT ? OFFSET ?
        ''',
        params + [page_size, offset]
    ).fetchall()

    task_list = []
    for t in tasks:
        task_dict = dict(t)
        task_dict['elder_care_level_name'] = CARE_LEVEL_MAP.get(task_dict.get('elder_care_level'), '标准护理')
        task_list.append(task_dict)

    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "list": task_list,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_count,
                "total_pages": (total_count + page_size - 1) // page_size
            }
        }
    })


# ========== 3. 获取任务详情 ==========
@care_tasks_bp.route('/<int:id>', methods=['GET'])
@login_required
def get_care_task_detail(id):
    user_role = session.get('role')
    user_id = session.get('user_id')

    conn = get_db_connection()
    task = conn.execute(
        '''
        SELECT ct.*, e.name as elder_name, e.room_number, e.bed_number,
               e.age as elder_age, e.gender as elder_gender,
               e.care_level as elder_care_level, e.medical_history as elder_medical_history,
               u.name as caregiver_name
        FROM care_tasks ct
        JOIN elders e ON ct.elder_id = e.id
        JOIN users u ON ct.caregiver_id = u.id
        WHERE ct.id = ?
        ''',
        (id,)
    ).fetchone()

    if not task:
        conn.close()
        return jsonify({"code": 404, "msg": "任务不存在", "data": None}), 404

    if user_role == 'caregiver' and task['caregiver_id'] != user_id:
        conn.close()
        return jsonify({"code": 403, "msg": "您没有权限查看该任务", "data": None}), 403

    task_dict = dict(task)
    task_dict['elder_care_level_name'] = CARE_LEVEL_MAP.get(task_dict.get('elder_care_level'), '标准护理')

    if task['completed_by']:
        completer = conn.execute('SELECT name FROM users WHERE id = ?', (task['completed_by'],)).fetchone()
        task_dict['completed_by_name'] = completer['name'] if completer else '未知'
    else:
        task_dict['completed_by_name'] = None

    conn.close()
    return jsonify({"code": 200, "msg": "获取成功", "data": task_dict})


# ========== 4. 确认完成任务 ==========
@care_tasks_bp.route('/<int:id>/complete', methods=['PUT'])
@caregiver_required
def complete_care_task(id):
    user_id = session['user_id']
    user_name = session.get('name', '')

    conn = get_db_connection()
    task = conn.execute('SELECT * FROM care_tasks WHERE id = ?', (id,)).fetchone()

    if not task:
        conn.close()
        return jsonify({"code": 404, "msg": "任务不存在", "data": None}), 404

    if task['caregiver_id'] != user_id:
        conn.close()
        return jsonify({"code": 403, "msg": "您没有权限完成此任务", "data": None}), 403

    if task['status'] == 'completed':
        conn.close()
        return jsonify({"code": 400, "msg": "该任务已完成，无法重复操作", "data": None}), 400

    conn.execute(
        '''UPDATE care_tasks
           SET status = 'completed', completed_at = CURRENT_TIMESTAMP, completed_by = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?''',
        (user_id, id)
    )
    conn.commit()

    updated = conn.execute(
        '''SELECT completed_at FROM care_tasks WHERE id = ?''', (id,)
    ).fetchone()
    completed_at = updated['completed_at'] if updated else None

    conn.close()

    log_action(
        user_id=session.get('user_id'),
        user_name=session.get('name'),
        action='update',
        module='care_tasks',
        description=f'完成任务: ID={id}, 完成人={user_name}',
        ip_address=request.remote_addr
    )

    return jsonify({
        "code": 200,
        "msg": "任务已完成",
        "data": {
            "id": id,
            "completed_at": completed_at,
            "completed_by": user_id,
            "completed_by_name": user_name
        }
    })


# ========== 5. 获取任务统计摘要 ==========
@care_tasks_bp.route('/stats-summary', methods=['GET'])
@login_required
def get_task_stats_summary():
    user_role = session.get('role')
    user_id = session.get('user_id')

    conn = get_db_connection()

    conditions = []
    params = []

    if user_role == 'caregiver':
        conditions.append("caregiver_id = ?")
        params.append(user_id)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    stats = conn.execute(
        f'''SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_count,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_count
        FROM care_tasks
        WHERE {where_clause}''',
        params
    ).fetchone()

    total = stats['total'] or 0
    pending = stats['pending_count'] or 0
    completed = stats['completed_count'] or 0
    rate = round(completed / total * 100, 1) if total > 0 else 0

    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "total": total,
            "pending_count": pending,
            "completed_count": completed,
            "completion_rate": rate
        }
    })
