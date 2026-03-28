import React, { FC } from 'react';

type Props = {
  styles: Record<string, string>;
  disabled: boolean;
  openPublicQrDialog: () => void;
  openPublicRankings: () => void;
};

const ControlPanelPublicSection: FC<Props> = ({
  styles,
  disabled,
  openPublicQrDialog,
  openPublicRankings,
}) => (
  <div className="space-y-4">
    <div className="grid grid-cols-[repeat(2,minmax(260px,1fr))] gap-3 overflow-x-auto">
      <div className={styles.adminCard}>
        <div className={styles.adminCardTitle}>Public View</div>
        <div className="flex flex-col gap-2 mt-3">
          <button
            className="modern-btn modern-btn-ghost"
            onClick={openPublicQrDialog}
            type="button"
            disabled={disabled}
          >
            Show public QR
          </button>
          <button
            className="modern-btn modern-btn-ghost"
            onClick={openPublicRankings}
            type="button"
            disabled={disabled}
          >
            Open public rankings
          </button>
        </div>
      </div>
    </div>
  </div>
);

export default ControlPanelPublicSection;
