"""
Deterministic end-to-end regression for the local analysis pipeline.
"""
from app.domain.market.prompt_engine import PromptEngine
from app.domain.market.technical_analysis import TechnicalAnalysis


def test_data_pipeline(mock_kline_data):
    kline_data = mock_kline_data[:80]
    closes = [item[4] for item in kline_data]
    highs = [item[2] for item in kline_data]
    lows = [item[3] for item in kline_data]

    macd = TechnicalAnalysis.calculate_macd(closes, 12, 26, 9)
    indicators = {
        "ema": TechnicalAnalysis.calculate_ema(closes, 20),
        "rsi": TechnicalAnalysis.calculate_rsi(closes, 14),
        "macd": dict(zip(("dif", "dea", "histogram"), macd)),
        "atr": TechnicalAnalysis.calculate_atr(highs, lows, closes, 14),
    }

    prompt = PromptEngine.build_analysis_prompt("BTC/USDT", kline_data, indicators)

    assert len(kline_data) == 80
    assert indicators["ema"] is not None
    assert indicators["rsi"] is not None
    assert indicators["macd"]["dif"] is not None
    assert indicators["atr"] is not None
    assert "BTC/USDT" in prompt
    assert '"signal": "BUY/SELL/HOLD"' in prompt
    assert "EMA (20)" in prompt
