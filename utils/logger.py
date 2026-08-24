import logging
import os
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_logger(name="AI-Guide"):
    """
    配置并返回一个标准的 logger
    支持: 控制台输出 + 可选文件输出（RotatingFileHandler）
    """
    logger = logging.getLogger(name)

    # 防止重复添加 handler
    if logger.handlers:
        return logger

    from config import settings
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)

    # 时区转换器
    from utils.time import now_in_timezone
    def time_converter(seconds):
        return now_in_timezone().timetuple()

    # 日志格式
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    formatter.converter = time_converter

    # 1. 控制台 Handler（始终启用）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. 文件 Handler（可选，通过 LOG_FILE 环境变量启用）
    log_file = os.getenv("LOG_FILE", "")
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            str(log_path),
            maxBytes=10 * 1024 * 1024,  # 10MB per file
            backupCount=5,
            encoding='utf-8',
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# 全局单例 logger
logger = setup_logger()
