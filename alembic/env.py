"""
Alembic env.py - 读取项目配置，连接数据库，运行迁移
"""
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

from config import settings
from app.infra.db.schema import Base
from app.infra.db.schema_runtime import include_app_schema_object

# Alembic Config 对象
config = context.config

if not config.attributes.get("use_configured_database_url"):
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# 配置日志
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# 目标 metadata（Alembic 用它来对比 schema 差异）
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """以 'offline' 模式运行迁移（只生成 SQL 不执行）"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_object=include_app_schema_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """以 'online' 模式运行迁移（连接数据库执行）"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_app_schema_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
