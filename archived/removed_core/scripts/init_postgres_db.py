import os
from sqlalchemy import create_engine, text
from urllib.parse import urlparse

def create_database():
    # 读取 .env 文件中的配置（简单读取）
    db_url = None
    with open('.env', 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip().startswith('DATABASE_URL='):
                db_url = line.strip().split('=', 1)[1]
                break
    
    if not db_url:
        print("[ERROR] 未在 .env 中找到 DATABASE_URL")
        return

    if 'sqlite' in db_url:
        print("[INFO] 当前配置也为 SQLite，无需创建 PostgreSQL 数据库。")
        return

    # 解析 URL 获取连接信息，连接到默认的 'postgres' 数据库
    # 格式: postgresql://user:pass@host:port/dbname
    try:
        url = urlparse(db_url)
        # 构造连接到 'postgres' 默认数据库的 URL
        default_db_url = f"{url.scheme}://{url.username}:{url.password}@{url.hostname}:{url.port}/postgres"
        target_db_name = url.path.lstrip('/')
        
        print(f"[CONN] 尝试连接到 PostgreSQL (postgres)...")
        engine = create_engine(default_db_url, isolation_level="AUTOCOMMIT")
        
        with engine.connect() as conn:
            # 检查数据库是否存在
            result = conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname = '{target_db_name}'"))
            if result.fetchone():
                print(f"[OK] 数据库 '{target_db_name}' 已存在。")
            else:
                print(f"[BUILD] 正在创建数据库 '{target_db_name}'...")
                conn.execute(text(f"CREATE DATABASE {target_db_name}"))
                print(f"[OK] 数据库 '{target_db_name}' 创建成功！")
                
    except Exception as e:
        print(f"[ERROR] 创建数据库失败: {e}")
        print("请检查 .env 文件中的密码是否正确。")

if __name__ == "__main__":
    try:
        # 安装依赖
        import psycopg2
    except ImportError:
        print("[WARN] 缺少 psycopg2-binary 依赖，正在尝试安装...")
        os.system("pip install psycopg2-binary")
        
    create_database()
