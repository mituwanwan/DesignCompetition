"""
报警管理API模块
提供报警查询、处理等功能
"""

from datetime import datetime
from flask import Blueprint, request, jsonify, session
from .decorators import login_required, admin_required
from .database import get_db, format_db_error, db_operation
import sys
import os
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import log_action

alarms_bp = Blueprint('alarms', __name__, url_prefix='/api/v1/alarms')


# ========== 1. 获取报警列表 (分页) ==========
@alarms_bp.route('', methods=['GET'])
@login_required
@db_operation
def get_alarms():
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    status_filter = request.args.get('status', '', type=str)
    elder_id = request.args.get('elder_id', 0, type=int)

    offset = (page - 1) * page_size

    try:
        with get_db() as conn:
            cursor = conn.cursor()

            where_conditions = ["1=1"]
            params = []

            if status_filter:
                where_conditions.append("a.status = ?")
                params.append(status_filter)

            if session.get('role') == 'family':
                where_conditions.append("feb.family_user_id = ?")
                params.append(session.get('user_id'))

            if session.get('role') == 'caregiver':
                where_conditions.append("cea.caregiver_id = ?")
                params.append(session.get('user_id'))

            if elder_id:
                where_conditions.append("a.elder_id = ?")
                params.append(elder_id)

            where_clause = " AND ".join(where_conditions)

            join_clause = ""
            if session.get('role') == 'family':
                join_clause = "JOIN family_elder_bindings feb ON a.elder_id = feb.elder_id"
            if session.get('role') == 'caregiver':
                join_clause = "JOIN caregiver_elder_assignments cea ON a.elder_id = cea.elder_id"

            # 计算总数
            cursor.execute(f"SELECT COUNT(*) FROM alarms a {join_clause} WHERE {where_clause}", params)
            total = cursor.fetchone()[0]

            # 分页查询
            query = f"""
                SELECT a.*, e.name as elder_name, e.room_number
                FROM alarms a
                JOIN elders e ON a.elder_id = e.id
                {join_clause}
                WHERE {where_clause}
                ORDER BY a.triggered_at DESC
                LIMIT ? OFFSET ?
            """
            params.extend([page_size, offset])
            cursor.execute(query, params)
            alarms = cursor.fetchall()

            result_list = []
            for alarm in alarms:
                alarm_dict = dict(alarm)

                # 计算响应时长
                response_duration = None
                if alarm['status'] in ('processing', 'resolved') and alarm['triggered_at'] and alarm['processing_at']:
                    try:
                        triggered = datetime.fromisoformat(alarm['triggered_at'])
                        processing = datetime.fromisoformat(alarm['processing_at'])
                        diff = processing - triggered
                        if diff.total_seconds() > 0:
                            hours = int(diff.total_seconds() // 3600)
                            mins = int((diff.total_seconds() % 3600) // 60)
                            if hours > 0:
                                response_duration = f"{hours}小时{mins}分钟"
                            else:
                                response_duration = f"{mins}分钟"
                    except:
                        pass
                alarm_dict['response_duration'] = response_duration

                result_list.append(alarm_dict)

            total_pages = (total + page_size - 1) // page_size

        return jsonify({
            "code": 200,
            "msg": "获取成功",
            "data": {
                "list": result_list,
                "pagination": {
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages
                }
            }
        })

    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# ========== 2. 查看单条报警详情 ==========
@alarms_bp.route('/<int:id>', methods=['GET'])
@login_required
@db_operation
def get_alarm_detail(id):
    try:
        with get_db() as conn:
            alarm = conn.execute('''
                SELECT a.*, e.name as elder_name, e.room_number,
                    u.name as handler_name
                FROM alarms a
                JOIN elders e ON a.elder_id = e.id
                LEFT JOIN users u ON a.handler_id = u.id
                WHERE a.id = ?
            ''', (id,)).fetchone()

            if not alarm:
                return jsonify({"code": 404, "msg": "报警记录不存在", "data": None}), 404

            alarm_dict = dict(alarm)

            # 获取处理记录
            action_logs = conn.execute('''
                SELECT al.*, u.name as operator_name
                FROM alarm_action_logs al
                JOIN users u ON al.user_id = u.id
                WHERE al.alarm_id = ?
                ORDER BY al.created_at DESC
            ''', (id,)).fetchall()

        return jsonify({
            "code": 200,
            "msg": "获取成功",
            "data": {
                "alarm": alarm_dict,
                "action_logs": [dict(log) for log in action_logs]
            }
        })

    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# ========== 3. 开始处理报警 ==========
@alarms_bp.route('/<int:id>/process', methods=['PUT'])
@login_required
@db_operation
def process_alarm(id):
    user_role = session.get('role')
    user_id = session.get('user_id')

    if user_role not in ('admin', 'caregiver'):
        return jsonify({"code": 403, "msg": "权限不足", "data": None}), 403

    try:
        with get_db() as conn:
            alarm = conn.execute('SELECT * FROM alarms WHERE id = ?', (id,)).fetchone()

            if not alarm:
                return jsonify({"code": 404, "msg": "报警记录不存在", "data": None}), 404

            if alarm['status'] != 'unhandled':
                return jsonify({"code": 400, "msg": "只能处理未处理状态的报警", "data": None}), 400

            if user_role == 'caregiver':
                assignment = conn.execute('''
                    SELECT 1 FROM caregiver_elder_assignments
                    WHERE caregiver_id = ? AND elder_id = ?
                ''', (user_id, alarm['elder_id'])).fetchone()
                if not assignment:
                    return jsonify({"code": 403, "msg": "您没有权限处理该报警，仅能处理负责老人的报警", "data": None}), 403

            handler_id = user_id

            conn.execute('''
                UPDATE alarms
                SET status = 'processing', handler_id = ?, processing_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (handler_id, id))

            conn.execute('''
                UPDATE incident_reports SET status = 'processing' WHERE alarm_id = ?
            ''', (id,))

            data = request.get_json() or {}
            note = data.get('note', '')
            conn.execute('''
                INSERT INTO alarm_action_logs (alarm_id, user_id, action, note)
                VALUES (?, ?, 'process', ?)
            ''', (id, handler_id, note))

        log_action(
            user_id=session.get('user_id'),
            user_name=session.get('name'),
            action='update',
            module='alarms',
            description=f'开始处理报警: ID={id}, 老人={alarm["elder_id"] if "elder_id" in alarm.keys() else "未知"}',
            ip_address=request.remote_addr
        )

        return jsonify({"code": 200, "msg": "已开始处理", "data": None})

    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# ========== 4. 处理完成报警 ==========
@alarms_bp.route('/<int:id>/resolve', methods=['PUT'])
@login_required
@db_operation
def resolve_alarm(id):
    user_role = session.get('role')
    user_id = session.get('user_id')

    if user_role not in ('admin', 'caregiver'):
        return jsonify({"code": 403, "msg": "权限不足", "data": None}), 403

    data = request.get_json() or {}
    result = data.get('result', '')

    if not result:
        return jsonify({"code": 400, "msg": "请填写处理结果", "data": None}), 400

    try:
        with get_db() as conn:
            alarm = conn.execute('SELECT * FROM alarms WHERE id = ?', (id,)).fetchone()

            if not alarm:
                return jsonify({"code": 404, "msg": "报警记录不存在", "data": None}), 404

            if alarm['status'] not in ('unhandled', 'processing'):
                return jsonify({"code": 400, "msg": "只能处理未处理或处理中的报警", "data": None}), 400

            if user_role == 'caregiver':
                assignment = conn.execute('''
                    SELECT 1 FROM caregiver_elder_assignments
                    WHERE caregiver_id = ? AND elder_id = ?
                ''', (user_id, alarm['elder_id'])).fetchone()
                if not assignment:
                    return jsonify({"code": 403, "msg": "您没有权限处理该报警，仅能处理负责老人的报警", "data": None}), 403

            handler_id = user_id

            conn.execute('''
                UPDATE alarms
                SET status = 'resolved', handler_id = ?, result = ?,
                    processing_at = CASE WHEN processing_at IS NULL THEN CURRENT_TIMESTAMP ELSE processing_at END,
                    resolved_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (handler_id, result, id))

            conn.execute('''
                UPDATE incident_reports SET status = 'resolved' WHERE alarm_id = ?
            ''', (id,))

            conn.execute('''
                INSERT INTO alarm_action_logs (alarm_id, user_id, action, note)
                VALUES (?, ?, 'resolve', ?)
            ''', (id, handler_id, result))

        log_action(
            user_id=session.get('user_id'),
            user_name=session.get('name'),
            action='update',
            module='alarms',
            description=f'完成处理报警: ID={id}, 结果={result}',
            ip_address=request.remote_addr
        )

        return jsonify({"code": 200, "msg": "处理完成", "data": None})

    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500
