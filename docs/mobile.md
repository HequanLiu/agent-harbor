# 移动端（首版）

模块：`apps/mobile`。选择 **Expo SDK 57 + React Native 0.86 + TypeScript + Expo Router**，复用现有 React/TypeScript 经验和后端接口。原生流式网络用 `expo/fetch`，登录会话用 `expo-secure-store`。Android 优先，保留 iOS 支持；Web 用于预览与自动化验收。

## 已实现

- 已有邮箱账号登录、显示/隐藏密码、会话失效返回登录、退出、切换工作空间。
- 原生端安全保存登录令牌，24 小时服务端有效期。登录页可勾选记住密码，验证成功后保存账号密码，退出后仍可自动填充；取消勾选立即删除。原生端使用 SecureStore，Web 使用 IndexedDB 中的 AES-GCM 密文和不可导出的 CryptoKey，不写明文 localStorage。Web 登录令牌仍只在内存保存，刷新后重新登录；记住密码需要 HTTPS 或本机安全上下文，浏览器本地加密不等同于系统密钥库，同源脚本仍可使用密钥。
- 首页直接进入对话：默认第一个 Agent，优先恢复它最近且凭据有效的会话；没有则选首个已有服务的未停用模型并创建会话。
- 顶部显示当前 Agent 和连接状态，隐藏模型名；右上角直接新建对话，左上角菜单进入历史列表，可切换 Agent。新建自动沿用当前或最近会话的模型配置。
- 文字流式回复、历史分页、停止生成、断线自动重连、回到前台恢复会话。
- 默认模型匹配只获取凭据 id/name/type，不把模型 API Key 下发到手机。
- 工具确认支持允许一次、拒绝、允许并记住服务端建议规则；展示工具参数，支持断线恢复并防止重复提交。外部执行工具仍需桌面端处理。

Agent、模型凭据、工具和知识库配置仍在桌面端操作。消息支持 Markdown 标题、列表、引用、粗斜体、链接、代码块和表格，流式回复及历史记录使用同一渲染方式；代码块和表格可横向滚动。暂不做附件、语音、完整工具结果卡片和注册页。

## 开发启动

使用本分支的后端（增加了移动登录接口）；旧版后端不能处理移动登录。依赖与桌面 Web 独立，移动端使用 npm 和自己的 package-lock.json。

```powershell
cd apps/mobile
npm.cmd ci
Copy-Item .env.example .env
# 编辑 .env 中 EXPO_PUBLIC_API_URL
npm.cmd start
```

在兼容 SDK 57 的 Expo Go 中扫描终端二维码。Android 模拟器也可以 `npm.cmd run android`；Web 预览用 `npm.cmd run web`，通常为 8081 端口。

地址全部由环境配置，登录页不显示服务地址输入框：

| 运行位置 | EXPO_PUBLIC_API_URL |
| --- | --- |
| 电脑 Web / iOS 模拟器 | http://127.0.0.1:8017/ |
| Android Studio 模拟器 | http://10.0.2.2:8017/ |
| 手机真机 | http://电脑的局域网IP:8017/ |
| 正式部署 | HTTPS 后端地址 |

未设置环境变量时，Android 默认使用 10.0.2.2，Web 本机预览跟随页面的 localhost / 127.0.0.1，其余平台使用 127.0.0.1。`.env.example` 默认不覆盖自动地址；真机必须改为电脑局域网 IP，手机中的 127.0.0.1 指手机自身。修改后重启 Metro，必要时 `npm.cmd start -- --clear`。`EXPO_PUBLIC_*` 会进入客户端包，只能放公开配置，不可放密钥。

真机与电脑需处在可互通网络，测试后端的根目录 `.env` 设置 `HARBOR_HOST=0.0.0.0` 才能被手机访问。只对自己的开发局域网开放。后端启动仍用根目录脚本或：

```powershell
# 在仓库根目录，先完成 Python 环境安装
.venv\Scripts\python.exe apps/server/main.py
```

Web 预览需要 `HARBOR_ALLOWED_ORIGINS` 包含实际页面来源。模板已经加入 `http://localhost:8081` 与 `http://127.0.0.1:8081`；已有 `.env` 需同步更新并重启后端。Web 页面来源必须在白名单内。移动端登录与 Bearer 请求允许白名单来源跨站访问 API（包括 localhost 页面连接 127.0.0.1）；桌面 Cookie 登录及 Cookie 写入仍禁止跨站请求。原生请求无浏览器 Origin，不需要为 Expo Go 配置页面来源。

## 原生构建

`npm.cmd run export:android -- --output-dir dist-android` 只验证 JS/Hermes 资源导出，不产生 APK。

本机安装 Android Studio / Android SDK 后，可用 `npx.cmd expo run:android` 生成开发构建；iOS 本机构建需要 macOS / Xcode。也可按 Expo 官方 EAS 文档配置账号、签名和构建配置后构建，当前未上传代码到 EAS。正式安装包使用 HTTPS 服务；局域网 HTTP 验收优先使用 Expo Go，独立安装包的 Android 网络安全策略需要随部署单独配置。

## 验证

```powershell
cd apps/mobile
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npx.cmd expo-doctor
npm.cmd run export:web
npm.cmd run export:android -- --output-dir dist-android
```

端到端测试需要 Python 的 httpx、Playwright 及 Edge。先为测试导出 Web，再从根目录运行；脚本使用 18017/18018，端口被占用会退出，不停止其他进程。

```powershell
$env:EXPO_PUBLIC_API_URL='http://127.0.0.1:18017/'
npm.cmd --prefix apps/mobile run export:web
Remove-Item Env:EXPO_PUBLIC_API_URL
# worktree 没有自己的 .venv 时，可指向已有环境
$env:HARBOR_PYTHON='D:\my-project\agent-harbor\.venv\Scripts\python.exe'
python -X utf8 scripts/smoke_mobile.py
```

脚本启动临时数据库和本地 OpenAI 兼容模型桩，验证失败登录、密码切换、登录、会话创建、SSE、历史重连去重、订阅前恰好结束回复的竞态、停止、注销和凭据投影；不调用付费模型。截图/日志在 `.runtime/mobile-smoke/`，运行结束后退出测试进程。测试构建指向临时服务，不作为日常预览构建；日常使用重新执行 `npm.cmd run web` 或按正常环境重新导出。

本次验证：后端 20 项测试、移动端 23 项协议/请求及对话测试、TypeScript、lint、Expo Doctor 21 项检查、Web/Android JS 导出与手机尺寸浏览器端到端流程通过。**尚未安装到 Android/iOS 真机，未验证原生键盘、SecureStore 与后台恢复的实际设备表现，也未生成签名 APK/IPA。**

依赖审计（2026-10-09）：SDK 兼容依赖仍报告 28 项传递依赖公告（18 high、10 moderate），来源包含 braces、node-forge、decode-uri-component、uuid；npm 建议的部分修复会跨 SDK 大版本或降级，未执行强制修复。公开发布前需跟进上游兼容补丁并重新审计。

参考：[Expo SDK 57 流式网络](https://docs.expo.dev/versions/v57.0.0/sdk/expo/)、[SecureStore](https://docs.expo.dev/versions/latest/sdk/securestore/)、[Expo Router](https://docs.expo.dev/router/installation/)。

移动端 Logo 直接复用 `apps/web/src-tauri/icons/icon.png`，主色与桌面 `--primary: #18191c` 一致，青绿色仅用作品牌点缀。浏览器回归覆盖记住密码的失败不保存、成功保存、退出/刷新恢复、取消后清除和密文存储。

### 新建对话

对话页右上角为新建对话，直接沿用当前会话的完整模型配置；会话列表新建时沿用所选 Agent 最近可用的模型配置。没有历史配置时自动选择已配置服务中的可用模型，无需弹出模型选择。模型凭据失效时会尝试可用配置；没有可用服务则提示前往桌面端配置。顶部隐藏模型名，顶部只显示连接状态小圆点和 Agent 名称，不显示“已连接”文字；回复、待确认及断线时显示必要提示。连接异常仍自动重连，也可通过错误提示中的“重试”恢复。
