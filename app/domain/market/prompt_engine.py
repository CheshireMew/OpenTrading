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

