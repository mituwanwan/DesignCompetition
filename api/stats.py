from flask import Blueprint, jsonify, session, request
import sqlite3
import os
from datetime import datetime, date
from .decorators import admin_required, caregiver_required, family_required

# 创建一个新蓝图，专门管统计数据
stats_bp = Blueprint('stats', __name__, url_prefix='/api/v1/stats')


def get_db_connection():
    # 使用绝对路径避免中文字符路径问题
    current_dir = os.path.dirname(__file__)
    db_path = os.path.join(current_dir, '..', 'instance', 'nursing_home.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@stats_bp.route('/admin-dashboard', methods=['GET'])
def admin_dashboard():
    conn = get_db_connection()

    # ========== 核心数字卡片 ==========
    # 1. 在院老人总数
    active_elders_count = conn.execute(
        "SELECT COUNT(*) FROM elders WHERE status = 'active'"
    ).fetchone()[0]

    # 2. 健康老人数（最近7天内无报警且健康数据正常）
    healthy_elders_count = conn.execute('''
        SELECT COUNT(DISTINCT e.id)
        FROM elders e
        LEFT JOIN alarms a ON e.id = a.elder_id
            AND a.triggered_at >= datetime('now', '-7 days')
        WHERE e.status = 'active'
            AND a.id IS NULL
    ''').fetchone()[0]

    # 3. 需关注老人数（最近7天内有报警的老人）
    attention_elders_count = conn.execute('''
        SELECT COUNT(DISTINCT e.id)
        FROM elders e
        JOIN alarms a ON e.id = a.elder_id
        WHERE e.status = 'active'
            AND a.triggered_at >= datetime('now', '-7 days')
    ''').fetchone()[0]

    # 4. 报警响应及时率（过去30天内24小时内处理的比例）
    total_resolved_alarms = conn.execute('''
        SELECT COUNT(*) FROM alarms
        WHERE status IN ('processing', 'resolved')
            AND triggered_at >= datetime('now', '-30 days')
    ''').fetchone()[0]

    timely_resolved_alarms = 0
    if total_resolved_alarms > 0:
        timely_resolved_alarms = conn.execute('''
            SELECT COUNT(*) FROM alarms
            WHERE status IN ('processing', 'resolved')
                AND triggered_at >= datetime('now', '-30 days')
                AND (
                    (processing_at IS NOT NULL
                        AND julianday(processing_at) - julianday(triggered_at) <= 1)
                    OR status = 'resolved'
                )
        ''').fetchone()[0]

    response_rate = 0
    if total_resolved_alarms > 0:
        response_rate = round(timely_resolved_alarms / total_resolved_alarms * 100, 1)

    # ========== 高风险老人预警 ==========
    high_risk_elders = conn.execute('''
        SELECT e.*,
            COUNT(a.id) as recent_alarm_count,
            MAX(a.triggered_at) as latest_alarm_at
        FROM elders e
        LEFT JOIN alarms a ON e.id = a.elder_id
            AND a.triggered_at >= datetime('now', '-3 days')
        WHERE e.status = 'active'
        GROUP BY e.id
        ORDER BY recent_alarm_count DESC, latest_alarm_at DESC
    ''').fetchall()

    high_risk_list = []

    alarm_rules_rows = conn.execute('SELECT * FROM alarm_rules WHERE is_enabled = 1').fetchall()
    alarm_rules_map = {r['rule_key']: dict(r) for r in alarm_rules_rows}

    for elder in high_risk_elders:
        elder_dict = dict(elder)
        recent_alarm_count = elder_dict['recent_alarm_count'] or 0

        has_consecutive_abnormal = False
        recent_records = conn.execute('''
            SELECT record_date, health_data FROM care_records
            WHERE elder_id = ?
                AND record_date >= date('now', '-3 days')
            ORDER BY record_date DESC
            LIMIT 3
        ''', (elder_dict['id'],)).fetchall()

        if len(recent_records) >= 3:
            abnormal_count = 0
            for record in recent_records:
                health_data = record['health_data']
                if health_data:
                    try:
                        import json
                        health = json.loads(health_data)
                        is_abnormal = False
                        temp = health.get('temperature')
                        systolic = health.get('systolic_pressure')
                        diastolic = health.get('diastolic_pressure')
                        hr = health.get('heart_rate')

                        r = alarm_rules_map.get('temp_high')
                        if r and temp and r['threshold_max'] is not None and temp > r['threshold_max']:
                            is_abnormal = True
                        r = alarm_rules_map.get('temp_low')
                        if r and temp and r['threshold_min'] is not None and temp < r['threshold_min']:
                            is_abnormal = True
                        r = alarm_rules_map.get('bp_high')
                        if r and systolic and r['threshold_max'] is not None and systolic > r['threshold_max']:
                            is_abnormal = True
                        r = alarm_rules_map.get('bp_low')
                        if r and diastolic and r['threshold_min'] is not None and diastolic < r['threshold_min']:
                            is_abnormal = True
                        r = alarm_rules_map.get('hr_high')
                        if r and hr and r['threshold_max'] is not None and hr > r['threshold_max']:
                            is_abnormal = True
                        r = alarm_rules_map.get('hr_low')
                        if r and hr and r['threshold_min'] is not None and hr < r['threshold_min']:
                            is_abnormal = True

                        if is_abnormal:
                            abnormal_count += 1
                    except:
                        pass
            if abnormal_count >= 3:
                has_consecutive_abnormal = True

        # 风险等级判定：
        # high（高风险/红色）：连续3天健康数据异常，或近3天报警>=3次
        # medium（需关注/橙色）：近3天有报警记录（1-2次）
        # normal（健康/绿色）：健康状态稳定，无报警记录
        if has_consecutive_abnormal or recent_alarm_count >= 3:
            elder_dict['risk_level'] = 'high'
        elif recent_alarm_count >= 1:
            elder_dict['risk_level'] = 'medium'
        else:
            elder_dict['risk_level'] = 'normal'

        high_risk_list.append(elder_dict)

    risk_order = {'high': 0, 'medium': 1, 'normal': 2}
    high_risk_list.sort(key=lambda x: (risk_order.get(x.get('risk_level', 'normal'), 9), -(x.get('recent_alarm_count') or 0)))

    # ========== 今日待办汇总 ==========
    today = date.today().isoformat()

    # 待审批探视预约
    pending_visits_count = conn.execute('''
        SELECT COUNT(*) FROM appointments
        WHERE status = 'pending'
    ''').fetchone()[0]

    # 待处理报警
    unhandled_alarms_count = conn.execute(
        "SELECT COUNT(*) FROM alarms WHERE status = 'unhandled'"
    ).fetchone()[0]

    # 待分配任务
    pending_tasks_count = conn.execute(
        "SELECT COUNT(*) FROM care_tasks WHERE status = 'pending'"
    ).fetchone()[0]

    completed_tasks_count = conn.execute(
        "SELECT COUNT(*) FROM care_tasks WHERE status = 'completed'"
    ).fetchone()[0]

    total_tasks_count = conn.execute(
        "SELECT COUNT(*) FROM care_tasks"
    ).fetchone()[0]

    task_completion_rate = round(completed_tasks_count / total_tasks_count * 100, 1) if total_tasks_count > 0 else 0

    # ========== 全院运营动态时间线 ==========
    recent_alarms = conn.execute('''
        SELECT
            a.id,
            'alarm' as type,
            a.triggered_at as created_at,
            e.name as elder_name,
            a.type as detail,
            a.status as status
        FROM alarms a
        JOIN elders e ON a.elder_id = e.id
        ORDER BY a.triggered_at DESC
        LIMIT 10
    ''').fetchall()

    recent_tasks = conn.execute('''
        SELECT
            ct.id,
            'task' as type,
            ct.completed_at as created_at,
            e.name as elder_name,
            ct.content as detail,
            ct.status as status
        FROM care_tasks ct
        JOIN elders e ON ct.elder_id = e.id
        WHERE ct.status = 'completed'
        ORDER BY ct.completed_at DESC
        LIMIT 10
    ''').fetchall()

    recent_visits = conn.execute('''
        SELECT
            v.id,
            'visit' as type,
            v.created_at,
            e.name as elder_name,
            v.type || '探视预约' as detail,
            v.status
        FROM appointments v
        JOIN elders e ON v.elder_id = e.id
        ORDER BY v.created_at DESC
        LIMIT 10
    ''').fetchall()

    # 合并并排序所有动态
    all_activities = []
    for item in recent_alarms:
        all_activities.append(dict(item))
    for item in recent_tasks:
        all_activities.append(dict(item))
    for item in recent_visits:
        all_activities.append(dict(item))

    # 按时间倒序排序
    all_activities.sort(key=lambda x: x['created_at'] or '', reverse=True)
    all_activities = all_activities[:15]

    # ========== 额外信息 ==========
    caregivers_count = conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'caregiver' AND status = 'enabled'"
    ).fetchone()[0]

    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "active_elders_count": active_elders_count,
            "healthy_elders_count": healthy_elders_count,
            "attention_elders_count": attention_elders_count,
            "alarm_response_rate": response_rate,
            "unhandled_alarms_count": unhandled_alarms_count,
            "pending_visits_count": pending_visits_count,
            "pending_tasks_count": pending_tasks_count,
            "completed_tasks_count": completed_tasks_count,
            "total_tasks_count": total_tasks_count,
            "task_completion_rate": task_completion_rate,
            "high_risk_elders": high_risk_list,
            "recent_activities": all_activities,
            "on_duty_caregivers_count": caregivers_count
        }
    })


@stats_bp.route('/caregiver-dashboard', methods=['GET'])
@caregiver_required
def caregiver_dashboard():
    """护工首页数据统计"""
    caregiver_id = session['user_id']
    today = date.today().isoformat()

    conn = get_db_connection()

    # 1. 今日护理任务统计
    today_tasks_result = conn.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
        FROM care_tasks
        WHERE caregiver_id = ? 
          AND date(due_time) = ?
    ''', (caregiver_id, today)).fetchone()

    today_tasks_count = today_tasks_result['total'] or 0
    tasks_completed_count = today_tasks_result['completed'] or 0

    # 2. 待处理报警数（只显示该护工负责老人的报警）
    unhandled_alarms_count = conn.execute('''
        SELECT COUNT(DISTINCT a.id) FROM alarms a
        INNER JOIN caregiver_elder_assignments cea ON a.elder_id = cea.elder_id
        WHERE cea.caregiver_id = ? 
          AND a.status = 'unhandled'
    ''', (caregiver_id,)).fetchone()[0]

    # 3. 今日已完成的护理记录数
    today_records_count = conn.execute('''
        SELECT COUNT(*) FROM care_records
        WHERE caregiver_id = ? AND record_date = ?
    ''', (caregiver_id, today)).fetchone()[0]

    # 4. 护理中的老人数（通过分配表）
    assigned_elders_count = conn.execute('''
        SELECT COUNT(DISTINCT elder_id) FROM caregiver_elder_assignments
        WHERE caregiver_id = ?
    ''', (caregiver_id,)).fetchone()[0]

    # 5. 获取今日护理任务列表（限制5条）
    today_tasks = conn.execute('''
        SELECT ct.*, e.name as elder_name, e.room_number
        FROM care_tasks ct
        JOIN elders e ON ct.elder_id = e.id
        WHERE ct.caregiver_id = ? AND ct.status = 'pending'
          AND date(ct.due_time) = ?
        ORDER BY ct.due_time
        LIMIT 5
    ''', (caregiver_id, today)).fetchall()

    # 6. 获取最近的报警（只显示该护工负责老人的，限制3条）
    recent_alarms = conn.execute('''
        SELECT a.*, e.name as elder_name, e.room_number
        FROM alarms a
        JOIN elders e ON a.elder_id = e.id
        INNER JOIN caregiver_elder_assignments cea ON a.elder_id = cea.elder_id
        WHERE cea.caregiver_id = ? 
          AND a.status = 'unhandled'
        ORDER BY a.triggered_at DESC
        LIMIT 3
    ''', (caregiver_id,)).fetchall()

    conn.close()

    # 转换为字典列表
    tasks_list = []
    for task in today_tasks:
        task_dict = dict(task)
        tasks_list.append(task_dict)

    alarms_list = []
    for alarm in recent_alarms:
        alarm_dict = dict(alarm)
        alarms_list.append(alarm_dict)

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "today_tasks_count": today_tasks_count,
            "tasks_completed_count": tasks_completed_count,
            "unhandled_alarms_count": unhandled_alarms_count,
            "today_records_count": today_records_count,
            "assigned_elders_count": assigned_elders_count,
            "today_tasks": tasks_list,
            "recent_alarms": alarms_list
        }
    })


@stats_bp.route('/family-dashboard', methods=['GET'])
@family_required
def family_dashboard():
    """子女首页数据统计"""
    family_id = session['user_id']

    conn = get_db_connection()

    # 1. 获取绑定的老人列表
    bound_elders = conn.execute('''
        SELECT e.*
        FROM elders e
        JOIN family_elder_bindings feb ON e.id = feb.elder_id
        WHERE feb.family_user_id = ? AND e.status = 'active'
    ''', (family_id,)).fetchall()

    bound_elders_list = [dict(elder) for elder in bound_elders]
    bound_elders_count = len(bound_elders_list)

    # 2. 获取最近的留言（限制5条）
    recent_messages = conn.execute('''
        SELECT m.*, e.name as elder_name,
               u.name as sender_name, u.role as sender_role
        FROM messages m
        JOIN elders e ON m.elder_id = e.id
        JOIN users u ON m.sender_id = u.id
        WHERE m.elder_id IN (
            SELECT elder_id FROM family_elder_bindings
            WHERE family_user_id = ?
        )
        ORDER BY m.created_at DESC
        LIMIT 5
    ''', (family_id,)).fetchall()

    # 3. 获取最近的护理记录（每个老人最近一条）
    recent_care_records = []
    for elder in bound_elders_list:
        record = conn.execute('''
            SELECT * FROM care_records
            WHERE elder_id = ?
            ORDER BY record_date DESC, created_at DESC
            LIMIT 1
        ''', (elder['id'],)).fetchone()
        if record:
            record_dict = dict(record)
            record_dict['elder_name'] = elder['name']
            recent_care_records.append(record_dict)

    # 4. 获取最近的报警（限制3条）
    recent_alarms = conn.execute('''
        SELECT a.*, e.name as elder_name
        FROM alarms a
        JOIN elders e ON a.elder_id = e.id
        WHERE a.elder_id IN (
            SELECT elder_id FROM family_elder_bindings
            WHERE family_user_id = ?
        )
        ORDER BY a.triggered_at DESC
        LIMIT 3
    ''', (family_id,)).fetchall()

    conn.close()

    # 转换为字典列表
    messages_list = []
    for msg in recent_messages:
        msg_dict = dict(msg)
        messages_list.append(msg_dict)

    alarms_list = []
    for alarm in recent_alarms:
        alarm_dict = dict(alarm)
        alarms_list.append(alarm_dict)

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "bound_elders_count": bound_elders_count,
            "bound_elders": bound_elders_list,
            "recent_messages": messages_list,
            "recent_care_records": recent_care_records,
            "recent_alarms": alarms_list
        }
    })


@stats_bp.route('/admin-reports', methods=['GET'])
@admin_required
def admin_reports():
    """管理员统计报表数据 - 带筛选功能"""
    conn = get_db_connection()

    month = request.args.get('month')
    floor = request.args.get('floor')
    caregiver_id = request.args.get('caregiver_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    def build_time_condition(field='triggered_at'):
        conditions = ["1=1"]
        params = []
        if start_date and end_date:
            conditions.append(f"{field} >= ? AND {field} <= ?")
            params.append(start_date + ' 00:00:00')
            params.append(end_date + ' 23:59:59')
        elif month:
            conditions.append(f"strftime('%Y-%m', {field}) = ?")
            params.append(month)
        else:
            conditions.append(f"{field} >= datetime('now', '-30 days')")
        return ' AND '.join(conditions), params

    def build_elder_filter(table_alias='e'):
        conditions = []
        params = []
        if floor:
            conditions.append(f"SUBSTR({table_alias}.room_number, 1, 1) = ?")
            params.append(floor)
        return ' AND '.join(conditions), params

    alarm_time_where, alarm_time_params = build_time_condition('triggered_at')

    elder_floor_where, elder_floor_params = build_elder_filter('e')

    alarm_where_parts = [alarm_time_where]
    alarm_where_params = list(alarm_time_params)
    if floor:
        alarm_where_parts.append("""a.elder_id IN (SELECT id FROM elders WHERE SUBSTR(room_number, 1, 1) = ?)""")
        alarm_where_params.append(floor)
    alarm_where = ' AND '.join(alarm_where_parts)

    alarm_trend = conn.execute('''
        SELECT date(triggered_at) as day, COUNT(*) as count
        FROM alarms a
        WHERE ''' + alarm_where + '''
        GROUP BY date(triggered_at)
        ORDER BY day
    ''', alarm_where_params).fetchall()

    alarm_types = conn.execute('''
        SELECT type, COUNT(*) as count
        FROM alarms a
        WHERE ''' + alarm_where + '''
        GROUP BY type
    ''', alarm_where_params).fetchall()

    alarm_status = conn.execute('''
        SELECT status, COUNT(*) as count
        FROM alarms a
        WHERE ''' + alarm_where + '''
        GROUP BY status
    ''', alarm_where_params).fetchall()

    total_alarms_in_period = conn.execute(
        'SELECT COUNT(*) FROM alarms a WHERE ' + alarm_where, alarm_where_params
    ).fetchone()[0]
    timely_alarms = 0
    if total_alarms_in_period > 0:
        timely_alarms = conn.execute('''
            SELECT COUNT(*) FROM alarms a
            WHERE ''' + alarm_where + '''
                AND processing_at IS NOT NULL
                AND julianday(processing_at) - julianday(triggered_at) <= 1.0/24.0
        ''', alarm_where_params).fetchone()[0]
    alarm_response_rate = round(timely_alarms / total_alarms_in_period * 100, 1) if total_alarms_in_period > 0 else 0

    task_where_parts = ["1=1"]
    task_params = []
    if caregiver_id:
        task_where_parts.append("caregiver_id = ?")
        task_params.append(caregiver_id)
    if start_date and end_date:
        task_where_parts.append("created_at >= ? AND created_at <= ?")
        task_params.append(start_date + ' 00:00:00')
        task_params.append(end_date + ' 23:59:59')
    elif month:
        task_where_parts.append("strftime('%Y-%m', created_at) = ?")
        task_params.append(month)
    else:
        task_where_parts.append("created_at >= datetime('now', '-30 days')")
    task_where = ' AND '.join(task_where_parts)

    task_stats = conn.execute('''
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
        FROM care_tasks
        WHERE ''' + task_where, task_params).fetchone()

    task_trend_where_parts = ["created_at >= datetime('now', '-7 days')"]
    task_trend_params = []
    if caregiver_id:
        task_trend_where_parts.append("caregiver_id = ?")
        task_trend_params.append(caregiver_id)
    task_trend_where = ' AND '.join(task_trend_where_parts)

    task_trend = conn.execute('''
        SELECT date(created_at) as day,
               COUNT(*) as total,
               SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
        FROM care_tasks
        WHERE ''' + task_trend_where + '''
        GROUP BY date(created_at)
        ORDER BY day
    ''', task_trend_params).fetchall()

    user_counts = conn.execute('''
        SELECT role, COUNT(*) as count
        FROM users WHERE status = 'enabled'
        GROUP BY role
    ''').fetchall()

    health_where_parts = ["health_data IS NOT NULL"]
    health_params = []
    if start_date and end_date:
        health_where_parts.append("record_date >= ? AND record_date <= ?")
        health_params.append(start_date)
        health_params.append(end_date)
    elif month:
        health_where_parts.append("strftime('%Y-%m', record_date) = ?")
        health_params.append(month)
    else:
        health_where_parts.append("record_date >= date('now', '-7 days')")
    if floor:
        health_where_parts.append("elder_id IN (SELECT id FROM elders WHERE SUBSTR(room_number, 1, 1) = ?)")
        health_params.append(floor)
    if caregiver_id:
        health_where_parts.append("caregiver_id = ?")
        health_params.append(caregiver_id)
    health_where = ' AND '.join(health_where_parts)

    health_stats = conn.execute('''
        SELECT
            AVG(json_extract(health_data, '$.temperature')) as avg_temperature,
            AVG(json_extract(health_data, '$.heart_rate')) as avg_heart_rate,
            AVG(json_extract(health_data, '$.systolic_pressure')) as avg_systolic,
            AVG(json_extract(health_data, '$.diastolic_pressure')) as avg_diastolic
        FROM care_records
        WHERE ''' + health_where, health_params).fetchone()

    elder_status_where_parts = ["1=1"]
    elder_status_params = []
    if floor:
        elder_status_where_parts.append("SUBSTR(room_number, 1, 1) = ?")
        elder_status_params.append(floor)
    elder_status_where = ' AND '.join(elder_status_where_parts)

    elder_status = conn.execute('''
        SELECT status, COUNT(*) as count
        FROM elders
        WHERE ''' + elder_status_where + '''
        GROUP BY status
    ''', elder_status_params).fetchall()

    caregiver_workload_where_parts = ["u.role = 'caregiver' AND u.status = 'enabled'"]
    caregiver_workload_params = []
    if caregiver_id:
        caregiver_workload_where_parts.append("u.id = ?")
        caregiver_workload_params.append(caregiver_id)
    caregiver_workload_where = ' AND '.join(caregiver_workload_where_parts)

    task_time_filter = ""
    task_time_params_wl = []
    if start_date and end_date:
        task_time_filter = " AND ct.created_at >= ? AND ct.created_at <= ?"
        task_time_params_wl = [start_date + ' 00:00:00', end_date + ' 23:59:59']
    elif month:
        task_time_filter = " AND strftime('%Y-%m', ct.created_at) = ?"
        task_time_params_wl = [month]

    record_time_filter = ""
    record_time_params_wl = []
    if start_date and end_date:
        record_time_filter = " AND cr.created_at >= ? AND cr.created_at <= ?"
        record_time_params_wl = [start_date + ' 00:00:00', end_date + ' 23:59:59']
    elif month:
        record_time_filter = " AND strftime('%Y-%m', cr.created_at) = ?"
        record_time_params_wl = [month]

    wl_params = caregiver_workload_params + task_time_params_wl + record_time_params_wl
    caregiver_workload = conn.execute('''
        SELECT u.id, u.name,
            COUNT(DISTINCT ct.id) as completed_count,
            (SELECT COUNT(*) FROM care_records cr WHERE cr.caregiver_id = u.id''' + record_time_filter + ''') as record_count
        FROM users u
        LEFT JOIN care_tasks ct ON u.id = ct.caregiver_id AND ct.status = 'completed' ''' + task_time_filter + '''
        WHERE ''' + caregiver_workload_where + '''
        GROUP BY u.id, u.name
        ORDER BY completed_count DESC
        LIMIT 10
    ''', wl_params).fetchall()

    floor_health_where_parts = ["e.status = 'active'"]
    floor_health_params = []
    if floor:
        floor_health_where_parts.append("SUBSTR(e.room_number, 1, 1) = ?")
        floor_health_params.append(floor)
    floor_health_where = ' AND '.join(floor_health_where_parts)

    floor_health = conn.execute('''
        SELECT
            SUBSTR(e.room_number, 1, 1) as floor_name,
            COUNT(DISTINCT e.id) as total_elders,
            SUM(CASE
                WHEN json_extract(health_data, '$.temperature') IS NOT NULL
                THEN 1 ELSE 0
            END) as measured_count
        FROM elders e
        LEFT JOIN care_records cr ON e.id = cr.elder_id
            AND cr.record_date >= date('now', '-7 days')
        WHERE ''' + floor_health_where + '''
        GROUP BY SUBSTR(e.room_number, 1, 1)
        ORDER BY floor_name
    ''', floor_health_params).fetchall()

    disease_stats = []
    try:
        disease_elder_where = ["status = 'active' AND medical_history IS NOT NULL"]
        disease_params = []
        if floor:
            disease_elder_where.append("SUBSTR(room_number, 1, 1) = ?")
            disease_params.append(floor)
        disease_elder_where_sql = ' AND '.join(disease_elder_where)
        elders = conn.execute('''
            SELECT medical_history FROM elders
            WHERE ''' + disease_elder_where_sql, disease_params).fetchall()
        disease_count = {}
        for elder in elders:
            if elder['medical_history']:
                diseases = str(elder['medical_history']).split(',')
                for d in diseases:
                    d_clean = d.strip()
                    if d_clean:
                        disease_count[d_clean] = disease_count.get(d_clean, 0) + 1
        disease_stats = [{'name': k, 'count': v} for k, v in sorted(disease_count.items(), key=lambda x: -x[1])[:10]]
    except Exception:
        pass

    rt_where_parts = ["a.status IN ('processing', 'resolved')", "a.handler_id IS NOT NULL", "a.processing_at IS NOT NULL"]
    rt_params = []
    if caregiver_id:
        rt_where_parts.append("a.handler_id = ?")
        rt_params.append(caregiver_id)
    if start_date and end_date:
        rt_where_parts.append("a.triggered_at >= ? AND a.triggered_at <= ?")
        rt_params.append(start_date + ' 00:00:00')
        rt_params.append(end_date + ' 23:59:59')
    elif month:
        rt_where_parts.append("strftime('%Y-%m', a.triggered_at) = ?")
        rt_params.append(month)
    else:
        rt_where_parts.append("a.triggered_at >= datetime('now', '-30 days')")
    if floor:
        rt_where_parts.append("a.elder_id IN (SELECT id FROM elders WHERE SUBSTR(room_number, 1, 1) = ?)")
        rt_params.append(floor)
    rt_where = ' AND '.join(rt_where_parts)

    response_time_stats = conn.execute('''
        SELECT
            handler_id,
            u.name as caregiver_name,
            COUNT(*) as total_alarms,
            AVG(julianday(processing_at) - julianday(triggered_at)) * 24 * 60 as avg_response_minutes,
            MIN(julianday(processing_at) - julianday(triggered_at)) * 24 * 60 as min_response_minutes,
            MAX(julianday(processing_at) - julianday(triggered_at)) * 24 * 60 as max_response_minutes
        FROM alarms a
        LEFT JOIN users u ON a.handler_id = u.id
        WHERE ''' + rt_where + '''
        GROUP BY handler_id, u.name
        ORDER BY avg_response_minutes ASC
    ''', rt_params).fetchall()

    floors = conn.execute('''
        SELECT DISTINCT SUBSTR(room_number, 1, 1) as floor FROM elders
        WHERE status = 'active'
        ORDER BY floor
    ''').fetchall()

    caregivers = conn.execute('''
        SELECT id, name FROM users
        WHERE role = 'caregiver' AND status = 'enabled'
        ORDER BY name
    ''').fetchall()

    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "alarm_trend": [dict(r) for r in alarm_trend],
            "alarm_types": [dict(r) for r in alarm_types],
            "alarm_status": [dict(r) for r in alarm_status],
            "alarm_response_rate": alarm_response_rate,
            "task_stats": {
                "total": task_stats['total'],
                "completed": task_stats['completed'],
                "rate": round(task_stats['completed'] / task_stats['total'] * 100, 1) if task_stats['total'] else 0
            },
            "task_trend": [dict(r) for r in task_trend],
            "user_counts": [dict(r) for r in user_counts],
            "health_stats": {
                "avg_temperature": round(health_stats['avg_temperature'], 1) if health_stats['avg_temperature'] else None,
                "avg_heart_rate": round(health_stats['avg_heart_rate'], 1) if health_stats['avg_heart_rate'] else None,
                "avg_systolic": round(health_stats['avg_systolic'], 1) if health_stats['avg_systolic'] else None,
                "avg_diastolic": round(health_stats['avg_diastolic'], 1) if health_stats['avg_diastolic'] else None
            },
            "elder_status": [dict(r) for r in elder_status],
            "caregiver_workload": [dict(r) for r in caregiver_workload],
            "disease_stats": disease_stats,
            "floor_health": [dict(r) for r in floor_health],
            "response_time_stats": [dict(r) for r in response_time_stats],
            "filters": {
                "floors": [dict(r) for r in floors],
                "caregivers": [dict(r) for r in caregivers]
            }
        }
    })
