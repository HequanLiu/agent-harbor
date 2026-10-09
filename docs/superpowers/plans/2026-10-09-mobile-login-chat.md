# 移动端登录与对话实施计划

**Goal:** 在独立 worktree 的 `apps/mobile` 交付登录和文字对话首版。
**Architecture:** Expo Router + React Native；后端新增移动端 Bearer 登录入口，复用可撤销会话；桌面 Cookie 登录与租户校验继续工作。客户端通过 GET SSE 订阅、POST 触发回复；断线重连先读取持久化历史，再订阅事件。
**Tech Stack:** Expo SDK 57、React Native 0.86、React 19、TypeScript 6、expo/fetch、SecureStore。

## 方案与边界
- 选择 Expo：沿用 React/TypeScript，原生移动端交互，官方流式 fetch 和安全存储。
- Tauri 移动端可复用 Web UI，但本次单独的手机交互和鉴权仍要改造，暂不增加移动端 Rust 工程。
- Flutter 需新增 Dart 技术栈，此首版没有收益。
- 默认 Android 优先，代码兼容 iOS；Web 为本机预览和回归入口。
- 首版：邮箱密码登录、密码可见切换、安全保存会话、过期回登录、退出、空间切换、选择已有 Agent、会话历史、新建会话、选择已有模型、文本流式回复、停止、网络重试。
- 工具审批仅提示到桌面端处理，并提供停止；模型密钥/Agent/工具/知识库配置继续在桌面端。
- 不新建真实账号、不调用付费模型；验收使用临时数据库与本地模型 fixture。

## 实施步骤
- [x] 创建 `.worktrees/mobile` / `feat/mobile-login-chat`，后端 9 项和桌面 7 项基线通过。
- [x] `apps/server/tests/test_mobile_auth.py`：先验证 token 登录缺失；覆盖 Bearer 鉴权、无 Cookie 回退、租户隔离、切换、注销撤销、缓存与跨域来源限制。
- [x] `apps/server/harbor/auth.py`：增加 `/harbor/auth/mobile/login`；统一从 Bearer 或 Cookie 提取会话，注销/空间切换使用同一会话；增加受来源白名单限制的 CORS。
- [x] `apps/server/harbor/mobile.py`：仅返回已有模型凭据 id/type/name，不向手机传模型密钥。
- [x] `apps/mobile/src/core/`：类型、SSE 分帧/UTF-8/去重、消息投影、可取消会话控制；使用 Node 单测覆盖拆包与重放。
- [x] `apps/mobile/src/api/`、`src/auth/`：原生流式 fetch、超时/401、SecureStore、环境地址。
- [x] `apps/mobile/src/app/`、`src/components/`：登录、首页会话、模型选择和聊天界面，安全区/键盘/可访问性。
- [x] TypeScript、Expo lint/doctor、协议单测、后端回归、Android/Web JS 导出。
- [x] 使用真实临时后端和本地 fixture 验收浏览器登录、SSE、历史、停止、注销；记录原生未验证边界。
- [x] `docs/mobile.md`：启动/局域网地址/Expo Go/打包/首版范围与验收说明。

## 核心契约
`POST /harbor/auth/mobile/login {email,password}` 返回 `{access_token,token_type:'bearer',expires_in:86400,identity}`，响应禁止缓存；失败不写会话。
`Authorization: Bearer <token>`、`X-Tenant-ID` 在 JSON 与 SSE 请求中一致；token 失效清除本地会话。
`POST /chat/ {agent_id,session_id,input:{role:'user',name:'user',content:[{type:'text',text}]}}` 仅在 SSE 订阅成功后触发，不自动重试 POST。
`GET /sessions/{id}/stream?agent_id=...` 解析 AgentScope 事件；恢复连接时用服务端历史覆盖本地推测状态。

## 参考
- https://docs.expo.dev/versions/v57.0.0/sdk/expo/
- https://docs.expo.dev/versions/latest/sdk/securestore/
- https://docs.expo.dev/router/installation/

## 审查收尾

独立审查发现并修复历史读取与订阅之间的完成事件丢失、长回复重放日志截断两个边界。补充完成后的持久化历史校准、未知 reply_id 消息占位和回归测试；延迟 SSE 订阅的真实后端浏览器场景通过。复查未发现新的阻塞问题。
