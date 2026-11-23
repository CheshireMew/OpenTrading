import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class BaseIndicatorProvider:
    """
    市场核心指标提供者的基类
    各维度的指标拉取类需继承此基类并实现抓取逻辑
    """
    
    def __init__(self):
        # 初始化时可配置通用的 HTTP Client 等
        pass

    async def fetch_data(self) -> List[Dict[str, Any]]:
        """
        统一的数据拉取接口
        必须返回标准格式的字典列表：
        [
            {
                "indicator_id": "FEAR_GREED",  # 与 MarketIndicatorMeta.id 对应
                "timestamp": datetime对象,
                "value": float数值
            },
            ...
        ]
        """
        raise NotImplementedError("子类必须实现此方法以供定时任务调用")
