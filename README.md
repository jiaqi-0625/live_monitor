# 汽车直播智能辅助工具

面向内部盯播优化师的实时直播监控试点。当前版本支持：

- Windows 系统音频采集；
- Chrome/Edge 直播标签页音频采集；
- 懂车云店实时大屏指标采集；
- 抖音直播链接解析和服务器直连监听；
- 抖音、懂车云店场次标记；
- 浏览器实时监控工作台；
- WebSocket 音频传输和连接状态；
- 阿里云实时语音识别；
- WAV 录音、转写和历史场次保存。
- OpenAI 兼容大模型实时诊断、动作建议和推荐话术。
- 用户注册、管理员审核、角色管理，以及场次和语料按账号隔离。

## 项目结构

```text
apps/
  web/            React/Vite 浏览器工作台
  browser-extension/ Chrome/Edge 标签页音频与大屏数据采集
  collector-win/  Windows WASAPI 音频采集助手
services/
  api/            FastAPI 后端、实时通道和 ASR 适配器
docs/
  aliyun-asr-setup.md  阿里云配置说明
```

## 本地运行

### 后端

```powershell
cd services/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 浏览器工作台

```powershell
pnpm install
pnpm dev:web
```

访问 `http://127.0.0.1:5173`。

### Windows 采集助手

```powershell
cd apps/collector-win
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python -m collector
```

先在浏览器创建场次，再将完整场次 ID 粘贴到采集助手。

### 抖音链接直连监听

创建抖音场次时填写 `https://live.douyin.com/房间号`，进入场次后：

1. 点击“测试链接抓取”确认直播流在线；
2. 点击“开始链接监听”；
3. 服务器使用 Streamlink 解析媒体地址，通过 FFmpeg 提取 16 kHz 单声道音频；
4. 音频会同时写入 WAV 录音并发送给阿里云实时语音识别；
5. 点击“停止链接监听”完成 WAV 封装。

链接直连监听和 Windows 采集助手不能同时连接同一场次。直播间未开播时可以直接重试，不会锁死场次。

## 语音识别模式

默认使用 `mock` 验证音频链路，不识别真实讲话。启用阿里云：

```dotenv
ASR_PROVIDER=aliyun
ALIYUN_NLS_APPKEY=项目AppKey
ALIYUN_ACCESS_KEY_ID=RAM用户AccessKeyID
ALIYUN_ACCESS_KEY_SECRET=RAM用户AccessKeySecret
```

完整步骤见 [阿里云实时语音识别配置](docs/aliyun-asr-setup.md)。

## 浏览器扩展

首版推荐使用 `apps/browser-extension`。扩展直接采集当前直播标签页声音，并捕获懂车云店大屏指标接口，不读取或上传 Cookie。安装方法见
`apps/browser-extension/README.md`。

## DeepSeek 与 AI 配置中心

管理员可在“账号权限管理 → AI 配置中心”分别配置“AI 实时分析”和
“整理语料库”。配置保存后对所有启用账号即时生效；API Key 只写不回显，
并以密文保存。首期仅支持 DeepSeek 官方 API。

环境变量仍可作为管理员尚未保存配置时的初始回退：

```dotenv
LLM_API_BASE=https://api.deepseek.com
LLM_API_KEY=DeepSeek API Key
LLM_MODEL=deepseek-chat
LLM_ANALYSIS_INTERVAL_SECONDS=60
```

服务器会长期保存大屏指标，并按设定间隔结合最近转写生成风险判断、建议动作和主播推荐话术。未配置 API Key 时仍可测试音频、转写和指标采集。

实时分析和整场复盘在调用大模型前都会执行本地语料检索：禁用与约束、标准话术、
指标阈值优先进入上下文，再使用 [rank_bm25](https://github.com/dorianbrown/rank_bm25)
从当前优化师的已启用语料中召回与指标、车型和转写相关的片段。检索过程不依赖外部
向量数据库，并在服务日志中记录命中的语料 ID、分类、分数和原因。

使用 Docker Compose 部署时，也可以在项目根目录 `.env` 中配置
`DEEPSEEK_API_KEY`，Compose 会将其映射为 API 服务使用的
`LLM_API_KEY`。默认模型为 `deepseek-chat`，也可以通过
`DEEPSEEK_MODEL` 覆盖。

生产环境建议配置 `APP_CONFIG_ENCRYPTION_KEY`（Fernet 密钥）；未显式配置时，
服务端会在持久化数据目录生成 `.ai-config.key`，该文件必须随数据库一起备份。

## 账号与权限

新用户注册后默认为“待审核”，需要管理员在“账号权限管理”中启用。用户分为
`admin`（管理员）和 `operator`（优化师）；优化师只能访问自己创建的直播场次和语料，
管理员可查看全部场次并管理账号。

首次启动前，在 `services/api/.env` 中配置初始管理员：

```dotenv
AUTH_REQUIRED=true
AUTH_SESSION_DAYS=14
AUTH_COOKIE_SECURE=false
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=请填写强密码
BOOTSTRAP_ADMIN_DISPLAY_NAME=系统管理员
```

当前以 HTTP IP 访问时，`AUTH_COOKIE_SECURE` 必须为 `false`；后续启用 HTTPS 后应改为
`true`。初始管理员创建成功后会保存在数据库中，密码不要提交到代码仓库或日志。

## 验证

```powershell
cd services/api
python -m pytest -q
python -m ruff check app tests

cd ..\..
pnpm lint:web
pnpm build:web
```

## 安全要求

- 不得提交 `.env`、AccessKey、服务器密码或 Token；
- 不得提交直播录音、转写和内部资料；
- 生产密钥只通过服务器环境变量注入；
- 仓库是公开仓库，推送前必须检查敏感信息。
