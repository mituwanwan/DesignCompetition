"""
Excel导出工具模块
提供将数据导出为Excel文件的功能
"""

import pandas as pd
import io


def export_elders_to_excel(elders_data):
    """
    将老人数据导出为Excel文件

    Args:
        elders_data: 老人数据列表，每个元素为字典格式

    Returns:
        io.BytesIO: 包含Excel文件的字节流
    """
    if not elders_data:
        # 如果没有数据，创建空的DataFrame
        df = pd.DataFrame(columns=['ID', '姓名', '性别', '年龄', '房间号', '床位号',
                                  '紧急联系人姓名', '紧急联系人电话', '病史', '状态', '创建时间'])
    else:
        # 将数据转换为DataFrame
        df = pd.DataFrame(elders_data)

        # 重命名列
        column_mapping = {
            'id': 'ID',
            'name': '姓名',
            'gender': '性别',
            'age': '年龄',
            'room_number': '房间号',
            'bed_number': '床位号',
            'emergency_contact_name': '紧急联系人姓名',
            'emergency_contact_phone': '紧急联系人电话',
            'medical_history': '病史',
            'status': '状态',
            'created_at': '创建时间'
        }

        # 只保留存在的列
        existing_columns = {k: v for k, v in column_mapping.items() if k in df.columns}
        df = df.rename(columns=existing_columns)

        # 转换性别
        if '性别' in df.columns:
            df['性别'] = df['性别'].map({'male': '男', 'female': '女'})

        # 转换状态
        if '状态' in df.columns:
            df['状态'] = df['状态'].map({'active': '在院', 'discharged': '已出院'})

        # 按ID排序
        if 'ID' in df.columns:
            df = df.sort_values('ID')

    # 创建Excel文件
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='老人信息')

    output.seek(0)
    return output


def generate_filename(prefix="老人信息"):
    """
    生成导出文件名

    Args:
        prefix: 文件名前缀

    Returns:
        str: 文件名
    """
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}.xlsx"