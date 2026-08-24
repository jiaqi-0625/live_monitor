# 阿里云实时语音识别配置

本文用于将汽车直播监控工具从 `mock` 模式切换到阿里云智能语音交互的实时语音识别。

## 1. 创建独立 RAM 用户

不要使用阿里云主账号 AccessKey。

1. 进入阿里云 RAM 访问控制；
2. 创建仅供本项目使用的 RAM 用户，例如 `live-monitor-asr`；
3. 为该用户授予官方 NLS 权限 `AliyunNLSFullAccess`；
4. 为 RAM 用户创建 AccessKey；
5. 安全保存 `AccessKey ID` 和仅显示一次的 `AccessKey Secret`。

密钥不得粘贴到 GitHub、代码、截图或普通文档。

## 2. 创建智能语音交互项目

1. 进入阿里云智能语音交互控制台；
2. 新建项目；
3. 启用实时语音识别；
4. 选择支持 16 kHz 普通话的识别模型；
5. 保存项目并复制项目 `AppKey`。

当前采集端发送的音频是：

- PCM；
- 16bit；
- 单声道；
- 16000 Hz。

与阿里云 WebSocket 实时语音识别的输入要求一致。

## 3. 配置后端

在服务器的 `services/api` 目录创建 `.env`，不要提交该文件：

```dotenv
APP_ENV=production
ASR_PROVIDER=aliyun

ALIYUN_NLS_APPKEY=替换为项目AppKey
ALIYUN_ACCESS_KEY_ID=替换为RAM用户AccessKeyID
ALIYUN_ACCESS_KEY_SECRET=替换为RAM用户AccessKeySecret
ALIYUN_NLS_REGION_ID=cn-shanghai
ALIYUN_NLS_WEBSOCKET_URL=wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1
```

如已在语音自学习平台创建汽车品牌和车型热词词表，再增加：

```dotenv
ALIYUN_NLS_VOCABULARY_ID=替换为泛热词ID
```

首轮联调可以暂不配置热词。

## 4. 安装依赖并启动

```bash
cd services/api
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Windows PowerShell 激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

## 5. 检查配置

访问：

```text
GET /api/health
```

正确结果应包含：

```json
{
  "status": "ok",
  "asr_provider": "aliyun",
  "asr_configured": true
}
```

如果 `asr_configured` 是 `false`，说明 AppKey 或 AccessKey 环境变量缺失。

## 6. 首场联调

1. 在浏览器创建测试场次；
2. 将场次 ID 填入 Windows 采集助手；
3. 播放一段清晰的普通话汽车介绍；
4. 确认网页显示“音频采集：已连接”；
5. 在主播停顿后确认页面出现最终识别句子；
6. 停止采集并确认 WAV 录音可以播放；
7. 登录阿里云费用中心核对识别时长消耗。

## 7. 生产注意事项

- Token 通常约 24 小时有效，后端会使用 RAM AccessKey 自动获取并提前刷新；
- 识别费用从发送 `StartTranscription` 并开始推送音频后计算；
- 多个直播间同时推流时，时长分别累计；
- 30 小时套餐用于联调和首轮试点，正式使用前应评估月直播总时长；
- 录音永久保存需要单独配置 OSS，不能只依赖轻量服务器本地磁盘；
- 公开仓库中不得出现真实密钥、Token、录音或转写内容。

## 官方资料

- [智能语音交互产品](https://ai.aliyun.com/nls)
- [WebSocket 实时语音识别](https://help.aliyun.com/zh/isi/developer-reference/websocket)
- [开通与鉴权](https://help.aliyun.com/zh/isi/getting-started/start-here)
- [计费与并发](https://help.aliyun.com/zh/isi/product-overview/pricing)
