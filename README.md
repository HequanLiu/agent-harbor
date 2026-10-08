# AgentHarbor · 智港

基于 AgentScope 的多租户通用智能体框架。增加账号、登录会话、工作空间与成员管理。

## 本地启动（Windows）

需要 Python 3.11、uv、Node.js 22.12+ 和 pnpm 11.19.0（可用 Corepack 启用）。无需另装 Redis 或数据库服务。前端使用从原示例适配的 pnpm 锁文件，固定兼容版本。

```powershell
cd D:\my-project\agent-harbor
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

打开 http://127.0.0.1:5177，点击“第一次使用？创建账号”。自行设置邮箱、至少 10 字符的密码和空间名称，没有内置管理员密码。

在界面添加模型提供商凭据、创建 Agent、选择模型后开始对话。未配置有效模型凭据时不能获得真实模型回复。不会从原项目复制 `.env` 或模型密钥。

```powershell
# 停止本项目记录的进程
powershell -ExecutionPolicy Bypass -File scripts\stop.ps1
# 后端测试
cd apps\server
..\..\.venv\Scripts\python.exe -m pytest -q
# 前端生产构建
cd ..\web
npm.cmd run build
```

`.env` 控制 API/前端端口；改动前端端口时同步更新 `HARBOR_ALLOWED_ORIGINS`。脚本遇到端口占用会报错，不会终止未知进程。日志在 `.runtime/`。

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
apps/web/              React + TypeScript + Vite
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

## Windows 客户端

已接入 Tauri 2，客户端开发、构建和后端连接方式见 [桌面端说明](docs/desktop.md)。
