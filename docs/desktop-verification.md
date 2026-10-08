# Windows 客户端验收

验收日期：2026-10-08。项目：AgentHarbor 0.1.0。

## 已通过

- `pnpm run test:desktop`：7 项通过，覆盖服务地址、hash 路由、原生 Blob MIME、取消和超时。
- 后端 `test_auth.py` + `test_desktop_origins.py`：12 项通过。
- 前端 TypeScript/Vite 发布构建、修改文件 ESLint、Rust release 与 NSIS x64 打包通过。
- 直接启动发布版 `agent-harbor.exe`，通过 WebView2 的本地调试端口连接实际 Tauri 页面，确认来源为 `http://tauri.localhost`。
- 原生窗口中的注册、登录、退出重登、空间创建/切换和跨空间 Agent 隔离通过。
- 通过原生 HTTP Cookie 会话完成 SSE 聊天和 multipart Skill 文件夹上传。
- 原生权限拒绝远程明文 HTTP 地址。
- 独立代码复核提出的 Blob MIME 和取消语义问题已修复，并通过回归测试。

## 验收边界

原生测试使用独立后端数据目录和 WebView profile，未修改正式账号。模型为本机 OpenAI 兼容 fixture，没有调用付费模型。没有验收真实模型提供商、HTTPS 远程部署、系统保存对话框的人工交互和 PDF 阅读器显示，也未执行安装向导；验证的是已打包 EXE，NSIS 安装包已成功生成。安装包未签名。

原生验收截图和 JSON 报告随交付说明保存。启动脚本与连接方式见 `docs/desktop.md`。

安装包 SHA256：`002869078B2409FE690F56208691F030304DE5DA41A88A2ECBAFA62004BFB9AF`。
