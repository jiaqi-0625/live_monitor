# Windows 音频采集助手

## 功能

- 枚举Windows WASAPI回环设备；
- 采集电脑全部系统声音；
- 转换为16 kHz、单声道、PCM16音频；
- 通过WebSocket持续发送给后端；
- 显示采集状态和实时音量；
- 保存后端地址和最近音频设备。

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python -m collector
```

先在浏览器工作台创建场次，再把场次ID粘贴到采集助手。

## 后续打包

正式试点前使用PyInstaller生成Windows EXE。构建产物不得提交到公开仓库。

