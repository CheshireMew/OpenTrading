from datetime import datetime
import pytz
from typing import Union, Optional
from config import settings

class TimeManager:
    """
    统一时间管理模块
    负责时区转换、当前时间获取
    """
    
    DEFAULT_TIMEZONE = 'Asia/Shanghai'
    
    @staticmethod
    def get_timezone(tz_name: Optional[str] = None) -> pytz.timezone:
        """获取 pytz 时区对象，默认为 DEFAULT_TIMEZONE"""
        if not tz_name:
            # 尝试从 settings 获取，否则使用默认
            tz_name = getattr(settings, 'TIMEZONE', TimeManager.DEFAULT_TIMEZONE)
        try:
            return pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            return pytz.timezone(TimeManager.DEFAULT_TIMEZONE)

    @staticmethod
    def get_now(tz_name: Optional[str] = None) -> datetime:
        """获取当前带时区的时间"""
        tz = TimeManager.get_timezone(tz_name)
        return datetime.now(tz)

    @staticmethod
    def convert_to_utc(dt_or_str: Union[datetime, str], from_tz_name: Optional[str] = None) -> datetime:
        """
        将时间转换为 UTC 时间
        :param dt_or_str: datetime 对象或日期字符串 (YYYY-MM-DD HH:MM:SS)
        :param from_tz_name: 来源时区 (如果 dt 是 naive 且 str 没带时区信息)
        """
        tz = TimeManager.get_timezone(from_tz_name)
        
        if isinstance(dt_or_str, str):
            # 简单解析，假设格式规范
            try:
                dt = datetime.strptime(dt_or_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    dt = datetime.strptime(dt_or_str, "%Y-%m-%d")
                except ValueError:
                     raise ValueError(f"Unsupported date format: {dt_or_str}")
        else:
            dt = dt_or_str
            
        if dt.tzinfo is None:
            dt = tz.localize(dt)
            
        return dt.astimezone(pytz.UTC)

    @staticmethod
    def convert_from_utc(dt: datetime, to_tz_name: Optional[str] = None) -> datetime:
        """将 UTC 时间转换为目标时区时间"""
        tz = TimeManager.get_timezone(to_tz_name)
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        return dt.astimezone(tz)
