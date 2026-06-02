# 智慧养老院管理系统

一个功能完整的养老院管理系统，支持管理员、护工、家属三类角色使用。

## 功能特性

### 账号权限管理
- 用户账号的增删改查
- 子女与老人的绑定/解绑
- 护工与负责老人的分配管理
- 账号锁定/解锁管理
- 登录日志审计

### 老人信息管理
- 老人档案的增删改查
- 按姓名/房间号模糊搜索
- 老人信息导出为 Excel
- 健康记录管理

### 日常护理任务
- 护理任务创建和分配
- 任务状态管理
- 任务完成记录

### 异常报警管理
- 异常情况上报
- 报警状态处理
- 响应时间统计

### 家属功能
- 查看绑定老人健康信息
- 报警消息查看
- 与护工双向留言
- 探视预约

## 快速开始

### 环境要求
- Python 3.8+

### Windows 用户

1. 双击运行 `start.bat` 启动脚本
2. 脚本会自动完成以下步骤：
   - 检查 Python 环境
   - 安装依赖库
   - 初始化数据库
   - 启动应用服务
3. 在浏览器中访问：http://localhost:5000

### Mac/Linux 用户

1. 在终端中运行：`chmod +x start.sh && ./start.sh`
2. 脚本会自动完成所有初始化步骤
3. 在浏览器中访问：http://localhost:5000

### 手动启动

```bash
# 安装依赖
pip install -r requirements.txt

# 初始化数据库
python setup_db.py

# 启动服务
python app.py
```

## 默认测试账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 管理员 | admin | Admin@123 |
| 护工 | caregiver1 | Caregiver@123 |
| 家属 | family1 | Family@123 |

## 项目结构

```
nursing_home/
├── app.py                 # 应用入口
├── setup_db.py           # 数据库初始化脚本
├── init_database.sql     # 数据库结构定义
├── requirements.txt      # Python 依赖列表
├── start.bat            # Windows 一键启动脚本
├── start.sh             # Mac/Linux 一键启动脚本
├── instance/            # 数据库文件目录
├── api/                 # API 接口模块
├── utils/               # 工具函数
├── static/              # 静态资源（CSS/JS/图片）
└── templates/           # HTML 模板页面
```

## 技术栈

- **后端**: Python Flask + SQLite
- **前端**: HTML5 + Bootstrap5 + JavaScript
- **数据可视化**: Plotly
- **表格处理**: Pandas + Openpyxl

## 账号安全

- 密码使用 SHA256 + Salt 加密存储
- 密码错误 3 次会锁定账号 10 分钟
- Session 超时时间：30 分钟
- 完整的登录日志记录
- 基于角色的权限控制

## 常见问题

### 端口被占用
如果 5000 端口已被占用，可以修改 `app.py` 最后一行的 `port=5000` 为其他端口。

### 依赖安装失败
可以尝试使用国内镜像源安装：
```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 数据库无法写入
确保 `instance` 目录有写入权限，或者检查是否有其他程序正在使用数据库文件。
