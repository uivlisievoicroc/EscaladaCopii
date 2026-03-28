import React, { FC } from 'react';
import { sanitizeBoxName } from '../../utilis/sanitize';

type BoxLike = {
  categorie?: string;
  initiated?: boolean;
};

type Props = {
  styles: Record<string, string>;
  adminActionsDisabled: boolean;
  listboxes: BoxLike[];
  initiatedBoxIds: number[];
  scoringEnabled: boolean;
  scoringBoxId: number | null;
  setScoringBoxId: (value: number | null) => void;
  scoringBoxSelected: boolean;
  scoringBoxHasMarked: boolean;
  showTieBreaksEnabled: boolean;
  openModifyScoreFromAdmin: () => void;
  openCeremonyFromAdmin: () => void;
  openShowTieBreaksDialog: () => void;
  judgeAccessEnabled: boolean;
  judgeAccessBoxId: number | null;
  setJudgeAccessBoxId: (value: number | null) => void;
  judgeAccessSelected: boolean;
  judgeAccessBox: BoxLike | null;
  openSetJudgePasswordDialog: (boxId: number) => void;
  openQrDialog: (boxId: number) => void;
  openJudgeViewFromAdmin: () => void;
  setupBoxId: number | null;
  setSetupBoxId: (value: number | null) => void;
  openBoxTimerDialog: (boxId: number | null) => void;
  openRoutesetterDialog: (boxId: number | null) => void;
};

const ControlPanelActionsSection: FC<Props> = ({
  styles,
  adminActionsDisabled,
  listboxes,
  initiatedBoxIds,
  scoringEnabled,
  scoringBoxId,
  setScoringBoxId,
  scoringBoxSelected,
  scoringBoxHasMarked,
  showTieBreaksEnabled,
  openModifyScoreFromAdmin,
  openCeremonyFromAdmin,
  openShowTieBreaksDialog,
  judgeAccessEnabled,
  judgeAccessBoxId,
  setJudgeAccessBoxId,
  judgeAccessSelected,
  judgeAccessBox,
  openSetJudgePasswordDialog,
  openQrDialog,
  openJudgeViewFromAdmin,
  setupBoxId,
  setSetupBoxId,
  openBoxTimerDialog,
  openRoutesetterDialog,
}) => (
  <div className="space-y-4">
    <div className="grid grid-cols-[repeat(3,minmax(260px,1fr))] gap-3 overflow-x-auto">
      <div className={styles.adminCard}>
        <div className={styles.adminCardTitle}>Scoring</div>
        <label className={styles.modalField}>
          <span className={styles.modalLabel}>Select category</span>
          <select
            className={styles.modalSelect}
            value={scoringBoxId ?? ''}
            onChange={(e) => {
              const value = e.target.value;
              setScoringBoxId(value === '' ? null : Number(value));
            }}
            disabled={adminActionsDisabled || !scoringEnabled}
          >
            {scoringEnabled ? (
              initiatedBoxIds.map((idx) => (
                <option key={idx} value={idx}>
                  {sanitizeBoxName(listboxes[idx].categorie || `Box ${idx}`)}
                </option>
              ))
            ) : (
              <option value="">No initiated boxes</option>
            )}
          </select>
        </label>
        {!scoringEnabled && (
          <div className="text-xs" style={{ color: 'var(--text-tertiary)', marginTop: '8px' }}>
            upload a category and initiate contest
          </div>
        )}
        <div className="mt-3 flex flex-col gap-2">
          <button
            className="modern-btn modern-btn-ghost"
            onClick={openModifyScoreFromAdmin}
            disabled={adminActionsDisabled || !scoringBoxSelected || !scoringBoxHasMarked}
            type="button"
          >
            Modify score
          </button>
          <button
            className="modern-btn modern-btn-ghost"
            onClick={openCeremonyFromAdmin}
            disabled={adminActionsDisabled || !scoringBoxSelected}
            type="button"
          >
            Award ceremony
          </button>
          <button
            className="modern-btn modern-btn-ghost"
            onClick={openShowTieBreaksDialog}
            disabled={adminActionsDisabled || !showTieBreaksEnabled}
            type="button"
          >
            Show Tie-breaks
          </button>
        </div>
      </div>

      <div className={styles.adminCard}>
        <div className={styles.adminCardTitle}>Judge access</div>
        <label className={styles.modalField}>
          <span className={styles.modalLabel}>Select category</span>
          <select
            className={styles.modalSelect}
            value={judgeAccessBoxId ?? ''}
            onChange={(e) => {
              const value = e.target.value;
              setJudgeAccessBoxId(value === '' ? null : Number(value));
            }}
            disabled={adminActionsDisabled || !judgeAccessEnabled}
          >
            {judgeAccessEnabled ? (
              listboxes.map((b, idx) => (
                <option key={idx} value={idx}>
                  {sanitizeBoxName(b.categorie || `Box ${idx}`)}
                </option>
              ))
            ) : (
              <option value="">No boxes available</option>
            )}
          </select>
        </label>
        {!judgeAccessEnabled && (
          <div className="text-xs" style={{ color: 'var(--text-tertiary)', marginTop: '8px' }}>
            upload a category and initiate contest
          </div>
        )}
        <div className="mt-3 flex flex-col gap-2">
          <button
            className="modern-btn modern-btn-ghost"
            onClick={() => {
              if (judgeAccessBoxId == null) return;
              openSetJudgePasswordDialog(judgeAccessBoxId);
            }}
            disabled={adminActionsDisabled || !judgeAccessSelected}
            type="button"
          >
            Set judge password
          </button>
          <button
            className="modern-btn modern-btn-ghost"
            onClick={() => {
              if (judgeAccessBoxId == null) return;
              openQrDialog(judgeAccessBoxId);
            }}
            disabled={adminActionsDisabled || !judgeAccessSelected}
            type="button"
          >
            Generate QR
          </button>
          <button
            className="modern-btn modern-btn-ghost"
            onClick={openJudgeViewFromAdmin}
            disabled={adminActionsDisabled || !judgeAccessSelected || !judgeAccessBox?.initiated}
            type="button"
          >
            Open judge view
          </button>
        </div>
      </div>

      <div className={styles.adminCard}>
        <div className={styles.adminCardTitle}>Setup</div>
        <label className={styles.modalField}>
          <span className={styles.modalLabel}>Select category</span>
          <select
            className={styles.modalSelect}
            value={listboxes.length === 0 ? '' : setupBoxId ?? 0}
            onChange={(e) => {
              const value = e.target.value;
              setSetupBoxId(value === '' ? null : Number(value));
            }}
            disabled={adminActionsDisabled || listboxes.length === 0}
          >
            {listboxes.length === 0 ? (
              <option value="">No boxes available</option>
            ) : (
              listboxes.map((b, idx) => (
                <option key={idx} value={idx}>
                  {sanitizeBoxName(b.categorie || `Box ${idx}`)}
                </option>
              ))
            )}
          </select>
        </label>
        <div className="flex flex-col gap-2 mt-3">
          <button
            className="modern-btn modern-btn-ghost"
            onClick={() => openBoxTimerDialog(setupBoxId)}
            disabled={adminActionsDisabled || listboxes.length === 0 || setupBoxId == null}
            type="button"
          >
            Set timer
          </button>
          <button
            className="modern-btn modern-btn-ghost"
            onClick={() => openRoutesetterDialog(setupBoxId)}
            disabled={adminActionsDisabled || listboxes.length === 0 || setupBoxId == null}
            type="button"
          >
            Set competition officials
          </button>
        </div>
      </div>
    </div>
  </div>
);

export default ControlPanelActionsSection;
