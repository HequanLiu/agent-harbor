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

登录页默认连接 `http://127.0.0.1:8017/`。更改地址后点击“连接”，再登录。连接远程服务时使用 HTTPS；地址可以包含反向代理前缀，但不能包含账号密码、查询参数或片段。远程后端应在 `.env` 设置 `HARBOR_SECURE_COOKIE=true`，并保留 `HARBOR_ALLOWED_ORIGINS` 中的 Tauri 来源。

客户端关闭后需要重新登录。服务地址保存在当前 Windows 用户的 WebView 数据中，开发版与安装版可能各自保存；账号、Agent 和历史会话保存在后端。

## 开发与构建

需要 Node.js、pnpm、Rust stable MSVC、Visual Studio C++ Build Tools 和 WebView2。

```powershell
cd D:\my-project\agent-harbor\apps\web
pnpm install --frozen-lockfile
pnpm run test:desktop
pnpm run desktop:dev
```

开发命令自动启动 Vite，要求 5177 端口空闲；如已有浏览器版开发进程，请先使用项目的 `scripts\stop.ps1` 停止，再单独启动后端。Tauri 开发地址固定为 5177；若更改 `.env` 中的 `HARBOR_WEB_PORT`，同时修改 `src-tauri\tauri.conf.json` 的 `build.devUrl`。

在项目根目录打包：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\desktop.ps1 -Mode Build
```

首次构建会下载 Rust 和 NSIS 工具链。锁文件 `pnpm-lock.yaml` 与 `src-tauri/Cargo.lock` 应一起纳入版本管理。

## 实现范围

- 原生 HTTP 接口负责 Cookie 会话、JSON 请求、SSE 流和 multipart 上传；浏览器版保留同源代理方式。
- 桌面路由使用 hash，支持空间切换、退出登录和页面刷新。
- 知识库图片/PDF 先经认证读取为 Blob；下载使用系统保存对话框，只允许写入用户选定的文件。
- 原生上传显示等待/完成状态，不伪造逐字节进度。HTTP 插件会将上传内容读入内存，大文件上传仍需后续优化。
- 未加入自动更新、托盘、开机启动、代码签名或 Python sidecar。本版本安装包未签名。
