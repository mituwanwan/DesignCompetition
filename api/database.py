import sqlite3
import os
import threading
import time
from functools import wraps
from queue import Queue, Empty


class DatabasePool:
    """线程安全的 SQLite 数据库连接池"""
    
    def __init__(self, db_path, max_connections=5, timeout=30.0):
        self.db_path = db_path
        self.max_connections = max_connections
        self.timeout = timeout
        self.pool = Queue(maxsize=max_connections)
        self.lock = threading.Lock()
        self.active_connections = 0
        
        # 预创建一些连接
        for _ in range(min(2, max_connections)):
            self.pool.put(self._create_connection())
            self.active_connections += 1
    
    def _create_connection(self):
        """创建新的数据库连接"""
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.timeout,
            check_same_thread=False,
            isolation_level=None
        )
        conn.row_factory = sqlite3.Row
        
        # 启用 WAL 模式以提高并发性能
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=30000;")
        conn.commit()
        
        return conn
    
    def get_connection(self):
        """从池中获取连接"""
        start_time = time.time()
        
        while time.time() - start_time < self.timeout:
            try:
                if not self.pool.empty():
                    conn = self.pool.get(timeout=1.0)
                    # 检查连接是否有效
                    try:
                        cursor = conn.cursor()
                        cursor.execute("SELECT 1")
                        return conn
                    except (sqlite3.OperationalError, sqlite3.ProgrammingError):
                        conn.close()
                        with self.lock:
                            self.active_connections -= 1
                        continue
                
                # 池为空，尝试创建新连接
                with self.lock:
                    if self.active_connections < self.max_connections:
                        conn = self._create_connection()
                        self.active_connections += 1
                        return conn
                
                # 等待片刻后重试
                time.sleep(0.1)
                
            except Empty:
                continue
        
        raise sqlite3.OperationalError(f"Database connection pool exhausted after {self.timeout} seconds")
    
    def return_connection(self, conn):
        """将连接返回到池中"""
        if conn:
            try:
                self.pool.put(conn, timeout=1.0)
            except Full:
                conn.close()
                with self.lock:
                    self.active_connections -= 1


# 全局数据库连接池实例
_db_pool = None
_db_lock = threading.Lock()


def init_database_pool():
    """初始化数据库连接池（单例模式）"""
    global _db_pool
    
    with _db_lock:
        if _db_pool is None:
            current_dir = os.path.dirname(__file__)
            db_path = os.path.join(current_dir, '..', 'instance', 'nursing_home.db')
            db_path = os.path.abspath(db_path)
            _db_pool = DatabasePool(db_path, max_connections=10, timeout=30.0)
    
    return _db_pool


def get_db():
    """获取数据库连接（Context Manager 支持）"""
    pool = init_database_pool()
    conn = pool.get_connection()
    
    class DBContext:
        def __init__(self, connection):
            self.conn = connection
            self._closed = False
        
        def __enter__(self):
            return self.conn
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            if not self._closed:
                if exc_type is None:
                    try:
                        self.conn.commit()
                    except:
                        pass
                else:
                    try:
                        self.conn.rollback()
                    except:
                        pass
                pool.return_connection(self.conn)
                self._closed = True
    
    return DBContext(conn)


def db_operation(func):
    """数据库操作装饰器：自动管理连接和异常处理"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        retry_count = 3
        last_exception = None
        
        for attempt in range(retry_count):
            try:
                return func(*args, **kwargs)
            except sqlite3.OperationalError as e:
                last_exception = e
                if "database is locked" in str(e) and attempt < retry_count - 1:
                    time.sleep(0.5 * (attempt + 1))  # 指数退避
                    continue
                raise
            except sqlite3.Error as e:
                raise
    
    return wrapper


def format_db_error(exception):
    """格式化数据库错误为用户友好信息"""
    error_msg = str(exception).lower()
    
    if "database is locked" in error_msg:
        return "系统繁忙，请稍后重试"
    elif "unable to open database file" in error_msg:
        return "数据库连接失败，请联系管理员"
    elif "constraint failed" in error_msg:
        return "操作失败，数据不合法"
    elif "no such table" in error_msg:
        return "系统数据异常，请联系管理员"
    else:
        return "操作失败，请稍后重试或联系管理员"


# 清理函数，在应用关闭时调用
def close_database_pool():
    """关闭数据库连接池"""
    global _db_pool
    with _db_lock:
        if _db_pool:
            while not _db_pool.pool.empty():
                try:
                    conn = _db_pool.pool.get_nowait()
                    conn.close()
                    _db_pool.active_connections -= 1
                except:
                    pass
            _db_pool = None
