from flask import Blueprint, request, jsonify, send_file
import io
import os
import json
from .decorators import admin_required, login_required
from .database import get_db, format_db_error, db_operation
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import log_action

# 创建一个新蓝图，专门管老人信息接口
elders_bp = Blueprint('elders', __name__, url_prefix='/api/v1/elders')


# 接口1：获取老人列表 (GET /api/v1/elders)
@elders_bp.route('', methods=['GET'])
@login_required
@db_operation
def get_elders():
    # 获取查询参数
    name = request.args.get('name', '').strip()
    room_number = request.args.get('room_number', '').strip()
    status = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    # 参数验证
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    with get_db() as conn:
        # 构建查询条件
        conditions = []
        params = []

        if name:
            conditions.append("name LIKE ?")
            params.append(f"%{name}%")

        if room_number:
            conditions.append("room_number LIKE ?")
            params.append(f"%{room_number}%")

        if status:
            conditions.append("status = ?")
            params.append(status)

        # 构建SQL查询
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        count_sql = f"SELECT COUNT(*) FROM elders WHERE {where_clause}"
        total_count = conn.execute(count_sql, params).fetchone()[0]

        # 计算分页
        offset = (page - 1) * page_size
        query_sql = f"SELECT * FROM elders WHERE {where_clause} ORDER BY id DESC LIMIT ? OFFSET ?"
        params_with_limit = params + [page_size, offset]

        # 执行查询
        elders = conn.execute(query_sql, params_with_limit).fetchall()

    # 将数据库的行对象转换成字典列表发给前端
    elders_list = [dict(row) for row in elders]

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": {
            "list": elders_list,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_count,
                "total_pages": (total_count + page_size - 1) // page_size
            }
        }
    })


# 接口2：新增录入老人 (POST /api/v1/elders)
@elders_bp.route('', methods=['POST'])
@admin_required
@db_operation
def add_elder():
    data = request.get_json()

    try:
        with get_db() as conn:
            cursor = conn.cursor()

            # 验证必填字段
            required_fields = ['name', 'gender', 'age', 'room_number', 'bed_number',
                            'emergency_contact_name', 'emergency_contact_phone']
            for field in required_fields:
                if not data.get(field):
                    return jsonify({"code": 400, "msg": f"{field}字段不能为空", "data": None}), 400

            # 验证手机号格式（11位数字，以1开头）
            phone = data.get('emergency_contact_phone')
            if not (phone.isdigit() and len(phone) == 11 and phone.startswith('1')):
                return jsonify({"code": 400, "msg": "紧急联系人电话必须是11位数字且以1开头", "data": None}), 400

            # 验证年龄范围
            age = data.get('age')
            if age is not None and (age < 0 or age > 150):
                return jsonify({"code": 400, "msg": "年龄必须在0-150之间", "data": None}), 400

            # 执行插入语句，把前端传来的数据塞进数据库
            cursor.execute('''
                INSERT INTO elders (name, gender, age, room_number, bed_number,
                                emergency_contact_name, emergency_contact_phone, emergency_contact, medical_history)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data.get('name'), data.get('gender'), data.get('age'),
                data.get('room_number'), data.get('bed_number'),
                data.get('emergency_contact_name'), data.get('emergency_contact_phone'),
                '', data.get('medical_history', '')
            ))
            new_id = cursor.lastrowid

        log_action(
            user_id=session.get('user_id'),
            user_name=session.get('name'),
            action='create',
            module='elders',
            description=f'新增老人: {data.get("name")}, 房间: {data.get("room_number")}',
            ip_address=request.remote_addr,
            new_data=json.dumps({'name': data.get('name'), 'room_number': data.get('room_number')}, ensure_ascii=False)
        )

        return jsonify({"code": 200, "msg": "添加成功", "data": {"id": new_id}})
    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500


# 接口3：获取单个老人详情 (GET /api/v1/elders/<id>)
@elders_bp.route('/<int:id>', methods=['GET'])
@login_required
@db_operation
def get_elder(id):
    with get_db() as conn:
        elder = conn.execute('SELECT * FROM elders WHERE id = ?', (id,)).fetchone()

    if not elder:
        return jsonify({"code": 404, "msg": "老人信息不存在", "data": None}), 404

    return jsonify({
        "code": 200,
        "msg": "获取成功",
        "data": dict(elder)
    })


# 接口4：更新老人信息 (PUT /api/v1/elders/<id>)
@elders_bp.route('/<int:id>', methods=['PUT'])
@admin_required
@db_operation
def update_elder(id):
    data = request.get_json()

    with get_db() as conn:
        elder = conn.execute('SELECT * FROM elders WHERE id = ?', (id,)).fetchone()
        if not elder:
            return jsonify({"code": 404, "msg": "老人信息不存在", "data": None}), 404

        old_data = {'name': elder['name'], 'age': elder['age'], 'room_number': elder['room_number'],
                    'bed_number': elder['bed_number'], 'status': elder['status']}

        update_fields = []
        update_values = []

        if 'emergency_contact_phone' in data:
            phone = data['emergency_contact_phone']
            if not (phone.isdigit() and len(phone) == 11 and phone.startswith('1')):
                return jsonify({"code": 400, "msg": "紧急联系人电话必须是11位数字且以1开头", "data": None}), 400

        if 'age' in data and data['age'] is not None:
            if data['age'] < 0 or data['age'] > 150:
                return jsonify({"code": 400, "msg": "年龄必须在0-150之间", "data": None}), 400

        fields = ['name', 'gender', 'age', 'room_number', 'bed_number',
                'emergency_contact_name', 'emergency_contact_phone',
                'medical_history', 'status']
        for field in fields:
            if field in data:
                update_fields.append(f"{field} = ?")
                update_values.append(data[field])

        if 'emergency_contact_name' in data or 'emergency_contact_phone' in data:
            update_fields.append('emergency_contact = ?')
            update_values.append('')

        if not update_fields:
            return jsonify({"code": 400, "msg": "没有提供更新数据", "data": None}), 400

        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        update_values.append(id)
        update_sql = f"UPDATE elders SET {', '.join(update_fields)} WHERE id = ?"
        conn.execute(update_sql, update_values)

    log_action(
        user_id=session.get('user_id'),
        user_name=session.get('name'),
        action='update',
        module='elders',
        description=f'修改老人信息: {old_data["name"]}',
        ip_address=request.remote_addr,
        old_data=json.dumps(old_data, ensure_ascii=False),
        new_data=json.dumps(data, ensure_ascii=False)
    )

    return jsonify({"code": 200, "msg": "更新成功", "data": None})


# 接口5：删除老人信息 (DELETE /api/v1/elders/<id>)
@elders_bp.route('/<int:id>', methods=['DELETE'])
@admin_required
@db_operation
def delete_elder(id):
    with get_db() as conn:
        elder = conn.execute('SELECT * FROM elders WHERE id = ?', (id,)).fetchone()
        if not elder:
            return jsonify({"code": 404, "msg": "老人信息不存在", "data": None}), 404

        elder_name = elder['name']
        conn.execute('DELETE FROM elders WHERE id = ?', (id,))

    log_action(
        user_id=session.get('user_id'),
        user_name=session.get('name'),
        action='delete',
        module='elders',
        description=f'删除老人: {elder_name}',
        ip_address=request.remote_addr,
        is_sensitive=1
    )

    return jsonify({"code": 200, "msg": "删除成功", "data": None})


# 接口6：导出老人信息Excel (GET /api/v1/elders/export)
@elders_bp.route('/export', methods=['GET'])
@admin_required
@db_operation
def export_elders():
    try:
        with get_db() as conn:
            # 获取所有老人数据
            elders = conn.execute('SELECT * FROM elders ORDER BY id').fetchall()

        # 转换为字典列表
        elders_list = [dict(row) for row in elders]

        # 导出Excel
        try:
            from utils.excel_export import export_elders_to_excel, generate_filename
            excel_file = export_elders_to_excel(elders_list)
            filename = generate_filename()

            return send_file(
                excel_file,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=filename
            )
        except ImportError:
            return jsonify({
                "code": 500,
                "msg": "导出功能依赖pandas库，请安装：pip install pandas openpyxl",
                "data": None
            }), 500
        except Exception as e:
            return jsonify({
                "code": 500,
                "msg": f"导出失败: {str(e)}",
                "data": None
            }), 500
    except Exception as e:
        user_msg = format_db_error(e)
        return jsonify({"code": 500, "msg": user_msg, "data": None}), 500
