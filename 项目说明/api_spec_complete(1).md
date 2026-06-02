补充版API接口文档
**文件名**：`api_spec_complete.md`  

### 基础信息
- **Base URL**: `http://localhost:5000/api/v1`
- **认证方式**: JWT Token（Header中添加：`Authorization: Bearer {token}`）
- **统一响应格式**:
```json
{
    "code": 200,
    "msg": "操作成功",
    "data": {}
}
```

---

### 一、认证与通用接口（负责人1）
#### 1. 用户登录（原有）
**接口**: `POST /auth/login`  
**请求参数**:
```json
{
    "username": "string, 必填, 用户名",
    "password": "string, 必填, 密码"
}
```
**响应**:
```json
{
    "code": 200,
    "msg": "登录成功",
    "data": {
        "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "user_info": {
            "id": 1,
            "username": "admin",
            "role": "admin",
            "name": "管理员"
        }
    }
}
```

#### 2. 退出登录（新增）
**接口**: `POST /auth/logout`  
**权限**: 所有已登录用户  
**响应**:
```json
{
    "code": 200,
    "msg": "退出成功",
    "data": null
}
```

#### 3. 修改密码（新增）
**接口**: `PUT /auth/change-password`  
**权限**: 所有已登录用户  
**请求参数**:
```json
{
    "old_password": "string, 必填, 原密码",
    "new_password": "string, 必填, 新密码(至少8位,含大小写字母和数字)"
}
```

#### 4. 获取未读消息数（新增）
**接口**: `GET /notifications/unread-count`  
**权限**: 所有已登录用户  
**响应**:
```json
{
    "code": 200,
    "msg": "获取成功",
    "data": {
        "count": 5
    }
}
```

#### 5. 消息标记已读（新增）
**接口**: `PUT /notifications/:id/read`  
**权限**: 所有已登录用户（仅能标记自己的消息）

---

### 二、老人信息接口（负责人1）
#### 6. 获取老人列表（原有）
**接口**: `GET /elders`  
**权限**: admin, caregiver  
**请求参数**:
- `name`: string, 可选, 姓名模糊查询
- `room_number`: string, 可选, 房间号模糊查询
- `status`: string, 可选, 状态(active/discharged)
- `page`: int, 可选, 页码，默认1
- `page_size`: int, 可选, 每页数量，默认20

#### 7. 获取单个老人详情（原有）
**接口**: `GET /elders/:id`  
**权限**: admin, caregiver, family（仅可查看绑定的老人）

#### 8. 创建老人信息（原有）
**接口**: `POST /elders`  
**权限**: admin  
**请求参数**:
```json
{
    "name": "string, 必填, 姓名",
    "gender": "string, 必填, 性别(male/female)",
    "age": "int, 必填, 年龄",
    "room_number": "string, 必填, 房间号",
    "bed_number": "string, 必填, 床位号",
    "emergency_contact": "string, 必填, 紧急联系人",
    "medical_history": "string, 可选, 基础病史"
}
```

#### 9. 更新老人信息（新增）
**接口**: `PUT /elders/:id`  
**权限**: admin  
**请求参数**: 同创建老人信息（所有字段可选，仅更新提供的字段）

#### 10. 删除老人信息（新增）
**接口**: `DELETE /elders/:id`  
**权限**: admin  
**说明**: 删除前需检查是否有关联数据（护理记录、报警等），有关联则拒绝删除

#### 11. 导出老人信息Excel（新增）
**接口**: `GET /elders/export`  
**权限**: admin  
**响应**: 直接返回Excel文件流

---

### 三、护理记录接口（负责人2）
#### 12. 提交护理记录（原有）
**接口**: `POST /care-records`  
**权限**: caregiver  
**请求参数**:
```json
{
    "elder_id": "int, 必填, 老人ID",
    "record_date": "string, 必填, 记录日期(YYYY-MM-DD)",
    "health_data": {
        "temperature": "float, 可选, 体温(35.0-42.0)",
        "systolic_pressure": "int, 可选, 收缩压(60-200)",
        "diastolic_pressure": "int, 可选, 舒张压(40-120)",
        "heart_rate": "int, 可选, 心率(40-200)",
        "blood_sugar": "float, 可选, 血糖(2.0-30.0)"
    },
    "diet": {
        "breakfast": "string, 可选, 早餐状态(normal/little/much/none)",
        "lunch": "string, 可选, 午餐状态",
        "dinner": "string, 可选, 晚餐状态",
        "water_intake": "int, 可选, 饮水量(ml)"
    },
    "sleep": {
        "duration": "float, 可选, 睡眠时长(0-24)",
        "quality": "string, 可选, 睡眠质量(good/average/poor)"
    },
    "emotion": {
        "status": "string, 可选, 情绪状态(happy/calm/low/agitated)",
        "note": "string, 可选, 文字备注"
    }
}
```

#### 13. 获取老人护理记录列表（新增）
**接口**: `GET /elders/:id/care-records`  
**权限**: admin, caregiver, family（仅可查看绑定的老人）  
**请求参数**:
- `start_date`: string, 可选, 开始日期(YYYY-MM-DD)
- `end_date`: string, 可选, 结束日期(YYYY-MM-DD)
- `page`: int, 可选, 页码

#### 14. 获取单条护理记录详情（新增）
**接口**: `GET /care-records/:id`  
**权限**: admin, caregiver, family（仅可查看绑定的老人）

---

### 四、异常情况上报接口（负责人2）
#### 15. 提交异常上报（新增）
**接口**: `POST /incident-reports`  
**权限**: caregiver  
**请求参数**:
```json
{
    "elder_id": "int, 必填, 老人ID",
    "type": "string, 必填, 异常类型(fall/discomfort/agitation/other)",
    "note": "string, 可选, 备注(其他类型必填)",
    "images": "array, 可选, 图片路径数组(最多3张)"
}
```
**说明**: 提交成功后自动触发报警

#### 16. 获取异常上报记录列表（新增）
**接口**: `GET /incident-reports`  
**权限**: admin, caregiver  
**请求参数**:
- `elder_id`: int, 可选, 老人ID
- `type`: string, 可选, 异常类型
- `page`: int, 可选, 页码

---

### 五、护理任务接口（负责人2）
#### 17. 管理员创建护理任务（新增）
**接口**: `POST /care-tasks`  
**权限**: admin  
**请求参数**:
```json
{
    "caregiver_id": "int, 必填, 护工ID",
    "elder_id": "int, 必填, 老人ID",
    "content": "string, 必填, 任务内容",
    "due_time": "string, 必填, 要求完成时间(ISO8601)"
}
```

#### 18. 获取任务列表（原有）
**接口**: `GET /care-tasks`  
**权限**: caregiver（仅自己的任务）, admin（所有任务）  
**请求参数**:
- `status`: string, 可选, 任务状态(pending/completed)
- `caregiver_id`: int, 可选, 护工ID（仅admin可用）
- `page`: int, 可选, 页码

#### 19. 获取任务详情（新增）
**接口**: `GET /care-tasks/:id`  
**权限**: admin, caregiver（仅自己的任务）

#### 20. 确认完成任务（原有）
**接口**: `PUT /care-tasks/:id/complete`  
**权限**: caregiver（仅自己的任务）

---

### 六、用户管理接口（负责人3）
#### 21. 获取用户列表（原有）
**接口**: `GET /users`  
**权限**: admin  
**请求参数**:
- `role`: string, 可选, 用户角色(admin/caregiver/family)
- `status`: string, 可选, 状态(enabled/disabled)
- `page`: int, 可选, 页码

#### 22. 创建用户（原有）
**接口**: `POST /users`  
**权限**: admin  
**请求参数**:
```json
{
    "username": "string, 必填, 用户名",
    "password": "string, 必填, 密码",
    "role": "string, 必填, 用户角色",
    "name": "string, 必填, 姓名",
    "phone": "string, 可选, 手机号",
    "email": "string, 可选, 邮箱"
}
```

#### 23. 更新用户信息（新增）
**接口**: `PUT /users/:id`  
**权限**: admin  
**请求参数**: 可修改name, phone, email, status（不可修改username和role）

#### 24. 重置用户密码（新增）
**接口**: `PUT /users/:id/reset-password`  
**权限**: admin  
**请求参数**:
```json
{
    "new_password": "string, 必填, 新密码"
}
```

#### 25. 绑定老人与子女（原有）
**接口**: `POST /users/:family_user_id/bind-elder`  
**权限**: admin  
**请求参数**:
```json
{
    "elder_id": "int, 必填, 老人ID"
}
```

#### 26. 解绑老人与子女（新增）
**接口**: `DELETE /users/:family_user_id/bind-elder/:elder_id`  
**权限**: admin

---

### 七、报警管理接口（负责人3）
#### 27. 获取报警列表（原有）
**接口**: `GET /alarms`  
**权限**: admin, caregiver  
**请求参数**:
- `status`: string, 可选, 报警状态(unhandled/processing/resolved)
- `elder_id`: int, 可选, 老人ID
- `start_time`: string, 可选, 开始时间
- `end_time`: string, 可选, 结束时间
- `page`: int, 可选, 页码

#### 28. 获取报警详情（新增）
**接口**: `GET /alarms/:id`  
**权限**: admin, caregiver, family（仅可查看绑定老人的报警）

#### 29. 创建手动报警（新增）
**接口**: `POST /alarms/manual`  
**权限**: admin, caregiver  
**请求参数**:
```json
{
    "elder_id": "int, 必填, 老人ID",
    "type": "string, 必填, 报警类型",
    "note": "string, 可选, 备注"
}
```

#### 30. 更新报警状态（原有）
**接口**: `PUT /alarms/:id/status`  
**权限**: admin, caregiver  
**请求参数**:
```json
{
    "status": "string, 必填, 新状态(processing/resolved)",
    "result": "string, 可选, 处理结果(resolved状态必填)"
}
```

---

### 八、统计接口（负责人3）
#### 31. 管理员首页统计数据（新增）
**接口**: `GET /stats/admin-dashboard`  
**权限**: admin  
**响应**:
```json
{
    "code": 200,
    "msg": "获取成功",
    "data": {
        "active_elders_count": 120,
        "unhandled_alarms_count": 5,
        "on_duty_caregivers_count": 15
    }
}
```

#### 32. 护工响应时长统计（新增）
**接口**: `GET /stats/caregiver-response-time`  
**权限**: admin  
**请求参数**:
- `year_month`: string, 可选, 年月(YYYY-MM)，默认当前月
- `caregiver_id`: int, 可选, 护工ID

#### 33. 全院健康统计（新增）
**接口**: `GET /stats/health-overview`  
**权限**: admin  
**响应**:
```json
{
    "code": 200,
    "msg": "获取成功",
    "data": {
        "disease_distribution": [
            {"name": "高血压", "count": 45},
            {"name": "糖尿病", "count": 20},
            {"name": "心脏病", "count": 15},
            {"name": "其他", "count": 40}
        ],
        "floor_health_distribution": [...]
    }
}
```

---

### 九、子女端接口（负责人4）
#### 34. 获取绑定老人列表（新增）
**接口**: `GET /family/elders`  
**权限**: family  
**响应**:
```json
{
    "code": 200,
    "msg": "获取成功",
    "data": [
        {
            "id": 1,
            "name": "李爷爷",
            "age": 82,
            "room_number": "301",
            "bed_number": "1",
            "latest_health_data": {...}
        }
    ]
}
```

#### 35. 获取绑定老人健康数据（原有）
**接口**: `GET /family/elders/:id/health`  
**权限**: family（仅可查看绑定的老人）

#### 36. 获取报警消息（原有）
**接口**: `GET /family/alarms`  
**权限**: family  
**请求参数**:
- `status`: string, 可选, 状态
- `page`: int, 可选, 页码

#### 37. 获取留言列表（新增）
**接口**: `GET /family/elders/:id/messages`  
**权限**: family（仅可查看绑定的老人）  
**请求参数**:
- `page`: int, 可选, 页码

#### 38. 发送留言（原有）
**接口**: `POST /family/messages`  
**权限**: family  
**请求参数**:
```json
{
    "elder_id": "int, 必填, 老人ID",
    "content": "string, 必填, 留言内容"
}
```

#### 39. 护工回复留言（新增）
**接口**: `POST /caregiver/messages`  
**权限**: caregiver  
**请求参数**:
```json
{
    "elder_id": "int, 必填, 老人ID",
    "content": "string, 必填, 回复内容"
}
```
