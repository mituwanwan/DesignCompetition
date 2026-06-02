"""
异常上报接口模块
提供异常情况的提交和查询功能，提交后自动触发报警
"""

import json
import os
import uuid
from flask import Blueprint, request, jsonify, session
from .decorators import login_required, caregiver_required
from .database import get_db, format_db_error, db_operation

incident_reports_bp = Blueprint('incident_reports', __name__, url_prefix='/api/v1/incident-reports')

VALID_TYPES = ['fall', 'discomfort', 'agitation', 'other']
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}
MAX_FILE_SIZE = 2 * 1024 * 1024
MAX_IMAGES = 3


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_upload_dir():
    current_dir = os.path.dirname(__file__)
    upload_dir = os.path.join(current_dir, '..', 'uploads', 'incidents')
    upload_dir = os.path.abspath(upload_dir)
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def save_uploaded_file(file):
    if not file:
        return None

    if not allowed_file(file.filename):
        return None

    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)

    if file_size > MAX_FILE_SIZE:
        return None

    ext = file.filename.rsplit('.', 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"

    upload_dir = get_upload_dir()
    file_path = os.path.join(upload_dir, unique_name)
    file.save(file_path)

    relative_path = os.path.join('uploads', 'incidents', unique_name).replace('\\', '/')
    return relative_path


# ========== 1. 提交异常上报 ==========
@incident_reports_bp.route('', methods=['POST'])
@caregiver_required
@db_operation
def create_incident_report():
    if request.content_type and 'multipart/form-data' in request.content_type:
        elder_id = request.form.get('elder_id', type=int)
        incident_type = request.form.get('type')
        note = request.form.get('note', '').strip()
        files = request.files.getlist('images')
    elif request.is_json:
        data = request.get_json()
        elder_id = data.get('elder_id')
        incident_type = data.get('type')
        note = data.get('note', '').strip() if data.get('note') else ''
        files = []
    else:
        elder_id = request.form.get('elder_id', type=int)
        incident_type = request.form.get('type')
        note = request.form.get('note', '').strip()
        files = []

    if not elder_id:
        return jsonify({"code": 400, "msg": "老人ID不能为空", "data": None}), 400
    if not incident_type:
        return jsonify({"code": 400, "msg": "异常类型不能为空", "data": None}), 400
    if incident_type not in VALID_TYPES:
        return jsonify({"code": 400, "msg": f"异常类型必须是 {', '.join(VALID_TYPES)} 之一", "data": None}), 400
    if incident_type == 'other' and not note:
        return jsonify({"code": 400, "msg": "其他类型异常时备注为必填", "data": None}), 400

    images = []
    if files and len(files) > 0:
        actual_files = [f for f in files if f and f.filename]
        if len(actual_files) > MAX_IMAGES:
            return jsonify({"code": 400, "msg": "图片最多上传3张", "data": None}), 400

        for file in actual_files:
            saved_path = save_uploaded_file(file)
            if saved_path:
                images.append(saved_path)
            else:
                return jsonify({"code": 400, "msg": "仅支持 jpg/png 格式，单张图片不超过 2MB", "data": None}), 400

    caregiver_id = session['user_id']

    try:
        with get_db() as conn:
            elder = conn.execute('SELECT * FROM elders WHERE id = ?', (elder_id,)).fetchone()
            if not elder:
                return jsonify({"code": 404, "msg": "老人信息不存在", "data": None}), 404

            assignment = conn.execute(
                'SELECT 1 FROM caregiver_elder_assignments WHERE caregiver_id = ? AND elder_id = ?',
                (caregiver_id, elder_id)
            ).fetchone()
            if not assignment:
                return jsonify({"code": 403, "msg": "您无权为该老人提交异常上报", "data": None}), 403

            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO incident_reports (elder_id, caregiver_id, type, note, images, status)
                VALUES (?, ?, ?, ?, ?, 'unhandled')
            ''', (
                elder_id,
                caregiver_id,
                incident_type,
                note,
                json.dumps(images, ensure_ascii=False) if images else None
            ))
            report_id = cursor.lastrowid

            type_name_map = {'fall': '跌倒', 'discomfort': '身体不适', 'agitation': '情绪烦躁', 'other': '其他'}
            alarm_note = f"护工上报异常：老人 {elder['name']} 发生{type_name_map.get(incident_type, incident_type)}"
            if note:
                alarm_note += f" - {note[:100]}"

            cursor.execute('''
                INSERT INTO alarms (elder_id, type, trigger_source, trigger_note, status)
                VALUES (?, ?, ?, ?, 'unhandled')
            ''', (elder_id, 'manual_incident', str(report_id), alarm_note))
            alarm_id = cursor.lastrowid

            cursor.execute('''
                UPDATE incident_reports SET alarm_id = ? WHERE id = ?
            ''', (alarm_id, report_id))

            try:
                from .notifications import create_notification
                admins = conn.execute(
                    "SELECT id FROM users WHERE role = 'admin' AND status = 'enabled'"
                ).fetchall()
                for admin in admins:
                    create_notification(
                        admin['id'], 'alarm',
                        '新的异常报警',
                        f'老人 {elder["name"]} 发生{type_name_map.get(incident_type, "异常")}，请及时处理',
                        alarm_id
                    )

                family_members = conn.execute('''
                    SELECT family_user_id FROM family_elder_bindings WHERE elder_id = ?
                ''', (elder_id,)).fetchall()
                for fm in family_members:
                    create_notification(
                        fm['family_user_id'], 'alarm',
                        '老人异常通知',
                        f'您的家人 {elder["name"]} 发生异常，请关注',
                        alarm_id
                    )
            except Exception:
                pass

        return jsonify({
            "code": 200,
            "msg": "异常上报成功，已触发报警",
            "data": {
                "incident_report_id": report_id,
                "alarm_id": alarm_id
            }
        })

    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# ========== 2. 获取异常上报列表 ==========
@incident_reports_bp.route('', methods=['GET'])
@login_required
@db_operation
def get_incident_reports():
    elder_id = request.args.get('elder_id', type=int)
    incident_type = request.args.get('type', '').strip()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    user_role = session.get('role')
    user_id = session.get('user_id')

    try:
        with get_db() as conn:
            conditions = []
            params = []

            if user_role == 'caregiver':
                conditions.append("ir.caregiver_id = ?")
                params.append(user_id)
            elif user_role == 'family':
                conditions.append('''
                    ir.elder_id IN (SELECT elder_id FROM family_elder_bindings WHERE family_user_id = ?)
                ''')
                params.append(user_id)

            if elder_id:
                conditions.append("ir.elder_id = ?")
                params.append(elder_id)

            if incident_type:
                conditions.append("ir.type = ?")
                params.append(incident_type)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            total_count = conn.execute(
                f"SELECT COUNT(*) FROM incident_reports ir WHERE {where_clause}", params
            ).fetchone()[0]

            offset = (page - 1) * page_size
            reports = conn.execute(
                f'''
                SELECT ir.id, ir.elder_id, ir.caregiver_id, ir.type, ir.note, ir.images,
                    ir.alarm_id, ir.status, ir.created_at,
                    e.name as elder_name, e.room_number, u.name as caregiver_name,
                    a.status as alarm_status
                FROM incident_reports ir
                JOIN elders e ON ir.elder_id = e.id
                JOIN users u ON ir.caregiver_id = u.id
                LEFT JOIN alarms a ON ir.alarm_id = a.id
                WHERE {where_clause}
                ORDER BY ir.created_at DESC
                LIMIT ? OFFSET ?
                ''',
                params + [page_size, offset]
            ).fetchall()

        result_list = []
        for row in reports:
            r = dict(row)
            if r.get('images'):
                try:
                    r['images'] = json.loads(r['images'])
                except json.JSONDecodeError:
                    r['images'] = []
            else:
                r['images'] = []
            result_list.append(r)

        return jsonify({
            "code": 200,
            "msg": "获取成功",
            "data": {
                "list": result_list,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total_count,
                    "total_pages": (total_count + page_size - 1) // page_size
                }
            }
        })

    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# ========== 3. 获取单条异常上报详情 ==========
@incident_reports_bp.route('/<int:report_id>', methods=['GET'])
@login_required
@db_operation
def get_incident_report_detail(report_id):
    user_role = session.get('role')
    user_id = session.get('user_id')

    try:
        with get_db() as conn:
            report = conn.execute('''
                SELECT ir.*, e.name as elder_name, e.room_number, e.bed_number, e.gender, e.age,
                       u.name as caregiver_name, u.phone as caregiver_phone
                FROM incident_reports ir
                JOIN elders e ON ir.elder_id = e.id
                JOIN users u ON ir.caregiver_id = u.id
                WHERE ir.id = ?
            ''', (report_id,)).fetchone()

            if not report:
                return jsonify({"code": 404, "msg": "记录不存在", "data": None}), 404

            if user_role == 'family':
                binding = conn.execute('''
                    SELECT 1 FROM family_elder_bindings
                    WHERE family_user_id = ? AND elder_id = ?
                ''', (user_id, report['elder_id'])).fetchone()
                if not binding:
                    return jsonify({"code": 403, "msg": "无权查看此记录", "data": None}), 403

            if user_role == 'caregiver' and report['caregiver_id'] != user_id:
                return jsonify({"code": 403, "msg": "无权查看此记录", "data": None}), 403

            result = dict(report)
            if result.get('images'):
                try:
                    result['images'] = json.loads(result['images'])
                except json.JSONDecodeError:
                    result['images'] = []
            else:
                result['images'] = []

            alarm = None
            if result.get('alarm_id'):
                alarm = conn.execute('''
                    SELECT a.*, u.name as handler_name
                    FROM alarms a
                    LEFT JOIN users u ON a.handler_id = u.id
                    WHERE a.id = ?
                ''', (result['alarm_id'],)).fetchone()
            if not alarm:
                alarm = conn.execute('''
                    SELECT a.*, u.name as handler_name
                    FROM alarms a
                    LEFT JOIN users u ON a.handler_id = u.id
                    WHERE a.type = 'manual_incident' AND a.trigger_source = ?
                ''', (str(report_id),)).fetchone()
            if alarm:
                result['alarm'] = dict(alarm)
                if not result.get('alarm_id'):
                    conn.execute('UPDATE incident_reports SET alarm_id = ? WHERE id = ?', (alarm['id'], report_id))
            else:
                result['alarm'] = None

        return jsonify({
            "code": 200,
            "msg": "获取成功",
            "data": result
        })

    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500
