"""
系统日志API模块
提供登录日志和操作日志的查询功能
"""

from flask import Blueprint, request, jsonify, session, send_file
from .decorators import admin_required
import sqlite3
import os
import sys
import io
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import get_logs, get_users_list


logs_bp = Blueprint('logs', __name__, url_prefix='/api/v1/logs')


def get_db_connection():
    """获取数据库连接"""
    current_dir = os.path.dirname(__file__)
    db_path = os.path.join(current_dir, '..', 'instance', 'nursing_home.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@logs_bp.route('', methods=['GET'])
@admin_required
def list_logs():
    """获取系统操作日志列表 - 仅管理员"""
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 20))
    module = request.args.get('module')
    action = request.args.get('action')
    user_id = request.args.get('user_id', type=int)
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')

    offset = (page - 1) * limit

    result = get_logs(
        limit=limit,
        offset=offset,
        module=module,
        action=action,
        user_id=user_id,
        start_time=start_time,
        end_time=end_time
    )

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "logs": result['logs'],
            "total": result['total'],
            "page": page,
            "limit": limit
        }
    })


@logs_bp.route('/users', methods=['GET'])
@admin_required
def list_log_users():
    """获取日志用户列表 - 用于筛选"""
    users = get_users_list()
    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": users
    })


@logs_bp.route('/export', methods=['GET'])
@admin_required
def export_logs():
    """导出系统日志 - Excel格式"""
    module = request.args.get('module')
    action = request.args.get('action')
    user_id = request.args.get('user_id', type=int)
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')

    result = get_logs(
        limit=10000,
        offset=0,
        module=module,
        action=action,
        user_id=user_id,
        start_time=start_time,
        end_time=end_time
    )

    logs = result['logs']

    try:
        import pandas as pd
        from datetime import datetime

        module_map = {
            'auth': '认证', 'elders': '老人', 'users': '用户',
            'care_tasks': '任务', 'alarms': '报警', 'visits': '探视',
            'alarm_rules': '报警规则', 'incident_reports': '异常上报',
            'care_records': '护理记录', 'family': '家属', 'system': '系统'
        }
        action_map = {
            'login': '登录', 'logout': '退出', 'create': '创建',
            'update': '更新', 'delete': '删除', 'password_reset': '密码重置',
            'lock': '锁定', 'unlock': '解锁', 'batch_unlock': '批量解锁',
            'toggle_lockout_policy': '切换锁定策略'
        }

        data_rows = []
        for log in logs:
            data_rows.append({
                'ID': log['id'],
                '操作时间': log['created_at'],
                '操作人ID': log['user_id'],
                '操作人': log['user_name'] or '系统',
                '业务模块': module_map.get(log['module'], log['module']),
                '操作类型': action_map.get(log['action'], log['action']),
                '操作描述': log['description'] or '',
                'IP地址': log['ip_address'] or '',
                '敏感操作': '是' if log['is_sensitive'] else '否'
            })

        df = pd.DataFrame(data_rows)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='操作日志')
            worksheet = writer.sheets['操作日志']
            for idx, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max() if len(df) > 0 else 0, len(col))
                worksheet.column_dimensions[chr(65 + idx) if idx < 26 else chr(64 + idx // 26) + chr(65 + idx % 26)].width = min(max_len + 4, 50)

        output.seek(0)
        filename = f'操作日志_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except ImportError:
        return jsonify({"code": 500, "msg": "导出功能依赖pandas库，请安装：pip install pandas openpyxl", "data": None}), 500


@logs_bp.route('/login', methods=['GET'])
@admin_required
def list_login_logs():
    """获取登录日志列表 - 仅管理员"""
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 20))
    user_id = request.args.get('user_id', type=int)
    login_status = request.args.get('status')
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')

    offset = (page - 1) * limit

    conn = get_db_connection()

    # 构建查询条件
    conditions = []
    params = []

    if user_id:
        conditions.append('user_id = ?')
        params.append(user_id)

    if login_status:
        conditions.append('login_status = ?')
        params.append(login_status)

    if start_time:
        conditions.append('login_time >= ?')
        params.append(start_time)

    if end_time:
        conditions.append('login_time <= ?')
        params.append(end_time)

    where_clause = ' AND '.join(conditions) if conditions else '1=1'

    # 查询总数
    total = conn.execute(
        f'SELECT COUNT(*) FROM login_logs WHERE {where_clause}',
        params
    ).fetchone()[0]

    # 查询日志
    logs = conn.execute(f'''
        SELECT ll.*, u.name as user_name 
        FROM login_logs ll
        LEFT JOIN users u ON ll.user_id = u.id
        WHERE {where_clause}
        ORDER BY ll.login_time DESC
        LIMIT ? OFFSET ?
    ''', params + [limit, offset]).fetchall()

    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "logs": [dict(l) for l in logs],
            "total": total,
            "page": page,
            "limit": limit
        }
    })


@logs_bp.route('/login/export', methods=['GET'])
@admin_required
def export_login_logs():
    """导出登录日志 - Excel格式"""
    user_id = request.args.get('user_id', type=int)
    login_status = request.args.get('status')
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')

    conn = get_db_connection()
    conditions = []
    params = []

    if user_id:
        conditions.append('user_id = ?')
        params.append(user_id)

    if login_status:
        conditions.append('login_status = ?')
        params.append(login_status)

    if start_time:
        conditions.append('login_time >= ?')
        params.append(start_time)

    if end_time:
        conditions.append('login_time <= ?')
        params.append(end_time)

    where_clause = ' AND '.join(conditions) if conditions else '1=1'

    logs = conn.execute(f'''
        SELECT ll.*, u.name as user_name 
        FROM login_logs ll
        LEFT JOIN users u ON ll.user_id = u.id
        WHERE {where_clause}
        ORDER BY ll.login_time DESC
        LIMIT 10000
    ''', params).fetchall()

    conn.close()

    try:
        import pandas as pd
        from datetime import datetime

        status_map = {'success': '成功', 'failed': '失败', 'locked': '锁定'}

        data_rows = []
        for log in logs:
            data_rows.append({
                'ID': log['id'],
                '登录时间': log['login_time'],
                '用户ID': log['user_id'],
                '用户名': log['user_name'] or log['username'],
                '登录账号': log['username'],
                '登录状态': status_map.get(log['login_status'], log['login_status']),
                '失败原因': log['failure_reason'] or '',
                'IP地址': log['ip_address'] or '',
                '用户代理': log['user_agent'] or ''
            })

        df = pd.DataFrame(data_rows)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='登录日志')
            worksheet = writer.sheets['登录日志']
            for idx, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max() if len(df) > 0 else 0, len(col))
                worksheet.column_dimensions[chr(65 + idx) if idx < 26 else chr(64 + idx // 26) + chr(65 + idx % 26)].width = min(max_len + 4, 50)

        output.seek(0)
        filename = f'登录日志_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except ImportError:
        return jsonify({"code": 500, "msg": "导出功能依赖pandas库，请安装：pip install pandas openpyxl", "data": None}), 500


@logs_bp.route('/login/<int:log_id>', methods=['GET'])
@admin_required
def get_login_log_detail(log_id):
    """获取单条登录日志详情"""
    conn = get_db_connection()
    log = conn.execute('''
        SELECT ll.*, u.name as user_name 
        FROM login_logs ll
        LEFT JOIN users u ON ll.user_id = u.id
        WHERE ll.id = ?
    ''', (log_id,)).fetchone()
    conn.close()

    if not log:
        return jsonify({"code": 404, "msg": "日志不存在", "data": None}), 404

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": dict(log)
    })
