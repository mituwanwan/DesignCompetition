"""
消息通知系统API
提供消息通知的获取、标记已读等功能
"""

import sqlite3
import os
from flask import Blueprint, request, jsonify, session
from .decorators import login_required

# 创建蓝图
notifications_bp = Blueprint('notifications', __name__, url_prefix='/api/v1/notifications')


def get_db_connection():
    """获取数据库连接"""
    # 使用绝对路径避免中文字符路径问题
    current_dir = os.path.dirname(__file__)
    db_path = os.path.join(current_dir, '..', 'instance', 'nursing_home.db')
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# 接口1：获取未读消息数
@notifications_bp.route('/unread-count', methods=['GET'])
@login_required
def get_unread_count():
    """获取当前用户的未读消息数量"""
    user_id = session['user_id']

    conn = get_db_connection()
    count = conn.execute(
        'SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0',
        (user_id,)
    ).fetchone()[0]
    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "count": count
        }
    })


# 接口1b：获取留言未读数量（用于侧边栏红点）
@notifications_bp.route('/message-unread-count', methods=['GET'])
@login_required
def get_message_unread_count():
    """获取当前用户的未读留言数量，按角色区分查询范围"""
    user_id = session['user_id']
    role = session.get('role')

    conn = get_db_connection()

    if role == 'admin':
        count = conn.execute(
            'SELECT COUNT(*) FROM messages WHERE is_read = 0'
        ).fetchone()[0]
    elif role == 'family':
        count = conn.execute(
            '''
            SELECT COUNT(*) FROM messages m
            JOIN family_elder_bindings feb ON m.elder_id = feb.elder_id
            WHERE feb.family_user_id = ? AND m.sender_role = 'caregiver' AND m.is_read = 0
            ''',
            (user_id,)
        ).fetchone()[0]
    elif role == 'caregiver':
        count = conn.execute(
            '''
            SELECT COUNT(*) FROM messages m
            WHERE m.elder_id IN (
                SELECT DISTINCT elder_id FROM care_tasks WHERE caregiver_id = ?
            ) AND m.sender_role = 'family' AND m.is_read = 0
            ''',
            (user_id,)
        ).fetchone()[0]
    else:
        count = 0

    conn.close()

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {"count": count}
    })


# 接口2：获取消息列表
@notifications_bp.route('', methods=['GET'])
@login_required
def get_notifications():
    """获取当前用户的消息列表"""
    user_id = session['user_id']
    limit = request.args.get('limit', 10, type=int)
    offset = request.args.get('offset', 0, type=int)
    unread_only = request.args.get('unread_only', 'false') == 'true'

    # 参数验证
    if limit < 1 or limit > 100:
        limit = 10
    if offset < 0:
        offset = 0

    conn = get_db_connection()

    # 构建查询条件
    conditions = ["user_id = ?"]
    params = [user_id]

    if unread_only:
        conditions.append("is_read = 0")

    where_clause = " AND ".join(conditions)

    # 获取消息列表
    notifications = conn.execute(
        f'''
        SELECT * FROM notifications
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        ''',
        params + [limit, offset]
    ).fetchall()

    # 获取总数（用于分页）
    total = conn.execute(
        f'SELECT COUNT(*) FROM notifications WHERE {where_clause}',
        params
    ).fetchone()[0]

    conn.close()

    # 转换为字典列表
    notifications_list = [dict(row) for row in notifications]

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "list": notifications_list,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    })


# 接口3：标记消息已读
@notifications_bp.route('/<int:notification_id>/read', methods=['PUT'])
@login_required
def mark_as_read(notification_id):
    """标记指定消息为已读"""
    user_id = session['user_id']

    conn = get_db_connection()

    # 验证消息是否存在且属于当前用户
    notification = conn.execute(
        'SELECT * FROM notifications WHERE id = ? AND user_id = ?',
        (notification_id, user_id)
    ).fetchone()

    if not notification:
        conn.close()
        return jsonify({
            "code": 404,
            "msg": "消息不存在或无权访问",
            "data": None
        }), 404

    # 标记为已读
    conn.execute(
        'UPDATE notifications SET is_read = 1 WHERE id = ?',
        (notification_id,)
    )
    conn.commit()
    conn.close()

    return jsonify({
        "code": 200,
        "msg": "标记已读成功",
        "data": None
    })


# 接口4：批量标记已读
@notifications_bp.route('/mark-all-read', methods=['PUT'])
@login_required
def mark_all_as_read():
    """标记当前用户的所有消息为已读"""
    user_id = session['user_id']

    conn = get_db_connection()

    # 更新所有未读消息
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0',
        (user_id,)
    )
    updated_count = cursor.rowcount

    conn.commit()
    conn.close()

    return jsonify({
        "code": 200,
        "msg": f"已标记{updated_count}条消息为已读",
        "data": {
            "updated_count": updated_count
        }
    })


# 工具函数：创建通知（供其他模块调用）
def create_notification(user_id, type, title, content, related_id=None):
    """
    创建一条新的系统通知

    Args:
        user_id: 用户ID
        type: 通知类型 ('alarm', 'task', 'message')
        title: 通知标题
        content: 通知内容
        related_id: 关联ID（报警/任务/消息ID）

    Returns:
        int: 新创建的通知ID，失败返回None
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO notifications (user_id, type, title, content, related_id, is_read)
            VALUES (?, ?, ?, ?, ?, 0)
        ''', (user_id, type, title, content, related_id))

        notification_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return notification_id
    except Exception as e:
        print(f"创建通知失败: {e}")
        return None