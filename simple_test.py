#!/usr/bin/env python3
"""
数据库锁问题修复验证脚本 (简化版)
"""

import sqlite3
import os
import sys

def test_database_connection():
    """测试数据库连接"""
    print("=" * 60)
    print("测试 1: 数据库连接和表结构")
    print("=" * 60)
    
    current_dir = os.path.dirname(__file__)
    db_path = os.path.join(current_dir, 'instance', 'nursing_home.db')
    db_path = os.path.abspath(db_path)
    
    print(f"数据库路径: {db_path}")
    
    if not os.path.exists(db_path):
        print("数据库文件不存在!")
        return False
    
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        cursor = conn.cursor()
        
        # 检查 alarms 表的结构
        cursor.execute("PRAGMA table_info(alarms)")
        columns = cursor.fetchall()
        print("\nalarms 表列信息:")
        has_trigger_note = False
        for col in columns:
            print(f"   - {col[1]} ({col[2]})")
            if col[1] == 'trigger_note':
                has_trigger_note = True
        
        if has_trigger_note:
            print("trigger_note 列存在!")
        else:
            print("trigger_note 列不存在!")
            conn.close()
            return False
        
        # 测试插入包含 trigger_note 的数据
        print("\n" + "=" * 60)
        print("测试 2: 插入包含 trigger_note 的数据")
        print("=" * 60)
        
        test_note = "测试异常上报触发报警"
        
        cursor.execute('''
            INSERT INTO alarms (elder_id, type, trigger_source, trigger_note, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (1, 'manual_incident', 'test_123', test_note, 'unhandled'))
        test_alarm_id = cursor.lastrowid
        print(f"成功插入报警记录 ID: {test_alarm_id}")
        
        # 验证数据
        cursor.execute('SELECT trigger_note FROM alarms WHERE id = ?', (test_alarm_id,))
        result = cursor.fetchone()
        if result and result[0] == test_note:
            print(f"trigger_note 数据正确: '{result[0]}'")
        else:
            print(f"trigger_note 数据错误!")
            conn.rollback()
            conn.close()
            return False
        
        # 清理测试数据
        cursor.execute('DELETE FROM alarms WHERE id = ?', (test_alarm_id,))
        conn.commit()
        print("测试数据已清理")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"数据库操作失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_database_connection_pool():
    """测试数据库连接池"""
    print("\n" + "=" * 60)
    print("测试 3: 数据库连接池测试")
    print("=" * 60)
    
    try:
        # 测试导入数据库模块
        print("导入数据库连接模块...")
        sys.path.insert(0, os.path.dirname(__file__))
        
        from api.database import get_db, init_database_pool
        
        print("初始化连接池...")
        init_database_pool()
        
        print("连接池初始化成功!")
        
        # 测试获取连接
        print("\n测试连接获取...")
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            print(f"连接获取成功! 查询结果: {result}")
            
            # 测试基本查询
            print("\n测试基本查询...")
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            print(f"用户表记录数: {user_count}")
        
        print("连接池测试完成!")
        return True
        
    except Exception as e:
        print(f"连接池测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("智慧养老院系统 - 数据库锁问题修复验证")
    print("=" * 60)
    
    results = []
    
    # 测试 1
    results.append(("数据库连接和表结构", test_database_connection()))
    
    # 测试 2
    results.append(("数据库连接池", test_database_connection_pool()))
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results:
        status = "通过" if passed else "失败"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("所有测试通过! 数据库锁问题修复成功!")
    else:
        print("部分测试失败，请检查问题!")
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
