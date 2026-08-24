const serverInput = document.querySelector("#server-url");
const sessionInput = document.querySelector("#session-id");
const form = document.querySelector("#capture-form");
const startButton = document.querySelector("#start-button");
const stopButton = document.querySelector("#stop-button");
const statusDot = document.querySelector("#status-dot");
const statusText = document.querySelector("#status-text");
const tabTitle = document.querySelector("#tab-title");
const levelBar = document.querySelector("#level-bar");
const errorText = document.querySelector("#error-text");
const captureCount = document.querySelector("#capture-count");
const captureList = document.querySelector("#capture-list");
const metricStatus = document.querySelector("#metric-status");

let currentTab = null;

async function getCurrentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  currentTab = tab || null;
  return currentTab;
}

function render(state) {
  serverInput.value = state.serverUrl || serverInput.value;
  if (state.active && state.sessionId) sessionInput.value = state.sessionId;
  statusText.textContent = state.message || "等待开始";
  tabTitle.textContent = state.active
    ? state.tabTitle || "当前直播标签页"
    : currentTab?.title || "当前标签页尚未采集";
  statusDot.classList.toggle("live", Boolean(state.connected) && !state.audioSilent);
  statusDot.classList.toggle("silent", Boolean(state.audioSilent));
  levelBar.style.width = `${Math.round((state.level || 0) * 100)}%`;
  levelBar.classList.toggle("silent", Boolean(state.audioSilent));
  stopButton.disabled = !state.active;
  startButton.textContent = state.active ? "重新连接当前标签页" : "采集当前标签页";
  captureCount.textContent = `正在采集 ${state.activeCount || 0}/${state.maxCaptures || 3} 间`;
  captureList.replaceChildren();
  if (state.metricError) {
    metricStatus.textContent = `监控数据：上传失败（${state.metricError}）`;
    metricStatus.className = "metric-status error-status";
  } else if (state.metricUploadedAt) {
    metricStatus.textContent = `监控数据：已上传 ${new Date(
      state.metricUploadedAt,
    ).toLocaleTimeString("zh-CN", { hour12: false })}`;
    metricStatus.className = "metric-status success-status";
  } else if (state.metricCapturedAt) {
    metricStatus.textContent = "监控数据：已抓取，正在上传";
    metricStatus.className = "metric-status";
  } else if (state.active) {
    metricStatus.textContent = "监控数据：尚未抓到，请刷新懂车云店大屏";
    metricStatus.className = "metric-status warning-status";
  } else {
    metricStatus.textContent = "监控数据：等待抓取";
    metricStatus.className = "metric-status";
  }
  if (!state.captures?.length) {
    const empty = document.createElement("li");
    empty.className = "empty-capture";
    empty.textContent = "暂无正在采集的直播间";
    captureList.append(empty);
  }
  for (const capture of state.captures || []) {
    const item = document.createElement("li");
    const dot = document.createElement("span");
    dot.className = capture.connected ? "capture-dot live" : "capture-dot";
    const label = document.createElement("span");
    label.textContent = capture.tabTitle || capture.sessionId;
    label.title = capture.tabTitle || capture.sessionId;
    item.append(dot, label);
    captureList.append(item);
  }
}

async function getStatus() {
  const tab = await getCurrentTab();
  const state = await chrome.runtime.sendMessage({
    target: "background",
    type: "GET_STATUS",
    tabId: tab?.id || null,
  });
  if (state?.error) throw new Error(state.error);
  render(state);
  if (
    !state.active &&
    !sessionInput.value &&
    tab?.url?.startsWith("https://www.autoengine.com/jdc/industry/live/screen")
  ) {
    sessionInput.value = tab.url;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorText.textContent = "";
  startButton.disabled = true;
  try {
    const tab = await getCurrentTab();
    if (!tab?.id) throw new Error("未找到当前标签页");
    const state = await chrome.runtime.sendMessage({
      target: "background",
      type: "START_CAPTURE",
      serverUrl: serverInput.value.trim(),
      sessionId: sessionInput.value.trim(),
      tabId: tab.id,
      tabTitle: tab.title || "",
      tabUrl: tab.url || "",
    });
    if (state?.error) throw new Error(state.error);
    render(state);
  } catch (error) {
    errorText.textContent = error instanceof Error ? error.message : String(error);
  } finally {
    startButton.disabled = false;
  }
});

stopButton.addEventListener("click", async () => {
  errorText.textContent = "";
  stopButton.disabled = true;
  try {
    const tab = currentTab || (await getCurrentTab());
    if (!tab?.id) throw new Error("未找到当前标签页");
    const state = await chrome.runtime.sendMessage({
      target: "background",
      type: "STOP_CAPTURE",
      tabId: tab.id,
    });
    if (state?.error) throw new Error(state.error);
    render(state);
  } catch (error) {
    errorText.textContent = error instanceof Error ? error.message : String(error);
  } finally {
    stopButton.disabled = false;
  }
});

chrome.runtime.onMessage.addListener((message) => {
  if (message.target === "popup" && message.type === "STATUS_UPDATE") {
    if (!currentTab || message.state.tabId === currentTab.id) render(message.state);
    else void getStatus();
  }
});

getStatus().catch((error) => {
  errorText.textContent = error instanceof Error ? error.message : String(error);
});
