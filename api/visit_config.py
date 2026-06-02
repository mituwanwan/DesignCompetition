"""
预约时间段配置接口模块
提供预约时间段的管理功能
"""

import sqlite3
import os
from flask import Blueprint, request, jsonify
from .decorators import admin_required, login_required

visit_config_bp = Blueprint('visit_config', __name__, url_prefix='/api/v1/visit-config')


def get_db_connection():
    current_dir = os.path.dirname(__file__)
    db_path = os.path.join(current_dir, '..', 'instance', 'nursing_home.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ========== 1. 获取所有时间段配置 ==========
@visit_config_bp.route('', methods=['GET'])
@login_required
def get_configs():
    """获取所有预约时间段配置"""
    visit_type = request.args.get('type')
    conn = get_db_connection()

    query = 'SELECT * FROM visit_config WHERE 1=1'
    params = []

    if visit_type:
        query += ' AND (visit_type = ? OR visit_type = "all")'
        params.append(visit_type)

    query += ' ORDER BY visit_type, day_of_week, start_time'
    configs = conn.execute(query, params).fetchall()
    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": [dict(c) for c in configs]
    })


# ========== 2. 创建/新增时间段配置 ==========
@visit_config_bp.route('', methods=['POST'])
@admin_required
def create_config():
    data = request.get_json()

    required_fields = ['visit_type', 'start_time', 'end_time']
    for field in required_fields:
        if field not in data:
            return jsonify({"code": 400, "msg": f"{field}不能为空", "data": None}), 400

    visit_type = data.get('visit_type')
    if visit_type not in ('video', 'in_person', 'all'):
        return jsonify({"code": 400, "msg": "类型必须是video/in_person/all", "data": None}), 400

    day_of_week = data.get('day_of_week')
    if day_of_week is not None and (day_of_week < 0 or day_of_week > 6):
        return jsonify({"code": 400, "msg": "星期几必须是0-6的数字", "data": None}), 400

    start_time = data.get('start_time')
    end_time = data.get('end_time')
    max_appointments = data.get('max_appointments', 5)

    conn = get_db_connection()

    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO visit_config 
            (visit_type, day_of_week, start_time, end_time, max_appointments, is_enabled)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (visit_type, day_of_week, start_time, end_time, max_appointments))
        conn.commit()
        new_id = cursor.lastrowid
    except Exception as e:
        conn.close()
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}", "data": None}), 500

    conn.close()
    return jsonify({"code": 200, "msg": "创建成功", "data": {"id": new_id}})


# ========== 3. 更新时间段配置 ==========
@visit_config_bp.route('/<int:id>', methods=['PUT'])
@admin_required
def update_config(id):
    data = request.get_json()
    conn = get_db_connection()

    config = conn.execute('SELECT * FROM visit_config WHERE id = ?', (id,)).fetchone()
    if not config:
        conn.close()
        return jsonify({"code": 404, "msg": "配置不存在", "data": None}), 404

    try:
        update_fields = []
        update_values = []

        if 'visit_type' in data:
            update_fields.append('visit_type = ?')
            update_values.append(data['visit_type'])

        if 'day_of_week' in data:
            update_fields.append('day_of_week = ?')
            update_values.append(data['day_of_week'])

        if 'start_time' in data:
            update_fields.append('start_time = ?')
            update_values.append(data['start_time'])

        if 'end_time' in data:
            update_fields.append('end_time = ?')
            update_values.append(data['end_time'])

        if 'max_appointments' in data:
            update_fields.append('max_appointments = ?')
            update_values.append(data['max_appointments'])

        if 'is_enabled' in data:
            update_fields.append('is_enabled = ?')
            update_values.append(data['is_enabled'])

        if not update_fields:
            conn.close()
            return jsonify({"code": 400, "msg": "没有要更新的数据", "data": None}), 400

        update_fields.append('updated_at = CURRENT_TIMESTAMP')
        update_values.append(id)

        conn.execute(f'''
            UPDATE visit_config 
            SET {', '.join(update_fields)} 
            WHERE id = ?
        ''', update_values)
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}", "data": None}), 500

    conn.close()
    return jsonify({"code": 200, "msg": "更新成功", "data": None})


# ========== 4. 删除时间段配置 ==========
@visit_config_bp.route('/<int:id>', methods=['DELETE'])
@admin_required
def delete_config(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM visit_config WHERE id = ?', (id,))
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({"code": 404, "msg": "配置不存在", "data": None}), 404
    conn.commit()
    conn.close()
    return jsonify({"code": 200, "msg": "删除成功", "data": None})


# ========== 5. 检查是否是有效预约时间 ==========
def is_valid_visit_time(visit_type, appointment_date):
    """
    检查是否在可预约时间段内
    返回: (是否有效, 错误信息)
    """
    import datetime
    try:
        # 解析日期时间
        dt = datetime.datetime.fromisoformat(appointment_date)
        day_of_week = dt.weekday() + 1  # 0=周一，转成1-7，数据库是0=周日
        if day_of_week == 7:
            day_of_week = 0  # 周日是0
        hour = dt.hour
        minute = dt.minute
        time_str = f"{hour:02d}:{minute:02d}"

        conn = get_db_connection()
        configs = conn.execute('''
            SELECT * FROM visit_config 
            WHERE (visit_type = ? OR visit_type = "all")
              AND (day_of_week IS NULL OR day_of_week = ?)
              AND is_enabled = 1
        ''', (visit_type, day_of_week)).fetchall()
        conn.close()

        if not configs:
            return False, "当前时段不支持预约"

        for config in configs:
            if config['start_time'] <= time_str < config['end_time']:
                return True, ""

        return False, "请在可预约时段内选择时间"
    except Exception as e:
        return False, f"时间格式错误: {str(e)}"


# ========== 6. 检查预约冲突 ==========
def check_visit_conflict(elder_id, appointment_date):
    """检查同一老人同一时段是否有重复预约"""
    import datetime
    try:
        # 截取到小时
        dt = datetime.datetime.fromisoformat(appointment_date)
        start_hour = dt.hour
        dt_start = dt.replace(minute=0, second=0, microsecond=0)
        dt_end = dt_start.replace(hour=start_hour + 1)

        conn = get_db_connection()
        count = conn.execute('''
            SELECT COUNT(*) FROM appointments 
            WHERE elder_id = ?
              AND appointment_date >= ?
              AND appointment_date < ?
              AND status IN ('pending', 'approved')
        ''', (elder_id, dt_start.isoformat(), dt_end.isoformat())).fetchone()[0]
        conn.close()

        # 检查该时间段最大预约数
        visit_type = None
        max_appointments = 5
        return count < max_appointments, "该时段预约已满，请选择其他时段"
    except Exception as e:
        return False, f"冲突检查错误: {str(e)}"
