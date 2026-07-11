(() => {
  "use strict";

  const root = document.querySelector("[data-live-market]");
  if (!root) return;

  const refreshKey = `scan-full-refresh:${window.location.pathname}:${window.location.search}`;
  if (root.dataset.scanFallback === "true") {
    const attempts = Number(window.sessionStorage.getItem(refreshKey) || 0);
    if (attempts < 12) {
      window.sessionStorage.setItem(refreshKey, String(attempts + 1));
      window.setTimeout(() => {
        const url = new URL(window.location.href);
        url.searchParams.delete("refresh");
        window.location.replace(url.toString());
      }, 1500);
    }
  } else {
    window.sessionStorage.removeItem(refreshKey);
  }

  const symbolNodes = Array.from(document.querySelectorAll("[data-live-symbol]"));
  const symbols = Array.from(
    new Set(symbolNodes.map((node) => String(node.dataset.liveSymbol || "").toUpperCase()).filter(Boolean)),
  );
  if (!symbols.length) {
    root.hidden = true;
    return;
  }

  const nodesBySymbol = new Map();
  for (const node of symbolNodes) {
    const symbol = String(node.dataset.liveSymbol || "").toUpperCase();
    if (!nodesBySymbol.has(symbol)) nodesBySymbol.set(symbol, []);
    nodesBySymbol.get(symbol).push(node);
  }

  const statusNode = root.querySelector("[data-live-status]");
  const sourceNode = root.querySelector("[data-live-source]");
  const updatedNode = root.querySelector("[data-live-updated]");
  const reconnectButton = root.querySelector("[data-live-reconnect]");
  const labels = {
    connecting: root.dataset.labelConnecting || "Connecting",
    live: root.dataset.labelLive || "Live",
    fallback: root.dataset.labelFallback || "REST fallback",
    retry: root.dataset.labelRetry || "Retrying",
    websocket: root.dataset.labelWebsocket || "Binance WebSocket",
    rest: root.dataset.labelRest || "Binance REST",
  };

  const endpoints = [
    "wss://stream.binance.com:9443",
    "wss://stream.binance.com:443",
    "wss://data-stream.binance.vision",
  ];
  const streamPath = symbols.map((symbol) => `${symbol.toLowerCase()}@miniTicker`).join("/");
  const restUrl = `/api/market/realtime?symbols=${encodeURIComponent(symbols.join(","))}`;
  let socket = null;
  let reconnectTimer = 0;
  let connectTimer = 0;
  let restTimer = 0;
  let reconnectAttempts = 0;
  let endpointIndex = 0;
  let stopped = false;

  const setStatus = (state, text, source) => {
    root.dataset.liveState = state;
    if (statusNode) statusNode.textContent = text;
    if (sourceNode) sourceNode.textContent = source;
  };

  const formatPrice = (price) => {
    const decimals = price >= 1000 ? 2 : price >= 1 ? 6 : 8;
    return new Intl.NumberFormat(undefined, {
      maximumFractionDigits: decimals,
      minimumFractionDigits: price >= 1000 ? 2 : 0,
    }).format(price);
  };

  const formatChange = (change) => `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`;

  const markUpdated = (timestamp) => {
    if (!updatedNode) return;
    const date = timestamp ? new Date(timestamp) : new Date();
    updatedNode.textContent = Number.isNaN(date.getTime()) ? new Date().toLocaleTimeString() : date.toLocaleTimeString();
  };

  const pulse = (node, direction) => {
    node.classList.remove("live-tick-up", "live-tick-down");
    void node.offsetWidth;
    node.classList.add(direction >= 0 ? "live-tick-up" : "live-tick-down");
  };

  const applyMarketItem = (item, timestamp) => {
    const symbol = String(item.symbol || item.s || "").toUpperCase();
    const price = Number(item.price ?? item.c);
    const openPrice = Number(item.o);
    const explicitChange = item.change_pct;
    const change = explicitChange === null || explicitChange === undefined
      ? openPrice > 0
        ? ((price - openPrice) / openPrice) * 100
        : null
      : Number(explicitChange);
    if (!symbol || !Number.isFinite(price) || price <= 0 || !nodesBySymbol.has(symbol)) return;

    for (const container of nodesBySymbol.get(symbol)) {
      for (const priceNode of container.querySelectorAll("[data-live-price]")) {
        const previous = Number(priceNode.dataset.liveValue || price);
        priceNode.dataset.liveValue = String(price);
        priceNode.textContent = formatPrice(price);
        pulse(priceNode, price - previous);
      }
      if (Number.isFinite(change)) {
        for (const changeNode of container.querySelectorAll("[data-live-change]")) {
          changeNode.textContent = formatChange(change);
          changeNode.classList.toggle("positive", change >= 0);
          changeNode.classList.toggle("negative", change < 0);
        }
      }
      container.dataset.liveUpdatedAt = String(timestamp || Date.now());
    }
    markUpdated(timestamp);
  };

  const stopRestPolling = () => {
    if (restTimer) window.clearInterval(restTimer);
    restTimer = 0;
  };

  const pollRest = async () => {
    try {
      const response = await fetch(restUrl, { cache: "no-store", headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      for (const item of Array.isArray(payload.items) ? payload.items : []) {
        applyMarketItem(item, payload.generated_at);
      }
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        setStatus("fallback", labels.fallback, labels.rest);
      }
    } catch (_error) {
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        setStatus("retry", labels.retry, labels.rest);
      }
    }
  };

  const startRestPolling = () => {
    if (restTimer) return;
    void pollRest();
    restTimer = window.setInterval(pollRest, 15000);
  };

  const scheduleReconnect = (immediate = false) => {
    if (stopped || reconnectTimer) return;
    reconnectAttempts += 1;
    endpointIndex = (endpointIndex + 1) % endpoints.length;
    const delay = immediate ? 0 : Math.min(30000, 1000 * (2 ** Math.min(reconnectAttempts - 1, 5)));
    setStatus("retry", labels.retry, labels.websocket);
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = 0;
      connect();
    }, delay);
  };

  const connect = () => {
    if (stopped || document.hidden) return;
    if (socket && [WebSocket.CONNECTING, WebSocket.OPEN].includes(socket.readyState)) return;
    if (!("WebSocket" in window)) {
      startRestPolling();
      return;
    }

    setStatus("connecting", labels.connecting, labels.websocket);
    try {
      socket = new WebSocket(`${endpoints[endpointIndex]}/stream?streams=${streamPath}`);
    } catch (_error) {
      socket = null;
      startRestPolling();
      scheduleReconnect();
      return;
    }
    connectTimer = window.setTimeout(() => {
      if (socket && socket.readyState === WebSocket.CONNECTING) socket.close();
    }, 8000);

    socket.addEventListener("open", () => {
      window.clearTimeout(connectTimer);
      reconnectAttempts = 0;
      stopRestPolling();
      setStatus("live", labels.live, labels.websocket);
    });

    socket.addEventListener("message", (event) => {
      try {
        const envelope = JSON.parse(event.data);
        const payload = envelope && Object.prototype.hasOwnProperty.call(envelope, "data") ? envelope.data : envelope;
        const items = Array.isArray(payload) ? payload : [payload];
        for (const item of items) {
          if (item && item.e === "serverShutdown") {
            socket.close();
            return;
          }
          if (item) applyMarketItem(item, item.E);
        }
      } catch (_error) {
        // Ignore a malformed market event and keep the stream alive.
      }
    });

    socket.addEventListener("close", () => {
      window.clearTimeout(connectTimer);
      socket = null;
      startRestPolling();
      scheduleReconnect();
    });

    socket.addEventListener("error", () => {
      if (socket && socket.readyState !== WebSocket.CLOSED) socket.close();
    });
  };

  if (reconnectButton) {
    reconnectButton.addEventListener("click", () => {
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      reconnectTimer = 0;
      reconnectAttempts = 0;
      if (socket && socket.readyState !== WebSocket.CLOSED) socket.close();
      socket = null;
      scheduleReconnect(true);
    });
  }

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && (!socket || socket.readyState === WebSocket.CLOSED)) scheduleReconnect(true);
  });
  window.addEventListener("pagehide", () => {
    stopped = true;
    if (reconnectTimer) window.clearTimeout(reconnectTimer);
    if (connectTimer) window.clearTimeout(connectTimer);
    stopRestPolling();
    if (socket && socket.readyState !== WebSocket.CLOSED) socket.close();
  });

  connect();
})();
