"""
护理记录接口模块
提供护理记录的提交、查询等功能
"""

import json
from flask import Blueprint, request, jsonify, session
from .decorators import login_required, caregiver_required, admin_required
from .database import get_db, format_db_error, db_operation

care_records_bp = Blueprint('care_records', __name__, url_prefix='/api/v1')


def check_and_trigger_alarms(conn, elder_id, health_data, record_id):
    """
    检查健康数据并触发自动报警
    从 alarm_rules 表读取启用的规则，按规则配置的阈值判断是否触发报警
    """
    triggered_alarms = []

    rules = conn.execute(
        'SELECT * FROM alarm_rules WHERE is_enabled = 1'
    ).fetchall()
    rules_map = {rule['rule_key']: dict(rule) for rule in rules}

    systolic = health_data.get('systolic_pressure')
    diastolic = health_data.get('diastolic_pressure')
    heart_rate = health_data.get('heart_rate')
    temperature = health_data.get('temperature')
    blood_sugar = health_data.get('blood_sugar')

    rule = rules_map.get('bp_high')
    if rule and systolic and rule['threshold_max'] is not None:
        if systolic > rule['threshold_max']:
            alarm_id = create_alarm(conn, elder_id, 'auto_health',
                f"高血压: 收缩压 {systolic}mmHg > {rule['threshold_max']}mmHg", str(record_id))
            triggered_alarms.append(alarm_id)

    rule = rules_map.get('bp_low')
    if rule and diastolic and rule['threshold_min'] is not None:
        if diastolic < rule['threshold_min']:
            alarm_id = create_alarm(conn, elder_id, 'auto_health',
                f"低血压: 舒张压 {diastolic}mmHg < {rule['threshold_min']}mmHg", str(record_id))
            triggered_alarms.append(alarm_id)

    rule = rules_map.get('hr_high')
    if rule and heart_rate and rule['threshold_max'] is not None:
        if heart_rate > rule['threshold_max']:
            alarm_id = create_alarm(conn, elder_id, 'auto_health',
                f"心动过速: 心率 {heart_rate}bpm > {rule['threshold_max']}bpm", str(record_id))
            triggered_alarms.append(alarm_id)

    rule = rules_map.get('hr_low')
    if rule and heart_rate and rule['threshold_min'] is not None:
        if heart_rate < rule['threshold_min']:
            alarm_id = create_alarm(conn, elder_id, 'auto_health',
                f"心动过缓: 心率 {heart_rate}bpm < {rule['threshold_min']}bpm", str(record_id))
            triggered_alarms.append(alarm_id)

    rule = rules_map.get('temp_high')
    if rule and temperature and rule['threshold_max'] is not None:
        if temperature > rule['threshold_max']:
            alarm_id = create_alarm(conn, elder_id, 'auto_health',
                f"体温过高: 体温 {temperature}℃ > {rule['threshold_max']}℃", str(record_id))
            triggered_alarms.append(alarm_id)

    rule = rules_map.get('temp_low')
    if rule and temperature and rule['threshold_min'] is not None:
        if temperature < rule['threshold_min']:
            alarm_id = create_alarm(conn, elder_id, 'auto_health',
                f"体温过低: 体温 {temperature}℃ < {rule['threshold_min']}℃", str(record_id))
            triggered_alarms.append(alarm_id)

    rule = rules_map.get('bs_high')
    if rule and blood_sugar and rule['threshold_max'] is not None:
        if blood_sugar > rule['threshold_max']:
            alarm_id = create_alarm(conn, elder_id, 'auto_health',
                f"血糖偏高: 血糖 {blood_sugar}mmol/L > {rule['threshold_max']}mmol/L", str(record_id))
            triggered_alarms.append(alarm_id)

    rule = rules_map.get('bs_low')
    if rule and blood_sugar and rule['threshold_min'] is not None:
        if blood_sugar < rule['threshold_min']:
            alarm_id = create_alarm(conn, elder_id, 'auto_health',
                f"血糖偏低: 血糖 {blood_sugar}mmol/L < {rule['threshold_min']}mmol/L", str(record_id))
            triggered_alarms.append(alarm_id)

    rule = rules_map.get('sleep_deficit')
    if rule and health_data.get('sleep') and health_data.get('sleep').get('duration'):
        current_duration = health_data.get('sleep').get('duration')
        threshold = rule['threshold_max']
        if threshold is not None and current_duration and current_duration < threshold:
            recent_records = conn.execute('''
                SELECT sleep FROM care_records
                WHERE elder_id = ? AND record_date >= date('now', '-3 days')
                ORDER BY record_date DESC LIMIT 3
            ''', (elder_id,)).fetchall()

            low_sleep_count = 1
            for record in recent_records:
                sleep_data = None
                if record['sleep']:
                    try:
                        sleep_data = json.loads(record['sleep'])
                    except:
                        pass
                if sleep_data and sleep_data.get('duration') and sleep_data.get('duration') < threshold:
                    low_sleep_count += 1

            if low_sleep_count >= 3:
                alarm_id = create_alarm(conn, elder_id, 'auto_health',
                    f"连续{low_sleep_count}天睡眠不足{threshold}小时", str(record_id))
                triggered_alarms.append(alarm_id)

    return triggered_alarms


def create_alarm(conn, elder_id, alarm_type, trigger_note, trigger_source):
    """创建报警记录并发送通知"""
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO alarms (elder_id, type, trigger_source, trigger_note, status)
        VALUES (?, ?, ?, ?, 'unhandled')
    ''', (elder_id, alarm_type, trigger_source, trigger_note))
    alarm_id = cursor.lastrowid

    elder = conn.execute('SELECT name FROM elders WHERE id = ?', (elder_id,)).fetchone()
    elder_name = elder['name'] if elder else '未知'

    try:
        from .notifications import create_notification

        admins = conn.execute('SELECT id FROM users WHERE role = ?', ('admin',)).fetchall()
        for admin in admins:
            create_notification(
                admin['id'], 'alarm',
                '健康报警提醒',
                f'老人 {elder_name} 触发健康报警: {trigger_note}',
                alarm_id
            )

        family_members = conn.execute('''
            SELECT family_user_id FROM family_elder_bindings WHERE elder_id = ?
        ''', (elder_id,)).fetchall()
        for fm in family_members:
            create_notification(
                fm['family_user_id'], 'alarm',
                '健康报警提醒',
                f'您绑定的老人 {elder_name} 触发健康报警: {trigger_note}',
                alarm_id
            )
    except Exception as e:
        print(f"通知发送失败: {e}")

    return alarm_id


# ========== 接口1：提交护理记录 ==========
@care_records_bp.route('/care-records', methods=['POST'])
@caregiver_required
@db_operation
def create_care_record():
    """
    提交护理记录
    必填字段：elder_id, record_date, health_data中的temperature/heart_rate/systolic_pressure/diastolic_pressure/blood_sugar
    """
    data = request.get_json()

    if not data.get('elder_id'):
        return jsonify({"code": 400, "msg": "老人ID不能为空", "data": None}), 400

    if not data.get('record_date'):
        return jsonify({"code": 400, "msg": "记录日期不能为空", "data": None}), 400

    elder_id = data.get('elder_id')
    record_date = data.get('record_date')
    health_data = data.get('health_data') or {}

    required_health_fields = {
        'temperature': '体温',
        'heart_rate': '心率',
        'systolic_pressure': '收缩压',
        'diastolic_pressure': '舒张压',
        'blood_sugar': '血糖'
    }
    missing_fields = []
    for field, label in required_health_fields.items():
        val = health_data.get(field)
        if val is None or val == '':
            missing_fields.append(label)
    if missing_fields:
        return jsonify({"code": 400, "msg": f"以下健康指标为必填项：{', '.join(missing_fields)}", "data": None}), 400

    try:
        with get_db() as conn:
            elder = conn.execute('SELECT * FROM elders WHERE id = ?', (elder_id,)).fetchone()
            if not elder:
                return jsonify({"code": 404, "msg": "老人信息不存在", "data": None}), 404

            caregiver_id = session.get('user_id')

            assignment = conn.execute('''
                SELECT * FROM caregiver_elder_assignments
                WHERE caregiver_id = ? AND elder_id = ?
            ''', (caregiver_id, elder_id)).fetchone()
            if not assignment:
                return jsonify({"code": 403, "msg": "您没有权限操作该老人的数据", "data": None}), 403

            if health_data:
                temp = health_data.get('temperature')
                if temp is not None and (temp < 35.0 or temp > 42.0):
                    return jsonify({"code": 400, "msg": "体温值必须在35-42℃之间", "data": None}), 400

                sp = health_data.get('systolic_pressure')
                if sp is not None and (sp < 60 or sp > 200):
                    return jsonify({"code": 400, "msg": "血压值必须在60-200mmHg之间", "data": None}), 400

                dp = health_data.get('diastolic_pressure')
                if dp is not None and (dp < 40 or dp > 120):
                    return jsonify({"code": 400, "msg": "舒张压必须在40-120mmHg之间", "data": None}), 400

                hr = health_data.get('heart_rate')
                if hr is not None and (hr < 40 or hr > 200):
                    return jsonify({"code": 400, "msg": "心率值必须在40-200bpm之间", "data": None}), 400

                bs = health_data.get('blood_sugar')
                if bs is not None and (bs < 2.0 or bs > 30.0):
                    return jsonify({"code": 400, "msg": "血糖值必须在2.0-30.0mmol/L之间", "data": None}), 400

            diet = data.get('diet', {})
            sleep = data.get('sleep', {})
            if 'quality' in sleep and sleep['quality'] not in ['good', 'average', 'poor']:
                return jsonify({"code": 400, "msg": "睡眠质量必须是good/average/poor之一", "data": None}), 400
            if 'duration' in sleep:
                duration = sleep['duration']
                if duration is not None and (duration < 0 or duration > 24):
                    return jsonify({"code": 400, "msg": "睡眠时长必须在0-24之间", "data": None}), 400

            emotion = data.get('emotion', {})
            if 'status' in emotion and emotion['status'] not in ['happy', 'calm', 'low', 'agitated']:
                return jsonify({"code": 400, "msg": "情绪状态必须是happy/calm/low/agitated之一", "data": None}), 400

            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO care_records
                (elder_id, caregiver_id, record_date, health_data, diet, sleep, emotion)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                elder_id,
                caregiver_id,
                record_date,
                json.dumps(health_data, ensure_ascii=False) if health_data else None,
                json.dumps(diet, ensure_ascii=False) if diet else None,
                json.dumps(sleep, ensure_ascii=False) if sleep else None,
                json.dumps(emotion, ensure_ascii=False) if emotion else None
            ))
            new_id = cursor.lastrowid

            triggered_alarms = []
            if health_data:
                alarm_data = dict(health_data)
                if sleep:
                    alarm_data['sleep'] = sleep
                triggered_alarms = check_and_trigger_alarms(conn, elder_id, alarm_data, new_id)

        return jsonify({
            "code": 200,
            "msg": "护理记录提交成功" + ("（已触发健康报警）" if triggered_alarms else ""),
            "data": {"id": new_id, "triggered_alarms": triggered_alarms}
        })

    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# ========== 接口2：获取护理记录列表（支持多条件筛选） ==========
@care_records_bp.route('/care-records', methods=['GET'])
@login_required
@db_operation
def get_care_records_list():
    """
    获取护理记录列表，支持多条件筛选
    查询参数：elder_keyword, start_date, end_date, page, page_size
    """
    elder_keyword = request.args.get('elder_keyword', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    try:
        with get_db() as conn:
            user_role = session.get('role')
            user_id = session.get('user_id')

            conditions = []
            params = []

            if user_role == 'caregiver':
                conditions.append('cr.elder_id IN (SELECT elder_id FROM caregiver_elder_assignments WHERE caregiver_id = ?)')
                params.append(user_id)
            elif user_role == 'family':
                conditions.append('cr.elder_id IN (SELECT elder_id FROM family_elder_bindings WHERE family_user_id = ?)')
                params.append(user_id)

            if elder_keyword:
                conditions.append('(e.name LIKE ? OR CAST(e.id AS TEXT) LIKE ?)')
                kw = f'%{elder_keyword}%'
                params.extend([kw, kw])

            if start_date:
                conditions.append('cr.record_date >= ?')
                params.append(start_date)

            if end_date:
                conditions.append('cr.record_date <= ?')
                params.append(end_date)

            where_clause = ' AND '.join(conditions) if conditions else '1=1'

            count_sql = f'''
                SELECT COUNT(*) FROM care_records cr
                LEFT JOIN elders e ON cr.elder_id = e.id
                WHERE {where_clause}
            '''
            total_count = conn.execute(count_sql, params).fetchone()[0]

            offset = (page - 1) * page_size
            query_sql = f'''
                SELECT cr.*, u.name as caregiver_name, e.name as elder_name, e.room_number, e.bed_number
                FROM care_records cr
                LEFT JOIN users u ON cr.caregiver_id = u.id
                LEFT JOIN elders e ON cr.elder_id = e.id
                WHERE {where_clause}
                ORDER BY cr.record_date DESC, cr.created_at DESC
                LIMIT ? OFFSET ?
            '''
            records = conn.execute(query_sql, params + [page_size, offset]).fetchall()

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

    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# ========== 接口3：获取老人护理记录列表 ==========
@care_records_bp.route('/elders/<int:elder_id>/care-records', methods=['GET'])
@login_required
@db_operation
def get_elder_care_records(elder_id):
    """
    获取指定老人的护理记录列表
    支持按日期范围筛选，支持分页
    """
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    try:
        with get_db() as conn:
            elder = conn.execute('SELECT * FROM elders WHERE id = ?', (elder_id,)).fetchone()
            if not elder:
                return jsonify({"code": 404, "msg": "老人信息不存在", "data": None}), 404

            user_role = session.get('role')
            user_id = session.get('user_id')

            if user_role == 'family':
                binding = conn.execute(
                    'SELECT * FROM family_elder_bindings WHERE family_user_id = ? AND elder_id = ?',
                    (user_id, elder_id)
                ).fetchone()
                if not binding:
                    return jsonify({"code": 403, "msg": "您没有权限查看该老人的护理记录", "data": None}), 403

            conditions = ['cr.elder_id = ?']
            params = [elder_id]

            if start_date:
                conditions.append('cr.record_date >= ?')
                params.append(start_date)

            if end_date:
                conditions.append('cr.record_date <= ?')
                params.append(end_date)

            where_clause = ' AND '.join(conditions)

            count_sql = f'''
                SELECT COUNT(*) FROM care_records cr
                WHERE {where_clause}
            '''
            total_count = conn.execute(count_sql, params).fetchone()[0]

            offset = (page - 1) * page_size
            query_sql = f'''
                SELECT cr.*, u.name as caregiver_name
                FROM care_records cr
                LEFT JOIN users u ON cr.caregiver_id = u.id
                WHERE {where_clause}
                ORDER BY cr.record_date DESC, cr.created_at DESC
                LIMIT ? OFFSET ?
            '''
            params_with_limit = params + [page_size, offset]

            records = conn.execute(query_sql, params_with_limit).fetchall()

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

    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# ========== 接口4：获取单条护理记录详情 ==========
@care_records_bp.route('/care-records/<int:id>', methods=['GET'])
@login_required
@db_operation
def get_care_record_detail(id):
    """
    获取单条护理记录详情
    """
    try:
        with get_db() as conn:
            record = conn.execute('''
                SELECT cr.*, u.name as caregiver_name, e.name as elder_name, e.room_number, e.bed_number
                FROM care_records cr
                LEFT JOIN users u ON cr.caregiver_id = u.id
                LEFT JOIN elders e ON cr.elder_id = e.id
                WHERE cr.id = ?
            ''', (id,)).fetchone()

            if not record:
                return jsonify({"code": 404, "msg": "护理记录不存在", "data": None}), 404

            user_role = session.get('role')
            user_id = session.get('user_id')
            elder_id = record['elder_id']

            if user_role == 'family':
                binding = conn.execute(
                    'SELECT * FROM family_elder_bindings WHERE family_user_id = ? AND elder_id = ?',
                    (user_id, elder_id)
                ).fetchone()
                if not binding:
                    return jsonify({"code": 403, "msg": "您没有权限查看该护理记录", "data": None}), 403

            if user_role == 'caregiver':
                assignment = conn.execute(
                    'SELECT * FROM caregiver_elder_assignments WHERE caregiver_id = ? AND elder_id = ?',
                    (user_id, elder_id)
                ).fetchone()
                if not assignment:
                    return jsonify({"code": 403, "msg": "您没有权限查看该护理记录", "data": None}), 403

        result = dict(record)
        for field in ['health_data', 'diet', 'sleep', 'emotion']:
            if result.get(field):
                try:
                    result[field] = json.loads(result[field])
                except json.JSONDecodeError:
                    result[field] = None

        return jsonify({
            "code": 200,
            "msg": "获取成功",
            "data": result
        })

    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500
