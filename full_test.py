#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
智慧养老院管理系统 - 全面功能完整性测试脚本
测试范围：认证模块、管理员端、家属端、护工端、通知系统、数据链接稳定性、边界条件
"""

import requests
import json
import time
import sqlite3
import os
import sys
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============ 配置 ============
BASE_URL = "http://127.0.0.1:5000"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'nursing_home.db')

# 测试账号
TEST_ACCOUNTS = {
    'admin': {'username': 'admin', 'password': 'Admin@123'},
    'family1': {'username': 'family1', 'password': 'Family@123'},
    'caregiver1': {'username': 'caregiver1', 'password': 'Caregiver@123'},
}

# ============ 测试结果收集 ============
test_results = []
test_summary = {
    'total': 0,
    'passed': 0,
    'failed': 0,
    'start_time': None,
    'end_time': None,
}


def add_result(module, test_name, method, url, status_code, expected_status, passed, response_data, error_msg="", duration_ms=0):
    """记录测试结果"""
    result = {
        'module': module,
        'test_name': test_name,
        'method': method,
        'url': url,
        'status_code': status_code,
        'expected_status': expected_status,
        'passed': passed,
        'response_data': response_data,
        'error_msg': error_msg,
        'duration_ms': duration_ms,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    test_results.append(result)
    test_summary['total'] += 1
    if passed:
        test_summary['passed'] += 1
    else:
        test_summary['failed'] += 1

    status_icon = "PASS" if passed else "FAIL"
    print(f"  [{status_icon}] {test_name} | HTTP {status_code} (expected {expected_status}) | {duration_ms:.0f}ms")
    if not passed and error_msg:
        print(f"         Error: {error_msg}")


def make_request(session, method, url, expected_status=None, json_data=None, description=""):
    """发送HTTP请求并返回结果"""
    start = time.time()
    try:
        if method == 'GET':
            resp = session.get(f"{BASE_URL}{url}", timeout=10)
        elif method == 'POST':
            resp = session.post(f"{BASE_URL}{url}", json=json_data, timeout=10)
        elif method == 'PUT':
            resp = session.put(f"{BASE_URL}{url}", json=json_data, timeout=10)
        elif method == 'DELETE':
            resp = session.delete(f"{BASE_URL}{url}", timeout=10)
        else:
            resp = session.request(method, f"{BASE_URL}{url}", json=json_data, timeout=10)
        duration = (time.time() - start) * 1000

        try:
            resp_data = resp.json()
        except:
            resp_data = {'raw_text': resp.text[:500]}

        return resp.status_code, resp_data, duration
    except requests.exceptions.ConnectionError as e:
        duration = (time.time() - start) * 1000
        return 0, {'error': str(e)}, duration
    except Exception as e:
        duration = (time.time() - start) * 1000
        return -1, {'error': str(e)}, duration


def query_db(sql, params=()):
    """查询数据库获取测试数据"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"  [DB ERROR] {e}")
        return []


# ============ 预查询数据库获取有效ID ============
def get_test_ids():
    """从数据库获取有效的资源ID用于测试"""
    ids = {}

    # 获取老人ID
    elders = query_db("SELECT id, name FROM elders WHERE status='active' LIMIT 5")
    if elders:
        ids['elder_id'] = elders[0]['id']
        ids['elder_name'] = elders[0]['name']
        ids['elder_ids'] = [e['id'] for e in elders]

    # 获取用户ID
    users = query_db("SELECT id, username, role FROM users WHERE status='enabled' LIMIT 10")
    for u in users:
        if u['role'] == 'admin':
            ids['admin_user_id'] = u['id']
        elif u['role'] == 'family':
            if 'family_user_id' not in ids:
                ids['family_user_id'] = u['id']
        elif u['role'] == 'caregiver':
            if 'caregiver_user_id' not in ids:
                ids['caregiver_user_id'] = u['id']

    # 获取报警ID
    alarms = query_db("SELECT id FROM alarms LIMIT 5")
    if alarms:
        ids['alarm_id'] = alarms[0]['id']
        ids['alarm_ids'] = [a['id'] for a in alarms]

    # 获取预约ID
    appointments = query_db("SELECT id, status, family_user_id, elder_id FROM appointments LIMIT 10")
    if appointments:
        ids['appointment_id'] = appointments[0]['id']
        ids['pending_appointment_id'] = None
        ids['approved_appointment_id'] = None
        for apt in appointments:
            if apt['status'] == 'pending' and ids.get('pending_appointment_id') is None:
                ids['pending_appointment_id'] = apt['id']
            if apt['status'] == 'approved' and ids.get('approved_appointment_id') is None:
                ids['approved_appointment_id'] = apt['id']

    # 获取消息ID
    messages = query_db("SELECT id FROM messages LIMIT 5")
    if messages:
        ids['message_id'] = messages[0]['id']

    # 获取通知ID
    notifications = query_db("SELECT id FROM notifications LIMIT 5")
    if notifications:
        ids['notification_id'] = notifications[0]['id']

    # 获取家属绑定老人
    bindings = query_db("SELECT family_user_id, elder_id FROM family_elder_bindings LIMIT 5")
    if bindings:
        ids['family_bindings'] = bindings

    # 获取护工分配老人
    assignments = query_db("SELECT caregiver_id, elder_id FROM caregiver_elder_assignments LIMIT 5")
    if assignments:
        ids['caregiver_assignments'] = assignments

    # 获取未绑定老人（用于权限测试）
    if ids.get('family_user_id') and ids.get('elder_ids'):
        bound_elders = [b['elder_id'] for b in bindings if b['family_user_id'] == ids.get('family_user_id')]
        unbound = [eid for eid in ids['elder_ids'] if eid not in bound_elders]
        if unbound:
            ids['unbound_elder_id'] = unbound[0]
        else:
            ids['unbound_elder_id'] = 99999

    print(f"\n[数据库预查询] 获取到的测试ID:")
    for k, v in ids.items():
        if k not in ['family_bindings', 'caregiver_assignments', 'elder_ids', 'alarm_ids']:
            print(f"  {k}: {v}")

    return ids


# ============ 测试模块 ============

def test_server_health():
    """测试1: 服务器健康检查"""
    print("\n" + "=" * 70)
    print("模块1: 服务器健康检查")
    print("=" * 70)

    session = requests.Session()
    status, data, duration = make_request(session, 'GET', '/login')
    passed = status == 200
    add_result("服务器健康", "服务器可访问性检查", "GET", "/login",
               status, 200, passed, data, "" if passed else "服务器无法访问", duration)

    # 测试根路径重定向
    status, data, duration = make_request(session, 'GET', '/')
    passed = status in [200, 302, 308]
    add_result("服务器健康", "根路径重定向", "GET", "/",
               status, "200/302/308", passed, data, "" if passed else "根路径重定向异常", duration)


def test_auth_module():
    """测试2: 认证模块"""
    print("\n" + "=" * 70)
    print("模块2: 认证模块测试")
    print("=" * 70)

    # 2.1 管理员登录
    session = requests.Session()
    status, data, duration = make_request(session, 'POST', '/api/v1/auth/login',
                                          json_data=TEST_ACCOUNTS['admin'])
    passed = status == 200 and data.get('code') == 200
    add_result("认证模块", "管理员登录 (admin/Admin@123)", "POST", "/api/v1/auth/login",
               status, 200, passed, data,
               "" if passed else f"登录失败: {data.get('msg', '未知错误')}", duration)
    admin_session = session if passed else None

    # 2.2 家属登录
    session = requests.Session()
    status, data, duration = make_request(session, 'POST', '/api/v1/auth/login',
                                          json_data=TEST_ACCOUNTS['family1'])
    passed = status == 200 and data.get('code') == 200
    add_result("认证模块", "家属登录 (family1/Family@123)", "POST", "/api/v1/auth/login",
               status, 200, passed, data,
               "" if passed else f"登录失败: {data.get('msg', '未知错误')}", duration)
    family_session = session if passed else None

    # 2.3 护工登录
    session = requests.Session()
    status, data, duration = make_request(session, 'POST', '/api/v1/auth/login',
                                          json_data=TEST_ACCOUNTS['caregiver1'])
    passed = status == 200 and data.get('code') == 200
    add_result("认证模块", "护工登录 (caregiver1/Caregiver@123)", "POST", "/api/v1/auth/login",
               status, 200, passed, data,
               "" if passed else f"登录失败: {data.get('msg', '未知错误')}", duration)
    caregiver_session = session if passed else None

    # 2.4 未登录访问受保护API
    anon_session = requests.Session()
    status, data, duration = make_request(anon_session, 'GET', '/api/v1/users')
    passed = status == 401
    add_result("认证模块", "未登录访问受保护API (GET /api/v1/users)", "GET", "/api/v1/users",
               status, 401, passed, data,
               "" if passed else "未登录应返回401", duration)

    # 2.5 未登录访问受保护页面
    status, data, duration = make_request(anon_session, 'GET', '/admin')
    passed = status in [302, 308, 401] or (status == 200 and 'login' in str(data).lower())
    add_result("认证模块", "未登录访问管理员页面 (/admin)", "GET", "/admin",
               status, "302/401", passed, data,
               "" if passed else "未登录应被重定向或拒绝", duration)

    # 2.6 错误密码登录
    session = requests.Session()
    status, data, duration = make_request(session, 'POST', '/api/v1/auth/login',
                                          json_data={'username': 'admin', 'password': 'WrongPassword1'})
    passed = status == 400 and data.get('code') == 400
    add_result("认证模块", "错误密码登录", "POST", "/api/v1/auth/login",
               status, 400, passed, data,
               "" if passed else "错误密码应返回400", duration)

    # 2.7 空用户名登录
    status, data, duration = make_request(session, 'POST', '/api/v1/auth/login',
                                          json_data={'username': '', 'password': 'Test@123'})
    passed = status == 400
    add_result("认证模块", "空用户名登录", "POST", "/api/v1/auth/login",
               status, 400, passed, data,
               "" if passed else "空用户名应返回400", duration)

    # 2.8 空密码登录
    status, data, duration = make_request(session, 'POST', '/api/v1/auth/login',
                                          json_data={'username': 'admin', 'password': ''})
    passed = status == 400
    add_result("认证模块", "空密码登录", "POST", "/api/v1/auth/login",
               status, 400, passed, data,
               "" if passed else "空密码应返回400", duration)

    # 2.9 不存在的用户登录
    status, data, duration = make_request(session, 'POST', '/api/v1/auth/login',
                                          json_data={'username': 'nonexistent_user', 'password': 'Test@12345'})
    passed = status == 400
    add_result("认证模块", "不存在用户登录", "POST", "/api/v1/auth/login",
               status, 400, passed, data,
               "" if passed else "不存在用户应返回400", duration)

    # 2.10 登出
    if admin_session:
        status, data, duration = make_request(admin_session, 'POST', '/api/v1/auth/logout')
        passed = status == 200 and data.get('code') == 200
        add_result("认证模块", "管理员登出", "POST", "/api/v1/auth/logout",
                   status, 200, passed, data,
                   "" if passed else "登出失败", duration)

    return admin_session, family_session, caregiver_session


def test_admin_module(admin_session, test_ids):
    """测试3: 管理员端功能"""
    print("\n" + "=" * 70)
    print("模块3: 管理员端功能测试")
    print("=" * 70)

    if not admin_session:
        print("  [SKIP] 管理员登录失败，跳过管理员端测试")
        return

    # 3.1 用户管理
    status, data, duration = make_request(admin_session, 'GET', '/api/v1/users')
    passed = status == 200 and data.get('code') == 200
    add_result("管理员端", "获取用户列表 GET /api/v1/users", "GET", "/api/v1/users",
               status, 200, passed, data,
               "" if passed else f"获取用户列表失败: {data.get('msg', '')}", duration)

    # 3.2 用户管理 - 带筛选
    status, data, duration = make_request(admin_session, 'GET', '/api/v1/users?role=admin&page=1&page_size=10')
    passed = status == 200 and data.get('code') == 200
    add_result("管理员端", "获取用户列表(带筛选) GET /api/v1/users?role=admin", "GET", "/api/v1/users?role=admin",
               status, 200, passed, data,
               "" if passed else f"筛选用户失败: {data.get('msg', '')}", duration)

    # 3.3 老人信息
    status, data, duration = make_request(admin_session, 'GET', '/api/v1/elders')
    passed = status == 200 and data.get('code') == 200
    add_result("管理员端", "获取老人列表 GET /api/v1/elders", "GET", "/api/v1/elders",
               status, 200, passed, data,
               "" if passed else f"获取老人列表失败: {data.get('msg', '')}", duration)

    # 3.4 报警列表
    status, data, duration = make_request(admin_session, 'GET', '/api/v1/alarms')
    passed = status == 200 and data.get('code') == 200
    add_result("管理员端", "获取报警列表 GET /api/v1/alarms", "GET", "/api/v1/alarms",
               status, 200, passed, data,
               "" if passed else f"获取报警列表失败: {data.get('msg', '')}", duration)

    # 3.5 探视预约
    status, data, duration = make_request(admin_session, 'GET', '/api/v1/visits')
    passed = status == 200 and data.get('code') == 200
    add_result("管理员端", "获取探视预约 GET /api/v1/visits", "GET", "/api/v1/visits",
               status, 200, passed, data,
               "" if passed else f"获取探视预约失败: {data.get('msg', '')}", duration)

    # 3.6 消息管理
    status, data, duration = make_request(admin_session, 'GET', '/api/v1/admin/messages')
    passed = status == 200 and data.get('code') == 200
    add_result("管理员端", "获取消息列表 GET /api/v1/admin/messages", "GET", "/api/v1/admin/messages",
               status, 200, passed, data,
               "" if passed else f"获取消息列表失败: {data.get('msg', '')}", duration)

    # 3.7 通知列表
    status, data, duration = make_request(admin_session, 'GET', '/api/v1/notifications')
    passed = status == 200 and data.get('code') == 200
    add_result("管理员端", "获取通知列表 GET /api/v1/notifications", "GET", "/api/v1/notifications",
               status, 200, passed, data,
               "" if passed else f"获取通知列表失败: {data.get('msg', '')}", duration)

    # 3.8 批准预约
    pending_id = test_ids.get('pending_appointment_id')
    if pending_id:
        status, data, duration = make_request(admin_session, 'PUT',
                                              f'/api/v1/visits/{pending_id}/approve')
        # 可能返回400（非pending状态）或200
        passed = status in [200, 400]
        add_result("管理员端", f"批准预约 PUT /api/v1/visits/{pending_id}/approve",
                   "PUT", f"/api/v1/visits/{pending_id}/approve",
                   status, "200/400", passed, data,
                   "" if passed else f"批准预约异常: {data.get('msg', '')}", duration)
    else:
        # 创建一个预约再批准
        elder_id = test_ids.get('elder_id')
        if elder_id:
            future_date = (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%dT10:00:00')
            # 先用家属创建预约
            family_session = requests.Session()
            make_request(family_session, 'POST', '/api/v1/auth/login', json_data=TEST_ACCOUNTS['family1'])
            create_status, create_data, _ = make_request(family_session, 'POST', '/api/v1/visits',
                                                          json_data={'elder_id': elder_id, 'type': 'in_person',
                                                                     'appointment_date': future_date, 'notes': '测试预约'})
            if create_status == 200 and create_data.get('code') == 200:
                new_apt_id = create_data.get('data', {}).get('id')
                if new_apt_id:
                    status, data, duration = make_request(admin_session, 'PUT',
                                                          f'/api/v1/visits/{new_apt_id}/approve')
                    passed = status == 200 and data.get('code') == 200
                    add_result("管理员端", f"批准新建预约 PUT /api/v1/visits/{new_apt_id}/approve",
                               "PUT", f"/api/v1/visits/{new_apt_id}/approve",
                               status, 200, passed, data,
                               "" if passed else f"批准预约失败: {data.get('msg', '')}", duration)
                    test_ids['approved_appointment_id'] = new_apt_id
            else:
                add_result("管理员端", "批准预约(创建测试预约)", "POST", "/api/v1/visits",
                           create_status, 200, False, create_data,
                           f"无法创建测试预约: {create_data.get('msg', '')}", 0)

    # 3.9 拒绝预约 - 先创建一个pending预约用于拒绝
    elder_id = test_ids.get('elder_id')
    if elder_id:
        future_date = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%dT14:00:00')
        family_session = requests.Session()
        make_request(family_session, 'POST', '/api/v1/auth/login', json_data=TEST_ACCOUNTS['family1'])
        create_status, create_data, _ = make_request(family_session, 'POST', '/api/v1/visits',
                                                      json_data={'elder_id': elder_id, 'type': 'video',
                                                                 'appointment_date': future_date, 'notes': '测试拒绝预约'})
        if create_status == 200 and create_data.get('code') == 200:
            reject_id = create_data.get('data', {}).get('id')
            if reject_id:
                status, data, duration = make_request(admin_session, 'PUT',
                                                      f'/api/v1/visits/{reject_id}/reject',
                                                      json_data={'reason': '测试拒绝原因'})
                passed = status == 200 and data.get('code') == 200
                add_result("管理员端", f"拒绝预约 PUT /api/v1/visits/{reject_id}/reject",
                           "PUT", f"/api/v1/visits/{reject_id}/reject",
                           status, 200, passed, data,
                           "" if passed else f"拒绝预约失败: {data.get('msg', '')}", duration)

    # 3.10 页面渲染测试
    pages = [
        ('/admin', '管理员首页'),
        ('/admin/users', '用户管理页'),
        ('/admin/elders', '老人信息页'),
        ('/admin/alarms', '报警管理页'),
        ('/admin/visits', '探视预约页'),
        ('/admin/messages', '消息管理页'),
    ]
    for path, name in pages:
        status, data, duration = make_request(admin_session, 'GET', path)
        passed = status == 200
        add_result("管理员端-页面", f"页面渲染: {name} ({path})", "GET", path,
                   status, 200, passed, data,
                   "" if passed else f"页面渲染失败", duration)


def test_family_module(family_session, test_ids):
    """测试4: 家属端功能"""
    print("\n" + "=" * 70)
    print("模块4: 家属端功能测试")
    print("=" * 70)

    if not family_session:
        print("  [SKIP] 家属登录失败，跳过家属端测试")
        return

    elder_id = test_ids.get('elder_id')
    unbound_elder_id = test_ids.get('unbound_elder_id', 99999)

    # 4.1 绑定老人列表
    status, data, duration = make_request(family_session, 'GET', '/api/v1/family/elders')
    passed = status == 200 and data.get('code') == 200
    add_result("家属端", "获取绑定老人列表 GET /api/v1/family/elders", "GET", "/api/v1/family/elders",
               status, 200, passed, data,
               "" if passed else f"获取绑定老人失败: {data.get('msg', '')}", duration)

    # 4.2 含消息的老人列表
    status, data, duration = make_request(family_session, 'GET', '/api/v1/family/elders-with-messages')
    passed = status == 200 and data.get('code') == 200
    add_result("家属端", "获取含消息老人列表 GET /api/v1/family/elders-with-messages",
               "GET", "/api/v1/family/elders-with-messages",
               status, 200, passed, data,
               "" if passed else f"获取含消息老人列表失败: {data.get('msg', '')}", duration)

    # 4.3 老人护工信息
    if elder_id:
        status, data, duration = make_request(family_session, 'GET',
                                              f'/api/v1/family/elders/{elder_id}/caregivers')
        passed = status in [200, 403]  # 403也可能（未绑定）
        add_result("家属端", f"获取老人护工信息 GET /api/v1/family/elders/{elder_id}/caregivers",
                   "GET", f"/api/v1/family/elders/{elder_id}/caregivers",
                   status, "200/403", passed, data,
                   "" if passed else f"获取护工信息失败: {data.get('msg', '')}", duration)

    # 4.4 留言列表
    if elder_id:
        status, data, duration = make_request(family_session, 'GET',
                                              f'/api/v1/family/elders/{elder_id}/messages')
        passed = status in [200, 403]
        add_result("家属端", f"获取留言列表 GET /api/v1/family/elders/{elder_id}/messages",
                   "GET", f"/api/v1/family/elders/{elder_id}/messages",
                   status, "200/403", passed, data,
                   "" if passed else f"获取留言列表失败: {data.get('msg', '')}", duration)

    # 4.5 发送留言
    if elder_id:
        status, data, duration = make_request(family_session, 'POST', '/api/v1/family/messages',
                                              json_data={'elder_id': elder_id, 'content': '自动化测试留言 - 请忽略'})
        passed = status in [200, 403]
        add_result("家属端", "发送留言 POST /api/v1/family/messages",
                   "POST", "/api/v1/family/messages",
                   status, "200/403", passed, data,
                   "" if passed else f"发送留言失败: {data.get('msg', '')}", duration)

    # 4.6 报警列表
    status, data, duration = make_request(family_session, 'GET', '/api/v1/family/alarms')
    passed = status == 200 and data.get('code') == 200
    add_result("家属端", "获取报警列表 GET /api/v1/family/alarms", "GET", "/api/v1/family/alarms",
               status, 200, passed, data,
               "" if passed else f"获取报警列表失败: {data.get('msg', '')}", duration)

    # 4.7 报警详情
    alarm_id = test_ids.get('alarm_id')
    if alarm_id:
        status, data, duration = make_request(family_session, 'GET',
                                              f'/api/v1/family/alarms/{alarm_id}')
        passed = status in [200, 403, 404]
        add_result("家属端", f"获取报警详情 GET /api/v1/family/alarms/{alarm_id}",
                   "GET", f"/api/v1/family/alarms/{alarm_id}",
                   status, "200/403/404", passed, data,
                   "" if passed else f"获取报警详情失败: {data.get('msg', '')}", duration)

    # 4.8 未处理报警数
    status, data, duration = make_request(family_session, 'GET', '/api/v1/family/alarms/unhandled-count')
    passed = status == 200 and data.get('code') == 200
    add_result("家属端", "获取未处理报警数 GET /api/v1/family/alarms/unhandled-count",
               "GET", "/api/v1/family/alarms/unhandled-count",
               status, 200, passed, data,
               "" if passed else f"获取未处理报警数失败: {data.get('msg', '')}", duration)

    # 4.9 创建预约
    if elder_id:
        future_date = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%dT09:00:00')
        status, data, duration = make_request(family_session, 'POST', '/api/v1/visits',
                                              json_data={'elder_id': elder_id, 'type': 'video',
                                                         'appointment_date': future_date, 'notes': '自动化测试预约'})
        passed = status in [200, 400]  # 400可能是时间冲突
        add_result("家属端", "创建预约 POST /api/v1/visits",
                   "POST", "/api/v1/visits",
                   status, "200/400", passed, data,
                   "" if passed else f"创建预约失败: {data.get('msg', '')}", duration)

        # 保存创建的预约ID用于取消测试
        if status == 200 and data.get('code') == 200:
            test_ids['new_visit_id'] = data.get('data', {}).get('id')

    # 4.10 取消预约
    new_visit_id = test_ids.get('new_visit_id')
    if new_visit_id:
        status, data, duration = make_request(family_session, 'PUT',
                                              f'/api/v1/visits/{new_visit_id}/cancel')
        passed = status in [200, 400, 404]
        add_result("家属端", f"取消预约 PUT /api/v1/visits/{new_visit_id}/cancel",
                   "PUT", f"/api/v1/visits/{new_visit_id}/cancel",
                   status, "200/400/404", passed, data,
                   "" if passed else f"取消预约失败: {data.get('msg', '')}", duration)

    # 4.11 视频token验证
    status, data, duration = make_request(family_session, 'GET', '/api/v1/visits/video-token/invalid_token_test')
    passed = status in [400, 404]
    add_result("家属端", "视频token验证(无效token) GET /api/v1/visits/video-token/invalid_token_test",
               "GET", "/api/v1/visits/video-token/invalid_token_test",
               status, "400/404", passed, data,
               "" if passed else "无效token应返回400或404", duration)

    # 4.12 权限控制测试 - 访问未绑定老人的数据
    if unbound_elder_id:
        status, data, duration = make_request(family_session, 'GET',
                                              f'/api/v1/family/elders/{unbound_elder_id}/caregivers')
        passed = status == 403
        add_result("家属端-权限", f"访问未绑定老人护工信息(elder_id={unbound_elder_id})",
                   "GET", f"/api/v1/family/elders/{unbound_elder_id}/caregivers",
                   status, 403, passed, data,
                   "" if passed else "访问未绑定老人应返回403", duration)

        status, data, duration = make_request(family_session, 'GET',
                                              f'/api/v1/family/elders/{unbound_elder_id}/messages')
        passed = status == 403
        add_result("家属端-权限", f"访问未绑定老人留言(elder_id={unbound_elder_id})",
                   "GET", f"/api/v1/family/elders/{unbound_elder_id}/messages",
                   status, 403, passed, data,
                   "" if passed else "访问未绑定老人留言应返回403", duration)

    # 4.13 家属访问管理员接口（越权测试）
    status, data, duration = make_request(family_session, 'GET', '/api/v1/users')
    passed = status == 403
    add_result("家属端-权限", "家属访问管理员接口 GET /api/v1/users (应403)",
               "GET", "/api/v1/users",
               status, 403, passed, data,
               "" if passed else "家属不应访问管理员接口", duration)

    # 4.14 页面渲染测试
    pages = [
        ('/family', '家属首页'),
        ('/family/health', '健康数据页'),
        ('/family/messages', '留言页'),
        ('/family/alarms', '报警页'),
        ('/family/video-visit', '视频探视页'),
        ('/family/appointment', '预约页'),
    ]
    for path, name in pages:
        status, data, duration = make_request(family_session, 'GET', path)
        passed = status == 200
        add_result("家属端-页面", f"页面渲染: {name} ({path})", "GET", path,
                   status, 200, passed, data,
                   "" if passed else f"页面渲染失败", duration)

    # 4.15 视频房间页面
    status, data, duration = make_request(family_session, 'GET', '/family/video-room/test')
    passed = status == 200
    add_result("家属端-页面", "视频房间页面 /family/video-room/test", "GET", "/family/video-room/test",
               status, 200, passed, data,
               "" if passed else f"视频房间页面渲染失败", duration)


def test_caregiver_module(caregiver_session, test_ids):
    """测试5: 护工端功能"""
    print("\n" + "=" * 70)
    print("模块5: 护工端功能测试")
    print("=" * 70)

    if not caregiver_session:
        print("  [SKIP] 护工登录失败，跳过护工端测试")
        return

    # 5.1 负责老人列表
    status, data, duration = make_request(caregiver_session, 'GET', '/api/v1/caregiver/assigned-elders')
    passed = status == 200 and data.get('code') == 200
    add_result("护工端", "获取负责老人列表 GET /api/v1/caregiver/assigned-elders",
               "GET", "/api/v1/caregiver/assigned-elders",
               status, 200, passed, data,
               "" if passed else f"获取负责老人失败: {data.get('msg', '')}", duration)

    # 5.2 含消息的老人列表
    status, data, duration = make_request(caregiver_session, 'GET', '/api/v1/caregiver/assigned-elders-with-messages')
    passed = status == 200 and data.get('code') == 200
    add_result("护工端", "获取含消息老人列表 GET /api/v1/caregiver/assigned-elders-with-messages",
               "GET", "/api/v1/caregiver/assigned-elders-with-messages",
               status, 200, passed, data,
               "" if passed else f"获取含消息老人列表失败: {data.get('msg', '')}", duration)

    # 5.3 消息列表
    elder_id = test_ids.get('elder_id')
    if elder_id:
        status, data, duration = make_request(caregiver_session, 'GET',
                                              f'/api/v1/caregiver/messages/by-elder/{elder_id}')
        passed = status in [200, 403]
        add_result("护工端", f"获取老人消息 GET /api/v1/caregiver/messages/by-elder/{elder_id}",
                   "GET", f"/api/v1/caregiver/messages/by-elder/{elder_id}",
                   status, "200/403", passed, data,
                   "" if passed else f"获取消息失败: {data.get('msg', '')}", duration)

    # 5.4 发送消息
    if elder_id:
        status, data, duration = make_request(caregiver_session, 'POST', '/api/v1/caregiver/messages/send',
                                              json_data={'elder_id': elder_id, 'content': '自动化测试护工消息 - 请忽略'})
        passed = status in [200, 403]
        add_result("护工端", "发送消息 POST /api/v1/caregiver/messages/send",
                   "POST", "/api/v1/caregiver/messages/send",
                   status, "200/403", passed, data,
                   "" if passed else f"发送消息失败: {data.get('msg', '')}", duration)

    # 5.5 护工未读消息数
    status, data, duration = make_request(caregiver_session, 'GET', '/api/v1/caregiver/messages/unread-count')
    passed = status == 200 and data.get('code') == 200
    add_result("护工端", "获取未读消息数 GET /api/v1/caregiver/messages/unread-count",
               "GET", "/api/v1/caregiver/messages/unread-count",
               status, 200, passed, data,
               "" if passed else f"获取未读消息数失败: {data.get('msg', '')}", duration)

    # 5.6 护工任务列表
    status, data, duration = make_request(caregiver_session, 'GET', '/api/v1/caregiver/my-tasks')
    passed = status == 200 and data.get('code') == 200
    add_result("护工端", "获取任务列表 GET /api/v1/caregiver/my-tasks",
               "GET", "/api/v1/caregiver/my-tasks",
               status, 200, passed, data,
               "" if passed else f"获取任务列表失败: {data.get('msg', '')}", duration)

    # 5.7 护工工作台摘要
    status, data, duration = make_request(caregiver_session, 'GET', '/api/v1/caregiver/dashboard-summary')
    passed = status == 200 and data.get('code') == 200
    add_result("护工端", "获取工作台摘要 GET /api/v1/caregiver/dashboard-summary",
               "GET", "/api/v1/caregiver/dashboard-summary",
               status, 200, passed, data,
               "" if passed else f"获取工作台摘要失败: {data.get('msg', '')}", duration)

    # 5.8 护工访问管理员接口（越权测试）
    status, data, duration = make_request(caregiver_session, 'GET', '/api/v1/users')
    passed = status == 403
    add_result("护工端-权限", "护工访问管理员接口 GET /api/v1/users (应403)",
               "GET", "/api/v1/users",
               status, 403, passed, data,
               "" if passed else "护工不应访问管理员接口", duration)

    # 5.9 页面渲染测试
    pages = [
        ('/caregiver', '护工首页'),
        ('/caregiver/tasks', '任务页'),
        ('/caregiver/health-records', '健康记录页'),
        ('/caregiver/messages', '消息页'),
    ]
    for path, name in pages:
        status, data, duration = make_request(caregiver_session, 'GET', path)
        passed = status == 200
        add_result("护工端-页面", f"页面渲染: {name} ({path})", "GET", path,
                   status, 200, passed, data,
                   "" if passed else f"页面渲染失败", duration)


def test_notification_system(admin_session, family_session, caregiver_session):
    """测试6: 通知系统"""
    print("\n" + "=" * 70)
    print("模块6: 通知系统测试")
    print("=" * 70)

    # 6.1 管理员未读通知数
    if admin_session:
        status, data, duration = make_request(admin_session, 'GET', '/api/v1/notifications/unread-count')
        passed = status == 200 and data.get('code') == 200
        add_result("通知系统", "管理员-获取未读通知数 GET /api/v1/notifications/unread-count",
                   "GET", "/api/v1/notifications/unread-count",
                   status, 200, passed, data,
                   "" if passed else f"获取未读通知数失败: {data.get('msg', '')}", duration)

    # 6.2 家属未读通知数
    if family_session:
        status, data, duration = make_request(family_session, 'GET', '/api/v1/notifications/unread-count')
        passed = status == 200 and data.get('code') == 200
        add_result("通知系统", "家属-获取未读通知数 GET /api/v1/notifications/unread-count",
                   "GET", "/api/v1/notifications/unread-count",
                   status, 200, passed, data,
                   "" if passed else f"获取未读通知数失败: {data.get('msg', '')}", duration)

    # 6.3 护工未读通知数
    if caregiver_session:
        status, data, duration = make_request(caregiver_session, 'GET', '/api/v1/notifications/unread-count')
        passed = status == 200 and data.get('code') == 200
        add_result("通知系统", "护工-获取未读通知数 GET /api/v1/notifications/unread-count",
                   "GET", "/api/v1/notifications/unread-count",
                   status, 200, passed, data,
                   "" if passed else f"获取未读通知数失败: {data.get('msg', '')}", duration)

    # 6.4 消息未读数
    for role_name, session_obj in [('管理员', admin_session), ('家属', family_session), ('护工', caregiver_session)]:
        if session_obj:
            status, data, duration = make_request(session_obj, 'GET', '/api/v1/notifications/message-unread-count')
            passed = status == 200 and data.get('code') == 200
            add_result("通知系统", f"{role_name}-获取消息未读数 GET /api/v1/notifications/message-unread-count",
                       "GET", "/api/v1/notifications/message-unread-count",
                       status, 200, passed, data,
                       "" if passed else f"获取消息未读数失败: {data.get('msg', '')}", duration)

    # 6.5 通知列表
    if admin_session:
        status, data, duration = make_request(admin_session, 'GET', '/api/v1/notifications?limit=5')
        passed = status == 200 and data.get('code') == 200
        add_result("通知系统", "获取通知列表 GET /api/v1/notifications?limit=5",
                   "GET", "/api/v1/notifications?limit=5",
                   status, 200, passed, data,
                   "" if passed else f"获取通知列表失败: {data.get('msg', '')}", duration)

    # 6.6 标记所有通知已读
    if admin_session:
        status, data, duration = make_request(admin_session, 'PUT', '/api/v1/notifications/mark-all-read')
        passed = status == 200 and data.get('code') == 200
        add_result("通知系统", "标记所有通知已读 PUT /api/v1/notifications/mark-all-read",
                   "PUT", "/api/v1/notifications/mark-all-read",
                   status, 200, passed, data,
                   "" if passed else f"标记已读失败: {data.get('msg', '')}", duration)


def test_connection_stability():
    """测试7: 数据链接稳定性"""
    print("\n" + "=" * 70)
    print("模块7: 数据链接稳定性测试")
    print("=" * 70)

    # 7.1 连续10次请求
    session = requests.Session()
    make_request(session, 'POST', '/api/v1/auth/login', json_data=TEST_ACCOUNTS['admin'])

    success_count = 0
    total_duration = 0
    for i in range(10):
        status, data, duration = make_request(session, 'GET', '/api/v1/elders')
        total_duration += duration
        if status == 200 and data.get('code') == 200:
            success_count += 1

    passed = success_count == 10
    avg_duration = total_duration / 10
    add_result("链接稳定性", f"连续10次请求测试 (成功{success_count}/10, 平均{avg_duration:.0f}ms)",
               "GET", "/api/v1/elders",
               200 if passed else 0, 200, passed,
               {'success_count': success_count, 'avg_duration_ms': avg_duration},
               "" if passed else f"连续请求失败{10-success_count}次", avg_duration)

    # 7.2 并发请求测试
    def concurrent_request(index):
        s = requests.Session()
        make_request(s, 'POST', '/api/v1/auth/login', json_data=TEST_ACCOUNTS['admin'])
        start = time.time()
        try:
            resp = s.get(f"{BASE_URL}/api/v1/elders", timeout=15)
            duration = (time.time() - start) * 1000
            return resp.status_code, duration
        except Exception as e:
            duration = (time.time() - start) * 1000
            return -1, duration

    concurrent_count = 5
    with ThreadPoolExecutor(max_workers=concurrent_count) as executor:
        futures = [executor.submit(concurrent_request, i) for i in range(concurrent_count)]
        results = [f.result() for f in as_completed(futures)]

    concurrent_success = sum(1 for status, _ in results if status == 200)
    concurrent_avg = sum(d for _, d in results) / len(results) if results else 0
    passed = concurrent_success >= 4  # 允许1个失败
    add_result("链接稳定性", f"并发{concurrent_count}请求测试 (成功{concurrent_success}/{concurrent_count}, 平均{concurrent_avg:.0f}ms)",
               "GET", "/api/v1/elders",
               200 if passed else 0, 200, passed,
               {'concurrent_success': concurrent_success, 'avg_duration_ms': concurrent_avg},
               "" if passed else f"并发请求失败{concurrent_count-concurrent_success}次", concurrent_avg)


def test_boundary_conditions(admin_session, family_session, caregiver_session, test_ids):
    """测试8: 边界条件和异常场景"""
    print("\n" + "=" * 70)
    print("模块8: 边界条件和异常场景测试")
    print("=" * 70)

    # 8.1 不存在的资源ID
    if admin_session:
        # 不存在的老人
        status, data, duration = make_request(admin_session, 'GET', '/api/v1/elders/99999')
        passed = status == 404
        add_result("边界条件", "获取不存在的老人 GET /api/v1/elders/99999",
                   "GET", "/api/v1/elders/99999",
                   status, 404, passed, data,
                   "" if passed else "不存在的资源应返回404", duration)

        # 不存在的报警
        status, data, duration = make_request(admin_session, 'GET', '/api/v1/alarms/99999')
        passed = status == 404
        add_result("边界条件", "获取不存在的报警 GET /api/v1/alarms/99999",
                   "GET", "/api/v1/alarms/99999",
                   status, 404, passed, data,
                   "" if passed else "不存在的资源应返回404", duration)

        # 不存在的预约
        status, data, duration = make_request(admin_session, 'PUT', '/api/v1/visits/99999/approve')
        passed = status == 404
        add_result("边界条件", "批准不存在的预约 PUT /api/v1/visits/99999/approve",
                   "PUT", "/api/v1/visits/99999/approve",
                   status, 404, passed, data,
                   "" if passed else "不存在的资源应返回404", duration)

    # 8.2 无效参数
    if admin_session:
        # 无效分页参数
        status, data, duration = make_request(admin_session, 'GET', '/api/v1/users?page=-1&page_size=0')
        passed = status == 200 and data.get('code') == 200
        add_result("边界条件", "无效分页参数 GET /api/v1/users?page=-1&page_size=0",
                   "GET", "/api/v1/users?page=-1&page_size=0",
                   status, 200, passed, data,
                   "" if passed else "无效分页参数应被自动修正", duration)

        # 无效角色筛选
        status, data, duration = make_request(admin_session, 'GET', '/api/v1/users?role=invalid_role')
        passed = status == 200 and data.get('code') == 200
        add_result("边界条件", "无效角色筛选 GET /api/v1/users?role=invalid_role",
                   "GET", "/api/v1/users?role=invalid_role",
                   status, 200, passed, data,
                   "" if passed else "无效筛选参数应被忽略", duration)

    # 8.3 空数据提交
    if family_session:
        # 发送空留言
        status, data, duration = make_request(family_session, 'POST', '/api/v1/family/messages',
                                              json_data={'elder_id': test_ids.get('elder_id', 1), 'content': ''})
        passed = status == 400
        add_result("边界条件", "发送空留言 POST /api/v1/family/messages (空内容)",
                   "POST", "/api/v1/family/messages",
                   status, 400, passed, data,
                   "" if passed else "空内容应返回400", duration)

        # 发送超长留言
        status, data, duration = make_request(family_session, 'POST', '/api/v1/family/messages',
                                              json_data={'elder_id': test_ids.get('elder_id', 1),
                                                         'content': 'A' * 501})
        passed = status == 400
        add_result("边界条件", "发送超长留言 POST /api/v1/family/messages (501字)",
                   "POST", "/api/v1/family/messages",
                   status, 400, passed, data,
                   "" if passed else "超长内容应返回400", duration)

        # 缺少elder_id创建预约
        status, data, duration = make_request(family_session, 'POST', '/api/v1/visits',
                                              json_data={'type': 'video', 'appointment_date': '2026-06-01T10:00:00'})
        passed = status == 400
        add_result("边界条件", "缺少elder_id创建预约 POST /api/v1/visits",
                   "POST", "/api/v1/visits",
                   status, 400, passed, data,
                   "" if passed else "缺少必填字段应返回400", duration)

        # 无效预约类型
        if test_ids.get('elder_id'):
            status, data, duration = make_request(family_session, 'POST', '/api/v1/visits',
                                                  json_data={'elder_id': test_ids['elder_id'], 'type': 'invalid',
                                                             'appointment_date': '2026-06-01T10:00:00'})
            passed = status == 400
            add_result("边界条件", "无效预约类型 POST /api/v1/visits (type=invalid)",
                       "POST", "/api/v1/visits",
                       status, 400, passed, data,
                       "" if passed else "无效预约类型应返回400", duration)

    # 8.4 越权访问测试
    # 家属尝试访问管理员页面
    if family_session:
        status, data, duration = make_request(family_session, 'GET', '/admin')
        passed = status in [302, 308, 403] or (status == 200 and 'login' in str(data).lower())
        add_result("边界条件-越权", "家属访问管理员页面 /admin (应被拒绝)",
                   "GET", "/admin",
                   status, "302/403", passed, data,
                   "" if passed else "家属不应访问管理员页面", duration)

    # 护工尝试访问家属页面
    if caregiver_session:
        status, data, duration = make_request(caregiver_session, 'GET', '/family')
        passed = status in [302, 308, 403] or (status == 200 and 'login' in str(data).lower())
        add_result("边界条件-越权", "护工访问家属页面 /family (应被拒绝)",
                   "GET", "/family",
                   status, "302/403", passed, data,
                   "" if passed else "护工不应访问家属页面", duration)

    # 管理员尝试访问护工API
    if admin_session:
        status, data, duration = make_request(admin_session, 'GET', '/api/v1/caregiver/assigned-elders')
        passed = status == 403
        add_result("边界条件-越权", "管理员访问护工API GET /api/v1/caregiver/assigned-elders (应403)",
                   "GET", "/api/v1/caregiver/assigned-elders",
                   status, 403, passed, data,
                   "" if passed else "管理员不应访问护工专属API", duration)

    # 8.5 过去的预约时间
    if family_session and test_ids.get('elder_id'):
        past_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%dT10:00:00')
        status, data, duration = make_request(family_session, 'POST', '/api/v1/visits',
                                              json_data={'elder_id': test_ids['elder_id'], 'type': 'video',
                                                         'appointment_date': past_date, 'notes': '过去时间预约'})
        passed = status == 400
        add_result("边界条件", "过去时间预约 POST /api/v1/visits",
                   "POST", "/api/v1/visits",
                   status, 400, passed, data,
                   "" if passed else "过去时间应返回400", duration)

    # 8.6 无效日期格式
    if family_session and test_ids.get('elder_id'):
        status, data, duration = make_request(family_session, 'POST', '/api/v1/visits',
                                              json_data={'elder_id': test_ids['elder_id'], 'type': 'video',
                                                         'appointment_date': 'invalid-date', 'notes': '无效日期'})
        passed = status == 400
        add_result("边界条件", "无效日期格式预约 POST /api/v1/visits",
                   "POST", "/api/v1/visits",
                   status, 400, passed, data,
                   "" if passed else "无效日期格式应返回400", duration)

    # 8.7 SQL注入测试
    if admin_session:
        status, data, duration = make_request(admin_session, 'GET', "/api/v1/elders?name=' OR 1=1--")
        passed = status == 200  # 不应该报错，但也不应该泄露数据
        add_result("边界条件-安全", "SQL注入测试 GET /api/v1/elders?name=' OR 1=1--",
                   "GET", "/api/v1/elders?name=' OR 1=1--",
                   status, 200, passed, data,
                   "" if passed else "SQL注入测试异常", duration)

    # 8.8 XSS测试
    if family_session and test_ids.get('elder_id'):
        xss_content = '<script>alert("xss")</script>'
        status, data, duration = make_request(family_session, 'POST', '/api/v1/family/messages',
                                              json_data={'elder_id': test_ids['elder_id'], 'content': xss_content})
        # 消息可能被接受但应该被转义，不应该导致服务器错误
        passed = status in [200, 400, 403]
        add_result("边界条件-安全", "XSS内容留言 POST /api/v1/family/messages",
                   "POST", "/api/v1/family/messages",
                   status, "200/400/403", passed, data,
                   "" if passed else "XSS内容不应导致服务器错误", duration)


# ============ 主测试流程 ============

def run_all_tests():
    """执行全部测试"""
    print("=" * 70)
    print("  智慧养老院管理系统 - 全面功能完整性测试")
    print(f"  测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  目标服务: {BASE_URL}")
    print("=" * 70)

    test_summary['start_time'] = datetime.now()

    # 预查询数据库获取测试ID
    test_ids = get_test_ids()

    # 模块1: 服务器健康检查
    test_server_health()

    # 模块2: 认证模块
    admin_session, family_session, caregiver_session = test_auth_module()

    # 重新登录确保session有效
    if admin_session:
        make_request(admin_session, 'POST', '/api/v1/auth/login', json_data=TEST_ACCOUNTS['admin'])
    if family_session:
        make_request(family_session, 'POST', '/api/v1/auth/login', json_data=TEST_ACCOUNTS['family1'])
    if caregiver_session:
        make_request(caregiver_session, 'POST', '/api/v1/auth/login', json_data=TEST_ACCOUNTS['caregiver1'])

    # 模块3: 管理员端
    test_admin_module(admin_session, test_ids)

    # 模块4: 家属端
    test_family_module(family_session, test_ids)

    # 模块5: 护工端
    test_caregiver_module(caregiver_session, test_ids)

    # 模块6: 通知系统
    test_notification_system(admin_session, family_session, caregiver_session)

    # 模块7: 链接稳定性
    test_connection_stability()

    # 模块8: 边界条件
    test_boundary_conditions(admin_session, family_session, caregiver_session, test_ids)

    test_summary['end_time'] = datetime.now()

    # 生成报告
    generate_report()


def generate_report():
    """生成测试报告"""
    print("\n\n")
    print("=" * 70)
    print("  测 试 报 告")
    print("=" * 70)

    duration = (test_summary['end_time'] - test_summary['start_time']).total_seconds()
    pass_rate = (test_summary['passed'] / test_summary['total'] * 100) if test_summary['total'] > 0 else 0

    print(f"\n  测试时间: {test_summary['start_time'].strftime('%Y-%m-%d %H:%M:%S')} - {test_summary['end_time'].strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  测试耗时: {duration:.1f}秒")
    print(f"  测试用例总数: {test_summary['total']}")
    print(f"  通过数: {test_summary['passed']}")
    print(f"  失败数: {test_summary['failed']}")
    print(f"  通过率: {pass_rate:.1f}%")

    # 按模块统计
    print("\n" + "-" * 70)
    print("  各模块测试统计:")
    print("-" * 70)

    modules = {}
    for r in test_results:
        mod = r['module']
        if mod not in modules:
            modules[mod] = {'total': 0, 'passed': 0, 'failed': 0}
        modules[mod]['total'] += 1
        if r['passed']:
            modules[mod]['passed'] += 1
        else:
            modules[mod]['failed'] += 1

    for mod, stats in modules.items():
        rate = (stats['passed'] / stats['total'] * 100) if stats['total'] > 0 else 0
        status = "OK" if stats['failed'] == 0 else "WARN"
        print(f"  [{status}] {mod:20s} | 通过: {stats['passed']:2d}/{stats['total']:2d} | 通过率: {rate:5.1f}%")

    # 失败用例详情
    failed_tests = [r for r in test_results if not r['passed']]
    if failed_tests:
        print("\n" + "-" * 70)
        print("  失败用例详情:")
        print("-" * 70)
        for i, r in enumerate(failed_tests, 1):
            print(f"\n  [{i}] {r['module']} - {r['test_name']}")
            print(f"      请求: {r['method']} {r['url']}")
            print(f"      期望状态码: {r['expected_status']}, 实际状态码: {r['status_code']}")
            print(f"      错误信息: {r['error_msg']}")
            resp_data = r.get('response_data', {})
            if isinstance(resp_data, dict):
                msg = resp_data.get('msg', '')
                code = resp_data.get('code', '')
                if msg:
                    print(f"      响应消息: code={code}, msg={msg}")

    # 数据链接状态评估
    print("\n" + "-" * 70)
    print("  数据链接状态评估:")
    print("-" * 70)

    stability_tests = [r for r in test_results if r['module'] == '链接稳定性']
    if stability_tests:
        for st in stability_tests:
            print(f"  - {st['test_name']}")
            if isinstance(st.get('response_data'), dict):
                for k, v in st['response_data'].items():
                    print(f"    {k}: {v}")

    # 响应时间统计
    durations = [r['duration_ms'] for r in test_results if r['duration_ms'] > 0]
    if durations:
        avg_duration = sum(durations) / len(durations)
        max_duration = max(durations)
        min_duration = min(durations)
        print(f"\n  响应时间统计:")
        print(f"    平均响应时间: {avg_duration:.0f}ms")
        print(f"    最大响应时间: {max_duration:.0f}ms")
        print(f"    最小响应时间: {min_duration:.0f}ms")

        slow_requests = [r for r in test_results if r['duration_ms'] > 2000]
        if slow_requests:
            print(f"\n  慢请求 (>2000ms):")
            for sr in slow_requests:
                print(f"    - {sr['method']} {sr['url']} | {sr['duration_ms']:.0f}ms | {sr['test_name']}")

    # 总体评估
    print("\n" + "=" * 70)
    print("  总体评估:")
    print("=" * 70)

    if pass_rate >= 95:
        grade = "优秀"
        recommendation = "系统功能完整性良好，可以上线运行"
    elif pass_rate >= 80:
        grade = "良好"
        recommendation = "系统基本功能完整，存在少量问题需要修复"
    elif pass_rate >= 60:
        grade = "一般"
        recommendation = "系统存在较多问题，建议修复后再上线"
    else:
        grade = "不合格"
        recommendation = "系统存在严重问题，不建议上线"

    print(f"  质量等级: {grade}")
    print(f"  通过率: {pass_rate:.1f}%")
    print(f"  建议: {recommendation}")

    # 保存报告到文件
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_report.json')
    report_data = {
        'summary': {
            'total': test_summary['total'],
            'passed': test_summary['passed'],
            'failed': test_summary['failed'],
            'pass_rate': pass_rate,
            'grade': grade,
            'recommendation': recommendation,
            'start_time': test_summary['start_time'].strftime('%Y-%m-%d %H:%M:%S'),
            'end_time': test_summary['end_time'].strftime('%Y-%m-%d %H:%M:%S'),
            'duration_seconds': duration,
        },
        'modules': {mod: stats for mod, stats in modules.items()},
        'failed_tests': [{
            'module': r['module'],
            'test_name': r['test_name'],
            'method': r['method'],
            'url': r['url'],
            'expected_status': r['expected_status'],
            'actual_status': r['status_code'],
            'error_msg': r['error_msg'],
            'response_msg': r.get('response_data', {}).get('msg', '') if isinstance(r.get('response_data'), dict) else '',
        } for r in failed_tests],
        'all_results': [{
            'module': r['module'],
            'test_name': r['test_name'],
            'method': r['method'],
            'url': r['url'],
            'status_code': r['status_code'],
            'passed': r['passed'],
            'duration_ms': round(r['duration_ms'], 1),
        } for r in test_results],
    }

    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    print(f"\n  详细报告已保存至: {report_path}")

    print("\n" + "=" * 70)
    print("  测试完成!")
    print("=" * 70)


if __name__ == '__main__':
    run_all_tests()
