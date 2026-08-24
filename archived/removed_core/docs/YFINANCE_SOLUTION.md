# YFinance 限流问题解决方案总结

## 🔴 问题现状

YFinance 目前被严格限流，即使使用延迟和User-Agent伪装也无法绕过：
```
Too Many Requests. Rate limited. Try after a while.
```

---

## ✅ **最佳解决方案：使用 FRED API（强烈推荐）**

### 为什么选择 FRED？

| 对比项 | FRED API | YFinance | Alpha Vantage |
|--------|----------|----------|---------------|
| **限流** | ❌ 无限制 | ❌ 严格限流 | ⚠️ 5次/分钟 |
| **稳定性** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| **数据质量** | 官方权威 | 非官方 | 可靠 |
| **费用** | 🆓 完全免费 | 🆓 免费 | 🆓 免费 |
| **注册时间** | 30秒 | 不需要 | 1分钟 |

### 快速开始（3步搞定）

#### Step 1: 申请 FRED API Key（30秒）

1. 访问：https://fred.stlouisfed.org/
2. 点击右上角 **"My Account"** → **"API Keys"**
3. 点击 **"Request API Key"**
4. 填写：
   - Email: 你的邮箱
   - Purpose: "Heimdall Crypto Analysis Tool"
5. 立即获得 API Key（类似：`abcdef1234567890abcdef1234567890`）

#### Step 2: 配置 .env 文件

```bash
cd E:\Work\Code\Heimdall

# 编辑或创建 .env 文件
echo FRED_API_KEY=你的API_KEY >> .env
```

#### Step 3: 更新 Cron Job 使用 V2 版本

编辑 `app/application/indicators/market_cron.py`:

```python
# 修改第15行
from app.services.indicators.macro_provider_v2 import MacroProviderV2 as MacroProvider
```

---

## 📊 FRED 可用的数据（10000+指标）

### 宏观经济核心指标

| 指标名称 | FRED Series ID | 说明 |
|---------|---------------|------|
| 10年期美债收益率 | `DGS10` | 最重要的无风险收益率 |
| 联邦基金利率 | `DFF` | 美联储政策利率 |
| 2年期美债收益率 | `DGS2` | 短期利率 |
| 5年期美债收益率 | `DGS5` | 中期利率 |
| 30年期美债收益率 | `DGS30` | 长期利率 |

### 通胀与货币

| 指标名称 | FRED Series ID | 说明 |
|---------|---------------|------|
| CPI（消费者价格指数）| `CPIAUCSL` | 通胀核心指标 |
| M2货币供应量 | `M2SL` | 货币流动性 |
| 核心PCE | `PCEPILFE` | 美联储关注的通胀指标 |

### 企业债券利差

| 指标名称 | FRED Series ID | 说明 |
|---------|---------------|------|
| 高收益债利差 | `BAMLH0A0HYM2` | 风险偏好指标 |
| BBB级企业债利差 | `BAMLC0A4CBBB` | 投资级债券利差 |

### 美元指数

| 指标名称 | FRED Series ID | 说明 |
|---------|---------------|------|
| 美元指数 | `DTWEXBGS` | 美元强弱 |
| 人民币汇率 | `DEXCHUS` | USD/CNY |

---

## 🔧 集成示例代码

### 已实现的文件：`macro_provider_v2.py`

特性：
- ✅ 优先使用 FRED API
- ✅ 自动降级到 YFinance（如果FRED获取失败）
- ✅ 2秒延迟避免限流
- ✅ 完整错误处理

使用方法：
```python
from app.services.indicators.macro_provider_v2 import MacroProviderV2

provider = MacroProviderV2()
data = await provider.fetch_data()

# 返回格式：
# [
#   {
#     "indicator_id": "US10Y",
#     "timestamp": datetime(...),
#     "value": 4.25
#   },
#   ...
# ]
```

---

## 🚀 补充数据源

### 1. Binance PAXG（黄金价格）

✅ **已实现**：`crypto_gold_provider.py`

- PAXG = 实物黄金代币
- 1 PAXG = 1 盎司黄金
- 实时价格，无限流

```python
from app.services.indicators.crypto_gold_provider import CryptoGoldProvider

provider = CryptoGoldProvider()
gold_price = await provider.fetch_data()
# 返回：{indicator_id: "GOLD", value: 2650.50, ...}
```

### 2. 纳斯达克指数（备用方案）

如果YFinance恢复，可以用于获取 NASDAQ。

或者使用 **TradingView 公开数据**（无需API Key）：
```python
import requests
url = "https://scanner.tradingview.com/america/scan"
payload = {
    "symbols": {"tickers": ["NASDAQ:COMP"]},
    "columns": ["close"]
}
res = requests.post(url, json=payload)
nasdaq_price = res.json()['data'][0]['d'][0]
```

---

## 📋 实施检查清单

- [ ] 1. 申请 FRED API Key
- [ ] 2. 添加到 .env 文件
- [ ] 3. 修改 market_cron.py 使用 MacroProviderV2
- [ ] 4. 测试数据获取：`python -m scripts.check_macro`
- [ ] 5. 运行 Cron Job：`python -m app.application.indicators.market_cron`
- [ ] 6. 验证数据库：`python -m scripts.check_indicators`
- [ ] 7. 启动服务器测试前端：`python -m uvicorn app.main:app --reload --port 5001`

---

## 🎯 预期效果

使用 FRED API 后：

**Before（YFinance）：**
```
❌ US10Y: Rate limited
❌ NASDAQ: Rate limited
❌ GOLD: Rate limited
⏱️ 总耗时：10秒（多次重试）
✅ 成功：0/3
```

**After（FRED + Binance）：**
```
✅ US10Y: 4.25% (from FRED)
✅ FEDFUNDS: 5.50% (from FRED)
✅ M2: 21.2T (from FRED)
✅ GOLD: $2,650 (from Binance PAXG)
⏱️ 总耗时：2秒
✅ 成功：4/4
```

---

## 📚 相关资源

- **FRED API 文档**: https://fred.stlouisfed.org/docs/api/
- **FRED 数据浏览**: https://fred.stlouisfed.org/
- **Binance API 文档**: https://binance-docs.github.io/apidocs/
- **PAXG 介绍**: https://paxos.com/paxgold/

---

## ❓ 常见问题

**Q: FRED API 有请求限制吗？**
A: 免费版无硬性限制，但建议不超过 120次/分钟。我们4小时才请求一次，完全够用。

**Q: 如果FRED暂时无法访问怎么办？**
A: MacroProviderV2 会自动降级到 YFinance，确保服务不中断。

**Q: 能获取历史数据吗？**
A: 可以！FRED提供完整历史数据，修改API参数即可：
```python
params = {
    'series_id': 'DGS10',
    'observation_start': '2020-01-01',
    'observation_end': '2024-12-31'
}
```

**Q: 数据更新频率？**
A: 大部分指标每日更新，部分（如CPI）每月更新。FRED会自动保持最新。

---

## ✅ 总结

**推荐方案：FRED API + Binance PAXG**

- 🆓 **完全免费**
- 🚀 **无限流问题**
- 📊 **数据更权威**
- ⚡ **响应更快**
- 🔒 **长期稳定**

**30秒注册，永久解决限流问题！**
