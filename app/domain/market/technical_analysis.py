import math

from app.domain.market.constants import DEFAULT_ATR_PERIOD, DEFAULT_VOLATILITY_PERIOD


class TechnicalAnalysis:
    @staticmethod
    def calculate_ema(prices, period):
        """
        计算指数移动平均线 (EMA)
        """
        series = TechnicalAnalysis.calculate_ema_series(prices, period)
        return series[-1] if series else None

    @staticmethod
    def calculate_ema_series(prices, period):
        if period <= 0 or len(prices) < period:
            return []

        initial_sma = sum(prices[:period]) / period
        multiplier = 2.0 / (period + 1)
        current_ema = initial_sma
        values = [current_ema]

        for price in prices[period:]:
            current_ema = (price - current_ema) * multiplier + current_ema
            values.append(current_ema)

        return values

    @staticmethod
    def calculate_macd(prices, fast_period=12, slow_period=26, signal_period=9):
        """
        计算 MACD
        Returns: (dif, dea, macd_hist)
        """
        if len(prices) < slow_period:
            return None, None, None

        fast_emas = TechnicalAnalysis.calculate_ema_series(prices, fast_period)
        slow_emas = TechnicalAnalysis.calculate_ema_series(prices, slow_period)
        if not fast_emas or not slow_emas:
            return None, None, None

        overlap = len(slow_emas)
        fast_aligned = fast_emas[-overlap:]
        dif_series = [fast - slow for fast, slow in zip(fast_aligned, slow_emas)]
        current_dif = dif_series[-1]

        if len(dif_series) < signal_period:
            return current_dif, None, None

        dea_series = TechnicalAnalysis.calculate_ema_series(dif_series, signal_period)
        current_dea = dea_series[-1] if dea_series else None
        macd_hist = current_dif - current_dea if current_dea is not None else None
        return current_dif, current_dea, macd_hist

    @staticmethod
    def calculate_rsi(prices, period=14):
        """
        计算 RSI (Wilder's Smoothing)
        """
        if period <= 0 or len(prices) <= period:
            return None

        gains = 0.0
        losses = 0.0

        for index in range(1, period + 1):
            change = prices[index] - prices[index - 1]
            if change > 0:
                gains += change
            else:
                losses += abs(change)

        avg_gain = gains / period
        avg_loss = losses / period

        for index in range(period + 1, len(prices)):
            change = prices[index] - prices[index - 1]
            if change > 0:
                avg_gain = (avg_gain * (period - 1) + change) / period
                avg_loss = (avg_loss * (period - 1)) / period
            else:
                avg_gain = (avg_gain * (period - 1)) / period
                avg_loss = (avg_loss * (period - 1) + abs(change)) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def calculate_atr(highs, lows, closes, period=DEFAULT_ATR_PERIOD):
        """
        计算 ATR (Average True Range)
        """
        series = TechnicalAnalysis.calculate_atr_series(highs, lows, closes, period)
        return series[-1] if series else None

    @staticmethod
    def calculate_atr_series(highs, lows, closes, period=DEFAULT_ATR_PERIOD):
        if period <= 0 or len(highs) != len(lows) or len(lows) != len(closes) or len(closes) <= period:
            return []

        true_ranges = [0.0] * len(closes)
        for index in range(1, len(closes)):
            tr1 = highs[index] - lows[index]
            tr2 = abs(highs[index] - closes[index - 1])
            tr3 = abs(lows[index] - closes[index - 1])
            true_ranges[index] = max(tr1, tr2, tr3)

        current_atr = sum(true_ranges[1:period + 1]) / period
        values = [current_atr]
        for index in range(period + 1, len(closes)):
            current_atr = (current_atr * (period - 1) + true_ranges[index]) / period
            values.append(current_atr)

        return values

    @staticmethod
    def calculate_atr_pct(highs, lows, closes, period=DEFAULT_ATR_PERIOD):
        atr = TechnicalAnalysis.calculate_atr(highs, lows, closes, period)
        if atr is None or not closes or closes[-1] <= 0:
            return None
        return atr / closes[-1]

    @staticmethod
    def calculate_returns(prices, use_log=True):
        if len(prices) < 2:
            return []

        returns = []
        for previous_price, current_price in zip(prices[:-1], prices[1:]):
            if previous_price <= 0 or current_price <= 0:
                continue
            if use_log:
                returns.append(math.log(current_price / previous_price))
            else:
                returns.append((current_price / previous_price) - 1.0)
        return returns

    @staticmethod
    def calculate_realized_volatility(prices, period=DEFAULT_VOLATILITY_PERIOD, use_log=True):
        if period <= 1 or len(prices) < period + 1:
            return None

        sampled_prices = prices[-(period + 1):]
        returns = TechnicalAnalysis.calculate_returns(sampled_prices, use_log=use_log)
        if len(returns) < 2:
            return None

        mean = sum(returns) / len(returns)
        variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
        return math.sqrt(variance)

    @staticmethod
    def calculate_annualized_volatility(
        prices,
        period=DEFAULT_VOLATILITY_PERIOD,
        periods_per_year=365,
        use_log=True,
    ):
        realized_volatility = TechnicalAnalysis.calculate_realized_volatility(
            prices,
            period=period,
            use_log=use_log,
        )
        if realized_volatility is None:
            return None
        return realized_volatility * math.sqrt(periods_per_year)

    @staticmethod
    def analyze_trend(price, ema20):
        """简单的趋势判断"""
        if price > ema20:
            return "Bullish (价格在 EMA20 之上)"
        return "Bearish (价格在 EMA20 之下)"
