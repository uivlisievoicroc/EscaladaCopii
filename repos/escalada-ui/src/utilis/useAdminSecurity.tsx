import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  ADMIN_SECURITY_FORCE_LOCK_EVENT,
  clearAdminSecurityToken,
  consumeRecoveryCode as consumeRecoveryCodeApi,
  forceAdminSecurityLock,
  getAdminSecurityToken,
  LicenseStatus,
  lockAdminSecurity,
  refreshAdminSecurityStatus,
  unlockAdminSecurity,
} from './adminSecurityService';

const API_BASE = '';

type AdminSecurityContextValue = {
  licenseValid: boolean;
  licenseReason: string;
  adminLicenseValid: boolean;
  adminLicenseReason: string;
  adminLicenseExpiresAt: string | null;
  adminLicenseInGrace: boolean;
  adminLicenseGraceUntil: string | null;
  adminLicenseId: string | null;
  recoveryOverrideActive: boolean;
  recoveryOverrideUntil: string | null;
  recoveryCodesRemaining: number;
  adminUnlocked: boolean;
  adminToken: string | null;
  sseConnected: boolean;
  loading: boolean;
  refreshStatus: () => Promise<void>;
  unlock: () => Promise<void>;
  lock: () => Promise<void>;
  consumeRecoveryCode: (code: string) => Promise<void>;
};

const AdminSecurityContext = createContext<AdminSecurityContextValue | null>(null);

const DEFAULT_LOCK_REASON = 'not_checked';

export const AdminSecurityProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [licenseValid, setLicenseValid] = useState<boolean>(false);
  const [licenseReason, setLicenseReason] = useState<string>(DEFAULT_LOCK_REASON);
  const [adminLicenseValid, setAdminLicenseValid] = useState<boolean>(false);
  const [adminLicenseReason, setAdminLicenseReason] = useState<string>('not_checked');
  const [adminLicenseExpiresAt, setAdminLicenseExpiresAt] = useState<string | null>(null);
  const [adminLicenseInGrace, setAdminLicenseInGrace] = useState<boolean>(false);
  const [adminLicenseGraceUntil, setAdminLicenseGraceUntil] = useState<string | null>(null);
  const [adminLicenseId, setAdminLicenseId] = useState<string | null>(null);
  const [recoveryOverrideActive, setRecoveryOverrideActive] = useState<boolean>(false);
  const [recoveryOverrideUntil, setRecoveryOverrideUntil] = useState<string | null>(null);
  const [recoveryCodesRemaining, setRecoveryCodesRemaining] = useState<number>(0);
  const [adminUnlocked, setAdminUnlocked] = useState<boolean>(false);
  const [adminToken, setAdminToken] = useState<string | null>(() => getAdminSecurityToken());
  const [sseConnected, setSseConnected] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const reconnectTimerRef = useRef<number | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const setLockedLocal = useCallback((reason: string) => {
    clearAdminSecurityToken();
    setAdminToken(null);
    setAdminUnlocked(false);
    setLicenseReason(reason || 'locked');
  }, []);

  const applyStatus = useCallback(
    (status: LicenseStatus) => {
      setLicenseValid(!!status.license_valid);
      setLicenseReason(status.license_reason || 'error');
      setAdminLicenseValid(!!status.admin_license_valid);
      setAdminLicenseReason(status.admin_license_reason || 'error');
      setAdminLicenseExpiresAt(status.admin_license_expires_at ?? null);
      setAdminLicenseInGrace(!!status.admin_license_in_grace);
      setAdminLicenseGraceUntil(status.admin_license_grace_until ?? null);
      setAdminLicenseId(status.admin_license_id ?? null);
      setRecoveryOverrideActive(!!status.recovery_override_active);
      setRecoveryOverrideUntil(status.recovery_override_until ?? null);
      setRecoveryCodesRemaining(Number(status.recovery_codes_remaining || 0));
      if (status.admin_unlocked) {
        setAdminUnlocked(true);
        setAdminToken(getAdminSecurityToken());
      } else {
        setLockedLocal(status.license_reason || 'locked');
      }
    },
    [setLockedLocal],
  );

  const refreshStatus = useCallback(async () => {
    try {
      const status = await refreshAdminSecurityStatus();
      applyStatus(status);
    } catch {
      // Keep previous state on transient failures; SSE/polling retries will recover.
    }
  }, [applyStatus]);

  const unlock = useCallback(async () => {
    setLoading(true);
    try {
      const { token, status } = await unlockAdminSecurity();
      setAdminToken(token);
      applyStatus(status);
    } finally {
      setLoading(false);
    }
  }, [applyStatus]);

  const lock = useCallback(async () => {
    setLoading(true);
    try {
      const status = await lockAdminSecurity();
      if (status) {
        applyStatus(status);
      } else {
        setLockedLocal('manual_lock');
      }
    } finally {
      setLoading(false);
    }
  }, [applyStatus, setLockedLocal]);

  const consumeRecoveryCode = useCallback(
    async (code: string) => {
      setLoading(true);
      try {
        await consumeRecoveryCodeApi(code);
        const status = await refreshAdminSecurityStatus();
        applyStatus(status);
      } finally {
        setLoading(false);
      }
    },
    [applyStatus],
  );

  useEffect(() => {
    const onForceLock = (event: Event) => {
      const customEvent = event as CustomEvent<{ reason?: string }>;
      const reason = customEvent.detail?.reason || 'locked';
      setLockedLocal(reason);
    };
    window.addEventListener(ADMIN_SECURITY_FORCE_LOCK_EVENT, onForceLock);
    return () => {
      window.removeEventListener(ADMIN_SECURITY_FORCE_LOCK_EVENT, onForceLock);
    };
  }, [setLockedLocal]);

  useEffect(() => {
    let disposed = false;

    const handleLicenseEvent = (raw: MessageEvent<string>) => {
      try {
        const data = JSON.parse(raw.data) as Record<string, unknown>;
        const valid =
          typeof data.license_valid === 'boolean'
            ? data.license_valid
            : Boolean(data.valid);
        const reason =
          typeof data.license_reason === 'string'
            ? data.license_reason
            : typeof data.reason === 'string'
            ? data.reason
            : 'error';
        setLicenseValid(valid);
        setLicenseReason(reason);
        if (!valid) {
          setLockedLocal(reason);
        } else if (typeof data.admin_unlocked === 'boolean') {
          setAdminUnlocked(data.admin_unlocked);
          if (!data.admin_unlocked) {
            setLockedLocal(reason || 'locked');
          }
        }
        if (typeof data.admin_license_valid === 'boolean') {
          setAdminLicenseValid(data.admin_license_valid);
        }
        if (typeof data.admin_license_reason === 'string') {
          setAdminLicenseReason(data.admin_license_reason || 'error');
        }
        if (typeof data.admin_license_expires_at === 'string') {
          setAdminLicenseExpiresAt(data.admin_license_expires_at);
        }
        if (typeof data.admin_license_in_grace === 'boolean') {
          setAdminLicenseInGrace(data.admin_license_in_grace);
        }
        if (typeof data.admin_license_grace_until === 'string') {
          setAdminLicenseGraceUntil(data.admin_license_grace_until);
        }
        if (typeof data.admin_license_id === 'string') {
          setAdminLicenseId(data.admin_license_id);
        }
        if (typeof data.recovery_override_active === 'boolean') {
          setRecoveryOverrideActive(data.recovery_override_active);
        }
        if (typeof data.recovery_override_until === 'string') {
          setRecoveryOverrideUntil(data.recovery_override_until);
        }
        if (typeof data.recovery_codes_remaining === 'number') {
          setRecoveryCodesRemaining(Number(data.recovery_codes_remaining || 0));
        }
      } catch {
        // ignore malformed events
      }
    };

    const handleAdminLockedEvent = (raw: MessageEvent<string>) => {
      try {
        const data = JSON.parse(raw.data) as Record<string, unknown>;
        const reason =
          typeof data.reason === 'string' && data.reason ? data.reason : 'admin_locked';
        forceAdminSecurityLock(reason);
      } catch {
        forceAdminSecurityLock('admin_locked');
      }
    };

    const connectSse = () => {
      if (disposed) return;
      const es = new EventSource(`${API_BASE}/api/license/events`, {
        withCredentials: true,
      });
      eventSourceRef.current = es;

      es.onopen = () => {
        setSseConnected(true);
      };

      es.onerror = () => {
        setSseConnected(false);
        es.close();
        if (!disposed) {
          reconnectTimerRef.current = window.setTimeout(connectSse, 5000);
        }
      };

      es.addEventListener('license_status_changed', handleLicenseEvent);
      es.addEventListener('admin_locked', handleAdminLockedEvent);
    };

    connectSse();
    return () => {
      disposed = true;
      if (reconnectTimerRef.current != null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [setLockedLocal]);

  useEffect(() => {
    refreshStatus();
    const interval = window.setInterval(() => {
      void refreshStatus();
    }, 5000);
    return () => window.clearInterval(interval);
  }, [refreshStatus]);

  const value = useMemo<AdminSecurityContextValue>(
    () => ({
      licenseValid,
      licenseReason,
      adminUnlocked,
      adminLicenseValid,
      adminLicenseReason,
      adminLicenseExpiresAt,
      adminLicenseInGrace,
      adminLicenseGraceUntil,
      adminLicenseId,
      recoveryOverrideActive,
      recoveryOverrideUntil,
      recoveryCodesRemaining,
      adminToken,
      sseConnected,
      loading,
      refreshStatus,
      unlock,
      lock,
      consumeRecoveryCode,
    }),
    [
      licenseValid,
      licenseReason,
      adminLicenseValid,
      adminLicenseReason,
      adminLicenseExpiresAt,
      adminLicenseInGrace,
      adminLicenseGraceUntil,
      adminLicenseId,
      recoveryOverrideActive,
      recoveryOverrideUntil,
      recoveryCodesRemaining,
      adminUnlocked,
      adminToken,
      sseConnected,
      loading,
      refreshStatus,
      unlock,
      lock,
      consumeRecoveryCode,
    ],
  );

  return <AdminSecurityContext.Provider value={value}>{children}</AdminSecurityContext.Provider>;
};

export function useAdminSecurity(): AdminSecurityContextValue {
  const context = useContext(AdminSecurityContext);
  if (!context) {
    throw new Error('useAdminSecurity must be used within AdminSecurityProvider');
  }
  return context;
}
