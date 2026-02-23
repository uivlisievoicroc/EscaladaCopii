import { debugError } from './debug';
import { fetchWithRetry } from './fetch';
import { clearAuth } from './auth';

const API_PROTOCOL = window.location.protocol === 'https:' ? 'https' : 'http';

export const API_ENDPOINTS = {
  CMD: `${API_PROTOCOL}://${window.location.hostname}:8000/api/cmd`,
  ADMIN: `${API_PROTOCOL}://${window.location.hostname}:8000/api/admin`,
  STATE: `${API_PROTOCOL}://${window.location.hostname}:8000/api/state`,
};

type RequestJsonOptions = {
  retries?: number;
  timeoutMs?: number;
};

const DEFAULT_OPTIONS: Required<RequestJsonOptions> = {
  retries: 3,
  timeoutMs: 5000,
};

async function getErrorMessage(response: Response): Promise<string> {
  try {
    const errorData = await response.json();
    return errorData?.detail || `HTTP ${response.status}: ${response.statusText}`;
  } catch {
    return `HTTP ${response.status}: ${response.statusText}`;
  }
}

export async function validateApiResponse(
  response: Response,
  commandType: string,
): Promise<void> {
  if (response.ok) return;
  const errorMsg = await getErrorMessage(response);
  if (response.status === 401 || response.status === 403) {
    clearAuth();
  }
  const error = new Error(`[${commandType}] ${errorMsg}`) as Error & {
    status?: number;
    commandType?: string;
  };
  error.status = response.status;
  error.commandType = commandType;
  debugError(`Command failed: ${commandType}`, error);
  throw error;
}

export async function requestJson<T = any>(
  url: string,
  init: RequestInit,
  commandType: string,
  options: RequestJsonOptions = {},
): Promise<T> {
  const { retries, timeoutMs } = { ...DEFAULT_OPTIONS, ...options };
  try {
    const response = await fetchWithRetry(url, init, retries, timeoutMs);
    await validateApiResponse(response, commandType);
    return (await response.json()) as T;
  } catch (err) {
    debugError(`[requestJson:${commandType}] Error:`, err);
    throw err;
  }
}

export async function postCmd<T = any>(
  body: Record<string, unknown>,
  commandType: string,
  options?: RequestJsonOptions,
): Promise<T> {
  return requestJson<T>(
    API_ENDPOINTS.CMD,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(body),
    },
    commandType,
    options,
  );
}

export async function getStateSnapshot<T = any>(boxId: number): Promise<T> {
  return requestJson<T>(
    `${API_ENDPOINTS.STATE}/${boxId}`,
    {
      method: 'GET',
      credentials: 'include',
    },
    'GET_STATE',
  );
}

export async function requestAdminJson<T = any>(
  path: string,
  method: 'GET' | 'POST',
  commandType: string,
  body?: Record<string, unknown>,
): Promise<T> {
  return requestJson<T>(
    `${API_ENDPOINTS.ADMIN}${path}`,
    {
      method,
      credentials: 'include',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    },
    commandType,
  );
}
