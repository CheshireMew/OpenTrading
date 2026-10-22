<!-- readme-header:start -->

<p align="center">
  <img src="./docs/assets/opentrading-logo.png" width="160" alt="OpenTrading">
</p>

<h1 align="center">OpenTrading</h1>

<p align="center">
  <strong>相場チャート・戦略検証・ポートフォリオ分析ツール。</strong>
</p>

<p align="center">
  <a href="./README.md">中文</a> · <a href="./README.en.md">English</a> · <strong>日本語</strong> | <a href="./docs/README.md">文档</a> | <a href="./CONTRIBUTING.md">贡献</a> | <a href="https://github.com/CheshireMew/OpenTrading/issues">反馈</a>
</p>

<p align="center">
  <a href="https://x.com/0xCheshire" title="X"><img src="https://img.shields.io/badge/X-%400xCheshire-000000?logo=x&amp;logoColor=white" alt="X：@0xCheshire"></a>
  <a href="https://t.me/CheshireBTC" title="Telegram"><img src="https://img.shields.io/badge/Telegram-CheshireBTC-26A5E4?logo=telegram&amp;logoColor=white" alt="Telegram：CheshireBTC"></a>
  <a href="https://blog.blacknico.com/" title="Blog"><img src="https://img.shields.io/badge/Blog-blog.blacknico.com-2E7D32?logo=rss&amp;logoColor=white" alt="博客：blog.blacknico.com"></a>
  <a href="https://blacknico.com/" title="Homepage"><img src="https://img.shields.io/badge/Home-blacknico.com-1F6FEB?logo=googlechrome&amp;logoColor=white" alt="个人主页：blacknico.com"></a>
</p>

<p align="center">
  <a href="https://github.com/CheshireMew/OpenTrading/stargazers"><img src="https://img.shields.io/github/stars/CheshireMew/OpenTrading?style=flat" alt="GitHub Stars"></a>
  <a href="https://github.com/CheshireMew/OpenTrading/forks"><img src="https://img.shields.io/github/forks/CheshireMew/OpenTrading?style=flat" alt="GitHub Forks"></a>
  <a href="https://github.com/CheshireMew/OpenTrading/blob/main/LICENSE"><img src="https://img.shields.io/github/license/CheshireMew/OpenTrading?style=flat" alt="Repository License"></a>
</p>

<!-- readme-header:end -->

銘柄と時間足を選び、インジケーターや Pine スクリプトを追加できます。取引履歴の記録、資産の比較、戦略の検証にも対応しています。主な対象は暗号資産です。

## 機能

| 用途 | できること |
| --- | --- |
| [チャート](docs/CHART_WORKSPACE.md) | 1・2・4画面、自選リスト、描画ツール、テクニカル指標、Pine エディター、戦略テスター |
| [市場の確認](docs/DATA_SOURCES.md) | 市場シグナル、Binance デリバティブ、Web3 ランキング、[取引所が扱う株式関連銘柄](docs/EQUITY_CATALOG.md) |
| 投資ツール | 銘柄比較、積立投資（DCA）のシミュレーション、ビットコイン半減期の観察 |
| [ポートフォリオ分析](docs/RESEARCH_WORKFLOWS.md) | 取引台帳、取得原価と手数料、収益率、ベンチマーク比較、相関、ストレステスト |
| [戦略研究](docs/LOCAL_BACKTESTS.md) | Python バックテスト、[パラメーター比較](docs/PARAMETER_SWEEPS.md)、結果の振り返り、研究レポート |

## インストールと起動

現在の検証対象は **Windows** です。Git、Python **3.12.x**、Node.js **≥ 22.12.0**、npm が必要です。プロジェクトを置くディレクトリで PowerShell を開きます。

```powershell
git clone https://github.com/CheshireMew/OpenTrading.git
cd OpenTrading
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
npm --prefix frontend ci
Copy-Item .env.example .env
```

`.env` にデータベースの接続先を設定します。初めてローカルで使う場合は SQLite を選べます。

```dotenv
DATABASE_URL=sqlite:///./.opentrading_runtime/opentrading.db
```

アプリを起動します。

```powershell
.\dev_start.bat
```

ランチャーがデータベースを準備し、API、バックグラウンド処理、フロントエンドを起動します。準備完了の表示後、**[http://127.0.0.1:4173](http://127.0.0.1:4173)** を開くとチャート画面が表示されます。終了するには `Q` または `Ctrl+C` を押します。

Redis とモデルの API キーは任意です。PostgreSQL、手動起動、ログ、トラブル対処は[起動ガイド](docs/GETTING_STARTED.md)を参照してください。詳細ドキュメントは現在中国語です。

## 主な入口

| 入口 | パス・ドキュメント |
| --- | --- |
| チャート | `/` · [操作方法と Pine の対応範囲](docs/CHART_WORKSPACE.md) |
| ポートフォリオ | `/tools/portfolio-balance` |
| データの状態 | `/system/data-health` |
| API ドキュメント | [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) |
| Python バックテストとパラメーター比較 | `/research/backtests` · `/research/parameter-sweeps` |

研究ページは現在メインメニューに表示されません。起動後に各パスへ直接アクセスするか、研究 CLI を使います。

```powershell
.\venv\Scripts\python.exe -m scripts.research_cli --help
.\venv\Scripts\python.exe -m scripts.research_cli asset BTC/USDT --timeframe 1h
```

CLI はスクリプトから扱える構造化 JSON を返します。全コマンドは[研究ワークフロー](docs/RESEARCH_WORKFLOWS.md)と[戦略研究](docs/STRATEGY_RESEARCH.md)を参照してください。

## データとバックテストの制約

OpenTrading は研究とシミュレーション用で、取引口座に接続して発注する機能はありません。Pine v5/v6 は一部の機能に対応しています。Pine と Python のバックテストではエンジンと費用の計算方法が異なるため、結果を比較する前にそれぞれの説明を確認してください。

初期のビットコイン履歴には合成データと代理データが含まれます。出典と対象期間は [data/README.md](data/README.md) に記載しています。外部の相場データには欠損や遅延があり、過去の結果やモデルの分析は将来の収益を保証しません。

## 開発とドキュメント

フロントエンドは Vue 3、TypeScript、Vite、バックエンドは FastAPI、SQLAlchemy と独立したバックグラウンドプロセスで構成されています。開発コマンドと変更提案の手順は[貢献ガイド](CONTRIBUTING.md)、機能と構成は[ドキュメント一覧](docs/README.md)を参照してください。

## ライセンスと謝辞

プロジェクト独自のコードには [AGPL-3.0-or-later](LICENSE) を適用しています。範囲は [LICENSING.md](LICENSING.md) を参照してください。外部依存と金融データには各提供元の条件が適用されます。[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) に概要を記載しています。

チャートには [LuxAlgo Vela](https://luxalgo.com/vela)、Vela-pinets、[PineTS](https://github.com/alaa-eddine/PineTS) を使用しています。`.agents/skills/` の開発用スキルは [emilkowalski/skills](https://github.com/emilkowalski/skills) に由来し、[MIT ライセンス](.agents/skills/LICENSE)です。
