const API_BASE = '';

export const ADMIN_SECURITY_TOKEN_KEY = 'adminSecurityToken';
export const ADMIN_SECURITY_FORCE_LOCK_EVENT = 'admin-security-force-lock';

export type LicenseStatus = {
  license_valid: boolean;
  license_reason: string;
  license_mountpoint?: string | null;
  checked_at?: string | null;
  admin_unlocked: boolean;
  admin_license_valid: boolean;
  admin_license_reason: string;
  admin_license_expires_at?: string | null;
  admin_license_in_grace: boolean;
  admin_license_grace_until?: string | null;
  admin_license_id?: string | null;
  recovery_override_active: boolean;
  recovery_override_until?: string | null;
  recovery_codes_remaining: number;
};

type SecurityApiError = {
  code?: string;
  reason?: string;
  override_until?: string;
  detail?: string | { code?: string; reason?: string };
};

export function getAdminSecurityToken(): string | null {
  try {
    const token = sessionStorage.getItem(ADMIN_SECURITY_TOKEN_KEY);
    return token && token.trim() ? token : null;
  } catch {
    return null;
  }
}

export function setAdminSecurityToken(token: string): void {
  try {
    sessionStorage.setItem(ADMIN_SECURITY_TOKEN_KEY, token);
  } catch {
    // no-op
  }
}

export function clearAdminSecurityToken(): void {
  try {
    sessionStorage.removeItem(ADMIN_SECURITY_TOKEN_KEY);
  } catch {
    // no-op
  }
}

export function getAdminSecurityHeaders(
  baseHeaders?: HeadersInit,
): Record<string, string> {
  const headers = new Headers(baseHeaders || {});
  const token = getAdminSecurityToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  return Object.fromEntries(headers.entries());
}

export function forceAdminSecurityLock(reason = 'unknown'): void {
  clearAdminSecurityToken();
  window.dispatchEvent(
    new CustomEvent(ADMIN_SECURITY_FORCE_LOCK_EVENT, {
      detail: { reason },
    }),
  );
}

async function parseErrorData(response: Response): Promise<SecurityApiError | null> {
  try {
    const parsed = await response.clone().json();
    if (parsed && typeof parsed === 'object') return parsed as SecurityApiError;
    return null;
  } catch {
    return null;
  }
}

function extractErrorCode(errorData: SecurityApiError | null): string | null {
  if (!errorData) return null;
  if (typeof errorData.code === 'string') return errorData.code;
  if (typeof errorData.detail === 'string') return errorData.detail;
  if (
    errorData.detail &&
    typeof errorData.detail === 'object' &&
    typeof errorData.detail.code === 'string'
  ) {
    return errorData.detail.code;
  }
  return null;
}

export async function handleAdminSecurityErrorResponse(
  response: Response,
): Promise<boolean> {
  if (response.status !== 401 && response.status !== 403) {
    return false;
  }
  const errorData = await parseErrorData(response);
  const code = extractErrorCode(errorData);
  if (
    code === 'LICENSE_REQUIRED' ||
    code === 'ADMIN_SESSION_REQUIRED' ||
    code === 'ADMIN_LICENSE_REQUIRED'
  ) {
    forceAdminSecurityLock(code);
    return true;
  }
  return false;
}

function normalizeStatus(parsed: Partial<LicenseStatus>): LicenseStatus {
  return {
    license_valid: !!parsed.license_valid,
    license_reason: parsed.license_reason || 'error',
    license_mountpoint: parsed.license_mountpoint ?? null,
    checked_at: parsed.checked_at ?? null,
    admin_unlocked: !!parsed.admin_unlocked,
    admin_license_valid: !!parsed.admin_license_valid,
    admin_license_reason: parsed.admin_license_reason || 'error',
    admin_license_expires_at: parsed.admin_license_expires_at ?? null,
    admin_license_in_grace: !!parsed.admin_license_in_grace,
    admin_license_grace_until: parsed.admin_license_grace_until ?? null,
    admin_license_id: parsed.admin_license_id ?? null,
    recovery_override_active: !!parsed.recovery_override_active,
    recovery_override_until: parsed.recovery_override_until ?? null,
    recovery_codes_remaining: Number(parsed.recovery_codes_remaining || 0),
  };
}

async function readStatusJson(response: Response): Promise<LicenseStatus> {
  const parsed = (await response.json()) as Partial<LicenseStatus>;
  return normalizeStatus(parsed);
}

export async function refreshAdminSecurityStatus(): Promise<LicenseStatus> {
  const response = await fetch(`${API_BASE}/api/license/status`, {
    method: 'GET',
    credentials: 'include',
    headers: getAdminSecurityHeaders(),
  });
  if (!response.ok) {
    await handleAdminSecurityErrorResponse(response);
    throw new Error(`HTTP ${response.status}`);
  }
  return readStatusJson(response);
}

export async function unlockAdminSecurity(): Promise<{
  token: string;
  status: LicenseStatus;
}> {
  const response = await fetch(`${API_BASE}/api/admin/unlock`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...getAdminSecurityHeaders(),
    },
    body: JSON.stringify({}),
  });

  if (!response.ok) {
    await handleAdminSecurityErrorResponse(response);
    const data = await parseErrorData(response);
    const code = extractErrorCode(data) || 'unlock_failed';
    const reason =
      data?.reason ||
      (typeof data?.detail === 'string' ? data.detail : null) ||
      (typeof data?.detail === 'object' ? data?.detail?.reason : null) ||
      code;
    throw new Error(`${code}:${reason}`);
  }

  const parsed = (await response.json()) as LicenseStatus & { token: string };
  if (!parsed.token || typeof parsed.token !== 'string') {
    throw new Error('invalid_unlock_response');
  }
  setAdminSecurityToken(parsed.token);
  return {
    token: parsed.token,
    status: normalizeStatus(parsed),
  };
}

export async function lockAdminSecurity(): Promise<LicenseStatus | null> {
  const response = await fetch(`${API_BASE}/api/admin/lock`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...getAdminSecurityHeaders(),
    },
    body: JSON.stringify({}),
  });

  clearAdminSecurityToken();
  if (!response.ok) {
    await handleAdminSecurityErrorResponse(response);
    return null;
  }
  return readStatusJson(response);
}

export async function consumeRecoveryCode(code: string): Promise<{
  override_until: string | null;
  remaining: number;
}> {
  const response = await fetch(`${API_BASE}/api/admin/recovery/consume`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...getAdminSecurityHeaders(),
    },
    body: JSON.stringify({ code }),
  });

  if (!response.ok) {
    await handleAdminSecurityErrorResponse(response);
    const data = await parseErrorData(response);
    const codeValue = extractErrorCode(data) || `HTTP_${response.status}`;
    const reason =
      data?.reason ||
      (typeof data?.detail === 'string' ? data.detail : null) ||
      (typeof data?.detail === 'object' ? data?.detail?.reason : null) ||
      data?.override_until ||
      codeValue;
    throw new Error(`${codeValue}:${reason}`);
  }

  const parsed = (await response.json()) as {
    override_until?: string | null;
    remaining?: number;
  };
  return {
    override_until: parsed.override_until ?? null,
    remaining: Number(parsed.remaining || 0),
  };
}
