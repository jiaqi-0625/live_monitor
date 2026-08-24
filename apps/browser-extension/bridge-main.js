(() => {
  if (window.__carLiveMonitorBridgeInstalled) return;
  window.__carLiveMonitorBridgeInstalled = true;
  const MESSAGE_TYPE = "CAR_LIVE_MONITOR_METRICS";
  const endpointPattern =
    /\/motor\/dealer\/jdc_saas\/live\/(?:screen\/|data\/screen\/|room\/info)/;

  function publish(url, payload) {
    if (!endpointPattern.test(url) || !payload || typeof payload !== "object") {
      return;
    }
    let serialized;
    try {
      serialized = JSON.stringify(payload);
    } catch {
      return;
    }
    if (serialized.length > 300000) return;
    window.postMessage(
      {
        type: MESSAGE_TYPE,
        endpoint: url,
        payload,
        capturedAt: new Date().toISOString(),
      },
      window.location.origin,
    );
  }

  const originalFetch = window.fetch;
  window.fetch = async function (...args) {
    const response = await originalFetch.apply(this, args);
    const input = args[0];
    const url =
      typeof input === "string"
        ? input
        : input instanceof Request
          ? input.url
          : "";
    if (endpointPattern.test(url)) {
      response
        .clone()
        .json()
        .then((payload) => publish(url, payload))
        .catch(() => undefined);
    }
    return response;
  };

  const originalOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__carMonitorUrl = String(url);
    this.addEventListener("load", () => {
      if (!endpointPattern.test(this.__carMonitorUrl || "")) return;
      try {
        publish(this.__carMonitorUrl, JSON.parse(this.responseText));
      } catch {
        // Ignore non-JSON responses.
      }
    });
    return originalOpen.call(this, method, url, ...rest);
  };
})();
