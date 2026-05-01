import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { postCmd } from '../utilis/commandClient';

vi.mock('../utilis/debug', () => ({
  debugError: vi.fn(),
  debugWarn: vi.fn(),
}));

vi.mock('../utilis/auth', () => ({
  clearAuth: vi.fn(),
}));

vi.mock('../utilis/adminSecurityService', () => ({
  getAdminSecurityHeaders: vi.fn((headers) => headers || {}),
  handleAdminSecurityErrorResponse: vi.fn(async () => false),
}));

describe('postCmd', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('does not retry mutating commands after a network failure', async () => {
    const failure = new Error('network down');
    global.fetch = vi.fn(async () => {
      throw failure;
    }) as unknown as typeof fetch;

    const request = postCmd({ type: 'PROGRESS_UPDATE', boxId: 0, delta: 1 }, 'PROGRESS_UPDATE');
    const assertion = expect(request).rejects.toThrow('network down');
    await vi.advanceTimersByTimeAsync(5000);

    await assertion;
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });
});
