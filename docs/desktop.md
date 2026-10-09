# AgentHarbor Windows 客户端

现有 React 前端使用 Tauri 2 封装，发布版内置前端资源，不需要启动 Vite。Python / AgentScope 后端独立运行，未打包进客户端。

## 本地使用

在 `D:\my-project\agent-harbor` 启动后端（保持这个终端运行）：

```powershell
.\.venv\Scripts\python.exe -X utf8 apps\server\main.py
```

如果已通过 `scripts\dev.ps1` 启动后端，则直接运行客户端即可，不要重复启动同一端口：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\desktop.ps1
```

也可以运行 `apps\web\src-tauri\target\release\agent-harbor.exe`，或使用 `apps\web\src-tauri\target\release\bundle\nsis` 下的安装包。

登录页自动连接后端，无需输入服务地址。在项目根目录 `.env` 中配置：

```dotenv
VITE_HARBOR_SERVER_URL=http://127.0.0.1:8017/
```

未配置时桌面端默认连接上述地址。此配置也用于浏览器开发服务器的 `/api` 代理。修改后重启 Vite；桌面发布版需要重新构建，运行已有 exe 时修改 `.env` 不会生效。连接远程服务时使用 HTTPS；地址可以包含反向代理前缀，但不能包含账号密码、查询参数或片段。远程后端应在 `.env` 设置 `HARBOR_SECURE_COOKIE=true`，并保留 `HARBOR_ALLOWED_ORIGINS` 中的 Tauri 来源。

客户端关闭后需要重新登录。登录页勾选“记住密码”后，仅在登录成功时将邮箱和密码存入当前 Windows 用户的系统凭据库，下次打开自动回填；取消勾选立即清除保存内容。凭据按后端地址隔离，不写入 localStorage。密码框的眼睛按钮可切换显示/隐藏，默认隐藏；浏览器版使用浏览器自身的密码管理器。服务地址由构建时的环境配置决定，不再读取 WebView 中旧的地址缓存；账号、Agent 和历史会话保存在后端。

## 开发与构建

需要 Node.js、pnpm、Rust stable MSVC、Visual Studio C++ Build Tools 和 WebView2。以下命令以 `light-theme` worktree 为例，在其他工作区使用时替换为对应根目录。

### 首次准备依赖

每个 worktree 都需要独立安装前端依赖。不要通过 junction 或符号链接共享整个 `node_modules`，否则 pnpm 的相对链接可能解析错误，出现 `Cannot find module ... @tauri-apps\cli\tauri.js`。pnpm 会复用本机包缓存。

```powershell
cd D:\my-project\agent-harbor\.worktrees\light-theme
Push-Location apps\web
pnpm.cmd install --frozen-lockfile
pnpm.cmd run tauri --version
pnpm.cmd run test:desktop
Pop-Location
```

`tauri --version` 应能输出 CLI 版本。Python 虚拟环境 `(.venv)` 不提供 Node/Tauri 依赖。

### 开发模式启动

先按“本地使用”章节启动后端并保持运行，然后在另一个终端启动桌面开发模式：

```powershell
cd D:\my-project\agent-harbor\.worktrees\light-theme
powershell -ExecutionPolicy Bypass -File scripts\desktop.ps1 -Mode Dev
```

此命令自动启动 Vite 和 Tauri 开发客户端，前端修改支持热更新；首次运行仍需编译 Rust 桌面端。终端保持运行，使用 `Ctrl+C` 停止开发进程。

开发命令要求 5177 端口空闲，主工作区和其他 worktree 的 Vite 也可能占用该端口。先在对应终端停止占用端口的项目开发进程，并确保后端仍在运行。Tauri 开发地址固定为 5177；若更改当前 worktree 根目录 `.env` 中的 `HARBOR_WEB_PORT`，同时修改 `apps\web\src-tauri\tauri.conf.json` 的 `build.devUrl`。新 worktree 不会自动复制主工作区未跟踪的 `.env`；需要自定义后端地址时，在当前 worktree 配置 `VITE_HARBOR_SERVER_URL`。

### 构建发布版并运行

在当前 worktree 根目录执行构建，成功后再启动：

```powershell
cd D:\my-project\agent-harbor\.worktrees\light-theme
powershell -ExecutionPolicy Bypass -File scripts\desktop.ps1 -Mode Build
powershell -ExecutionPolicy Bypass -File scripts\desktop.ps1 -Mode Run
```

省略 `-Mode` 等同于 `-Mode Run`，只运行已有 exe，不会自动构建。若提示 `Build the desktop client first`，说明当前 worktree 中尚未生成桌面发布版。

产物位于当前 worktree：

- 可执行文件：`apps\web\src-tauri\target\release\agent-harbor.exe`
- NSIS 安装包：`apps\web\src-tauri\target\release\bundle\nsis\`

`pnpm.cmd run build` 仅构建 Web 前端，不会生成桌面 exe；`-Mode Build` 才会构建前端、编译桌面端并生成安装包。发布版内置前端，不需要 Vite，但仍需独立运行后端。

首次桌面构建可能需要下载 Rust 依赖和 NSIS 打包工具。脚本默认限制构建并发与 Node 内存用量；若已设置相关环境变量，则保留已有值。锁文件 `pnpm-lock.yaml` 与 `src-tauri/Cargo.lock` 应一起纳入版本管理。

## 实现范围

- 原生 HTTP 接口负责 Cookie 会话、JSON 请求、SSE 流和 multipart 上传；浏览器版保留同源代理方式。
- 桌面路由使用 hash，支持空间切换、退出登录和页面刷新。
- 知识库图片/PDF 先经认证读取为 Blob；下载使用系统保存对话框，只允许写入用户选定的文件。
- 原生上传显示等待/完成状态，不伪造逐字节进度。HTTP 插件会将上传内容读入内存，大文件上传仍需后续优化。
- 未加入自动更新、托盘、开机启动、代码签名或 Python sidecar。本版本安装包未签名。
