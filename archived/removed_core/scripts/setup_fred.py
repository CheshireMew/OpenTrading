"""
FRED API 配置引导脚本
交互式帮助你完成配置
"""
import os
import sys
from pathlib import Path

print("=" * 70)
print("          FRED API Key 配置助手")
print("=" * 70)
print()

# Step 1: 检查当前配置
print("[Step 1] 检查现有配置...")
env_path = Path(__file__).parent.parent / ".env"

if env_path.exists():
    print(f"[OK] 找到 .env 文件: {env_path}")
    with open(env_path, 'r') as f:
        content = f.read()
        if 'FRED_API_KEY' in content:
            # 提取API Key
            for line in content.split('\n'):
                if line.startswith('FRED_API_KEY'):
                    key = line.split('=')[1].strip()
                    if key and len(key) == 32:
                        print(f"[OK] FRED_API_KEY 已配置: {key[:8]}...{key[-4:]}")
                        configured = True
                    else:
                        print("[ERROR] FRED_API_KEY 格式错误（应该是32位字符）")
                        configured = False
                    break
            else:
                configured = False
        else:
            print("[ERROR] .env 文件中未找到 FRED_API_KEY")
            configured = False
else:
    print(f"[ERROR] 未找到 .env 文件: {env_path}")
    configured = False

print()

# Step 2: 引导申请
if not configured:
    print("[Step 2] 申请 FRED API Key")
    print("-" * 70)
    print()
    print("请按照以下步骤操作：")
    print()
    print("1.  打开浏览器，访问:")
    print("   https://fred.stlouisfed.org/")
    print()
    print("2.  点击右上角 'Log In' 或 'Sign Up'")
    print("   - 如果已有账号，直接登录")
    print("   - 如果没有账号，注册一个（30秒搞定）")
    print()
    print("3.  登录后，访问 API Keys 页面:")
    print("   https://fredaccount.stlouisfed.org/apikeys")
    print()
    print("4.  点击 'Request API Key' 按钮")
    print("   - Description: Heimdall Market Analysis")
    print("   - Purpose: 选择 Research 或 Education")
    print()
    print("5.  复制你的 API Key（32位字符）")
    print()
    print("-" * 70)
    print()

    api_key = input("请粘贴你的 FRED API Key (按 Enter 跳过): ").strip()

    if api_key:
        # 验证格式
        if len(api_key) == 32 and api_key.isalnum():
            print(f"[OK] API Key 格式正确: {api_key[:8]}...{api_key[-4:]}")

            # 写入 .env
            if env_path.exists():
                # 追加或更新
                with open(env_path, 'r') as f:
                    lines = f.readlines()

                found = False
                for i, line in enumerate(lines):
                    if line.startswith('FRED_API_KEY'):
                        lines[i] = f'FRED_API_KEY={api_key}\n'
                        found = True
                        break

                if not found:
                    lines.append(f'\n# Market Data APIs\nFRED_API_KEY={api_key}\n')

                with open(env_path, 'w') as f:
                    f.writelines(lines)
            else:
                # 创建新文件
                with open(env_path, 'w') as f:
                    f.write(f"# FRED API Configuration\nFRED_API_KEY={api_key}\n")

            print(f"[OK] 配置已保存到: {env_path}")
            configured = True
        else:
            print("[ERROR] API Key 格式错误！应该是32位字母和数字组合")
            print(f"  你输入的长度: {len(api_key)}")
    else:
        print("跳过配置。你可以稍后手动编辑 .env 文件")

print()

# Step 3: 测试连接
if configured:
    print("[Step 3] 测试 API 连接...")
    print("-" * 70)
    print()

    test = input("是否立即测试 FRED API 连接? (y/n, 默认 y): ").strip().lower()

    if test != 'n':
        print("正在测试...")
        try:
            import asyncio
            import httpx

            async def test_fred():
                from dotenv import load_dotenv
                load_dotenv()

                api_key = os.getenv('FRED_API_KEY')
                url = 'https://api.stlouisfed.org/fred/series/observations'
                params = {
                    'series_id': 'DGS10',
                    'api_key': api_key,
                    'file_type': 'json',
                    'limit': 1,
                    'sort_order': 'desc'
                }

                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.get(url, params=params)
                    if res.status_code == 200:
                        data = res.json()
                        obs = data['observations'][0]
                        print()
                        print("[OK] FRED API 连接成功!")
                        print(f"  10年期美债收益率: {obs['value']}%")
                        print(f"  数据日期: {obs['date']}")
                        return True
                    else:
                        print(f"[ERROR] API 返回错误: {res.status_code}")
                        print(f"  响应: {res.text[:200]}")
                        return False

            success = asyncio.run(test_fred())

            if success:
                print()
                print("🎉 配置成功！FRED API 工作正常！")

        except Exception as e:
            print(f"[ERROR] 测试失败: {e}")
            print()
            print("请检查:")
            print("  1. API Key 是否正确")
            print("  2. 网络连接是否正常")
            print("  3. 是否安装了 httpx: pip install httpx")

print()
print("=" * 70)
print("配置完成！")
print("=" * 70)
print()
print("下一步:")
print("  1. 更新 Cron Job: 修改 app/application/indicators/market_cron.py")
print("     使用 MacroProviderV2 替代 MacroProvider")
print()
print("  2. 测试数据采集:")
print("     python app/application/indicators/market_cron.py")
print()
print("  3. 查看详细文档:")
print("     docs/FRED_API_SETUP_GUIDE.md")
print()
print("如有问题，随时询问！")
print()
