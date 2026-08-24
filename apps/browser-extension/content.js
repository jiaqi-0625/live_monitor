(() => {
  if (window.__carLiveMonitorContentInstalled) return;
  window.__carLiveMonitorContentInstalled = true;
  const lastSentAt = new Map();
  const latestCaptures = new Map();
  const minimumIntervalMs = 5000;

  async function forwardMetric(capture, force = false) {
    const endpoint = String(capture.endpoint || "");
    const now = Date.now();
    if (!force && now - (lastSentAt.get(endpoint) || 0) < minimumIntervalMs) {
      return;
    }
    lastSentAt.set(endpoint, now);
    const result = await chrome.runtime.sendMessage({
      target: "background",
      type: "METRIC_CAPTURE",
      endpoint,
      pageUrl: capture.pageUrl || window.location.href,
      payload: capture.payload,
      capturedAt: capture.capturedAt,
    });
    if (result?.error) throw new Error(result.error);
  }

  window.addEventListener("message", (event) => {
    if (
      event.source !== window ||
      event.origin !== window.location.origin ||
      event.data?.type !== "CAR_LIVE_MONITOR_METRICS"
    ) {
      return;
    }
    const endpoint = String(event.data.endpoint || "");
    const capture = {
      endpoint,
      pageUrl: window.location.href,
      payload: event.data.payload,
      capturedAt: event.data.capturedAt,
    };
    latestCaptures.set(endpoint, capture);
    void forwardMetric(capture).catch(() => undefined);
  });

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message.target !== "content" || message.type !== "FLUSH_METRICS") {
      return false;
    }
    Promise.allSettled(
      Array.from(latestCaptures.values(), (capture) =>
        forwardMetric(capture, true),
      ),
    ).then((results) => {
      const failed = results.filter((result) => result.status === "rejected");
      sendResponse({
        ok: failed.length === 0,
        cachedCount: results.length,
        failedCount: failed.length,
      });
    });
    return true;
  });
})();
