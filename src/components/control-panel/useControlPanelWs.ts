import { backoffDelayMs, parseWsJson, replyPong } from '../../utilis/wsClient';

type WsOptions = {
  idx: number;
  url: string;
  onMessage: (msg: Record<string, any>) => void;
  onClosed?: () => void;
  onReconnectRequested: () => void;
  shouldReconnect: () => boolean;
  debugLog: (...args: any[]) => void;
  debugWarn: (...args: any[]) => void;
  debugError: (...args: any[]) => void;
};

type WsConnection = {
  ws: WebSocket;
  disconnect: () => void;
};

export const connectControlPanelWs = ({
  idx,
  url,
  onMessage,
  onClosed,
  onReconnectRequested,
  shouldReconnect,
  debugLog,
  debugWarn,
  debugError,
}: WsOptions): WsConnection => {
  const ws = new WebSocket(url);
  let heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  let lastPong = Date.now();

  ws.onopen = () => {
    debugLog(`✅ WebSocket connected for box ${idx}`);
    lastPong = Date.now();
    heartbeatInterval = setInterval(() => {
      const now = Date.now();
      const timeSinceLastPong = now - lastPong;
      if (timeSinceLastPong > 60000) {
        debugWarn(`⚠️ Heartbeat timeout for box ${idx}, closing connection...`);
        ws.close();
        return;
      }
      replyPong(ws, now);
    }, 30000);
  };

  ws.onmessage = (ev) => {
    const msg = parseWsJson(ev.data);
    if (!msg) return;
    if (msg.type === 'PING') {
      lastPong = Date.now();
      replyPong(ws, msg.timestamp);
      return;
    }
    onMessage(msg);
  };

  ws.onerror = (err) => {
    debugError(`❌ WebSocket error for box ${idx}:`, err);
  };

  ws.onclose = () => {
    debugLog(`🔌 WebSocket closed for box ${idx}`);
    if (heartbeatInterval) clearInterval(heartbeatInterval);
    onClosed?.();
    setTimeout(() => {
      if (!shouldReconnect()) return;
      debugLog(`🔄 Auto-reconnecting WebSocket for box ${idx}...`);
      onReconnectRequested();
    }, backoffDelayMs(1, 1000, 30000));
  };

  const disconnect = () => {
    if (heartbeatInterval) clearInterval(heartbeatInterval);
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
      try {
        ws.close();
      } catch {
        // Ignore close errors during teardown.
      }
    }
  };

  return { ws, disconnect };
};
