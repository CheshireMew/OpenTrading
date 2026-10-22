# 参与 OpenTrading

问题与功能建议请提交到 [GitHub Issues](https://github.com/CheshireMew/OpenTrading/issues)。描述你要完成的事、实际结果和预期结果；报告故障时附上复现步骤、Windows 与 Python / Node.js 版本，以及相关错误日志。请隐去密钥、账户信息和个人交易记录。

## 开发环境

先按 [README](README.md#安装与启动) 安装依赖并配置数据库。当前验证平台为 Windows，后端使用 Python 3.12.x，前端需要 Node.js ≥ 22.12.0。日常开发使用 `dev_start.bat`；需要分别启动服务时，参见[启动指南](docs/GETTING_STARTED.md#手动启动)。

| 路径 | 职责 |
| --- | --- |
| `app/` | FastAPI 路由、HTTP 契约、领域模型、业务服务和基础设施 |
| `alembic/` | 数据库迁移 |
| `config/` | 应用配置 |
| `frontend/` | Vue 界面、图表、状态管理和前端测试 |
| `scripts/` | CLI、数据处理和开发命令 |
| `test/` | Python 与接口契约测试 |
| `docs/` | 当前功能、架构和维护说明 |
| `data/` | 随仓库提供的数据及来源说明 |

`archived/` 是历史材料，不是当前应用入口。架构分层见 [ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 验证改动

按改动范围选择检查。在项目根目录运行：

```powershell
# 后端测试；单项修改可以指定对应测试文件
.\venv\Scripts\python.exe -m pytest -q

# 前端测试与类型检查
npm --prefix frontend test
npm --prefix frontend run typecheck
```

修改 FastAPI 路由、Pydantic 模型或前端契约消费者后，生成契约并构建前端：

```powershell
$env:OPENTRADING_PYTHON = (Resolve-Path .\venv\Scripts\python.exe).Path
npm run build:frontend
```

以下文件由 `scripts.generate_frontend_contracts` 生成，不应直接手写。检查生成差异，并与对应后端修改一起提交：

- `frontend/src/api/errors.ts`
- `frontend/src/api/routes.ts`
- `frontend/src/modules/market/generatedContracts.ts`
- `frontend/src/modules/system/generatedContracts.ts`
- `frontend/src/modules/tools/generatedContracts.ts`

CI 使用 Windows、Python 3.12.10 与 Node.js 22.23.0，执行语法检查、Ruff、后端测试、前端测试、类型检查、构建和契约漂移检查。仅修改文档时，核对事实、命令、相对链接及中英日 README 的一致性即可，不必运行产品全套测试。

## 提交修改

请让一个 PR 围绕一个明确的问题展开，说明触发场景、修改后的行为和实际完成的验证。有界面变化时可以附上对应页面截图；涉及数据库时，提供迁移和现有数据的处理说明。避免夹带无关格式化或依赖升级。

新增或调整功能时，同步修改对应专题文档。只有改变项目用途、安装步骤、主要入口或适用边界时，才需要更新三份 README。

不要提交 `.env`、`venv/`、`node_modules/`、本地数据库、日志、缓存或个人研究结果。保留第三方代码的许可证与署名；代码、文档和金融数据的许可范围见 [LICENSING.md](LICENSING.md) 与 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
