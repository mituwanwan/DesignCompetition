"""
探视预约接口模块
提供子女端视频探视和预约探望的CRUD功能，以及管理员审批功能
"""

import sqlite3
import os
import secrets
import hashlib
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session, render_template
from .decorators import family_required, admin_required, login_required
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.visit_config import is_valid_visit_time, check_visit_conflict
from .notifications import create_notification
from utils.logger import log_action

visits_bp = Blueprint('visits', __name__, url_prefix='/api/v1/visits')


def get_db_connection():
    current_dir = os.path.dirname(__file__)
    db_path = os.path.join(current_dir, '..', 'instance', 'nursing_home.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_table():
    conn = get_db_connection()

    try:
        check = conn.execute("SELECT status FROM appointments WHERE 1=0").fetchone()
        conn.execute("INSERT INTO appointments (status) VALUES ('rejected_test')")
        conn.rollback()
    except Exception:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS appointments_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                elder_id INTEGER NOT NULL,
                family_user_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('video', 'in_person')),
                appointment_date TEXT NOT NULL,
                notes TEXT,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'completed', 'cancelled', 'rejected')),
                video_token TEXT,
                reject_reason TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (elder_id) REFERENCES elders(id) ON DELETE CASCADE,
                FOREIGN KEY (family_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        cols = conn.execute("PRAGMA table_info(appointments)").fetchall()
        col_names = [c[1] for c in cols]
        common_cols = [c for c in col_names if c in ('id', 'elder_id', 'family_user_id', 'type', 'appointment_date', 'notes', 'status', 'video_token', 'reject_reason', 'created_at', 'updated_at')]
        conn.execute(f'''
            INSERT INTO appointments_new ({', '.join(common_cols)})
            SELECT {', '.join(common_cols)} FROM appointments
        ''')
        conn.execute("DROP TABLE appointments")
        conn.execute("ALTER TABLE appointments_new RENAME TO appointments")
        conn.commit()

    try:
        conn.execute("SELECT video_token FROM appointments LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE appointments ADD COLUMN video_token TEXT")

    try:
        conn.execute("SELECT reject_reason FROM appointments LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE appointments ADD COLUMN reject_reason TEXT")

    conn.commit()
    conn.close()


init_table()


def generate_video_token():
    token = secrets.token_urlsafe(32)
    return hashlib.sha256((token + str(datetime.now().timestamp())).encode()).hexdigest()[:48]


@visits_bp.route('', methods=['GET'])
@login_required
def get_visits():
    user_role = session.get('role')
    user_id = session.get('user_id')
    type_filter = request.args.get('type', '').strip()
    status = request.args.get('status', '').strip()
    elder_id = request.args.get('elder_id', type=int)
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    conn = get_db_connection()

    conditions = []
    params = []

    if user_role == 'family':
        conditions.append("a.family_user_id = ?")
        params.append(user_id)

    if type_filter in ('video', 'in_person'):
        conditions.append("a.type = ?")
        params.append(type_filter)

    if status:
        conditions.append("a.status = ?")
        params.append(status)

    if elder_id:
        conditions.append("a.elder_id = ?")
        params.append(elder_id)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    total_count = conn.execute(
        f"SELECT COUNT(*) FROM appointments a WHERE {where_clause}", params
    ).fetchone()[0]

    offset = (page - 1) * page_size
    visits = conn.execute(
        f'''
        SELECT a.*, e.name as elder_name, e.room_number, u.name as family_user_name
        FROM appointments a
        JOIN elders e ON a.elder_id = e.id
        JOIN users u ON a.family_user_id = u.id
        WHERE {where_clause}
        ORDER BY a.appointment_date DESC, a.created_at DESC
        LIMIT ? OFFSET ?
        ''',
        params + [page_size, offset]
    ).fetchall()
    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "list": [dict(v) for v in visits],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_count,
                "total_pages": (total_count + page_size - 1) // page_size
            }
        }
    })


@visits_bp.route('', methods=['POST'])
@family_required
def create_visit():
    family_id = session['user_id']
    data = request.get_json()

    elder_id = data.get('elder_id')
    visit_type = data.get('type')
    appointment_date = data.get('appointment_date')
    notes = data.get('notes', '').strip()

    if not elder_id:
        return jsonify({"code": 400, "msg": "请选择老人", "data": None}), 400
    if visit_type not in ('video', 'in_person'):
        return jsonify({"code": 400, "msg": "预约类型必须是 video 或 in_person", "data": None}), 400
    if not appointment_date:
        return jsonify({"code": 400, "msg": "请选择预约日期", "data": None}), 400
    if notes and len(notes) > 500:
        return jsonify({"code": 400, "msg": "备注不能超过500字", "data": None}), 400

    try:
        appt_dt = datetime.fromisoformat(appointment_date)
        if appt_dt < datetime.now():
            return jsonify({"code": 400, "msg": "预约时间不能早于当前时间", "data": None}), 400
    except ValueError:
        return jsonify({"code": 400, "msg": "日期格式不正确", "data": None}), 400

    conn = get_db_connection()

    binding = conn.execute(
        'SELECT 1 FROM family_elder_bindings WHERE family_user_id = ? AND elder_id = ?',
        (family_id, elder_id)
    ).fetchone()
    if not binding:
        conn.close()
        return jsonify({"code": 403, "msg": "您没有权限为该老人预约探视", "data": None}), 403

    is_valid, error_msg = is_valid_visit_time(visit_type, appointment_date)
    if not is_valid:
        conn.close()
        return jsonify({"code": 400, "msg": error_msg, "data": None}), 400

    no_conflict, conflict_msg = check_visit_conflict(elder_id, appointment_date)
    if not no_conflict:
        conn.close()
        return jsonify({"code": 400, "msg": conflict_msg, "data": None}), 400

    elder = conn.execute('SELECT * FROM elders WHERE id = ?', (elder_id,)).fetchone()
    if not elder:
        conn.close()
        return jsonify({"code": 404, "msg": "老人信息不存在", "data": None}), 404

    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO appointments (elder_id, family_user_id, type, appointment_date, notes)
            VALUES (?, ?, ?, ?, ?)
        ''', (elder_id, family_id, visit_type, appointment_date, notes))
        conn.commit()
        new_id = cursor.lastrowid

        visit_type_text = '现场探望' if visit_type == 'in_person' else '视频探视'
        admins = conn.execute("SELECT id FROM users WHERE role = 'admin' AND status = 'enabled'").fetchall()
        for admin in admins:
            create_notification(
                admin['id'], 'message', '新预约申请',
                f"{session.get('name')} 提交了 {elder['name']} 的{visit_type_text}预约申请，请及时审批",
                new_id
            )
    except Exception as e:
        conn.close()
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}", "data": None}), 500

    conn.close()
    return jsonify({"code": 200, "msg": "预约创建成功，请等待管理员审批", "data": {"id": new_id}})


@visits_bp.route('/<int:id>/cancel', methods=['PUT'])
@family_required
def cancel_visit(id):
    family_id = session['user_id']

    conn = get_db_connection()
    visit = conn.execute(
        'SELECT a.*, e.name as elder_name FROM appointments a JOIN elders e ON a.elder_id = e.id WHERE a.id = ? AND a.family_user_id = ?',
        (id, family_id)
    ).fetchone()

    if not visit:
        conn.close()
        return jsonify({"code": 404, "msg": "预约不存在或无权操作", "data": None}), 404

    if visit['status'] not in ('pending', 'approved'):
        conn.close()
        return jsonify({"code": 400, "msg": "只能取消待确认或已批准状态的预约", "data": None}), 400

    try:
        conn.execute(
            "UPDATE appointments SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (id,)
        )
        conn.commit()

        visit_type_text = '现场探望' if visit['type'] == 'in_person' else '视频探视'
        admins = conn.execute("SELECT id FROM users WHERE role = 'admin' AND status = 'enabled'").fetchall()
        for admin in admins:
            create_notification(
                admin['id'], 'message', '预约已取消',
                f"{session.get('name')} 取消了 {visit['elder_name']} 的{visit_type_text}预约",
                id
            )
    except Exception as e:
        conn.close()
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}", "data": None}), 500

    conn.close()
    return jsonify({"code": 200, "msg": "预约已取消", "data": None})


@visits_bp.route('/<int:id>/approve', methods=['PUT'])
@admin_required
def approve_visit(id):
    conn = get_db_connection()
    visit = conn.execute(
        'SELECT a.*, e.name as elder_name FROM appointments a JOIN elders e ON a.elder_id = e.id WHERE a.id = ?',
        (id,)
    ).fetchone()

    if not visit:
        conn.close()
        return jsonify({"code": 404, "msg": "预约不存在", "data": None}), 404

    if visit['status'] != 'pending':
        conn.close()
        return jsonify({"code": 400, "msg": "只能审批待确认状态的预约", "data": None}), 400

    video_token = None
    if visit['type'] == 'video':
        video_token = generate_video_token()

    try:
        if video_token:
            conn.execute(
                "UPDATE appointments SET status = 'approved', video_token = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (video_token, id)
            )
        else:
            conn.execute(
                "UPDATE appointments SET status = 'approved', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (id,)
            )
        conn.commit()

        visit_type_text = '现场探望' if visit['type'] == 'in_person' else '视频探视'
        create_notification(
            visit['family_user_id'], 'message', '预约已批准',
            f"您预约的{visit['elder_name']}的{visit_type_text}已获得批准" +
            ("，请在预约时间内点击进入视频通话" if visit['type'] == 'video' else "，请按时到院探视"),
            id
        )

        log_action(
            user_id=session.get('user_id'),
            user_name=session.get('name'),
            action='update',
            module='visits',
            description=f'批准预约: ID={id}, 老人={visit["elder_name"]}',
            ip_address=request.remote_addr
        )
    except Exception as e:
        conn.close()
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}", "data": None}), 500

    conn.close()
    return jsonify({"code": 200, "msg": "预约已批准", "data": {"video_token": video_token}})


@visits_bp.route('/<int:id>/reject', methods=['PUT'])
@admin_required
def reject_visit(id):
    data = request.get_json() or {}
    reject_reason = data.get('reason', '').strip()

    conn = get_db_connection()
    visit = conn.execute(
        'SELECT a.*, e.name as elder_name FROM appointments a JOIN elders e ON a.elder_id = e.id WHERE a.id = ?',
        (id,)
    ).fetchone()

    if not visit:
        conn.close()
        return jsonify({"code": 404, "msg": "预约不存在", "data": None}), 404

    if visit['status'] != 'pending':
        conn.close()
        return jsonify({"code": 400, "msg": "只能拒绝待确认状态的预约", "data": None}), 400

    try:
        conn.execute(
            "UPDATE appointments SET status = 'rejected', reject_reason = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (reject_reason, id)
        )
        conn.commit()

        visit_type_text = '现场探望' if visit['type'] == 'in_person' else '视频探视'
        reason_text = f"，原因：{reject_reason}" if reject_reason else ""
        create_notification(
            visit['family_user_id'], 'message', '预约已拒绝',
            f"您预约的{visit['elder_name']}的{visit_type_text}未被批准{reason_text}，可重新选择时间预约",
            id
        )

        log_action(
            user_id=session.get('user_id'),
            user_name=session.get('name'),
            action='update',
            module='visits',
            description=f'拒绝预约: ID={id}, 老人={visit["elder_name"]}',
            ip_address=request.remote_addr
        )
    except Exception as e:
        conn.close()
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}", "data": None}), 500

    conn.close()
    return jsonify({"code": 200, "msg": "预约已拒绝", "data": None})


@visits_bp.route('/<int:id>/complete', methods=['PUT'])
@admin_required
def complete_visit(id):
    conn = get_db_connection()
    visit = conn.execute(
        'SELECT a.*, e.name as elder_name FROM appointments a JOIN elders e ON a.elder_id = e.id WHERE a.id = ?',
        (id,)
    ).fetchone()

    if not visit:
        conn.close()
        return jsonify({"code": 404, "msg": "预约不存在", "data": None}), 404

    if visit['status'] != 'approved':
        conn.close()
        return jsonify({"code": 400, "msg": "只能完成已批准状态的预约", "data": None}), 400

    try:
        conn.execute(
            "UPDATE appointments SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (id,)
        )
        conn.commit()

        visit_type_text = '现场探望' if visit['type'] == 'in_person' else '视频探视'
        create_notification(
            visit['family_user_id'], 'message', '探视已完成',
            f"您预约的{visit['elder_name']}的{visit_type_text}已标记为完成",
            id
        )

        log_action(
            user_id=session.get('user_id'),
            user_name=session.get('name'),
            action='update',
            module='visits',
            description=f'完成预约: ID={id}, 老人={visit["elder_name"]}',
            ip_address=request.remote_addr
        )
    except Exception as e:
        conn.close()
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}", "data": None}), 500

    conn.close()
    return jsonify({"code": 200, "msg": "预约已标记为完成", "data": None})


@visits_bp.route('/video-token/<token>', methods=['GET'])
def validate_video_token(token):
    conn = get_db_connection()
    visit = conn.execute('''
        SELECT a.*, e.name as elder_name, u.name as family_user_name
        FROM appointments a
        JOIN elders e ON a.elder_id = e.id
        JOIN users u ON a.family_user_id = u.id
        WHERE a.video_token = ?
    ''', (token,)).fetchone()
    conn.close()

    if not visit:
        return jsonify({"code": 404, "msg": "无效的视频链接", "data": None}), 404

    if visit['status'] != 'approved':
        return jsonify({"code": 400, "msg": "该预约未处于已批准状态", "data": None}), 400

    try:
        appt_dt = datetime.fromisoformat(visit['appointment_date'])
        now = datetime.now()
        time_diff = (appt_dt - now).total_seconds()

        if time_diff > 1800:
            return jsonify({
                "code": 400,
                "msg": f"视频通话尚未开始，预约时间为 {visit['appointment_date']}，请在预约时间前后30分钟内进入",
                "data": {"appointment_date": visit['appointment_date'], "elder_name": visit['elder_name']}
            }), 400

        if time_diff < -3600:
            return jsonify({
                "code": 400,
                "msg": "该预约已过时，视频链接已失效",
                "data": None
            }), 400
    except ValueError:
        return jsonify({"code": 400, "msg": "预约时间格式异常", "data": None}), 400

    return jsonify({
        "code": 200,
        "msg": "链接有效",
        "data": {
            "appointment_id": visit['id'],
            "elder_name": visit['elder_name'],
            "family_user_name": visit['family_user_name'],
            "appointment_date": visit['appointment_date'],
            "type": visit['type']
        }
    })


@visits_bp.route('/export', methods=['GET'])
@admin_required
def export_visits():
    type_filter = request.args.get('type', '').strip()
    status = request.args.get('status', '').strip()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    conn = get_db_connection()

    conditions = []
    params = []

    if type_filter in ('video', 'in_person'):
        conditions.append("a.type = ?")
        params.append(type_filter)

    if status:
        conditions.append("a.status = ?")
        params.append(status)

    if start_date:
        conditions.append("a.appointment_date >= ?")
        params.append(start_date)

    if end_date:
        conditions.append("a.appointment_date <= ?")
        params.append(end_date)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    visits = conn.execute(f'''
        SELECT a.*, e.name as elder_name, e.room_number, u.name as family_user_name
        FROM appointments a
        JOIN elders e ON a.elder_id = e.id
        JOIN users u ON a.family_user_id = u.id
        WHERE {where_clause}
        ORDER BY a.appointment_date DESC
    ''', params).fetchall()
    conn.close()

    try:
        import pandas as pd
        import io

        type_map = {'video': '视频探视', 'in_person': '现场探视'}
        status_map = {'pending': '待审批', 'approved': '已批准', 'completed': '已完成', 'cancelled': '已取消', 'rejected': '已拒绝'}

        data_rows = []
        for visit in visits:
            data_rows.append({
                'ID': visit['id'],
                '老人姓名': visit['elder_name'],
                '房间号': visit['room_number'],
                '预约家属': visit['family_user_name'],
                '类型': type_map.get(visit['type'], visit['type']),
                '预约时间': visit['appointment_date'],
                '状态': status_map.get(visit['status'], visit['status']),
                '备注': visit['notes'] or '',
                '创建时间': visit['created_at']
            })

        df = pd.DataFrame(data_rows)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='探视预约')
            worksheet = writer.sheets['探视预约']
            for idx, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max() if len(df) > 0 else 0, len(col))
                worksheet.column_dimensions[chr(65 + idx) if idx < 26 else chr(64 + idx // 26) + chr(65 + idx % 26)].width = min(max_len + 4, 50)

        output.seek(0)
        filename = f'探视预约_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        from flask import send_file
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except ImportError:
        return jsonify({"code": 500, "msg": "导出功能依赖pandas库，请安装：pip install pandas openpyxl", "data": None}), 500
