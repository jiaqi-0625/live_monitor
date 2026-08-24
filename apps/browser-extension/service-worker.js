const MAX_CAPTURES = 3;

const defaultStore = {
  serverUrl: "http://124.220.147.243",
  captures: {},
};

const SESSION_ID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

async function getStore() {
  const stored = await chrome.storage.local.get(["captureStore", "captureState"]);
  if (stored.captureStore) {
    return {
      ...defaultStore,
      ...stored.captureStore,
      captures: stored.captureStore.captures || {},
    };
  }

  const legacy = stored.captureState;
  const captures = {};
  if (legacy?.active && legacy.tabId && legacy.sessionId) {
    captures[String(legacy.tabId)] = {
      active: true,
      connected: Boolean(legacy.connected),
      serverUrl: legacy.serverUrl || defaultStore.serverUrl,
      sessionId: legacy.sessionId,
      tabId: legacy.tabId,
      tabTitle: legacy.tabTitle || "直播标签页",
      level: legacy.level || 0,
      message: legacy.message || "正在恢复采集",
    };
  }
  const migrated = {
    serverUrl: legacy?.serverUrl || defaultStore.serverUrl,
    captures,
  };
  await chrome.storage.local.set({ captureStore: migrated });
  return migrated;
}

async function saveStore(store) {
  await chrome.storage.local.set({ captureStore: store });
}

function captureList(store) {
  return Object.values(store.captures).sort((left, right) =>
    String(left.tabTitle).localeCompare(String(right.tabTitle), "zh-CN"),
  );
}

async function getStatus(tabId) {
  const store = await getStore();
  const capture = store.captures[String(tabId)] || null;
  return {
    active: Boolean(capture),
    connected: Boolean(capture?.connected),
    serverUrl: capture?.serverUrl || store.serverUrl,
    sessionId: capture?.sessionId || "",
    tabId: tabId || null,
    tabTitle: capture?.tabTitle || "当前标签页尚未采集",
    level: capture?.level || 0,
    audioSilent: Boolean(capture?.audioSilent),
    message: capture?.message || "等待开始",
    metricCapturedAt: capture?.metricCapturedAt || null,
    metricUploadedAt: capture?.metricUploadedAt || null,
    metricEndpoint: capture?.metricEndpoint || "",
    metricError: capture?.metricError || "",
    captures: captureList(store),
    activeCount: captureList(store).length,
    maxCaptures: MAX_CAPTURES,
  };
}

async function updateCapture(tabId, patch) {
  const store = await getStore();
  const key = String(tabId);
  const current = store.captures[key];
  if (!current && !patch.sessionId) return getStatus(tabId);
  store.captures[key] = { ...(current || {}), ...patch, tabId };
  if (patch.serverUrl) store.serverUrl = patch.serverUrl;
  await saveStore(store);
  const status = await getStatus(tabId);
  chrome.runtime
    .sendMessage({ target: "popup", type: "STATUS_UPDATE", state: status })
    .catch(() => undefined);
  return status;
}

async function removeCapture(tabId, message = "采集已停止") {
  const store = await getStore();
  delete store.captures[String(tabId)];
  await saveStore(store);
  const status = await getStatus(tabId);
  status.message = message;
  chrome.runtime
    .sendMessage({ target: "popup", type: "STATUS_UPDATE", state: status })
    .catch(() => undefined);
  return status;
}

async function hasOffscreenDocument() {
  if (chrome.offscreen.hasDocument) return chrome.offscreen.hasDocument();
  const contexts = await chrome.runtime.getContexts({
    contextTypes: ["OFFSCREEN_DOCUMENT"],
    documentUrls: [chrome.runtime.getURL("offscreen.html")],
  });
  return contexts.length > 0;
}

async function ensureOffscreenDocument() {
  if (await hasOffscreenDocument()) return;
  await chrome.offscreen.createDocument({
    url: "offscreen.html",
    reasons: ["USER_MEDIA"],
    justification: "同时采集用户主动选择的多个直播标签页音频并发送到盯播服务器",
  });
}

function normalizeServerUrl(value) {
  const url = new URL(value);
  if (!["http:", "https:"].includes(url.protocol)) {
    throw new Error("服务器地址必须以 http:// 或 https:// 开头");
  }
  return url.toString().replace(/\/$/, "");
}

async function responseJson(response) {
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.detail || `云端请求失败：HTTP ${response.status}`);
  }
  return data;
}

async function resolveSessionId(serverUrl, suppliedValue) {
  if (SESSION_ID_PATTERN.test(suppliedValue)) return suppliedValue;
  let liveUrl;
  try {
    liveUrl = new URL(suppliedValue);
  } catch {
    throw new Error("请填写完整场次ID，或粘贴懂车云店直播链接");
  }
  if (
    !["http:", "https:"].includes(liveUrl.protocol) ||
    liveUrl.hostname !== "www.autoengine.com"
  ) {
    throw new Error("首版仅支持懂车云店直播链接自动创建场次");
  }

  const normalizedLiveUrl = liveUrl.toString();
  const sessions = await responseJson(await fetch(`${serverUrl}/api/sessions`));
  const existing = sessions.find(
    (session) =>
      session.live_url === normalizedLiveUrl &&
      (session.status === "created" || session.status === "live"),
  );
  if (existing) return existing.id;

  const roomId = liveUrl.searchParams.get("room_id") || "未知直播间";
  const created = await responseJson(
    await fetch(`${serverUrl}/api/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: `懂车云店直播 ${roomId}`,
        platform: "dongchedi",
        operator_name: "浏览器扩展",
        room_name: roomId,
        live_url: normalizedLiveUrl,
      }),
    }),
  );
  return created.id;
}

async function ensureMetricCapture(tabId, tabUrl) {
  if (!tabUrl?.startsWith("https://www.autoengine.com/jdc/industry/live/screen")) {
    return;
  }
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["bridge-main.js"],
    world: "MAIN",
    injectImmediately: true,
  });
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["content.js"],
    world: "ISOLATED",
    injectImmediately: true,
  });
}

async function startCapture(message) {
  const store = await getStore();
  const key = String(message.tabId);
  if (!store.captures[key] && captureList(store).length >= MAX_CAPTURES) {
    throw new Error(`最多同时采集${MAX_CAPTURES}个直播间，请先停止一个直播间`);
  }

  const serverUrl = normalizeServerUrl(message.serverUrl);
  const suppliedValue = String(message.sessionId || "").trim();
  if (!suppliedValue) throw new Error("请填写场次ID或直播链接");
  const sessionId = await resolveSessionId(serverUrl, suppliedValue);
  await ensureMetricCapture(message.tabId, message.tabUrl);
  await ensureOffscreenDocument();
  const streamId = await chrome.tabCapture.getMediaStreamId({
    targetTabId: message.tabId,
  });
  await updateCapture(message.tabId, {
    active: true,
    connected: false,
    serverUrl,
    sessionId,
    tabTitle: message.tabTitle || "当前直播标签页",
    level: 0,
    audioSilent: false,
    message: "正在连接直播标签页与云端",
    metricError: "",
  });
  const result = await chrome.runtime.sendMessage({
    target: "offscreen",
    type: "START_CAPTURE",
    streamId,
    serverUrl,
    sessionId,
    tabId: message.tabId,
    tabTitle: message.tabTitle || "",
  });
  if (result?.error) {
    await removeCapture(message.tabId, result.error);
    throw new Error(result.error);
  }
  chrome.tabs
    .sendMessage(message.tabId, {
      target: "content",
      type: "FLUSH_METRICS",
    })
    .catch(() => undefined);
  return getStatus(message.tabId);
}

async function stopCapture(tabId) {
  if (await hasOffscreenDocument()) {
    await chrome.runtime.sendMessage({
      target: "offscreen",
      type: "STOP_CAPTURE",
      tabId,
    });
  }
  return removeCapture(tabId);
}

async function forwardMetric(message, sender) {
  const tabId = sender.tab?.id;
  if (!tabId) return { ignored: true };
  const store = await getStore();
  const capture = store.captures[String(tabId)];
  if (!capture?.sessionId || !capture?.serverUrl) return { ignored: true };
  await updateCapture(tabId, {
    metricCapturedAt: message.capturedAt || new Date().toISOString(),
    metricEndpoint: message.endpoint || "",
    metricError: "",
  });
  try {
    const response = await fetch(
      `${capture.serverUrl}/api/sessions/${encodeURIComponent(capture.sessionId)}/metrics`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          endpoint: message.endpoint,
          page_url: message.pageUrl,
          payload: message.payload,
          captured_at: message.capturedAt,
        }),
      },
    );
    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      throw new Error(
        detail?.detail || `大屏数据上传失败：HTTP ${response.status}`,
      );
    }
    await updateCapture(tabId, {
      metricUploadedAt: new Date().toISOString(),
      metricEndpoint: message.endpoint || "",
      metricError: "",
    });
    return { ok: true };
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    await updateCapture(tabId, { metricError: errorMessage });
    throw error;
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.target !== "background") return false;
  (async () => {
    if (message.type === "GET_STATUS") return getStatus(message.tabId);
    if (message.type === "START_CAPTURE") return startCapture(message);
    if (message.type === "STOP_CAPTURE") return stopCapture(message.tabId);
    if (message.type === "CAPTURE_STATUS") {
      return updateCapture(message.tabId, message.patch);
    }
    if (message.type === "METRIC_CAPTURE") {
      return forwardMetric(message, sender);
    }
    return { ok: false };
  })()
    .then(sendResponse)
    .catch(async (error) => {
      if (message.tabId && message.type !== "METRIC_CAPTURE") {
        await updateCapture(message.tabId, {
          connected: false,
          message: error instanceof Error ? error.message : String(error),
        });
      }
      sendResponse({ error: error instanceof Error ? error.message : String(error) });
    });
  return true;
});

chrome.tabs.onRemoved.addListener((tabId) => {
  getStore().then((store) => {
    if (store.captures[String(tabId)]) void stopCapture(tabId);
  });
});

chrome.runtime.onInstalled.addListener(() => {
  void getStore();
});
