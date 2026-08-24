# FRED API Key 申请完整指南

## 📝 目录
- [第一步：注册 FRED 账号](#第一步注册-fred-账号)
- [第二步：申请 API Key](#第二步申请-api-key)
- [第三步：配置到项目](#第三步配置到项目)
- [第四步：测试验证](#第四步测试验证)
- [第五步：更新代码](#第五步更新代码)
- [常见问题](#常见问题)

---

## 第一步：注册 FRED 账号

### 1.1 访问 FRED 官网

打开浏览器，访问：
```
https://fred.stlouisfed.org/
```

### 1.2 点击注册按钮

- 页面右上角找到 **"Log In"** 或 **"Sign Up"** 按钮
- 点击 **"Sign Up"**（注册）

### 1.3 填写注册信息

填写以下信息：
- **Email Address**（邮箱地址）：你的常用邮箱
- **Password**（密码）：设置一个安全的密码
- **Confirm Password**（确认密码）：再次输入密码
- **First Name**（名字）：可以用拼音，如 Dylan
- **Last Name**（姓氏）：可以用拼音，如 Wang

示例：
```
Email: your_email@gmail.com
Password: YourSecurePassword123!
First Name: Dylan
Last Name: Wang
```

### 1.4 验证邮箱

- 点击 **"Create Account"**（创建账号）
- 检查你的邮箱收件箱（可能在垃圾邮件中）
- 点击验证邮件中的链接
- 完成邮箱验证

---

## 第二步：申请 API Key

### 2.1 登录账号

- 使用刚才注册的邮箱和密码登录
- 登录后会跳转到 FRED 主页

### 2.2 进入 API Keys 页面

**方法1（直接链接）：**
```
https://fredaccount.stlouisfed.org/apikeys
```
直接复制这个链接到浏览器打开

**方法2（手动点击）：**
1. 点击页面右上角的用户名
2. 从下拉菜单选择 **"My Account"**
3. 在左侧菜单中点击 **"API Keys"**

### 2.3 申请新的 API Key

1. 点击页面中的 **"Request API Key"** 按钮

2. 填写申请表单：

   - **API Key Description**（API Key 描述）：
     ```
     Heimdall Crypto Market Analysis Tool
     ```
     或者随便写个描述，比如：
     ```
     Personal data analysis project
     ```

   - **API Key Purpose**（使用目的）：
     从下拉菜单选择：
     - ✅ **"Research"**（研究）
     - 或选择 **"Education"**（教育）

3. 勾选 **"I agree to the FRED® API Terms of Use"**（同意条款）

4. 点击 **"Request API key"**（申请 API Key）

### 2.4 获取 API Key

- 申请成功后，页面会立即显示你的 API Key
- API Key 格式类似：`abcdef1234567890abcdef1234567890`（32位字符）

**重要提示：**
- ✅ **复制并保存你的 API Key**（下一步要用）
- ✅ 这个 Key 随时可以在账号页面查看
- ✅ 可以创建多个 API Key（如果需要）

---

## 第三步：配置到项目

### 3.1 打开项目目录

```bash
cd E:\Work\Code\Heimdall
```

### 3.2 编辑或创建 .env 文件

**方法1（使用记事本）：**
```bash
# 打开或创建 .env 文件
notepad .env
```

**方法2（使用命令行）：**
```bash
# 如果文件不存在会自动创建
echo FRED_API_KEY=你的API_KEY >> .env
```

### 3.3 添加 API Key

在 `.env` 文件中添加：

```env
# FRED API Configuration
FRED_API_KEY=your_fred_api_key_here
```

**替换为你的实际 API Key！**

示例（完整的 .env 文件）：
```env
# Database
DATABASE_URL=postgresql://postgres:root123@localhost:5432/heimdall

# AI
DEEPSEEK_API_KEY=sk-xxxxx

# Market Data APIs
FRED_API_KEY=your_fred_api_key_here

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
```

### 3.4 保存文件

- 保存并关闭 `.env` 文件
- 确保文件名是 `.env`（不是 `.env.txt`）

---

## 第四步：测试验证

### 4.1 测试 API 连接

创建测试脚本：

```bash
cd E:\Work\Code\Heimdall
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv('FRED_API_KEY')
if api_key:
    print(f'API Key loaded: {api_key[:8]}...{api_key[-4:]}')
    print('Configuration OK!')
else:
    print('ERROR: FRED_API_KEY not found in .env')
"
```

**预期输出：**
```
API Key loaded: [redacted]
Configuration OK!
```

### 4.2 测试数据获取

运行我们提供的测试脚本：

```bash
# 方法1：测试 FRED API 直接调用
python -c "
import httpx
import asyncio

async def test_fred():
    api_key = 'YOUR_API_KEY'  # 替换为你的 API Key
    url = 'https://api.stlouisfed.org/fred/series/observations'
    params = {
        'series_id': 'DGS10',
        'api_key': api_key,
        'file_type': 'json',
        'limit': 1,
        'sort_order': 'desc'
    }

    async with httpx.AsyncClient() as client:
        res = await client.get(url, params=params)
        if res.status_code == 200:
            data = res.json()
            obs = data['observations'][0]
            print(f'✓ FRED API Working!')
            print(f'  10-Year Treasury: {obs[\"value\"]}%')
            print(f'  Date: {obs[\"date\"]}')
        else:
            print(f'✗ Error: {res.status_code}')

asyncio.run(test_fred())
"
```

### 4.3 使用 MacroProviderV2 测试

```bash
cd E:\Work\Code\Heimdall

# 创建测试文件
cat > test_fred.py << 'EOF'
import asyncio

from app.services.indicators.macro_provider_v2 import MacroProviderV2

async def test():
    print("Testing FRED API via MacroProviderV2...")
    provider = MacroProviderV2()

    # 测试单个指标
    result = await provider._fetch_fred_api("DGS10", "US10Y")

    if result:
        print(f"✓ Success!")
        print(f"  Indicator: {result['indicator_id']}")
        print(f"  Value: {result['value']}%")
        print(f"  Date: {result['timestamp']}")
    else:
        print("✗ Failed to fetch data")

    # 测试完整获取
    print("\nFetching all macro indicators...")
    data = await provider.fetch_data()
    print(f"✓ Fetched {len(data)} indicators")
    for d in data:
        print(f"  - {d['indicator_id']:15} : {d['value']}")

asyncio.run(test())
EOF

# 运行测试
python test_fred.py
```

**预期输出：**
```
Testing FRED API via MacroProviderV2...
✓ Success!
  Indicator: US10Y
  Value: 4.25%
  Date: 2026-02-25

Fetching all macro indicators...
✓ FRED API Working
✓ Fetched 4 indicators
  - US10Y          : 4.25
  - HY_SPREAD      : 3.45
  - NASDAQ         : 18234.5
  - GOLD           : 2650.0
```

---

## 第五步：更新代码

### 5.1 修改 Cron Job

编辑 `app/application/indicators/market_cron.py`：

```python
# 找到第15行左右
from app.services.indicators.macro_provider_v2 import MacroProviderV2 as MacroProvider
```

**或者直接运行命令替换：**
```bash
cd E:\Work\Code\Heimdall

# Windows (PowerShell)
(Get-Content app\application\indicators\market_cron.py) -replace 'from app.services.indicators.macro_provider_v2 import MacroProviderV2 as MacroProvider', 'from app.services.indicators.macro_provider_v2 import MacroProviderV2 as MacroProvider' | Set-Content app\application\indicators\market_cron.py
```

### 5.2 运行 Cron Job 测试

```bash
python app/application/indicators/market_cron.py
```

**预期输出：**
```
INFO - Starting MarketIndicator Cron Job...
INFO - ✓ US10Y from FRED
INFO - ✓ HY_SPREAD from FRED
INFO - ↓ NASDAQ fallback to YFinance
INFO - ✓ NASDAQ from YFinance
INFO - ✓ GOLD from Binance
INFO - MarketIndicator Cron Job Complete. Inserted 10 records.
```

### 5.3 验证数据库

```bash
python -m scripts.check_indicators
```

**预期看到：**
```
=== Market Indicator Meta ===
US10Y                | Us10y                          | General
NASDAQ               | Nasdaq                         | General
GOLD                 | Gold                           | General
HY_SPREAD            | Hy Spread                      | General

=== Market Indicator Data (Recent 10) ===
US10Y                | 2026-02-25 00:00:00 |         4.25
HY_SPREAD            | 2026-02-25 00:00:00 |         3.45
NASDAQ               | 2026-02-25 00:00:00 |     18234.50
GOLD                 | 2026-02-26 10:30:00 |      2650.00
```

---

## 常见问题

### Q1: 找不到 .env 文件怎么办？

**A:** 创建新文件：
```bash
cd E:\Work\Code\Heimdall
echo. > .env
notepad .env
```
然后添加配置。

---

### Q2: API Key 是否会过期？

**A:** FRED API Key **不会过期**，长期有效！

---

### Q3: 如果忘记了 API Key 怎么办？

**A:**
1. 登录 https://fredaccount.stlouisfed.org/apikeys
2. 查看现有的 API Keys
3. 或者删除旧的，创建新的

---

### Q4: 有请求次数限制吗？

**A:**
- 官方说明：无严格限制
- 建议：不超过 **120次/分钟**
- 我们的使用：**4小时才1次**，完全足够

---

### Q5: API Key 填错了怎么办？

**A:** 检查方法：
```bash
# 查看当前配置
cd E:\Work\Code\Heimdall
type .env | findstr FRED

# 重新编辑
notepad .env
```

---

### Q6: 测试时报错 "Invalid API Key"

**A:** 检查清单：
- [ ] API Key 是否包含空格或换行？
- [ ] 是否复制完整（32位字符）？
- [ ] .env 文件中格式是否正确？
  ```env
  FRED_API_KEY=abcd1234  ✓ 正确
  FRED_API_KEY = abcd1234  ✗ 错误（有空格）
  FRED_API_KEY="abcd1234"  ✗ 错误（有引号）
  ```

---

### Q7: 可以获取历史数据吗？

**A:** 可以！修改参数：
```python
params = {
    'series_id': 'DGS10',
    'observation_start': '2020-01-01',  # 开始日期
    'observation_end': '2024-12-31',    # 结束日期
    'sort_order': 'desc'
}
```

---

### Q8: 还有哪些有用的指标？

**A:** 热门指标列表：

| 指标 | Series ID | 说明 |
|------|-----------|------|
| 10年期美债 | DGS10 | 无风险利率 |
| 2年期美债 | DGS2 | 短期利率 |
| 联邦基金利率 | DFF | 美联储政策利率 |
| M2货币 | M2SL | 货币供应量 |
| CPI | CPIAUCSL | 通胀指数 |
| 失业率 | UNRATE | 就业情况 |
| GDP | GDP | 经济增长 |
| 原油价格 | DCOILWTICO | WTI原油 |

完整列表：https://fred.stlouisfed.org/categories

---

## ✅ 完成检查清单

- [ ] 1. 注册 FRED 账号
- [ ] 2. 申请 API Key
- [ ] 3. 复制并保存 API Key
- [ ] 4. 添加到 .env 文件
- [ ] 5. 测试配置加载
- [ ] 6. 测试 API 连接
- [ ] 7. 更新 market_cron.py
- [ ] 8. 运行 Cron Job
- [ ] 9. 验证数据库
- [ ] 10. 启动服务器验证前端

---

## 🎉 恭喜！

如果所有步骤都完成了，你已经成功：
- ✅ 永久解决了 YFinance 限流问题
- ✅ 获取了官方权威的经济数据
- ✅ 提升了数据采集的稳定性

**下一步：**
- 启动完整服务：`python -m uvicorn app.main:app --reload --port 5001`
- 访问前端查看指标：http://localhost:5000
- 享受零限流的数据体验！

---

## 📞 获取帮助

如果遇到问题，请检查：
1. 错误日志：查看终端输出
2. .env 配置：确认格式正确
3. 网络连接：确保能访问 FRED API

需要帮助随时问我！



8cfecb8295bb64016fd59e3a1996dfd1
