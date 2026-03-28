import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import JudgePage from '../components/JudgePage';

const authState = {
  authenticated: true,
};

const wsHookMock = vi.fn();
const updateProgressMock = vi.fn();
const startTimerMock = vi.fn();
const stopTimerMock = vi.fn();
const resumeTimerMock = vi.fn();
const submitScoreMock = vi.fn();
const getSessionIdMock = vi.fn();
const setSessionIdMock = vi.fn();

vi.mock('../utilis/debug', () => ({
  debugLog: vi.fn(),
  debugWarn: vi.fn(),
  debugError: vi.fn(),
}));

vi.mock('../utilis/auth', () => ({
  clearAuth: vi.fn(),
  isAuthenticated: () => authState.authenticated,
  getStoredRole: () => 'judge',
  getStoredBoxes: () => [0],
}));

vi.mock('../utilis/useWebSocketWithHeartbeat', () => ({
  default: (...args) => wsHookMock(...args),
}));

vi.mock('../utilis/contestActions', () => ({
  startTimer: (...args) => startTimerMock(...args),
  stopTimer: (...args) => stopTimerMock(...args),
  resumeTimer: (...args) => resumeTimerMock(...args),
  updateProgress: (...args) => updateProgressMock(...args),
  submitScore: (...args) => submitScoreMock(...args),
  getSessionId: (...args) => getSessionIdMock(...args),
  setSessionId: (...args) => setSessionIdMock(...args),
}));

vi.mock('../components/ModalScore', () => ({
  default: ({ isOpen, onClose }) =>
    isOpen ? (
      <div data-testid="score-modal">
        <label htmlFor="score-input">Score</label>
        <input id="score-input" />
        <button onClick={onClose}>Close Score Modal</button>
      </div>
    ) : null,
}));

vi.mock('../components/LoginOverlay', () => ({
  default: ({ onSuccess }) => (
    <div data-testid="login-overlay">
      <button onClick={onSuccess}>Mock Login</button>
    </div>
  ),
}));

vi.mock('../components/Skeleton', () => ({
  JudgePageSkeleton: () => <div>Loading judge...</div>,
}));

const baseState = {
  initiated: true,
  holdsCount: 12,
  currentClimber: 'Ion Popescu',
  timerState: 'running',
  holdCount: 2,
  competitors: [{ nume: 'Ion Popescu', marked: false }],
  sessionId: 'sid-0',
  boxVersion: 1,
  remaining: 280,
  timeCriterionEnabled: false,
};

let localStore = {};

const renderJudgePage = async (stateOverrides = {}) => {
  global.fetch = vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ ...baseState, ...stateOverrides }),
  }));

  render(
    <MemoryRouter initialEntries={['/judge/0']}>
      <Routes>
        <Route path="/judge/:boxId" element={<JudgePage />} />
      </Routes>
    </MemoryRouter>,
  );

  await screen.findByText('Judge Remote');
};

describe('JudgePage hardware shortcuts', () => {
  beforeEach(() => {
    authState.authenticated = true;
    localStore = {};

    global.localStorage.getItem.mockImplementation((key) => (key in localStore ? localStore[key] : null));
    global.localStorage.setItem.mockImplementation((key, value) => {
      localStore[key] = String(value);
    });
    global.localStorage.removeItem.mockImplementation((key) => {
      delete localStore[key];
    });
    global.localStorage.clear.mockImplementation(() => {
      localStore = {};
    });

    wsHookMock.mockReset();
    wsHookMock.mockReturnValue({
      ws: null,
      connected: false,
      wsError: '',
    });

    updateProgressMock.mockReset();
    updateProgressMock.mockResolvedValue({});
    startTimerMock.mockReset();
    stopTimerMock.mockReset();
    resumeTimerMock.mockReset();
    submitScoreMock.mockReset();
    getSessionIdMock.mockReset();
    getSessionIdMock.mockReturnValue('sid-0');
    setSessionIdMock.mockReset();
  });

  it.each([
    ['ArrowUp', 0.1],
    ['AudioVolumeUp', 0.1],
    ['ArrowDown', 1],
    ['AudioVolumeDown', 1],
  ])('maps %s to the expected hold delta', async (key, delta) => {
    await renderJudgePage();

    const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
    await act(async () => {
      window.dispatchEvent(event);
    });

    await waitFor(() => expect(updateProgressMock).toHaveBeenCalledTimes(1));
    expect(updateProgressMock).toHaveBeenCalledWith(0, delta);
    expect(event.defaultPrevented).toBe(true);
  });

  it('ignores repeated shortcut events', async () => {
    await renderJudgePage();

    await act(async () => {
      fireEvent.keyDown(window, { key: 'ArrowDown', repeat: true });
    });

    expect(updateProgressMock).not.toHaveBeenCalled();
  });

  it('ignores shortcuts while the score modal is open', async () => {
    await renderJudgePage();

    await act(async () => {
      screen.getByRole('button', { name: 'Insert Score' }).click();
    });
    expect(screen.getByTestId('score-modal')).toBeInTheDocument();

    await act(async () => {
      fireEvent.keyDown(window, { key: 'ArrowDown' });
    });

    expect(updateProgressMock).not.toHaveBeenCalled();
  });

  it('ignores shortcuts while login overlay is visible', async () => {
    authState.authenticated = false;
    global.fetch = vi.fn();

    render(
      <MemoryRouter initialEntries={['/judge/0']}>
        <Routes>
          <Route path="/judge/:boxId" element={<JudgePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByTestId('login-overlay')).toBeInTheDocument();

    await act(async () => {
      fireEvent.keyDown(window, { key: 'ArrowDown' });
    });

    expect(updateProgressMock).not.toHaveBeenCalled();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('keeps existing blocked states for hardware shortcuts', async () => {
    await renderJudgePage({ holdCount: 12, holdsCount: 12 });

    await act(async () => {
      fireEvent.keyDown(window, { key: 'ArrowDown' });
    });

    expect(updateProgressMock).not.toHaveBeenCalled();
  });

  it('ignores shortcuts when the timer is not running', async () => {
    await renderJudgePage({ timerState: 'idle' });

    await act(async () => {
      fireEvent.keyDown(window, { key: 'ArrowDown' });
    });

    expect(updateProgressMock).not.toHaveBeenCalled();
  });

  it('allows only one +0.1 shortcut per climber', async () => {
    await renderJudgePage();

    await act(async () => {
      fireEvent.keyDown(window, { key: 'ArrowUp' });
    });
    await waitFor(() => expect(updateProgressMock).toHaveBeenCalledTimes(1));
    await screen.findByText('Used');

    await act(async () => {
      fireEvent.keyDown(window, { key: 'AudioVolumeUp' });
    });

    expect(updateProgressMock).toHaveBeenCalledTimes(1);
  });
});
