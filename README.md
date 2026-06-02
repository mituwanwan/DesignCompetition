# DesignCompetition
中国大学生计算机设计大赛的比赛备份项目
智慧养老院的项目
我们采用统一的Web应用架构，所有角色端使用相同的技术栈
后端技术
语言: Python
框架: Flask
数据库: SQLite
前端技术
UI框架: Bootstrap
语言: HTML + CSS + JavaScript
图表库: Plotly（用于数据可视化）

虽然有三种不同的角色（管理员、护工、子女），但他们都是基于相同的技术栈开发的Web应用，只是展示的功能和界面不同。
1. 管理员端
访问方式: Web浏览器
前端: Bootstrap + HTML/CSS/JavaScript
后端API: Flask（Python）
特殊组件: Plotly图表（数据统计与可视化）
2. 护工端
访问方式: Web浏览器
前端: Bootstrap + HTML/CSS/JavaScript
后端API: Flask（Python）
特殊功能: 文件上传（异常情况图片）
3. 子女端
访问方式: Web浏览器
前端: Bootstrap + HTML/CSS/JavaScript
后端API: Flask（Python）
特殊功能: 浏览器通知API（新报警提醒）
技术栈详细说明
Python/Flask后端
所有角色共用同一套后端API，通过权限控制来区分不同角色的访问权限。

核心Python库：

Flask - Web框架
Flask-Session - 会话管理
pandas - 数据处理和Excel导出
plotly - 数据可视化
hashlib - 密码加密
sqlite3 - 数据库操作（Python内置）
Bootstrap前端
前端采用模块化设计，根据不同角色加载不同的页面组件，但使用相同的技术。

前端特性：

响应式设计（适配PC和Pad）
统一的界面风格
AJAX异步请求
10秒自动刷新轮询（消息通知）
