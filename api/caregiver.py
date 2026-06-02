
"""
护工管理API模块
提供护工相关的数据接口
"""

import sqlite3
import json
import os
from datetime import datetime, date
from flask import Blueprint, request, jsonify, session
from .decorators import login_required, caregiver_required

caregiver_bp = Blueprint('caregiver', __name__, url_prefix='/api/v1/caregiver')


def get_db_connection():
    """获取数据库连接"""
    current_dir = os.path.dirname(__file__)
    db_path = os.path.join(current_dir, '..', 'instance', 'nursing_home.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@caregiver_bp.route('/assigned-elders', methods=['GET'])
@caregiver_required
def get_assigned_elders():
    """获取当前护工负责的老人列表"""
    caregiver_id = session['user_id']
    today = date.today().isoformat()
    
    conn = get_db_connection()
    
    try:
        # 从护工老人分配表获取
        elders = conn.execute('''
            SELECT 
                e.id,
                e.name,
                e.gender,
                e.age,
                e.room_number,
                e.bed_number,
                e.medical_history,
                e.status
            FROM elders e
            INNER JOIN caregiver_elder_assignments cea ON e.id = cea.elder_id
            WHERE cea.caregiver_id = ? 
              AND e.status = 'active'
            ORDER BY e.room_number, e.bed_number
        ''', (caregiver_id,)).fetchall()
        
        elders_list = []
        for elder in elders:
            elder_dict = dict(elder)
            
            # 获取今日护理任务
            today_tasks = conn.execute('''
                SELECT ct.content
                FROM care_tasks ct
                WHERE ct.elder_id = ? 
                  AND ct.caregiver_id = ?
                  AND date(ct.due_time) = ?
                  AND ct.status = 'pending'
                LIMIT 3
            ''', (elder_dict['id'], caregiver_id, today)).fetchall()
            
            care_items = [task['content'] for task in today_tasks]
            elder_dict['today_care_items'] = '、'.join(care_items) if care_items else None
            
            # 获取今日是否已有记录
            today_record = conn.execute('''
                SELECT id FROM care_records
                WHERE elder_id = ? 
                  AND caregiver_id = ?
                  AND record_date = ?
                LIMIT 1
            ''', (elder_dict['id'], caregiver_id, today)).fetchone()
            
            elder_dict['has_today_record'] = today_record is not None
            
            elders_list.append(elder_dict)
        
        conn.close()
        
        return jsonify({
            'code': 200,
            'msg': '获取成功',
            'data': elders_list
        })
        
    except Exception as e:
        conn.close()
        return jsonify({
            'code': 500,
            'msg': f'获取失败: {str(e)}',
            'data': None
        }), 500


@caregiver_bp.route('/assigned-elders-with-messages', methods=['GET'])
@caregiver_required
def get_assigned_elders_with_messages():
    caregiver_id = session['user_id']

    conn = get_db_connection()

    try:
        elders = conn.execute('''
            SELECT 
                e.id,
                e.name,
                e.room_number
            FROM elders e
            INNER JOIN caregiver_elder_assignments cea ON e.id = cea.elder_id
            WHERE cea.caregiver_id = ? 
              AND e.status = 'active'
            ORDER BY e.room_number
        ''', (caregiver_id,)).fetchall()

        elders_list = []
        for elder in elders:
            elder_dict = dict(elder)

            unread = conn.execute('''
                SELECT COUNT(*) as count
                FROM messages
                WHERE elder_id = ? 
                  AND sender_role = 'family'
                  AND is_read = 0
            ''', (elder_dict['id'],)).fetchone()
            elder_dict['unread_count'] = unread['count'] or 0

            last_msg = conn.execute('''
                SELECT m.content, m.created_at, m.sender_role, m.sender_id, u.name as sender_name
                FROM messages m
                INNER JOIN users u ON m.sender_id = u.id
                WHERE m.elder_id = ?
                ORDER BY m.created_at DESC
                LIMIT 1
            ''', (elder_dict['id'],)).fetchone()

            if last_msg:
                elder_dict['last_message'] = last_msg['content']
                elder_dict['last_message_time'] = last_msg['created_at']
                elder_dict['last_message_sender_role'] = last_msg['sender_role']
                elder_dict['last_message_sender_name'] = last_msg['sender_name']
            else:
                elder_dict['last_message'] = None
                elder_dict['last_message_time'] = None
                elder_dict['last_message_sender_role'] = None
                elder_dict['last_message_sender_name'] = None

            family_members = conn.execute('''
                SELECT u.id, u.name
                FROM users u
                INNER JOIN family_elder_bindings feb ON u.id = feb.family_user_id
                WHERE feb.elder_id = ?
            ''', (elder_dict['id'],)).fetchall()
            elder_dict['family_members'] = [dict(fm) for fm in family_members]

            elders_list.append(elder_dict)

        conn.close()

        return jsonify({
            'code': 200,
            'msg': '获取成功',
            'data': elders_list
        })

    except Exception as e:
        conn.close()
        return jsonify({
            'code': 500,
            'msg': f'获取失败: {str(e)}',
            'data': None
        }), 500


@caregiver_bp.route('/messages/by-elder/<int:elder_id>', methods=['GET'])
@caregiver_required
def get_messages_by_elder(elder_id):
    """获取指定老人的所有消息"""
    caregiver_id = session['user_id']
    
    conn = get_db_connection()
    
    try:
        # 检查护工是否有权限
        permission = conn.execute('''
            SELECT 1 FROM caregiver_elder_assignments
            WHERE caregiver_id = ? AND elder_id = ?
        ''', (caregiver_id, elder_id)).fetchone()
        
        if not permission:
            conn.close()
            return jsonify({'code': 403, 'msg': '无权查看该老人的消息', 'data': None}), 403
        
        # 获取消息列表
        messages = conn.execute('''
            SELECT 
                m.*,
                e.name as elder_name,
                u.name as sender_name
            FROM messages m
            INNER JOIN elders e ON m.elder_id = e.id
            INNER JOIN users u ON m.sender_id = u.id
            WHERE m.elder_id = ?
            ORDER BY m.created_at ASC
        ''', (elder_id,)).fetchall()
        
        messages_list = []
        for msg in messages:
            msg_dict = dict(msg)
            messages_list.append(msg_dict)
        
        # 标记该老人的家属消息为已读
        conn.execute('''
            UPDATE messages 
            SET is_read = 1 
            WHERE elder_id = ? 
              AND sender_role = 'family'
              AND is_read = 0
        ''', (elder_id,))
        conn.commit()
        
        conn.close()
        
        return jsonify({
            'code': 200,
            'msg': '获取成功',
            'data': messages_list
        })
        
    except Exception as e:
        conn.close()
        return jsonify({
            'code': 500,
            'msg': f'获取失败: {str(e)}',
            'data': None
        }), 500


@caregiver_bp.route('/messages/send', methods=['POST'])
@caregiver_required
def send_message():
    caregiver_id = session['user_id']
    data = request.get_json()

    elder_id = data.get('elder_id')
    content = data.get('content', '').strip()

    if not elder_id:
        return jsonify({'code': 400, 'msg': '请选择老人', 'data': None}), 400
    if not content:
        return jsonify({'code': 400, 'msg': '请输入消息内容', 'data': None}), 400

    conn = get_db_connection()

    try:
        permission = conn.execute('''
            SELECT 1 FROM caregiver_elder_assignments
            WHERE caregiver_id = ? AND elder_id = ?
        ''', (caregiver_id, elder_id)).fetchone()

        if not permission:
            conn.close()
            return jsonify({'code': 403, 'msg': '无权操作', 'data': None}), 403

        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO messages (elder_id, sender_id, sender_role, content, is_read)
            VALUES (?, ?, 'caregiver', ?, 0)
        ''', (elder_id, caregiver_id, content))
        new_id = cursor.lastrowid
        conn.commit()

        new_msg = conn.execute('''
            SELECT m.*, u.name as sender_name
            FROM messages m
            INNER JOIN users u ON m.sender_id = u.id
            WHERE m.id = ?
        ''', (new_id,)).fetchone()

        try:
            from .notifications import create_notification
            family_members = conn.execute('''
                SELECT family_user_id FROM family_elder_bindings WHERE elder_id = ?
            ''', (elder_id,)).fetchall()
            elder_name = conn.execute('SELECT name FROM elders WHERE id = ?', (elder_id,)).fetchone()
            for fm in family_members:
                create_notification(
                    fm['family_user_id'], 'message',
                    '新留言通知',
                    f'护工回复了关于老人 {elder_name["name"] if elder_name else ""} 的留言',
                    new_id
                )
        except Exception:
            pass

        conn.close()

        return jsonify({
            'code': 200,
            'msg': '发送成功',
            'data': dict(new_msg) if new_msg else {'id': new_id}
        })

    except Exception as e:
        conn.close()
        return jsonify({
            'code': 500,
            'msg': f'发送失败: {str(e)}',
            'data': None
        }), 500


@caregiver_bp.route('/messages/unread-count', methods=['GET'])
@caregiver_required
def get_unread_count():
    """获取总未读消息数"""
    caregiver_id = session['user_id']
    
    conn = get_db_connection()
    
    try:
        unread = conn.execute('''
            SELECT COUNT(DISTINCT m.id) as count
            FROM messages m
            INNER JOIN caregiver_elder_assignments cea ON m.elder_id = cea.elder_id
            WHERE cea.caregiver_id = ? 
              AND m.sender_role = 'family'
              AND m.is_read = 0
        ''', (caregiver_id,)).fetchone()
        
        count = unread['count'] or 0
        
        conn.close()
        
        return jsonify({
            'code': 200,
            'msg': '获取成功',
            'data': {'total_unread': count}
        })
        
    except Exception as e:
        conn.close()
        return jsonify({
            'code': 500,
            'msg': f'获取失败: {str(e)}',
            'data': None
        }), 500


@caregiver_bp.route('/my-tasks', methods=['GET'])
@caregiver_required
def get_my_tasks():
    """获取当前护工的任务列表"""
    caregiver_id = session['user_id']
    
    status = request.args.get('status', 'pending')
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    
    conn = get_db_connection()
    
    try:
        # 构建查询条件
        where_conditions = ['ct.caregiver_id = ?']
        params = [caregiver_id]
        
        if status:
            where_conditions.append('ct.status = ?')
            params.append(status)
        
        where_clause = ' AND '.join(where_conditions)
        
        # 查询总数
        count_sql = f'''
            SELECT COUNT(*) as total
            FROM care_tasks ct
            WHERE {where_clause}
        '''
        total_result = conn.execute(count_sql, params).fetchone()
        total = total_result['total'] if total_result else 0
        
        # 查询数据
        offset = (page - 1) * page_size
        query_sql = f'''
            SELECT 
                ct.*,
                e.name as elder_name,
                e.room_number
            FROM care_tasks ct
            INNER JOIN elders e ON ct.elder_id = e.id
            WHERE {where_clause}
            ORDER BY ct.due_time DESC
            LIMIT ? OFFSET ?
        '''
        params_with_limit = params + [page_size, offset]
        tasks = conn.execute(query_sql, params_with_limit).fetchall()
        
        tasks_list = [dict(task) for task in tasks]
        
        conn.close()
        
        return jsonify({
            'code': 200,
            'msg': '获取成功',
            'data': {
                'list': tasks_list,
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total': total,
                    'total_pages': (total + page_size - 1) // page_size if total > 0 else 0
                }
            }
        })
        
    except Exception as e:
        conn.close()
        return jsonify({
            'code': 500,
            'msg': f'获取失败: {str(e)}',
            'data': None
        }), 500


@caregiver_bp.route('/dashboard-summary', methods=['GET'])
@caregiver_required
def get_dashboard_summary():
    """获取护工工作台摘要数据"""
    caregiver_id = session['user_id']
    today = date.today().isoformat()
    
    conn = get_db_connection()
    
    try:
        # 今日任务统计
        today_tasks = conn.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
            FROM care_tasks
            WHERE caregiver_id = ? 
              AND date(due_time) = ?
        ''', (caregiver_id, today)).fetchone()
        
        # 今日记录统计
        today_records = conn.execute('''
            SELECT COUNT(*) as count
            FROM care_records
            WHERE caregiver_id = ? 
              AND record_date = ?
        ''', (caregiver_id, today)).fetchone()
        
        # 负责老人数量
        assigned_elders = conn.execute('''
            SELECT COUNT(DISTINCT elder_id) as count
            FROM caregiver_elder_assignments
            WHERE caregiver_id = ?
        ''', (caregiver_id,)).fetchone()
        
        # 未处理报警（只显示该护工负责老人的报警）
        unhandled_alarms = conn.execute('''
            SELECT COUNT(DISTINCT a.id) as count
            FROM alarms a
            INNER JOIN caregiver_elder_assignments cea ON a.elder_id = cea.elder_id
            WHERE cea.caregiver_id = ? 
              AND a.status = 'unhandled'
        ''', (caregiver_id,)).fetchone()
        
        conn.close()
        
        return jsonify({
            'code': 200,
            'msg': '获取成功',
            'data': {
                'today_tasks_total': today_tasks['total'] or 0,
                'today_tasks_completed': today_tasks['completed'] or 0,
                'today_records_count': today_records['count'] or 0,
                'assigned_elders_count': assigned_elders['count'] or 0,
                'unhandled_alarms_count': unhandled_alarms['count'] or 0
            }
        })
        
    except Exception as e:
        conn.close()
        return jsonify({
            'code': 500,
            'msg': f'获取失败: {str(e)}',
            'data': None
        }), 500

