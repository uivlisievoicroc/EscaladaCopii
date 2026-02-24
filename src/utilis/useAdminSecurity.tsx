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
  forceAdminSecurityLock,
  getAdminSecurityToken,
  lockAdminSecurity,
  refreshAdminSecurityStatus,
  unlockAdminSecurity,
} from './adminSecurityService';

const API_PROTOCOL = window.location.protocol === 'https:' ? 'https' : 'http';
const API_BASE = `${API_PROTOCOL}://${window.location.hostname}:8000`;

type AdminSecurityContextValue = {
  licenseValid: boolean;
  licenseReason: string;
  adminUnlocked: boolean;
  adminToken: string | null;
  sseConnected: boolean;
  loading: boolean;
  refreshStatus: () => Promise<void>;
  unlock: () => Promise<void>;
  lock: () => Promise<void>;
};

const AdminSecurityContext = createContext<AdminSecurityContextValue | null>(null);

const DEFAULT_LOCK_REASON = 'not_checked';

export const AdminSecurityProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [licenseValid, setLicenseValid] = useState<boolean>(false);
  const [licenseReason, setLicenseReason] = useState<string>(DEFAULT_LOCK_REASON);
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
    (status: {
      license_valid: boolean;
      license_reason: string;
      admin_unlocked: boolean;
    }) => {
      setLicenseValid(!!status.license_valid);
      setLicenseReason(status.license_reason || 'error');
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
      adminToken,
      sseConnected,
      loading,
      refreshStatus,
      unlock,
      lock,
    }),
    [
      licenseValid,
      licenseReason,
      adminUnlocked,
      adminToken,
      sseConnected,
      loading,
      refreshStatus,
      unlock,
      lock,
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

