"""
报警规则管理API模块
提供报警规则的查询、配置等功能
"""

import sqlite3
import os
from flask import Blueprint, request, jsonify, session
from .decorators import admin_required
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import log_action

alarm_rules_bp = Blueprint('alarm_rules', __name__, url_prefix='/api/v1/alarm-rules')


def get_db_connection():
    current_dir = os.path.dirname(__file__)
    db_path = os.path.join(current_dir, '..', 'instance', 'nursing_home.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ========== 1. 获取所有报警规则 ==========
@alarm_rules_bp.route('', methods=['GET'])
@admin_required
def get_alarm_rules():
    conn = get_db_connection()
    rules = conn.execute('SELECT * FROM alarm_rules ORDER BY rule_type, rule_name').fetchall()
    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": [dict(r) for r in rules]
    })


# ========== 2. 更新报警规则 ==========
@alarm_rules_bp.route('/<int:id>', methods=['PUT'])
@admin_required
def update_alarm_rule(id):
    data = request.get_json()
    rule_name = data.get('rule_name', '')
    is_enabled = data.get('is_enabled')
    threshold_min = data.get('threshold_min')
    threshold_max = data.get('threshold_max')
    description = data.get('description')

    if not rule_name:
        return jsonify({"code": 400, "msg": "规则名称不能为空", "data": None}), 400

    conn = get_db_connection()
    rule = conn.execute('SELECT * FROM alarm_rules WHERE id = ?', (id,)).fetchone()

    if not rule:
        conn.close()
        return jsonify({"code": 404, "msg": "规则不存在", "data": None}), 404

    if is_enabled is None:
        is_enabled = rule['is_enabled']

    try:
        conn.execute('''
            UPDATE alarm_rules
            SET rule_name = ?, is_enabled = ?, threshold_min = ?, threshold_max = ?, description = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (rule_name, is_enabled, threshold_min, threshold_max, description, id))
        conn.commit()

        log_action(
            user_id=session.get('user_id'),
            user_name=session.get('name'),
            action='update',
            module='alarm_rules',
            description=f'修改报警规则: {rule_name}',
            ip_address=request.remote_addr
        )
    except Exception as e:
        conn.close()
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}", "data": None}), 500

    conn.close()
    return jsonify({"code": 200, "msg": "规则更新成功", "data": None})


# ========== 3. 切换规则启用/停用 ==========
@alarm_rules_bp.route('/<int:id>/toggle', methods=['PUT'])
@admin_required
def toggle_rule_status(id):
    data = request.get_json()
    is_enabled = data.get('is_enabled', 0)

    conn = get_db_connection()
    rule = conn.execute('SELECT * FROM alarm_rules WHERE id = ?', (id,)).fetchone()

    if not rule:
        conn.close()
        return jsonify({"code": 404, "msg": "规则不存在", "data": None}), 404

    conn.execute('UPDATE alarm_rules SET is_enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                 (is_enabled, id))
    conn.commit()
    conn.close()

    log_action(
        user_id=session.get('user_id'),
        user_name=session.get('name'),
        action='update',
        module='alarm_rules',
        description=f'{"启用" if is_enabled else "停用"}报警规则: {rule["rule_name"]}',
        ip_address=request.remote_addr
    )

    status_text = '已启用' if is_enabled else '已停用'
    return jsonify({"code": 200, "msg": f"规则{status_text}", "data": None})
