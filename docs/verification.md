# AgentHarbor · 智港

项目位置：`D:\my-project\agent-harbor`

本地入口：http://127.0.0.1:5177

首次使用点击“第一次使用？创建账号”，自行设置邮箱、密码和空间名称。没有默认管理员密码。注册后添加模型提供商凭据、创建 Agent、选择模型即可使用真实对话。

## 已实现

- React / TypeScript 前端，FastAPI / AgentScope 后端。
- 账号注册、登录、退出和 24 小时有效的服务端会话。
- 创建多个租户空间、切换空间、所有者添加/移除已注册成员。
- 服务端身份校验，按租户与用户隔离 Agent、会话、凭据和知识库数据。
- 同一租户中的成员资源各自私有，暂未实现共享 Agent / 共享会话。
- 独立工作目录、目录浏览和下载边界检查。
- 对话和账号使用 SQLite 持久化，向量数据使用本地 Qdrant 持久化。
- 沿用上游模型、MCP、技能、知识库、渠道和定时任务界面；外部集成需另行配置。

## 启动与停止

依赖已安装。以后启动：

```powershell
cd D:\my-project\agent-harbor
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

停止：

```powershell
cd D:\my-project\agent-harbor
powershell -ExecutionPolicy Bypass -File scripts\stop.ps1
```

迁移到另一台机器时先运行 `scripts\setup.ps1`。前端使用 pnpm 11.19.0 与固定锁文件，后端使用独立 `.venv` 和 `requirements.lock`。项目不依赖原 `D:\GithubProject\agentscope` 路径。

默认前端端口 `5177`，后端端口 `8017`。配置在项目 `.env`，日志在 `.runtime/`，正式数据在 `data/`。改动前端端口时同步更新允许的来源地址。

## 验证结果（2026-10-08）

- 后端 11 项测试通过：认证、会话撤销和过期、注册开关、成员权限、跨租户及凭据隔离、文件目录边界、相同 workspace ID 隔离、重启后读取会话。
- 最终目录的 Python 实际加载 `D:\my-project\agent-harbor\vendor\agentscope`。
- 前端 TypeScript 检查、生产构建及修改文件的 ESLint 检查通过。
- 真实 HTTP 验证：注册、配置凭据、创建 Agent/会话、触发对话、SSE 回复、消息持久化。
- Edge 浏览器验收：注册/登录/退出、创建和切换租户、添加成员、跨租户数据隔离，以及在聊天页面发送消息并显示流式回复。390px 下无横向溢出，聊天输入框在可见区域内，无页面运行异常。
- 对话验证使用本机 OpenAI 兼容模拟端点，未调用付费模型；真实模型、MCP、第三方渠道和知识库嵌入尚需用户配置后验收。

测试账号和模拟凭据保存在单独的 `.runtime/browser-validation/`，正式实例使用空白的 `data/`。

## 当前边界

这是可运行的单机多租户开发基础版。LocalWorkspace 的 shell/MCP 工具使用宿主机权限，尚无操作系统级沙箱；不应直接对不可信公网租户开放。生产环境还需容器/远程沙箱、密钥加密、审计、资源配额和部署加固。本版不包含计费、SSO、密码找回、共享资源和租户删除。

上游 Apache-2.0 许可保留；来源与快照记录见项目 `UPSTREAM.md`。原仓库未被修改。
