import json

class PromptEngine:
    @staticmethod
    def build_analysis_prompt(symbol, market_data, indicators):
        """
        构建发送给 AI 的 Prompt
        """
        if not market_data:
            return "No market data available."

        latest_candle = market_data[-1]
        close_price = latest_candle[4]
        
        # 格式化指标数据
        ema_val = indicators.get('ema')
        rsi_val = indicators.get('rsi')
        macd_val = indicators.get('macd')
        atr_val = indicators.get('atr')
        
        # 构建文本描述
        ema_desc = f"{ema_val:.2f}" if ema_val else "N/A"
        rsi_desc = f"{rsi_val:.2f}" if rsi_val else "N/A"
        
        macd_desc = "N/A"
        if macd_val and macd_val[0] is not None:
             dif, dea, hist = macd_val
             macd_desc = f"DIF={dif:.2f}, DEA={dea:.2f}, Histogram={hist:.2f}"

        atr_desc = f"{atr_val:.2f}" if atr_val else "N/A"

        # 使用双大括号转义 JSON 模板
        prompt = f"""
You are a professional crypto trading assistant. 
Analyze the following market data for {symbol} and provide trading advice.

### Market Data
- Current Price: {close_price}
- Technical Indicators:
    - EMA (20): {ema_desc}
    - RSI (14): {rsi_desc}
    - MACD: {macd_desc}
    - ATR: {atr_desc}
    
### Instructions
1. Analyze the trend based on Price vs EMA.
2. Analyze momentum based on RSI and MACD.
3. Provide a clear trading signal (BUY, SELL, or HOLD).
4. Estimate confidence level (0-100%).
5. Suggest Stop Loss and Take Profit levels if applicable.

### Output Format
You MUST output raw JSON only, no markdown formatting.
{{
    "signal": "BUY/SELL/HOLD",
    "confidence": 80,
    "reasoning": "Brief explanation...",
    "stop_loss": 12345.67,
    "take_profit": 13456.78
}}
"""
        return prompt.strip()

    @staticmethod
    def build_trade_setup_prompt(symbol, timeframe, market_data, indicators, account_size, style, strategy):
        if not market_data:
            return "No market data available."

        latest_candle = market_data[-1]
        close_price = latest_candle[4]
        ema_val = indicators.get("ema")
        rsi_val = indicators.get("rsi")
        macd_val = indicators.get("macd")
        atr_val = indicators.get("atr")
        recent_candles = [
            {
                "time": int(item[0]),
                "open": item[1],
                "high": item[2],
                "low": item[3],
                "close": item[4],
                "volume": item[5],
            }
            for item in market_data[-24:]
        ]
        macd_payload = None
        if macd_val:
            dif, dea, hist = macd_val
            macd_payload = {"dif": dif, "dea": dea, "histogram": hist}

        recent_window = market_data[-20:]
        recent_swing_high = max(item[2] for item in recent_window) if recent_window else None
        recent_swing_low = min(item[3] for item in recent_window) if recent_window else None
        distance_to_ema_pct = None
        if ema_val:
            try:
                distance_to_ema_pct = ((close_price - ema_val) / ema_val) * 100
            except ZeroDivisionError:
                distance_to_ema_pct = None

        context = {
            "symbol": symbol,
            "timeframe": timeframe,
            "current_price": close_price,
            "account_size": account_size,
            "style": style,
            "strategy": strategy,
            "indicators": {
                "ema": ema_val,
                "rsi": rsi_val,
                "macd": macd_payload,
                "atr": atr_val,
            },
            "market_structure": {
                "recent_swing_high": recent_swing_high,
                "recent_swing_low": recent_swing_low,
                "distance_to_ema_pct": distance_to_ema_pct,
            },
            "recent_candles": recent_candles,
        }

        return f"""
你是加密货币交易分析助手。请只基于下面给出的K线、指标和市场结构数据，生成一个可画在K线图上的多空方案。

要求：
1. 你的目标是优先给出可执行的交易计划，不要因为轻微分歧或单一指标偏高偏低就直接选择 HOLD。
2. 当一侧方向明显更占优时，直接输出该方向的交易计划；entry 可以使用当前价、回踩价或突破后回踩价。
3. entry、target、stop 的相对位置必须与方案方向自洽。
4. target 和 stop 需要贴近当前结构，形成合理且可执行的风险收益关系。
5. confidence 是 0 到 100 的整数。
6. reason 用一句中文说明最主要原因。
7. 只输出原始 JSON，不要 markdown，不要代码块。
8. 只有在多空两侧都缺乏依据、结构混乱、或者无法给出合理的 entry、target、stop 时，side 才输出 HOLD，entry/target/stop 输出 null。

输入数据：
{json.dumps(context, ensure_ascii=False)}

输出格式：
{{
  "side": "LONG/SHORT/HOLD",
  "entry": 12345.67,
  "target": 13456.78,
  "stop": 12000.00,
  "confidence": 72,
  "reason": "一句中文理由"
}}
""".strip()
