# 公开网站

公开部署设置 `PUBLIC_SITE=true`、`PUBLIC_HOST=trade.blacknico.com`，并使用 `npm run build:public` 构建前端。应用统一使用有容量上限的进程内存缓存，无需额外缓存服务。普通本地开发仍使用 `npm run build:frontend`。两种模式不要混用。

公开网站不提供模型配置、AI 信号、数据修复、服务器个人文档和服务器 Pine 执行接口，接口文档也不公开。行情和无状态的定投、对比、筛选计算可以匿名访问；筛选配置及结果仍由浏览器保存。公开 API 按实际路由选择，不依赖菜单隐藏或客户端传来的身份。

自选、布局、画线、脚本、研究记录、价格提醒及回测报告保存在访问者自己的 IndexedDB。浏览器之间互不共享，也不会自动同步设备；更换浏览器、域名或清理网站数据前，从设置中导出个人数据。导入保留现有内容，冲突项另存并调整引用。公开网站只读取程序内置的初始自选和只读脚本，不迁入服务器的个人记录。

Pine 回测在浏览器 Worker 内运行，服务器只提供行情。计算最多同时运行两个，五分钟后停止；关闭运行所在的网页会中断计算，已保存报告保留。浏览器打开期间检查提醒，关闭网站后停止检查。普通本地模式继续支持原有后台提醒和服务端回测。

`deployment/` 保存此站独立的 Nginx 和 systemd 配置。Nginx 负责 HTTPS、静态资源、短时共享行情缓存、真实访客 IP 和请求限制；后端只监听 `127.0.0.1:4335`，只信任本机代理。主页面禁止动态 JavaScript 求值，Pine Worker 单独允许引擎需要的编译能力，其网络连接仍限于本站。Cloudflare 可信地址从官方地址列表生成到 shared/cloudflare-real-ip.conf，不信任访客自行提交的转发头。

公开站关闭包含查询参数的常规访问日志，不把自选请求和定投金额写入日常访问记录。Linux 部署按锁定依赖安装，使用 `uv pip install --no-deps --require-hashes -r requirements.lock`，由项目锁提供完整依赖集。两种平台均使用维护中的 `mini-racer`，它提供 `py_mini_racer` 导入接口；PDM 明确排除旧同名发行包，避免在 Linux 上混装旧引擎。

程序位于 `/srv/opentrading/releases/<commit>`，`current` 指向当前版本，环境和数据位于 `shared`，数据库使用本机 Unix socket。更新先准备新版本、检查数据库迁移及前端资源，再切换指针并重启本站服务。旧版本保留供回退，不在部署过程中清空数据。两项应用服务共用一个 CPU 核心及 1.5 GB 内存上限，公开计算同时只接收一个；实时上游连接按品种和周期复用，全站最多 32 条，每个浏览器连接最多订阅八组。

通过 `systemctl status opentrading-api opentrading-background` 和 `journalctl -u opentrading-api -u opentrading-background` 检查本站；`https://trade.blacknico.com/health` 检查实际公开链路。配置和凭据不进入 Git。公开部署的安全限制应使用 `test/test_public_site.py` 回归；依赖更新后重新查询漏洞数据库。
