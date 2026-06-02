import sqlite3
import os

# 1. 按照你们约定的项目结构，数据库文件应该放在 instance 目录下
os.makedirs('instance', exist_ok=True)
db_path = 'instance/nursing_home.db'

# 2. 连接数据库（如果文件不存在，SQLite 会自动帮你创建）
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 3. 读取你写好的 SQL 初始化脚本
try:
    with open('init_database.sql', 'r', encoding='utf-8') as f:
        sql_script = f.read()

    # 4. 执行脚本并提交更改
    cursor.executescript(sql_script)
    conn.commit()
    print("🎉 数据库初始化成功！所有表结构和测试账号已就绪。")
    print(f"数据库文件已生成在: {os.path.abspath(db_path)}")

except Exception as e:
    print(f"初始化失败，报错信息: {e}")
finally:
    conn.close()