import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, act, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import ControlPanel from '../components/ControlPanel';


// Silence debug logging in tests
vi.mock('../utilis/debug', () => ({
  debugLog: vi.fn(),
  debugWarn: vi.fn(),
  debugError: vi.fn(),
}));

// Mock auth to bypass login overlay
vi.mock('../utilis/auth', () => ({
  getStoredToken: () => 'fake-test-token',
  getStoredRole: () => 'admin',
  getStoredBoxes: () => [],
  getAuthHeader: () => ({}),
  isAuthenticated: () => true,
  clearAuth: vi.fn(),
  logout: vi.fn(),
  login: vi.fn(),
}));

vi.mock('../utilis/useAdminSecurity', () => ({
  useAdminSecurity: () => ({
    licenseValid: true,
    licenseReason: 'ok',
    adminLicenseValid: true,
    adminLicenseReason: 'ok',
    adminLicenseExpiresAt: null,
    adminLicenseInGrace: false,
    adminLicenseGraceUntil: null,
    adminLicenseId: 'lic-test',
    recoveryOverrideActive: false,
    recoveryOverrideUntil: null,
    recoveryCodesRemaining: 20,
    adminUnlocked: true,
    adminToken: 'test-usb-token',
    sseConnected: true,
    loading: false,
    refreshStatus: vi.fn(),
    unlock: vi.fn(),
    lock: vi.fn(),
    consumeRecoveryCode: vi.fn(),
  }),
  AdminSecurityProvider: ({ children }) => <>{children}</>,
}));

let consoleWarnSpy;

function seedLocalStorageForTwoBoxes() {
  const listboxes = [
    {
      categorie: 'U16-Baieti',
      routesCount: 2,
      holdsCounts: [10, 12],
      routeIndex: 1,
      holdsCount: 10,
      initiated: true,
      timerPreset: '05:00',
      concurenti: [
        { nume: 'Ion', club: 'Alpin', marked: false },
        { nume: 'Mihai', club: 'Climb', marked: false },
      ],
    },
    {
      categorie: 'U16-Fete',
      routesCount: 2,
      holdsCounts: [8, 9],
      routeIndex: 1,
      holdsCount: 8,
      initiated: true,
      timerPreset: '05:00',
      concurenti: [
        { nume: 'Ana', club: 'Alpin', marked: false },
        { nume: 'Maria', club: 'Climb', marked: false },
      ],
    },
  ];

  // time criterion enabled
  global.localStorage.getItem.mockImplementation((key) => {
    if (key === 'listboxes') return JSON.stringify(listboxes);
    if (key === 'climbingTime') return JSON.stringify('05:00');
    if (key === 'timeCriterionEnabled-0') return 'on';
    if (key === 'timeCriterionEnabled-1') return 'on';
    if (key === 'timeCriterionEnabled') return 'on';
    // timer values used by readCurrentTimerSec
    if (key === 'timer-0') return '250'; // 4:10 remaining
    if (key === 'timer-1') return '295'; // 4:55 remaining
    return null;
  });
}

function buildPrevRoundsPendingEvent({
  rank = 4,
  fingerprint = `tb-prev-r${rank}`,
  members = [
    { name: 'Ana', time: 91.2, value: 2.0 },
    { name: 'Maria', time: 92.7, value: 2.0 },
  ],
  missingPrevRoundsMembers = members.map((member) => member.name),
} = {}) {
  return {
    context: 'overall',
    rank,
    members,
    fingerprint,
    stage: 'previous_rounds',
    affects_podium: rank <= 3,
    status: 'pending',
    detail: 'previous_rounds_pending',
    requires_prev_rounds_input: true,
    missing_prev_rounds_members: missingPrevRoundsMembers,
    is_resolved: false,
  };
}

async function emitControlPanelSnapshot(boxId, snapshot) {
  const getWsForBox = () => {
    for (let idx = global.WebSocket.mock.calls.length - 1; idx >= 0; idx -= 1) {
      const [url] = global.WebSocket.mock.calls[idx] || [];
      if (String(url).endsWith(`/api/ws/${boxId}`)) {
        return global.WebSocket.mock.results[idx]?.value ?? null;
      }
    }
    return null;
  };

  await waitFor(() => {
    expect(getWsForBox()?.onmessage).toBeTypeOf('function');
  });
  const ws = getWsForBox();
  await act(async () => {
    ws.onmessage({
      data: JSON.stringify({
        type: 'STATE_SNAPSHOT',
        boxId,
        ...snapshot,
      }),
    });
  });
}

describe('ControlPanel button flows', () => {
  beforeEach(() => {
    // reset mocks
    global.localStorage.getItem.mockReset();
    global.localStorage.setItem.mockReset();
    global.localStorage.removeItem.mockReset();
    seedLocalStorageForTwoBoxes();

    // mock fetch
    global.fetch = vi.fn(async () => ({ ok: true, json: async () => ({}) }));
    consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleWarnSpy?.mockRestore();
  });

  const openActionsSection = async () => {
    const actionsButtons = await screen.findAllByRole('button', { name: 'Actions' });
    await act(async () => {
      actionsButtons[0].click();
    });
  };

  it('sends PROGRESS_UPDATE when clicking +1 Hold for each listbox', async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <ControlPanel />
        </MemoryRouter>,
      );
    });

    // Start both boxes to enable +1 Hold
    const startButtons = await screen.findAllByText(/Start Timer/i);
    expect(startButtons.length).toBeGreaterThanOrEqual(2);
    // click for first two boxes
    await act(async () => {
      startButtons[0].click();
      startButtons[1].click();
    });

    const plusHoldButtons = await screen.findAllByText('+1 Hold');
    expect(plusHoldButtons.length).toBeGreaterThanOrEqual(2);

    await act(async () => {
      plusHoldButtons[0].click();
      plusHoldButtons[1].click();
    });

    // Verify fetch called with PROGRESS_UPDATE for both boxes
    const calls = global.fetch.mock.calls.map((c) => ({ url: c[0], body: c[1]?.body }));
    const progressCalls = calls.filter(
      (c) => typeof c.body === 'string' && c.body.includes('PROGRESS_UPDATE'),
    );
    // At least two progress updates (one per box)
    expect(progressCalls.length).toBeGreaterThanOrEqual(2);
    // Ensure boxIds 0 and 1 present
    const hasBox0 = progressCalls.some((c) => c.body.includes('"boxId":0'));
    const hasBox1 = progressCalls.some((c) => c.body.includes('"boxId":1'));
    expect(hasBox0).toBe(true);
    expect(hasBox1).toBe(true);
  });

  it('does not render Register Time button', async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <ControlPanel />
        </MemoryRouter>,
      );
    });

    await screen.findAllByText(/Start Timer/i);

    expect(screen.queryByText('Register Time')).toBeNull();
  });

  it('opens Insert Score modal without ContestPage open', async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <ControlPanel />
        </MemoryRouter>,
      );
    });

    await screen.findAllByText(/Start Timer/i);

    // Simulate a current climber update (normally written by ContestPage/Judge flows)
    await act(async () => {
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: 'currentClimber-0',
          newValue: JSON.stringify('Ion'),
        }),
      );
    });

    const insertButtons = await screen.findAllByText(/Insert Score/i);
    expect(insertButtons.length).toBeGreaterThanOrEqual(1);

    await act(async () => {
      insertButtons[0].click();
    });

    expect(await screen.findByLabelText('Score')).toBeInTheDocument();
  });

  it('opens Insert Score modal via backend state when currentClimber is missing', async () => {
    // mock fetch: /state returns currentClimber so modal can open headlessly
    global.fetch = vi.fn(async (url) => {
      if (String(url).includes('/api/state/0')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ currentClimber: 'Ion', sessionId: 'sid-0', boxVersion: 1 }),
        };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    await act(async () => {
      render(
        <MemoryRouter>
          <ControlPanel />
        </MemoryRouter>,
      );
    });

    const insertButtons = await screen.findAllByText(/Insert Score/i);
    expect(insertButtons.length).toBeGreaterThanOrEqual(1);

    await act(async () => {
      insertButtons[0].click();
    });

    expect(await screen.findByLabelText('Score')).toBeInTheDocument();
  });

  it('opens and closes Show Tie-breaks modal with fallback when tie-break snapshot is missing', async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <ControlPanel />
        </MemoryRouter>,
      );
    });

    await openActionsSection();

    const showButtons = await screen.findAllByRole('button', { name: 'Show Tie-breaks' });
    expect(showButtons[0]).toBeEnabled();
    await act(async () => {
      showButtons[0].click();
    });

    expect(await screen.findByText('Tie-break overview')).toBeInTheDocument();
    const hasMissingDataFallback = !!screen.queryByText(
      'No tie-break data available for this category yet.',
    );
    const hasNoEventsFallback = !!screen.queryByText(
      'No tie-break events recorded for this category.',
    );
    expect(hasMissingDataFallback || hasNoEventsFallback).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByText('Tie-break overview')).not.toBeInTheDocument();
  });

  it('shows TB Prev modal for unresolved non-podium ties from state snapshot', async () => {
    const pendingGroup = buildPrevRoundsPendingEvent({
      fingerprint: 'tb-prev-r4',
      members: [
        { name: 'Ana', time: 91.2, value: 2.0 },
        { name: 'Maria', time: 92.7, value: 2.0 },
      ],
      missingPrevRoundsMembers: ['Ana', 'Maria'],
    });
    global.fetch = vi.fn(async (url) => {
      if (String(url).includes('/api/state/0')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            sessionId: 'sid-0',
            boxVersion: 3,
            timeCriterionEnabled: true,
            timeTiebreakHasEligibleTie: true,
            leadRankingResolved: false,
            leadTieEvents: [pendingGroup],
          }),
        };
      }
      if (String(url).includes('/api/state/1')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            sessionId: 'sid-1',
            boxVersion: 1,
            timeCriterionEnabled: true,
          }),
        };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    await act(async () => {
      render(
        <MemoryRouter>
          <ControlPanel />
        </MemoryRouter>,
      );
    });

    expect(
      await screen.findByText(/Set previous-round rank for each newly tied athlete/i),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm TB Prev' })).toBeInTheDocument();
  });

  it('reopens pending non-podium TB Prev from Show Tie-breaks without stacking duplicates', async () => {
    const pendingGroup = buildPrevRoundsPendingEvent({
      fingerprint: 'tb-prev-r4-reopen',
      members: [
        { name: 'Ana', time: 61, value: 4.743 },
        { name: 'Preda Emilia', time: 63, value: 4.743 },
      ],
      missingPrevRoundsMembers: ['Ana', 'Preda Emilia'],
    });
    global.fetch = vi.fn(async (url) => {
      if (String(url).includes('/api/state/0')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            sessionId: 'sid-0',
            boxVersion: 3,
            timeCriterionEnabled: true,
            timeTiebreakHasEligibleTie: true,
            leadRankingResolved: false,
            leadTieEvents: [pendingGroup],
          }),
        };
      }
      if (String(url).includes('/api/state/1')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            sessionId: 'sid-1',
            boxVersion: 1,
            timeCriterionEnabled: true,
          }),
        };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    await act(async () => {
      render(
        <MemoryRouter>
          <ControlPanel />
        </MemoryRouter>,
      );
    });

    expect(
      await screen.findByText(/Set previous-round rank for each newly tied athlete/i),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Later' }));
    await waitFor(() => {
      expect(
        screen.queryByText(/Set previous-round rank for each newly tied athlete/i),
      ).not.toBeInTheDocument();
    });

    await openActionsSection();
    const showButtons = await screen.findAllByRole('button', { name: 'Show Tie-breaks' });
    fireEvent.click(showButtons[0]);

    expect(await screen.findByText('Tie-break overview')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Resolve now' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Resolve now' }));

    await waitFor(() => {
      expect(screen.queryByText('Tie-break overview')).not.toBeInTheDocument();
    });
    expect(
      await screen.findByText(/Set previous-round rank for each newly tied athlete/i),
    ).toBeInTheDocument();
    expect((await screen.findAllByText('Preda Emilia')).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: 'Later' }));
    await waitFor(() => {
      expect(
        screen.queryByText(/Set previous-round rank for each newly tied athlete/i),
      ).not.toBeInTheDocument();
    });

    const showButtonsAgain = await screen.findAllByRole('button', { name: 'Show Tie-breaks' });
    fireEvent.click(showButtonsAgain[0]);
    expect(await screen.findByText('Tie-break overview')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Resolve now' }));
    expect(
      await screen.findByText(/Set previous-round rank for each newly tied athlete/i),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Later' }));
    await waitFor(() => {
      expect(
        screen.queryByText(/Set previous-round rank for each newly tied athlete/i),
      ).not.toBeInTheDocument();
    });
  });

  it('opens the correct pending request from Show Tie-breaks when multiple TB Prev events exist', async () => {
    const firstGroup = buildPrevRoundsPendingEvent({
      rank: 4,
      fingerprint: 'tb-prev-r4-multi',
      members: [
        { name: 'Ana', time: 91.2, value: 2.0 },
        { name: 'Maria', time: 92.7, value: 2.0 },
      ],
      missingPrevRoundsMembers: ['Ana', 'Maria'],
    });
    const secondGroup = buildPrevRoundsPendingEvent({
      rank: 6,
      fingerprint: 'tb-prev-r6-multi',
      members: [
        { name: 'Ioana', time: 81.2, value: 6.0 },
        { name: 'Sara', time: 82.7, value: 6.0 },
      ],
      missingPrevRoundsMembers: ['Ioana', 'Sara'],
    });
    global.fetch = vi.fn(async (url) => {
      if (String(url).includes('/api/state/0')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            sessionId: 'sid-0',
            boxVersion: 3,
            timeCriterionEnabled: true,
            timeTiebreakHasEligibleTie: true,
            leadRankingResolved: false,
            leadTieEvents: [firstGroup, secondGroup],
          }),
        };
      }
      if (String(url).includes('/api/state/1')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            sessionId: 'sid-1',
            boxVersion: 1,
            timeCriterionEnabled: true,
          }),
        };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    await act(async () => {
      render(
        <MemoryRouter>
          <ControlPanel />
        </MemoryRouter>,
      );
    });

    expect(
      await screen.findByText(/Set previous-round rank for each newly tied athlete/i),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Later' }));
    expect((await screen.findAllByText('Ioana')).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: 'Later' }));
    await waitFor(() => {
      expect(
        screen.queryByText(/Set previous-round rank for each newly tied athlete/i),
      ).not.toBeInTheDocument();
    });

    await openActionsSection();
    const showButtons = await screen.findAllByRole('button', { name: 'Show Tie-breaks' });
    fireEvent.click(showButtons[0]);
    expect(await screen.findByText('Tie-break overview')).toBeInTheDocument();

    const resolveButtons = screen.getAllByRole('button', { name: 'Resolve now' });
    expect(resolveButtons).toHaveLength(2);
    fireEvent.click(resolveButtons[1]);

    await waitFor(() => {
      expect(screen.queryByText('Tie-break overview')).not.toBeInTheDocument();
    });
    expect((await screen.findAllByText('Ioana')).length).toBeGreaterThan(0);
    expect((await screen.findAllByText('Sara')).length).toBeGreaterThan(0);
  });

  it('marks history-only pending TB Prev items as non-actionable in Show Tie-breaks', async () => {
    const pendingGroup = buildPrevRoundsPendingEvent({
      fingerprint: 'tb-prev-r4-history',
      members: [
        { name: 'Ana Fîntîneanu', time: 1, value: 4.743 },
        { name: 'Preda Emilia', time: 3, value: 4.743 },
      ],
      missingPrevRoundsMembers: ['Ana Fîntîneanu', 'Preda Emilia'],
    });
    global.fetch = vi.fn(async (url) => {
      if (String(url).includes('/api/state/0')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            sessionId: 'sid-0',
            boxVersion: 3,
            timeCriterionEnabled: true,
            timeTiebreakHasEligibleTie: true,
            leadRankingResolved: false,
            leadTieEvents: [pendingGroup],
          }),
        };
      }
      if (String(url).includes('/api/state/1')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            sessionId: 'sid-1',
            boxVersion: 1,
            timeCriterionEnabled: true,
          }),
        };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    await act(async () => {
      render(
        <MemoryRouter>
          <ControlPanel />
        </MemoryRouter>,
      );
    });

    expect(
      await screen.findByText(/Set previous-round rank for each newly tied athlete/i),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Later' }));
    await waitFor(() => {
      expect(
        screen.queryByText(/Set previous-round rank for each newly tied athlete/i),
      ).not.toBeInTheDocument();
    });

    await emitControlPanelSnapshot(0, {
      sessionId: 'sid-0',
      boxVersion: 4,
      timeCriterionEnabled: true,
      timeTiebreakHasEligibleTie: false,
      leadRankingResolved: true,
      leadTieEvents: [],
    });

    await openActionsSection();
    const showButtons = await screen.findAllByRole('button', { name: 'Show Tie-breaks' });
    fireEvent.click(showButtons[0]);
    expect(await screen.findByText('Tie-break overview')).toBeInTheDocument();
    expect(screen.getByText('Overall rank #4')).toBeInTheDocument();
    expect(
      screen.getByText('Historical event; not currently actionable.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Resolve now' })).not.toBeInTheDocument();
  });

  it('keeps Resolve now available for pending TB Prev overview items when the snapshot is unresolved but eligibleGroups are temporarily missing', async () => {
    const pendingGroup = buildPrevRoundsPendingEvent({
      fingerprint: 'tb-prev-r4-stale-snapshot',
      members: [
        { name: 'Cinca Albert', time: 1, value: 4.5 },
        { name: 'Scutelnicu Ilie Nicolas', time: 156, value: 4.5 },
      ],
      missingPrevRoundsMembers: ['Cinca Albert', 'Scutelnicu Ilie Nicolas'],
    });
    global.fetch = vi.fn(async (url) => {
      if (String(url).includes('/api/state/0')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            sessionId: 'sid-0',
            boxVersion: 3,
            timeCriterionEnabled: true,
            timeTiebreakHasEligibleTie: true,
            leadRankingResolved: false,
            leadTieEvents: [pendingGroup],
          }),
        };
      }
      if (String(url).includes('/api/state/1')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            sessionId: 'sid-1',
            boxVersion: 1,
            timeCriterionEnabled: true,
          }),
        };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });

    await act(async () => {
      render(
        <MemoryRouter>
          <ControlPanel />
        </MemoryRouter>,
      );
    });

    expect(
      await screen.findByText(/Set previous-round rank for each newly tied athlete/i),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Later' }));
    await waitFor(() => {
      expect(
        screen.queryByText(/Set previous-round rank for each newly tied athlete/i),
      ).not.toBeInTheDocument();
    });

    await emitControlPanelSnapshot(0, {
      sessionId: 'sid-0',
      boxVersion: 4,
      timeCriterionEnabled: true,
      timeTiebreakHasEligibleTie: true,
      leadRankingResolved: false,
      leadTieEvents: [],
    });

    await openActionsSection();
    const showButtons = await screen.findAllByRole('button', { name: 'Show Tie-breaks' });
    fireEvent.click(showButtons[0]);
    expect(await screen.findByText('Tie-break overview')).toBeInTheDocument();
    expect(screen.getByText('Overall rank #4')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Resolve now' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Resolve now' }));
    await waitFor(() => {
      expect(screen.queryByText('Tie-break overview')).not.toBeInTheDocument();
    });
    expect(
      await screen.findByText(/Set previous-round rank for each newly tied athlete/i),
    ).toBeInTheDocument();
    expect((await screen.findAllByText('Cinca Albert')).length).toBeGreaterThan(0);
  });

  it('submits SUBMIT_SCORE using competitor from backend state', async () => {
    const calls = [];
    global.fetch = vi.fn(async (url, init) => {
      calls.push({ url: String(url), body: init?.body });
      if (String(url).includes('/api/state/0')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ currentClimber: 'Ion', sessionId: 'sid-0', boxVersion: 1 }),
        };
      }
      // /api/cmd calls
      return { ok: true, status: 200, json: async () => ({ status: 'ok' }) };
    });

    await act(async () => {
      render(
        <MemoryRouter>
          <ControlPanel />
        </MemoryRouter>,
      );
    });

    const insertButtons = await screen.findAllByText(/Insert Score/i);
    await act(async () => {
      insertButtons[0].click();
    });
    const scoreInput = await screen.findByLabelText('Score');
    await act(async () => {
      scoreInput.value = '';
    });
    await act(async () => {
      scoreInput.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => {
      scoreInput.value = '5';
      scoreInput.dispatchEvent(new Event('input', { bubbles: true }));
    });

    // Confirm deviation dialog (holds counter differs) if prompted.
    const originalConfirm = window.confirm;
    window.confirm = () => true;
    try {
      const submitButton = await screen.findByText('Submit');
      await act(async () => {
        submitButton.click();
      });
    } finally {
      window.confirm = originalConfirm;
    }

    const cmdCalls = calls.filter((c) => c.url.includes('/api/cmd') && typeof c.body === 'string');
    const submit = cmdCalls.find((c) => c.body.includes('"type":"SUBMIT_SCORE"'));
    expect(submit).toBeTruthy();
    expect(submit.body).toContain('"competitor":"Ion"');
  });

  it('clears per-box persisted keys when deleting the last box', async () => {
    global.localStorage.getItem.mockReset();
    global.localStorage.setItem.mockReset();
    global.localStorage.removeItem.mockReset();

    const listboxes = [
      {
        categorie: 'U16-Baieti',
        routesCount: 1,
        holdsCounts: [10],
        routeIndex: 1,
        holdsCount: 10,
        initiated: true,
        timerPreset: '05:00',
        concurenti: [{ nume: 'Ion', club: 'Alpin', marked: false }],
      },
    ];

    global.localStorage.getItem.mockImplementation((key) => {
      if (key === 'listboxes') return JSON.stringify(listboxes);
      if (key === 'climbingTime') return JSON.stringify('05:00');
      if (key === 'timer-0') return '123';
      if (key === 'timeCriterionEnabled-0') return 'on';
      if (key === 'routesetterName-0-1') return 'Test Routesetter';
      return null;
    });

    global.fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) }));

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    try {
      await act(async () => {
        render(
          <MemoryRouter>
            <ControlPanel />
          </MemoryRouter>,
        );
      });

      const deleteButton = await screen.findByRole('button', { name: /delete/i });
      await act(async () => {
        deleteButton.click();
      });

      await waitFor(() => {
        expect(global.localStorage.removeItem).toHaveBeenCalledWith('escalada_timeCriterionEnabled-0');
      });

      expect(global.localStorage.removeItem).toHaveBeenCalledWith('timeCriterionEnabled-0');
      expect(global.localStorage.removeItem).toHaveBeenCalledWith('escalada_timeCriterionEnabled');
      expect(global.localStorage.removeItem).toHaveBeenCalledWith('timeCriterionEnabled');
      expect(global.localStorage.removeItem).toHaveBeenCalledWith('escalada_timer-0');
      expect(global.localStorage.removeItem).toHaveBeenCalledWith('timer-0');
      expect(global.localStorage.removeItem).toHaveBeenCalledWith('escalada_routesetterName-0-1');
      expect(global.localStorage.removeItem).toHaveBeenCalledWith('routesetterName-0-1');
    } finally {
      confirmSpy.mockRestore();
    }
  });
});
