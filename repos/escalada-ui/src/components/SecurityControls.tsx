import React from 'react';
import { useAdminSecurity } from '../utilis/useAdminSecurity';

type SecurityControlsProps = {
  disabled?: boolean;
};

const SecurityControls: React.FC<SecurityControlsProps> = ({ disabled = false }) => {
  const {
    licenseValid,
    licenseReason,
    adminLicenseValid,
    adminLicenseReason,
    recoveryOverrideActive,
    recoveryOverrideUntil,
    recoveryCodesRemaining,
    adminUnlocked,
    loading,
    sseConnected,
    unlock,
    lock,
    consumeRecoveryCode,
  } = useAdminSecurity();
  const [recoveryCodeInput, setRecoveryCodeInput] = React.useState<string>('');
  const [recoverySubmitting, setRecoverySubmitting] = React.useState<boolean>(false);
  const [recoveryMessage, setRecoveryMessage] = React.useState<{
    type: 'success' | 'error';
    text: string;
  } | null>(null);

  const formatDateTime = (value: string | null): string => {
    if (!value) return '—';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString();
  };

  const onUnlock = async (): Promise<void> => {
    try {
      await unlock();
    } catch (error) {
      const message =
        error instanceof Error && error.message ? error.message : String(error);
      alert(
        `Unlock failed (${message}).\n\n` +
          `Note: Unlock is allowed only on the host/admin laptop (trusted IP).`,
      );
    }
  };
  const onActivateRecovery = async (): Promise<void> => {
    const code = recoveryCodeInput.trim();
    if (!code) {
      setRecoveryMessage({ type: 'error', text: 'Enter a recovery code first.' });
      return;
    }

    setRecoverySubmitting(true);
    setRecoveryMessage(null);
    try {
      await consumeRecoveryCode(code);
      setRecoveryCodeInput('');
      setRecoveryMessage({
        type: 'success',
        text: 'Emergency override activated for 24 hours.',
      });
    } catch (error) {
      const raw = error instanceof Error ? error.message : String(error);
      const codePrefix = raw.split(':', 1)[0] || 'unknown';
      let message = `Activation failed (${codePrefix}).`;
      if (codePrefix === 'RECOVERY_CODE_INVALID') {
        message = 'Recovery code is invalid or already used.';
      } else if (codePrefix === 'RECOVERY_RATE_LIMIT') {
        message = 'Too many attempts. Please wait and try again.';
      } else if (codePrefix === 'OVERRIDE_ALREADY_ACTIVE') {
        message = 'Emergency override is already active.';
      } else if (codePrefix === 'ADMIN_LICENSE_REQUIRED') {
        message = 'Admin license is invalid or expired.';
      } else if (codePrefix === 'ADMIN_TRUSTED_IP_REQUIRED') {
        message = 'Emergency recovery can be activated only from trusted admin IPs.';
      }
      setRecoveryMessage({ type: 'error', text: message });
    } finally {
      setRecoverySubmitting(false);
    }
  };

  const unlockAllowed = (licenseValid || recoveryOverrideActive) && adminLicenseValid;

  return (
    <div className="flex flex-col gap-2 items-end">
      <div className="flex items-center gap-2 flex-wrap justify-end">
        <span
          className={`modern-badge ${
            licenseValid ? 'modern-badge-success' : 'modern-badge-danger'
          }`}
        >
          USB {licenseValid ? 'Connected' : 'Disconnected'}
        </span>
        <span
          className={`modern-badge ${
            adminLicenseValid ? 'modern-badge-success' : 'modern-badge-danger'
          }`}
        >
          Admin License {adminLicenseValid ? 'Valid' : 'Invalid'}
        </span>
        {recoveryOverrideActive && (
          <span className="modern-badge modern-badge-warning">
            Override until {formatDateTime(recoveryOverrideUntil)}
          </span>
        )}
        <span className="modern-badge modern-badge-neutral">
          {adminUnlocked ? 'Unlocked' : 'Locked'}
        </span>
        <span className="modern-badge modern-badge-neutral">
          {sseConnected ? 'Live' : 'Polling'}
        </span>
        {adminUnlocked ? (
          <button
            className="modern-btn modern-btn-ghost"
            type="button"
            disabled={disabled || loading}
            onClick={() => void lock()}
          >
            Lock
          </button>
        ) : (
          <button
            className="modern-btn modern-btn-primary"
            type="button"
            disabled={disabled || loading || !unlockAllowed}
            onClick={() => void onUnlock()}
            title={
              !adminLicenseValid
                ? `Admin license invalid (${adminLicenseReason})`
                : !licenseValid && !recoveryOverrideActive
                ? `USB not valid (${licenseReason}) and no emergency override active`
                : 'Unlock admin actions'
            }
          >
            Unlock
          </button>
        )}
      </div>
      <div className="flex items-center gap-2 flex-wrap justify-end">
        <span className="text-xs text-secondary">Emergency recovery</span>
        <input
          type="text"
          value={recoveryCodeInput}
          onChange={(event) => setRecoveryCodeInput(event.target.value.toUpperCase())}
          placeholder="XXXX-XXXX-XXXX-XXXX"
          className="modern-input"
          disabled={disabled || loading || recoverySubmitting}
        />
        <button
          className="modern-btn modern-btn-primary"
          type="button"
          disabled={disabled || loading || recoverySubmitting || !adminLicenseValid}
          onClick={() => void onActivateRecovery()}
          title={
            adminLicenseValid
              ? 'Activate emergency override'
              : `Admin license invalid (${adminLicenseReason})`
          }
        >
          Activate override
        </button>
        <span className="modern-badge modern-badge-neutral">
          Remaining: {recoveryCodesRemaining}
        </span>
      </div>
      {recoveryMessage && (
        <div
          className={`text-xs ${
            recoveryMessage.type === 'success' ? 'text-green-400' : 'text-red-400'
          }`}
        >
          {recoveryMessage.text}
        </div>
      )}
    </div>
  );
};

export default SecurityControls;
