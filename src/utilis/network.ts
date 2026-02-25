const normalizePath = (path: string): string =>
  path.startsWith('/') ? path : `/${path}`;

export const getHttpProtocol = (): 'http' | 'https' =>
  window.location.protocol === 'https:' ? 'https' : 'http';

export const getWsProtocol = (): 'ws' | 'wss' =>
  window.location.protocol === 'https:' ? 'wss' : 'ws';

export const buildApiPath = (path: string): string => normalizePath(path);

export const buildApiUrl = (path: string): string =>
  `${getHttpProtocol()}://${window.location.host}${normalizePath(path)}`;

export const buildWsUrl = (path: string): string =>
  `${getWsProtocol()}://${window.location.host}${normalizePath(path)}`;

