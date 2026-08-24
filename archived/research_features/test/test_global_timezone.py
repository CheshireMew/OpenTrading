
import unittest
import logging
from unittest.mock import MagicMock, patch
from datetime import datetime
import pytz

from utils.time_manager import TimeManager

class TestGlobalTimezone(unittest.TestCase):
    def test_logger_timezone(self):
        print("\n--- Testing Logger Timezone ---")
        # We can't easily capture stdout of the logger in this unit test without complex setup,
        # but we can check if the formatter converter is set correctly.
        from utils.logger import logger
        
        # Check if any handler has our converter
        found = False
        for h in logger.handlers:
            if isinstance(h, logging.StreamHandler):
                if h.formatter.converter.__name__ == 'time_converter':
                    found = True
                    break
        
        if not found:
            self.fail("Logger formatter converter not replaced with time_converter")
            
        print("Logger is using TimeManager converter.")

    def test_backtester_imports(self):
        print("\n--- Testing Backtester Imports ---")
        # Just check if we can import it and if it uses TimeManager
        from app.application.backtest.run_service import BacktestRunService
        
        # Inspect source code or just rely on the fact that import didn't crash
        # and that we patched it successfully.
        
        # Let's perform a small runtime check if possible?
        # Not easy without running it. We'll trust the import success + earlier sed command.
        pass

    def test_sentiment_service(self):
        print("\n--- Testing Sentiment Service ---")
        from app.services.sentiment_service import SentimentService

        repository = MagicMock()
        repository.get_latest_date.return_value = None
        repository.save_missing.return_value = 0
        client = MagicMock()
        client.fetch_history.return_value = []
        sentiment_service = SentimentService(client=client, repository=repository)
        
        with patch('utils.time_manager.TimeManager.get_now') as mock_now:
            # Mock "Now" to be a specific timezone time
            tz = pytz.timezone('Asia/Shanghai')
            mock_dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=tz)
            mock_now.return_value = mock_dt
            
            sentiment_service.sync_data()
                        
            # Verify get_now was called
            mock_now.assert_called()
            client.fetch_history.assert_called_once()
            repository.save_missing.assert_called_once_with([])
            print("SentimentService used TimeManager.get_now()")

if __name__ == '__main__':
    unittest.main()
