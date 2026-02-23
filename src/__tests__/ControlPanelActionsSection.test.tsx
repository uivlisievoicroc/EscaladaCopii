import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import ControlPanelActionsSection from '../components/control-panel/ControlPanelActionsSection';

const baseStyles = {
  adminCard: 'adminCard',
  adminCardTitle: 'adminCardTitle',
  modalField: 'modalField',
  modalLabel: 'modalLabel',
  modalSelect: 'modalSelect',
};

const baseProps = {
  styles: baseStyles,
  listboxes: [{ categorie: 'Seniori', initiated: true }],
  initiatedBoxIds: [0],
  scoringEnabled: true,
  scoringBoxId: 0,
  setScoringBoxId: vi.fn(),
  scoringBoxSelected: true,
  scoringBoxHasMarked: true,
  showTieBreaksEnabled: true,
  openModifyScoreFromAdmin: vi.fn(),
  openCeremonyFromAdmin: vi.fn(),
  openShowTieBreaksDialog: vi.fn(),
  judgeAccessEnabled: true,
  judgeAccessBoxId: 0,
  setJudgeAccessBoxId: vi.fn(),
  judgeAccessSelected: true,
  judgeAccessBox: { categorie: 'Seniori', initiated: true },
  openSetJudgePasswordDialog: vi.fn(),
  openQrDialog: vi.fn(),
  openJudgeViewFromAdmin: vi.fn(),
  setupBoxId: 0,
  setSetupBoxId: vi.fn(),
  openBoxTimerDialog: vi.fn(),
  openRoutesetterDialog: vi.fn(),
};

describe('ControlPanelActionsSection - Show Tie-breaks button', () => {
  it('renders Show Tie-breaks and triggers dialog callback', () => {
    render(<ControlPanelActionsSection {...baseProps} />);

    const button = screen.getByRole('button', { name: 'Show Tie-breaks' });
    expect(button).toBeEnabled();

    fireEvent.click(button);
    expect(baseProps.openShowTieBreaksDialog).toHaveBeenCalledTimes(1);
  });

  it('disables Show Tie-breaks when scoring category is not selected', () => {
    render(
      <ControlPanelActionsSection
        {...baseProps}
        scoringBoxSelected={false}
        showTieBreaksEnabled={false}
      />,
    );

    const button = screen.getByRole('button', { name: 'Show Tie-breaks' });
    expect(button).toBeDisabled();
  });
});

