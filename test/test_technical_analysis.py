from app.domain.market.technical_analysis import TechnicalAnalysis
import pytest

def test_ema():
    prices = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
    period = 5
    # SMA first 5: (10+11+12+13+14)/5 = 12
    # Multiplier: 2/(5+1) = 1/3
    # EMA #6 (Price 15): (15 - 12) * 1/3 + 12 = 13
    # EMA #7 (Price 16): (16 - 13) * 1/3 + 13 = 14
    
    ema = TechnicalAnalysis.calculate_ema(prices, period)
    assert ema == pytest.approx(17.0)

def test_rsi():
    # Alternating up and down
    prices = [100, 102, 101, 104, 102, 105, 103, 108, 105, 110] # 10 prices
    period = 6
    rsi = TechnicalAnalysis.calculate_rsi(prices, period)
    assert rsi == pytest.approx(70.83854818523153)
    assert 0 <= rsi <= 100

def test_macd():
    # Need at least 26 + 9 candles ideally, let's make dummy long data
    prices = [i + (i%5)*2 for i in range(100)] # 100 candles with some waves
    dif, dea, hist = TechnicalAnalysis.calculate_macd(prices)
    
    assert dif == pytest.approx(7.353687798986655)
    assert dea == pytest.approx(7.051042466310648)
    assert hist == pytest.approx(0.3026453326760077)
