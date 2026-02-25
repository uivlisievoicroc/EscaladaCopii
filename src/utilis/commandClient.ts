import { debugError } from './debug';
import { fetchWithRetry } from './fetch';
import { clearAuth } from './auth';
import {
  getAdminSecurityHeaders,
  handleAdminSecurityErrorResponse,
} from './adminSecurityService';

export const API_ENDPOINTS = {
  CMD: '/api/cmd',
  ADMIN: '/api/admin',
  STATE: '/api/state',
};

type RequestJsonOptions = {
  retries?: number;
  timeoutMs?: number;
};

const DEFAULT_OPTIONS: Required<RequestJsonOptions> = {
  retries: 3,
  timeoutMs: 5000,
};

export async function validateApiResponse(
  response: Response,
  commandType: string,
): Promise<void> {
  if (response.ok) return;
  let errorData: any = null;
  try {
    errorData = await response.clone().json();
  } catch {
    errorData = null;
  }

  const handledSecurityLock = await handleAdminSecurityErrorResponse(response);
  if ((response.status === 401 || response.status === 403) && !handledSecurityLock) {
    clearAuth();
  }
  const errorMsg =
    errorData?.detail?.reason ||
    errorData?.reason ||
    errorData?.detail ||
    `HTTP ${response.status}: ${response.statusText}`;
  const error = new Error(`[${commandType}] ${errorMsg}`) as Error & {
    status?: number;
    commandType?: string;
    code?: string;
  };
  error.status = response.status;
  error.commandType = commandType;
  error.code =
    errorData?.code ||
    (errorData?.detail && typeof errorData.detail === 'object' ? errorData.detail.code : undefined);
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
      headers: getAdminSecurityHeaders({ 'Content-Type': 'application/json' }),
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
  const headers = getAdminSecurityHeaders(body ? { 'Content-Type': 'application/json' } : undefined);
  return requestJson<T>(
    `${API_ENDPOINTS.ADMIN}${path}`,
    {
      method,
      credentials: 'include',
      headers: Object.keys(headers).length ? headers : undefined,
      body: body ? JSON.stringify(body) : undefined,
    },
    commandType,
  );
}
