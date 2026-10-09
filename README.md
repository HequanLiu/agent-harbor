# AgentHarbor · 智港

基于 AgentScope 的多租户通用智能体框架。增加账号、登录会话、工作空间与成员管理。

## 本地启动（Windows）

### 1. 安装依赖

需要 Python 3.11、uv、Node.js 22.12+ 和 pnpm 11.19.0。无需另装 Redis 或数据库服务。桌面/Web 使用 pnpm 锁文件；移动端使用独立的 npm 锁文件。

下面的命令除特别说明外均在仓库根目录执行。使用移动端 worktree 时，根目录是 `D:\my-project\agent-harbor\.worktrees\mobile`，请在每个终端中进入同一个 checkout：

```powershell
cd D:\my-project\agent-harbor
# 如果使用移动端 worktree，改为：
# cd D:\my-project\agent-harbor\.worktrees\mobile

powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

安装脚本创建当前 checkout 的 `.venv`，安装后端及 Web/客户端依赖，并在缺少根目录 `.env` 时从模板复制，不覆盖已有配置。移动端依赖在下文单独安装。

### 2. 启动后端

客户端和移动端共用 Python 后端。在终端 A 执行并保持运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 apps\server\main.py
```

默认地址为 `http://127.0.0.1:8017/`。如果 worktree 尚未安装自己的 `.venv`，也可以使用主仓库已安装依赖的环境，启动的仍是当前 worktree 的后端源码：

```powershell
# 在 .worktrees\mobile 根目录执行
& 'D:\my-project\agent-harbor\.venv\Scripts\python.exe' -X utf8 apps\server\main.py
```

同一端口只启动一次后端。出现 `10048` / 端口占用时，先确认是否已有本项目后端运行，不要重复启动。前台启动的进程用 `Ctrl+C` 停止。

### 3. 启动 Windows 客户端

开发模式还需要 Rust stable MSVC、Visual Studio C++ Build Tools 和 WebView2。在终端 B、仓库根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\desktop.ps1 -Mode Dev
```

此命令自动启动 Vite 和 Tauri 窗口；`5177` 端口必须空闲，不要同时运行浏览器版的 Vite。Python 后端仍需按上一步单独启动。

构建和运行发布版：

```powershell
# 首次使用或代码更新后构建
powershell -ExecutionPolicy Bypass -File scripts\desktop.ps1 -Mode Build
# 启动已构建的客户端，不再启动 Vite
powershell -ExecutionPolicy Bypass -File scripts\desktop.ps1 -Mode Run
```

可执行文件在 `apps/web/src-tauri/target/release/agent-harbor.exe`，安装包在同目录的 `bundle/nsis/`。发布版不包含 Python 后端，运行时仍需后端在线。

登录页默认连接 `http://127.0.0.1:8017/`，不用输入服务地址。修改仓库根目录 `.env` 中的配置：

```dotenv
VITE_HARBOR_SERVER_URL=http://127.0.0.1:8017/
```

修改后重启开发服务；发布版需重新构建。更多说明见 [桌面端文档](docs/desktop.md)。

### 4. 启动移动端

移动端需使用包含移动登录接口的本分支后端。在另一个终端，从仓库根目录执行：

```powershell
cd apps\mobile
npm.cmd ci
# 首次创建配置；保留已有 .env
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
# 浏览器预览
npm.cmd run web -- --port 8081
```

打开 `http://localhost:8081`。登录页无需输入服务地址；默认自动连接本机 `8017` 端口。根目录 `.env` 的 `HARBOR_ALLOWED_ORIGINS` 须包含 `http://localhost:8081` 和 `http://127.0.0.1:8081`，当前模板已包含；已有配置需自行补充并重启后端。

使用模拟器或真机时，在 `apps/mobile` 中选择一种启动方式：

```powershell
# 启动 Metro，用兼容 SDK 57 的 Expo Go 扫描二维码
npm.cmd start
# 或启动已安装的 Android 模拟器
npm.cmd run android
```

后端地址配置在 **`apps/mobile/.env`** 的 `EXPO_PUBLIC_API_URL`，不同于根目录的后端配置：

| 运行位置 | 后端地址 |
| --- | --- |
| 电脑浏览器 | 默认跟随页面使用 `http://localhost:8017/` 或 `http://127.0.0.1:8017/` |
| Android Studio 模拟器 | 默认 `http://10.0.2.2:8017/` |
| 手机真机 | 设置 `EXPO_PUBLIC_API_URL=http://电脑局域网IP:8017/` |

真机与电脑需在可互通的网络中，并在根目录 `.env` 设置 `HARBOR_HOST=0.0.0.0` 后重启后端，允许开发网络访问 `8017` 端口。手机上的 `127.0.0.1` 指手机自身，不能用于连接电脑。修改移动端环境变量后重启 Metro，必要时使用 `npm.cmd start -- --clear`；`EXPO_PUBLIC_*` 只能放公开配置，不能放模型密钥。

移动端支持记住密码、默认 Agent/模型、直接新建对话、Markdown 流式回复和工具确认。更多配置、构建及验证步骤见 [移动端文档](docs/mobile.md)。

### 浏览器版一键启动

如果只使用浏览器版，可在仓库根目录执行以下命令，**一次启动后端和 Vite**，不用再单独启动后端：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

打开 `http://127.0.0.1:5177`。首次使用在客户端或浏览器版点击“第一次使用？创建账号”，设置邮箱、至少 10 字符的密码和空间名称；没有内置管理员密码。移动端使用已有账号登录。

在客户端或浏览器版添加模型提供商凭据、创建 Agent、选择模型后开始对话。未配置有效模型凭据时不能获得真实模型回复，不会从原项目复制 `.env` 或模型密钥。

```powershell
# 停止 dev.ps1 记录的本项目进程
powershell -ExecutionPolicy Bypass -File scripts\stop.ps1
```

端口默认值：后端 `8017`，Web/Tauri 开发服务 `5177`，移动端 Metro/Web `8081`。根目录 `.env` 控制后端和 Web 端口；调整浏览器来源时同步更新 `HARBOR_ALLOWED_ORIGINS`。Tauri 的开发地址固定为 `5177`，修改时还需同步 `apps/web/src-tauri/tauri.conf.json` 的 `build.devUrl`。启动脚本不会终止占用端口的未知进程，日志位于 `.runtime/`。

默认数据位于运行后端源码所属 checkout 的 `data/`，例如 mobile worktree 使用 `.worktrees/mobile/data/`，不在 `apps/server/`。可通过 `HARBOR_DATA_DIR` 指定其他目录；不要删除数据目录来升级或重装。

### 检查与构建

以下命令从仓库根目录执行：

```powershell
# 后端测试
.\.venv\Scripts\python.exe -m pytest apps\server\tests -q
# Web 生产构建
pnpm.cmd --dir apps/web run build
# 移动端检查
npm.cmd --prefix apps/mobile run typecheck
npm.cmd --prefix apps/mobile run lint
npm.cmd --prefix apps/mobile test
```

## 能力与隔离模型

- HttpOnly、SameSite cookie 登录，scrypt 密码哈希，数据库仅保存会话令牌摘要；会话 24 小时过期，退出即时撤销。
- 创建多个租户空间，切换空间，所有者添加/移除已注册成员；每次请求校验成员关系。
- AgentScope 数据身份由服务端组合 `tenant UUID + user UUID`，忽略客户端伪造的 `X-User-ID`。
- 同一租户内成员的 Agent、会话、模型凭据、知识库及文件仍各自私有；本版不包含共享 Agent 或共享会话。
- 会话流式事件、模型配置、MCP、技能、知识库、定时任务及渠道页面沿用上游。各外部服务需要自己的配置，页面存在不代表已完成外部集成验收。
- SQLite 持久化账号和运行数据，本地 Qdrant 持久化向量；数据位于 `data/`，升级或重新安装不应删除该目录。

## 目录

```text
apps/server/harbor/    身份、租户边界、运行时组合及工作空间适配
apps/server/tests/     身份、权限、会话与持久化测试
apps/web/              React + TypeScript + Vite + Tauri Windows 客户端
apps/mobile/           Expo + React Native，登录与文字对话
vendor/agentscope/     独立可安装的上游运行时源码快照
scripts/              安装、启动、停止脚本
docs/                 设计、实施计划及验收记录
data/                 运行时数据（不入版本库）
```

## 当前运行边界

这是单机开发基础版，默认只监听本机。HTTP 数据接口有身份与租户隔离，目录浏览/文件下载限制在 Agent 工作目录内。但 LocalWorkspace 中的 shell、MCP 和工具运行在宿主机权限下，**不具备操作系统级沙箱隔离**。不能直接作为对不可信租户开放的公网服务；此类部署应先接入容器/远程沙箱工作空间、资源限额、审计和网络策略。

账号和 Agent 元数据使用 SQLite，事件总线为内存模式，本版运行一个 Python worker；尚无计费、配额、SSO、密码找回和租户删除。模型凭据由上游存储，数据目录须按敏感数据管理；生产密钥加密和密钥管理服务尚未接入。`HARBOR_ALLOW_REGISTRATION=false` 可关闭自主注册，HTTPS 部署须启用 `HARBOR_SECURE_COOKIE=true`。

## 来源

保留 AgentScope 的 Apache-2.0 LICENSE。上游来源、快照信息与改动说明见 `UPSTREAM.md`。上游代码置于 vendor，业务扩展置于 apps/server/harbor，便于今后升级。
