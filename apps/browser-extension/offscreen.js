const captures = new Map();

function report(tabId, patch) {
  chrome.runtime
    .sendMessage({
      target: "background",
      type: "CAPTURE_STATUS",
      tabId,
      patch,
    })
    .catch(() => undefined);
}

function websocketUrl(serverUrl, sessionId) {
  const url = new URL(serverUrl);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = `/ws/audio/${encodeURIComponent(sessionId)}`;
  url.search = "source=browser_extension";
  return url.toString();
}

function toPcm16(input) {
  const pcm = new Int16Array(input.length);
  for (let index = 0; index < input.length; index += 1) {
    const value = Math.max(-1, Math.min(1, input[index]));
    pcm[index] = value < 0 ? value * 32768 : value * 32767;
  }
  return pcm;
}

function clearReconnectTimer(capture) {
  if (capture.reconnectTimer) clearTimeout(capture.reconnectTimer);
  capture.reconnectTimer = null;
}

function scheduleReconnect(capture) {
  if (capture.reconnectTimer || !captures.has(capture.tabId)) return;
  const delay = Math.min(10000, 1000 * 2 ** capture.reconnectAttempt);
  capture.reconnectAttempt += 1;
  capture.reconnectTimer = setTimeout(() => {
    capture.reconnectTimer = null;
    connectWebsocket(capture).catch(() => scheduleReconnect(capture));
  }, delay);
}

async function connectWebsocket(capture) {
  if (capture.websocket?.readyState === WebSocket.OPEN) return;
  if (capture.websocket) capture.websocket.close(1000, "reconnect");
  const socket = new WebSocket(websocketUrl(capture.serverUrl, capture.sessionId));
  capture.websocket = socket;
  socket.binaryType = "arraybuffer";
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("云端连接超时")), 12000);
    socket.onopen = () => {
      clearTimeout(timeout);
      clearReconnectTimer(capture);
      capture.reconnectAttempt = 0;
      report(capture.tabId, { connected: true, message: "浏览器扩展已连接，正在采集" });
      resolve();
    };
    socket.onerror = () => {
      clearTimeout(timeout);
      reject(new Error("无法连接云端音频通道"));
    };
    socket.onclose = (event) => {
      if (capture.websocket !== socket || !captures.has(capture.tabId)) return;
      report(capture.tabId, {
        connected: false,
        message:
          event.code === 4409
            ? "该场次已有其他音频采集连接"
            : "云端暂时断开，正在自动重连",
      });
      if (event.code !== 4409) scheduleReconnect(capture);
    };
  });
}

async function startMedia(capture, streamId) {
  capture.mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      mandatory: {
        chromeMediaSource: "tab",
        chromeMediaSourceId: streamId,
      },
    },
    video: false,
  });
  capture.audioContext = new AudioContext({ sampleRate: 16000 });
  capture.sourceNode = capture.audioContext.createMediaStreamSource(capture.mediaStream);
  capture.processorNode = capture.audioContext.createScriptProcessor(2048, 1, 1);
  capture.processorNode.onaudioprocess = (event) => {
    const input = event.inputBuffer.getChannelData(0);
    let peak = 0;
    for (let index = 0; index < input.length; index += 1) {
      peak = Math.max(peak, Math.abs(input[index]));
    }
    if (
      capture.websocket?.readyState === WebSocket.OPEN &&
      capture.websocket.bufferedAmount < 1024 * 1024
    ) {
      capture.websocket.send(toPcm16(input).buffer);
    }
    const now = Date.now();
    if (peak > 0.001) {
      capture.lastAudibleAt = now;
      if (capture.silenceWarningActive) {
        capture.silenceWarningActive = false;
        report(capture.tabId, {
          audioSilent: false,
          message: "标签页声音已恢复，正在采集和识别",
        });
      }
    } else if (
      !capture.silenceWarningActive &&
      now - capture.startedAt >= 8000 &&
      now - capture.lastAudibleAt >= 8000
    ) {
      capture.silenceWarningActive = true;
      report(capture.tabId, {
        audioSilent: true,
        message: "连续8秒未检测到声音，请播放并取消静音后重新采集",
      });
    }
    if (now - capture.latestLevelSentAt >= 400) {
      capture.latestLevelSentAt = now;
      report(capture.tabId, { level: Math.min(1, peak) });
    }
  };
  capture.sourceNode.connect(capture.processorNode);
  capture.processorNode.connect(capture.audioContext.destination);
  capture.sourceNode.connect(capture.audioContext.destination);
  const track = capture.mediaStream.getAudioTracks()[0];
  track.addEventListener("ended", () => {
    report(capture.tabId, {
      connected: false,
      level: 0,
      message: "直播标签页音频已停止，请重新连接该标签页",
    });
  });
}

async function cleanupCapture(capture) {
  clearReconnectTimer(capture);
  if (capture.processorNode) {
    capture.processorNode.disconnect();
    capture.processorNode.onaudioprocess = null;
  }
  if (capture.sourceNode) capture.sourceNode.disconnect();
  if (capture.mediaStream) {
    for (const track of capture.mediaStream.getTracks()) track.stop();
  }
  if (capture.audioContext) await capture.audioContext.close();
  if (capture.websocket) capture.websocket.close(1000, "user stopped");
}

async function stopCapture(tabId) {
  const capture = captures.get(tabId);
  if (!capture) return;
  captures.delete(tabId);
  await cleanupCapture(capture);
}

async function startCapture(message) {
  await stopCapture(message.tabId);
  const capture = {
    tabId: message.tabId,
    tabTitle: message.tabTitle,
    serverUrl: message.serverUrl,
    sessionId: message.sessionId,
    websocket: null,
    mediaStream: null,
    audioContext: null,
    sourceNode: null,
    processorNode: null,
    reconnectTimer: null,
    reconnectAttempt: 0,
    latestLevelSentAt: 0,
    startedAt: Date.now(),
    lastAudibleAt: Date.now(),
    silenceWarningActive: false,
  };
  captures.set(message.tabId, capture);
  try {
    await connectWebsocket(capture);
    await startMedia(capture, message.streamId);
    report(capture.tabId, {
      active: true,
      connected: true,
      audioSilent: false,
      tabTitle: capture.tabTitle,
      message: "正在采集当前直播标签页",
    });
  } catch (error) {
    captures.delete(message.tabId);
    await cleanupCapture(capture);
    throw error;
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.target !== "offscreen") return false;
  const action =
    message.type === "START_CAPTURE"
      ? startCapture(message)
      : message.type === "STOP_CAPTURE"
        ? stopCapture(message.tabId)
        : Promise.resolve();
  action
    .then(() => sendResponse({ ok: true }))
    .catch((error) => {
      report(message.tabId, {
        connected: false,
        message: error instanceof Error ? error.message : String(error),
      });
      sendResponse({ error: error instanceof Error ? error.message : String(error) });
    });
  return true;
});
