"""
数据库 Schema 定义
仅定义表结构数据模型，与业务逻辑分离
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, JSON, BigInteger, Index
from sqlalchemy.orm import declarative_base, relationship

from app.domain.market.constants import KLINE_SYMBOL_MAX_LENGTH
from utils.time import utc_now_naive

Base = declarative_base()


class BinanceMarketResearchSeries(Base):
    """Binance historical research series persisted after normalization."""
    __tablename__ = 'binance_market_research_series'

    id = Column(Integer, primary_key=True, autoincrement=True)
    market = Column(String(20), nullable=False)
    series = Column(String(60), nullable=False)
    symbol = Column(String(40), nullable=False)
    period = Column(String(20), nullable=False, default="")
    contract_type = Column(String(30), nullable=False, default="")
    item_key = Column(String(80), nullable=False)
    timestamp = Column(BigInteger, nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        Index(
            'ix_binance_market_research_unique',
            'market',
            'series',
            'symbol',
            'period',
            'contract_type',
            'item_key',
            unique=True,
        ),
        Index(
            'ix_binance_market_research_lookup',
            'market',
            'series',
            'symbol',
            'period',
            'contract_type',
            'timestamp',
        ),
    )

    def __repr__(self):
        return (
            f"<BinanceMarketResearchSeries(market={self.market}, series={self.series}, symbol={self.symbol}, "
            f"period={self.period}, contract_type={self.contract_type}, timestamp={self.timestamp})>"
        )


class Kline(Base):
    """K线数据表 (用于缓存)"""
    __tablename__ = 'klines'
    
    # 复合主键: symbol + timeframe + timestamp
    symbol = Column(String(KLINE_SYMBOL_MAX_LENGTH), primary_key=True, nullable=False)
    timeframe = Column(String(10), primary_key=True, nullable=False)
    timestamp = Column(BigInteger, primary_key=True, nullable=False) # 毫秒时间戳
    
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)

    __table_args__ = (
        Index("ix_klines_timeframe_timestamp", "timeframe", "timestamp"),
    )

    def to_list(self):
        """转换为 [ts, o, h, l, c, v] 格式"""
        return [self.timestamp, self.open, self.high, self.low, self.close, self.volume]
    
    
    def __repr__(self):
        return f"<Kline({self.symbol}, {self.timeframe}, {self.timestamp})>"

class Sentiment(Base):
    """市场情绪数据表 (如 Fear & Greed Index)"""
    __tablename__ = 'sentiment'
    
    date = Column(DateTime, primary_key=True) # 日期 (00:00:00)
    value = Column(Integer, nullable=False) # 指数数值 (0-100)
    classification = Column(String(20), nullable=True) # 分类 (Extreme Fear, etc.)
    timestamp = Column(BigInteger, nullable=True) # 原始时间戳
    
    def __repr__(self):
        return f"<Sentiment({self.date}, {self.value})>"

class MarketIndicatorMeta(Base):
    """市场指标元数据配置表"""
    __tablename__ = 'market_indicator_meta'
    
    id = Column(String(50), primary_key=True)  # 指标唯一标识，如 'US10Y', 'FearGreedIndex'
    name = Column(String(100), nullable=False)  # 展示名称
    category = Column(String(50), nullable=False)  # 所属维度: Macro, Onchain, Sentiment, Tech
    unit = Column(String(20), nullable=True)  # 单位: %, USD, EH/s等
    frequency = Column(String(20), default='daily')  # 更新频率: daily, hourly
    description = Column(Text, nullable=True)  # 指标描述说明
    is_active = Column(Integer, default=1)  # 是否激活采抓取 (1/0)
    
    # 关联关系
    data_points = relationship("MarketIndicatorData", back_populates="meta_info", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<MarketIndicatorMeta(id={self.id}, name={self.name})>"

class MarketIndicatorData(Base):
    """市场指标历史数据流"""
    __tablename__ = 'market_indicator_data'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    indicator_id = Column(String(50), ForeignKey('market_indicator_meta.id'), nullable=False)  # 外键
    timestamp = Column(DateTime, nullable=False)  # 数据时间点 (可能精确到日或小时)
    value = Column(Float, nullable=False)  # 指标数值
    
    # 关联关系
    meta_info = relationship("MarketIndicatorMeta", back_populates="data_points")

    __table_args__ = (
        Index('ix_indicator_data_id_ts', 'indicator_id', 'timestamp', unique=True),
    )

    def __repr__(self):
        return f"<MarketIndicatorData(indicator={self.indicator_id}, ts={self.timestamp}, val={self.value})>"


class PortfolioCollectionState(Base):
    """Singleton revision and active selection for the portfolio aggregate."""

    __tablename__ = "portfolio_collection_state"

    id = Column(String(32), primary_key=True)
    revision = Column(Integer, nullable=False, default=0)
    active_portfolio_id = Column(String(120), nullable=True)
    updated_at = Column(DateTime, default=utc_now_naive, nullable=False)


class PortfolioRecord(Base):
    """Versioned portfolio document. Deleted records remain restorable."""

    __tablename__ = "portfolio_records"

    id = Column(String(120), primary_key=True)
    payload = Column(JSON, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    position = Column(Integer, nullable=False, default=0)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        Index("ix_portfolio_records_deleted_position", "deleted_at", "position"),
    )


class PortfolioSimulationResultRecord(Base):
    """Large derived simulation artifact stored outside editable portfolio documents."""

    __tablename__ = "portfolio_simulation_results"

    portfolio_id = Column(
        String(120),
        ForeignKey("portfolio_records.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source_fingerprint = Column(String(64), nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, nullable=False)


class RuntimeComponentStatus(Base):
    """Cross-process heartbeat and last job outcome for product readiness."""

    __tablename__ = "runtime_component_status"

    component = Column(String(80), primary_key=True)
    owner_id = Column(String(160), nullable=False)
    status = Column(String(32), nullable=False)
    started_at = Column(DateTime, nullable=False)
    heartbeat_at = Column(DateTime, nullable=False)
    last_success_at = Column(DateTime, nullable=True)
    last_failure_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    error_code = Column(String(80), nullable=True)
    error_detail = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False)


