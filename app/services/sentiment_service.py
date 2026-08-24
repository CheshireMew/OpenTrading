from __future__ import annotations

from datetime import datetime

from app.services.sentiment_client import SentimentApiClient
from app.application.persistence_ports import SentimentRepositoryPort
from utils.logger import logger
from utils.time import now_in_timezone


class SentimentService:
    def __init__(
        self,
        *,
        client: SentimentApiClient,
        repository: SentimentRepositoryPort,
    ) -> None:
        self.client = client
        self.repository = repository

    def sync_data(self) -> None:
        try:
            latest_date = self.repository.get_latest_date()
            today = now_in_timezone().date()
            if latest_date and latest_date.date() >= today:
                return

            logger.info("正在更新恐慌贪婪指数数据...")
            records = self.client.fetch_history()
            inserted = self.repository.save_missing(records)
            if inserted:
                logger.info(f"已同步 {inserted} 条情绪数据")
            else:
                logger.info("情绪数据已同步")
        except Exception as exc:
            logger.error(f"同步情绪数据失败: {exc}")

    def get_sentiment_history(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, int]:
        self.sync_data()
        return self.repository.list_history(start_date, end_date)

    def get_fear_greed_index(self) -> dict[str, int | str] | None:
        self.sync_data()
        return self.repository.get_latest_index()
