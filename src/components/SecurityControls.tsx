import React from 'react';
import { useAdminSecurity } from '../utilis/useAdminSecurity';

type SecurityControlsProps = {
  disabled?: boolean;
};

const SecurityControls: React.FC<SecurityControlsProps> = ({ disabled = false }) => {
  const {
    licenseValid,
    licenseReason,
    adminUnlocked,
    loading,
    sseConnected,
    unlock,
    lock,
  } = useAdminSecurity();

  return (
    <div className="flex items-center gap-2">
      <span
        className={`modern-badge ${
          licenseValid ? 'modern-badge-success' : 'modern-badge-danger'
        }`}
      >
        USB {licenseValid ? 'Connected' : 'Disconnected'}
      </span>
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
          disabled={disabled || loading || !licenseValid}
          onClick={() => void unlock()}
          title={!licenseValid ? `USB not valid (${licenseReason})` : 'Unlock admin actions'}
        >
          Unlock
        </button>
      )}
    </div>
  );
};

export default SecurityControls;

