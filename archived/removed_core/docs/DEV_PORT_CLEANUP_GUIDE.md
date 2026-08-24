# 开发端口残留自动清理指南

这份文档记录 Heimdall 本次处理“前端/后端端口残留导致启动失败”的完整做法、复用步骤、踩坑点和注意事项。目标是下次遇到类似问题时可以直接照着做，也能迁移给其他本地开发项目参考。

## 背景问题

Heimdall 本地开发环境固定使用：

- 后端 API：`127.0.0.1:8000`
- 前端 Vite：`127.0.0.1:4173`

如果上一次启动后有残留进程没有退出，下次启动同一个端口时会失败，典型错误包括：

```text
ERROR: [WinError 10013] 以一种访问权限不允许的方式做了一个访问套接字的尝试。
```

或：

```text
address already in use
```

本次修复的目标不是简单粗暴地“谁占端口就杀谁”，而是做到：

1. 能识别这是本项目的前端/后端残留进程。
2. 是本项目残留就自动停止并重启。
3. 不是本项目的进程就不杀，打印 PID 和命令行后中止。
4. 前端不允许 Vite 偷偷换端口启动。

## 根因边界

端口本身不能可靠地“打标签”。真正可判断的边界是：

```text
监听这个端口的进程是谁？
这个进程是否属于当前项目？
```

所以本次修复把边界定义为：

```text
端口被当前项目的开发进程残留占用
```

而不是：

```text
端口被占用
```

这点很重要。如果只按“端口被占用”处理，就会误杀别的项目、数据库代理、调试服务或用户手动启动的进程。

## 总体方案

启动脚本在真正启动前端/后端前先做端口检查：

1. 查询 `8000` 和 `4173` 是否有监听进程。
2. 通过端口拿到 owner PID。
3. 通过 `Win32_Process` 读取该进程命令行。
4. 向上追溯父进程链，最多追溯 8 层。
5. 优先用显式项目标签判断是否属于 Heimdall。
6. 兼容旧启动方式，通过命令行形态判断旧残留进程。
7. 确认是本项目残留后自动停止。
8. 无法确认归属时中止启动，不做危险猜测。

## 实现步骤

### 1. 固定端口和进程标签

在 `dev_start.ps1` 里定义端口和角色标签：

```powershell
$apiHost = "127.0.0.1"
$apiPort = 8000
$frontendHost = "127.0.0.1"
$frontendPort = 4173
$backendTag = "HEIMDALL_BACKEND_$apiHost`:$apiPort"
$frontendTag = "HEIMDALL_FRONTEND_$frontendHost`:$frontendPort"
```

注意：

```powershell
`:
```

这里的反引号不能省。PowerShell 字符串插值里，变量后面直接跟 `:` 容易被解析成作用域变量语法，所以要写成：

```powershell
"$apiHost`:$apiPort"
```

### 2. 给子进程打标识

启动后端命令里加：

```powershell
`$env:HEIMDALL_PROCESS_TAG='$backendTag'
```

启动前端命令里加：

```powershell
`$env:HEIMDALL_PROCESS_TAG='$frontendTag'
```

这个环境变量会进入子进程的命令链，后续启动脚本再运行时，就能通过进程链判断这个端口是不是 Heimdall 自己留下的。

### 3. 查询监听端口

Windows 上用：

```powershell
Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
```

返回结果里最关键的是：

```text
OwningProcess
```

它就是监听这个端口的进程 PID。

### 4. 读取进程链

用 CIM 读取进程命令行：

```powershell
Get-CimInstance Win32_Process -Filter "ProcessId = $currentPid"
```

然后通过：

```text
ParentProcessId
```

向上追溯父进程。

为什么要追溯父进程？

- `uvicorn --reload` 会有 supervisor/worker 多进程。
- `npm run dev` 可能经过 `npm.cmd`、`cmd.exe`、`node.exe` 多层。
- 端口 owner 不一定是你在窗口里直接看到的那个进程。

### 5. 判断是不是本项目进程

判断分两层。

第一层是显式标签：

```text
HEIMDALL_PROCESS_TAG
```

只要进程链里出现这个标签，就认为它属于 Heimdall。

第二层是旧进程兼容判断，用于清理这次功能上线前已经残留的进程。

后端旧形态：

```text
进程名包含 python
命令行包含 uvicorn
命令行包含 app.main:app
命令行包含 --port 8000
```

前端旧形态：

```text
进程名是 node/npm/cmd
命令行包含 vite
命令行包含 4173
命令行包含项目 frontend 或 root 路径
```

注意：旧形态判断只看真正监听端口的 owner 进程，不对整条父进程链做模糊匹配。父进程的命令行很容易被测试脚本或终端命令污染。

### 6. 停止残留进程

确认是本项目残留后，停止：

- 当前监听端口的 owner PID。
- 进程链里带 `HEIMDALL_PROCESS_TAG` 的进程。
- 明确的后端 `python + uvicorn + app.main:app` 进程。
- 明确的前端 `node/npm/cmd + vite` 进程。

不要因为父进程命令行包含项目目录就杀它。项目目录只能作为识别辅助，不能作为最终 kill 条件。

原因是很多进程都可能在项目目录下运行：

- 当前终端
- Codex
- 编辑器
- 测试脚本
- 临时诊断命令

### 7. 未确认归属时中止

如果端口被占用，但无法证明是 Heimdall 进程，脚本应该打印进程链并中止：

```powershell
Write-Host "$Name port $Port is already used by a non-Heimdall process:" -ForegroundColor Red
Write-Host (Format-ProcessLineage -Lineage $lineage) -ForegroundColor DarkGray
throw "$Name port $Port is occupied by another process. Stop it manually or change the port."
```

这是必要保护，不是多余逻辑。

## 前端端口注意点

Vite 默认可能在端口冲突时自动换端口，比如从 `4173` 换到 `4174`。这会造成一种假象：

```text
前端看起来启动成功了，但项目约定的地址不可用。
```

所以启动命令必须显式指定：

```powershell
npm run dev -- --host 127.0.0.1 --port 4173 --strictPort
```

`--strictPort` 的意义是：

```text
端口不可用就失败，不自动换端口。
```

这样端口冲突会被启动脚本正确暴露和处理。

## 后端端口注意点

后端使用：

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --reload --reload-dir app --reload-dir config --reload-dir utils --port 8000
```

`--reload` 会引入多进程行为：

- 父进程负责监听文件变化。
- 子进程负责实际运行服务。
- 有时端口 owner 是子进程。
- 只杀子进程可能会被父进程重新拉起。

因此清理时不能只看一个 PID，需要结合进程链。

## 验证方法

### PowerShell 语法检查

```powershell
$tokens=$null
$errors=$null
[System.Management.Automation.Language.Parser]::ParseFile('D:\Code\Heimdall\dev_start.ps1', [ref]$tokens, [ref]$errors) > $null
if ($errors.Count) { $errors | ForEach-Object { $_.Message }; exit 1 } else { 'PowerShell syntax OK' }
```

### 查看端口当前状态

```powershell
Get-NetTCPConnection -LocalPort 8000,4173 -State Listen -ErrorAction SilentlyContinue |
    Select-Object LocalAddress,LocalPort,State,OwningProcess
```

没有输出代表两个端口都没有监听进程。

### 手动排查端口占用

```powershell
netstat -ano | Select-String ':8000'
```

拿到 PID 后：

```powershell
Get-CimInstance Win32_Process -Filter "ProcessId = <PID>" |
    Select-Object ProcessId,CommandLine |
    Format-List
```

把 `<PID>` 换成实际 PID。

### 预期行为

实现完成后应该满足：

- Heimdall 后端残留占用 `8000` 时，会自动停止并重启。
- Heimdall 前端残留占用 `4173` 时，会自动停止并重启。
- 非 Heimdall 进程占用端口时，不会被杀。
- 非 Heimdall 占用会打印 PID 和命令行，方便人工处理。
- Vite 不会自动换端口。
- 当前启动脚本可以重复运行。

## 这次踩过的坑

### 1. 端口不能真正打标签

一开始容易想到“给端口打标识”。实际系统接口里没有可靠的端口标签机制。能做的是给进程打标识，然后通过端口找到进程。

### 2. 不能只杀端口 owner

后端 `uvicorn --reload` 下，端口 owner 可能只是 worker。只杀 worker，supervisor 可能马上重启它。

正确做法是：确认归属后处理相关进程链。

### 3. 不能用项目目录作为 kill 条件

测试时发现，如果把项目目录作为停止条件，运行诊断命令的 PowerShell 也会被误判，因为它也在 `D:\Code\Heimdall` 下执行。

正确做法是：

```text
项目目录可以辅助识别，但不能单独作为停止条件。
```

### 4. 父进程命令行会污染判断

测试脚本本身可能包含 `uvicorn`、`vite`、`app.main:app` 等字符串。如果对整条进程链做旧形态模糊匹配，父 PowerShell 会被误判。

正确做法是：

- 显式 tag 可以查整条进程链。
- 旧形态兼容判断只查真正监听端口的 owner 进程。

### 5. PowerShell 字符串插值里的冒号要转义

错误写法风险：

```powershell
"HEIMDALL_BACKEND_$apiHost:$apiPort"
```

推荐写法：

```powershell
"HEIMDALL_BACKEND_$apiHost`:$apiPort"
```

### 6. `Get-NetTCPConnection` 查不到时可能报错

检查端口时加：

```powershell
-ErrorAction SilentlyContinue
```

否则没有监听进程时也可能产生噪声错误。

### 7. Vite 不加 `--strictPort` 会隐藏问题

Vite 自动换端口会让启动日志看起来正常，但用户打开固定地址时仍然失败。

本地开发脚本应该明确失败，而不是悄悄换端口。

### 8. Windows 端口排除是另一个问题

如果没有任何进程监听端口，但绑定仍然失败，需要查 Windows 排除端口范围：

```powershell
netsh interface ipv4 show excludedportrange protocol=tcp
```

如果目标端口在排除范围里，处理方式不是杀进程，而是换端口或调整系统端口保留来源。

## 给其他项目复用的模板

复用时按这个流程迁移：

1. 明确项目的固定开发端口。
2. 每个角色定义唯一标签，例如：

```text
PROJECT_BACKEND_127.0.0.1:8000
PROJECT_FRONTEND_127.0.0.1:4173
```

3. 启动子进程前写入环境变量：

```powershell
$env:PROJECT_PROCESS_TAG='...'
```

4. 启动前用端口查 owner PID。
5. 用 `Win32_Process` 读取 command line 和 parent PID。
6. 优先按 tag 判断归属。
7. 只保留一小段旧进程兼容判断。
8. 确认是项目残留才杀。
9. 未确认归属就打印进程链并中止。
10. 前端开发服务器开启 strict port。

跨平台项目可以分别实现：

- Windows：`Get-NetTCPConnection` + `Get-CimInstance Win32_Process`
- macOS/Linux：`lsof -tiTCP:<port> -sTCP:LISTEN` + `ps -o pid,ppid,command`

平台可以不同，但原则不变：

```text
先证明归属，再清理进程。
```

## 最终原则

这类问题不要按现象修：

```text
端口被占用 -> 杀掉端口进程
```

应该按根因边界修：

```text
端口被当前项目的残留开发进程占用 -> 自动清理
端口被其他进程占用 -> 中止并提示
```

这样既能提升本地开发体验，也不会把风险扩散到其他项目或系统服务。
