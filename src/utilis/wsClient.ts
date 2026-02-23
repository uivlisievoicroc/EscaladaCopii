export const getHttpProtocol = (): 'http' | 'https' =>
  window.location.protocol === 'https:' ? 'https' : 'http';

export const getWsProtocol = (): 'ws' | 'wss' =>
  window.location.protocol === 'https:' ? 'wss' : 'ws';

export const buildApiUrl = (path: string): string =>
  `${getHttpProtocol()}://${window.location.hostname}:8000${path}`;

export const buildWsUrl = (path: string): string =>
  `${getWsProtocol()}://${window.location.hostname}:8000${path}`;

export const backoffDelayMs = (
  attempt: number,
  baseMs = 1000,
  maxMs = 30000,
): number => {
  const normalized = Number.isFinite(attempt) && attempt > 0 ? Math.trunc(attempt) : 0;
  return Math.min(baseMs * Math.pow(2, normalized), maxMs);
};

export const parseWsJson = (payload: unknown): Record<string, any> | null => {
  if (typeof payload !== 'string') return null;
  try {
    const parsed = JSON.parse(payload);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
};

export const replyPong = (ws: WebSocket, timestamp?: unknown): void => {
  if (ws.readyState !== WebSocket.OPEN) return;
  const message =
    typeof timestamp === 'number' && Number.isFinite(timestamp)
      ? { type: 'PONG', timestamp }
      : { type: 'PONG' };
  try {
    ws.send(JSON.stringify(message));
  } catch {
    // Ignore send errors; socket lifecycle handlers will reconnect/cleanup.
  }
};
