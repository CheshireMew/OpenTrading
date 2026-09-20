"""
数据库 Schema 定义
仅定义表结构数据模型，与业务逻辑分离
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, JSON, BigInteger, Index, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

from app.domain.market.constants import KLINE_SYMBOL_MAX_LENGTH
from utils.time import utc_now_naive

Base = declarative_base()


class LocalBacktestRunRow(Base):
    __tablename__ = "local_backtest_runs"
    id = Column(String(64), primary_key=True)
    status = Column(String(30), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive)
    payload = Column(JSON, nullable=False)


class LocalBacktestRecordRow(Base):
    __tablename__ = "local_backtest_records"
    run_id = Column(String(64), ForeignKey("local_backtest_runs.id"), primary_key=True)
    kind = Column(String(20), primary_key=True)
    sequence = Column(Integer, primary_key=True)
    timestamp = Column(BigInteger, nullable=False)
    payload = Column(JSON, nullable=False)
    __table_args__ = (Index("ix_local_backtest_record_time", "run_id", "kind", "timestamp"),)


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


class ResearchWatchlist(Base):
    """Named research collection; archived lists remain recoverable."""

    __tablename__ = "research_watchlists"

    id = Column(String(120), primary_key=True)
    name = Column(String(160), nullable=False)
    description = Column(Text, nullable=False, default="")
    position = Column(Integer, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=1)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        Index("ix_research_watchlists_active_position", "archived_at", "position"),
    )


class ResearchWatchItem(Base):
    """A durable symbol-level research thesis inside a watchlist."""

    __tablename__ = "research_watch_items"

    id = Column(String(120), primary_key=True)
    watchlist_id = Column(
        String(120),
        ForeignKey("research_watchlists.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol = Column(String(160), nullable=False)
    asset_class = Column(String(32), nullable=False, default="crypto")
    display_name = Column(String(200), nullable=False, default="")
    thesis = Column(Text, nullable=False, default="")
    target_price = Column(Float, nullable=True)
    invalidation_price = Column(Float, nullable=True)
    tags = Column(JSON, nullable=False, default=list)
    source_context = Column(JSON, nullable=False, default=dict)
    position = Column(Integer, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=1)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        UniqueConstraint("watchlist_id", "symbol", name="uq_research_watch_item_symbol"),
        Index("ix_research_watch_items_symbol_active", "symbol", "archived_at"),
        Index("ix_research_watch_items_list_position", "watchlist_id", "archived_at", "position"),
    )


class ResearchNote(Base):
    """Versioned research journal entry attached to a symbol."""

    __tablename__ = "research_notes"

    id = Column(String(120), primary_key=True)
    watch_item_id = Column(
        String(120),
        ForeignKey("research_watch_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    symbol = Column(String(160), nullable=False)
    kind = Column(String(32), nullable=False, default="update")
    title = Column(String(240), nullable=False)
    content = Column(Text, nullable=False, default="")
    snapshot = Column(JSON, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=1)
    occurred_at = Column(DateTime, nullable=False)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        Index("ix_research_notes_symbol_occurred", "symbol", "archived_at", "occurred_at"),
    )


class ResearchAlertRule(Base):
    """Persisted threshold or crossing rule evaluated by the research runtime."""

    __tablename__ = "research_alert_rules"

    id = Column(String(120), primary_key=True)
    watch_item_id = Column(
        String(120),
        ForeignKey("research_watch_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    symbol = Column(String(160), nullable=False)
    name = Column(String(200), nullable=False)
    metric = Column(String(80), nullable=False)
    operator = Column(String(24), nullable=False)
    threshold = Column(Float, nullable=False)
    secondary_threshold = Column(Float, nullable=True)
    enabled = Column(Integer, nullable=False, default=1)
    cooldown_minutes = Column(Integer, nullable=False, default=60)
    notification_channels = Column(JSON, nullable=False, default=list)
    configuration = Column(JSON, nullable=False, default=dict)
    last_value = Column(Float, nullable=True)
    last_evaluated_at = Column(DateTime, nullable=True)
    last_triggered_at = Column(DateTime, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        Index("ix_research_alerts_enabled_symbol", "archived_at", "enabled", "symbol"),
    )


class ResearchEvent(Base):
    """Immutable timeline event emitted by research, alerts, signals, and reports."""

    __tablename__ = "research_events"

    id = Column(String(120), primary_key=True)
    entity_type = Column(String(40), nullable=False)
    entity_id = Column(String(120), nullable=True)
    symbol = Column(String(160), nullable=True)
    kind = Column(String(60), nullable=False)
    title = Column(String(240), nullable=False)
    body = Column(Text, nullable=False, default="")
    payload = Column(JSON, nullable=False, default=dict)
    occurred_at = Column(DateTime, nullable=False)
    acknowledged_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        Index("ix_research_events_timeline", "occurred_at", "kind"),
        Index("ix_research_events_entity", "entity_type", "entity_id", "occurred_at"),
    )


class PortfolioTransactionRecord(Base):
    """Recoverable transaction ledger used to derive holdings and performance."""

    __tablename__ = "portfolio_transactions"

    id = Column(String(120), primary_key=True)
    portfolio_id = Column(
        String(120),
        ForeignKey("portfolio_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    transaction_type = Column(String(32), nullable=False)
    symbol = Column(String(160), nullable=False, default="")
    quantity = Column(Float, nullable=False, default=0)
    unit_price = Column(Float, nullable=False, default=0)
    cash_amount = Column(Float, nullable=False, default=0)
    fee = Column(Float, nullable=False, default=0)
    currency = Column(String(16), nullable=False, default="USD")
    fee_currency = Column(String(16), nullable=False, default="USD")
    external_id = Column(String(200), nullable=True)
    note = Column(Text, nullable=False, default="")
    metadata_payload = Column("metadata", JSON, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=1)
    occurred_at = Column(DateTime, nullable=False)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        Index("ix_portfolio_transactions_timeline", "portfolio_id", "archived_at", "occurred_at"),
        Index("ix_portfolio_transactions_symbol", "portfolio_id", "symbol", "occurred_at"),
    )


class TradeSignalRecord(Base):
    """Generated trade setup plus its independently evaluated market outcome."""

    __tablename__ = "trade_signal_records"

    id = Column(String(120), primary_key=True)
    symbol = Column(String(160), nullable=False)
    timeframe = Column(String(16), nullable=False)
    source = Column(String(32), nullable=False)
    mode = Column(String(32), nullable=False)
    signal_status = Column(String(32), nullable=False)
    side = Column(String(16), nullable=True)
    entry = Column(Float, nullable=True)
    target = Column(Float, nullable=True)
    stop = Column(Float, nullable=True)
    risk_reward = Column(Float, nullable=True)
    confidence = Column(Integer, nullable=True)
    risk_amount = Column(Float, nullable=True)
    style = Column(String(40), nullable=True)
    strategy = Column(String(80), nullable=True)
    reason = Column(Text, nullable=False, default="")
    error_code = Column(String(80), nullable=True)
    current_price = Column(Float, nullable=True)
    entry_time = Column(BigInteger, nullable=True)
    market_snapshot = Column(JSON, nullable=False, default=dict)
    outcome_status = Column(String(32), nullable=False, default="pending")
    outcome_price = Column(Float, nullable=True)
    target_hit_at = Column(DateTime, nullable=True)
    stop_hit_at = Column(DateTime, nullable=True)
    mfe_pct = Column(Float, nullable=True)
    mae_pct = Column(Float, nullable=True)
    forward_returns = Column(JSON, nullable=False, default=dict)
    evaluated_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        Index("ix_trade_signals_pending", "archived_at", "outcome_status", "created_at"),
        Index("ix_trade_signals_symbol_time", "symbol", "timeframe", "created_at"),
        Index("ix_trade_signals_source_outcome", "source", "outcome_status", "created_at"),
    )


class SavedMarketScreener(Base):
    """Versioned market filter definition with recoverable archives."""

    __tablename__ = "saved_market_screeners"

    id = Column(String(120), primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    filters = Column(JSON, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=1)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (Index("ix_saved_screeners_active_updated", "archived_at", "updated_at"),)


class MarketScreenerRun(Base):
    """Immutable screener result snapshot used for historical replay."""

    __tablename__ = "market_screener_runs"

    id = Column(String(120), primary_key=True)
    screener_id = Column(String(120), ForeignKey("saved_market_screeners.id", ondelete="CASCADE"), nullable=False)
    filters_snapshot = Column(JSON, nullable=False, default=dict)
    result_items = Column(JSON, nullable=False, default=list)
    result_count = Column(Integer, nullable=False, default=0)
    snapshot_as_of = Column(DateTime, nullable=False)
    evaluated_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        Index("ix_screener_runs_history", "screener_id", "snapshot_as_of"),
        Index("ix_screener_runs_evaluated", "evaluated_at"),
    )


class ResearchReportRecord(Base):
    """Generated, reproducible research report with the structured source snapshot."""

    __tablename__ = "research_reports"

    id = Column(String(120), primary_key=True)
    title = Column(String(240), nullable=False)
    report_type = Column(String(40), nullable=False)
    symbol = Column(String(160), nullable=True)
    portfolio_id = Column(String(120), ForeignKey("portfolio_records.id", ondelete="SET NULL"), nullable=True)
    content_markdown = Column(Text, nullable=False)
    data_snapshot = Column(JSON, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=1)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        Index("ix_research_reports_type_created", "report_type", "archived_at", "created_at"),
        Index("ix_research_reports_symbol_created", "symbol", "created_at"),
    )


