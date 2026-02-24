import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ADMIN_SECURITY_TOKEN_KEY,
} from '../utilis/adminSecurityService';
import { AdminSecurityProvider, useAdminSecurity } from '../utilis/useAdminSecurity';

type MockListener = (event: MessageEvent<string>) => void;

class MockEventSource {
  static instances: MockEventSource[] = [];

  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  close = vi.fn();

  private readonly listeners = new Map<string, Set<MockListener>>();

  constructor(
    public readonly url: string,
    public readonly options?: EventSourceInit,
  ) {
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    const fn = listener as MockListener;
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set());
    }
    this.listeners.get(type)?.add(fn);
  }

  removeEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    this.listeners.get(type)?.delete(listener as MockListener);
  }

  emit(type: string, payload: Record<string, unknown>): void {
    const event = { data: JSON.stringify(payload) } as MessageEvent<string>;
    for (const listener of this.listeners.get(type) || []) {
      listener(event);
    }
  }

  triggerError(): void {
    this.onerror?.(new Event('error'));
  }

  static reset(): void {
    MockEventSource.instances = [];
  }
}

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const Probe: React.FC = () => {
  const { licenseValid, licenseReason, adminUnlocked, unlock, lock, refreshStatus } =
    useAdminSecurity();
  return (
    <div>
      <span data-testid="license-valid">{String(licenseValid)}</span>
      <span data-testid="license-reason">{licenseReason}</span>
      <span data-testid="admin-unlocked">{String(adminUnlocked)}</span>
      <button type="button" onClick={() => void refreshStatus()}>
        refresh
      </button>
      <button type="button" onClick={() => void unlock()}>
        unlock
      </button>
      <button type="button" onClick={() => void lock()}>
        lock
      </button>
    </div>
  );
};

describe('useAdminSecurity', () => {
  beforeEach(() => {
    MockEventSource.reset();
    sessionStorage.clear();
    vi.stubGlobal('EventSource', MockEventSource as unknown as typeof EventSource);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    sessionStorage.clear();
  });

  it('handles refresh, unlock and lock state transitions', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/license/status')) {
        return jsonResponse({
          license_valid: true,
          license_reason: 'ok',
          admin_unlocked: false,
        });
      }
      if (url.endsWith('/api/admin/unlock')) {
        return jsonResponse({
          token: 'usb-token-123',
          license_valid: true,
          license_reason: 'ok',
          admin_unlocked: true,
        });
      }
      if (url.endsWith('/api/admin/lock')) {
        return jsonResponse({
          license_valid: true,
          license_reason: 'ok',
          admin_unlocked: false,
        });
      }
      throw new Error(`Unexpected URL ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);

    render(
      <AdminSecurityProvider>
        <Probe />
      </AdminSecurityProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('license-valid')).toHaveTextContent('true');
      expect(screen.getByTestId('admin-unlocked')).toHaveTextContent('false');
    });

    fireEvent.click(screen.getByRole('button', { name: 'unlock' }));
    await waitFor(() => {
      expect(screen.getByTestId('admin-unlocked')).toHaveTextContent('true');
    });
    expect(sessionStorage.getItem(ADMIN_SECURITY_TOKEN_KEY)).toBe('usb-token-123');

    fireEvent.click(screen.getByRole('button', { name: 'lock' }));
    await waitFor(() => {
      expect(screen.getByTestId('admin-unlocked')).toHaveTextContent('false');
    });
    expect(sessionStorage.getItem(ADMIN_SECURITY_TOKEN_KEY)).toBeNull();
  });

  it('locks locally when SSE emits admin_locked', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/license/status')) {
        return jsonResponse({
          license_valid: true,
          license_reason: 'ok',
          admin_unlocked: false,
        });
      }
      if (url.endsWith('/api/admin/unlock')) {
        return jsonResponse({
          token: 'usb-token-456',
          license_valid: true,
          license_reason: 'ok',
          admin_unlocked: true,
        });
      }
      if (url.endsWith('/api/admin/lock')) {
        return jsonResponse({
          license_valid: true,
          license_reason: 'ok',
          admin_unlocked: false,
        });
      }
      throw new Error(`Unexpected URL ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);

    render(
      <AdminSecurityProvider>
        <Probe />
      </AdminSecurityProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('license-valid')).toHaveTextContent('true');
    });

    fireEvent.click(screen.getByRole('button', { name: 'unlock' }));
    await waitFor(() => {
      expect(screen.getByTestId('admin-unlocked')).toHaveTextContent('true');
    });

    const source = MockEventSource.instances[0];
    expect(source).toBeDefined();

    act(() => {
      source.emit('admin_locked', { reason: 'license_invalid' });
    });

    await waitFor(() => {
      expect(screen.getByTestId('admin-unlocked')).toHaveTextContent('false');
      expect(screen.getByTestId('license-reason')).toHaveTextContent('license_invalid');
    });
    expect(sessionStorage.getItem(ADMIN_SECURITY_TOKEN_KEY)).toBeNull();
  });

  it('uses polling fallback after SSE error', async () => {
    vi.useFakeTimers();
    let statusCalls = 0;

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/license/status')) {
        statusCalls += 1;
        return jsonResponse({
          license_valid: true,
          license_reason: 'ok',
          admin_unlocked: false,
        });
      }
      if (url.endsWith('/api/admin/unlock')) {
        return jsonResponse({
          token: 'usb-token-polling',
          license_valid: true,
          license_reason: 'ok',
          admin_unlocked: true,
        });
      }
      if (url.endsWith('/api/admin/lock')) {
        return jsonResponse({
          license_valid: true,
          license_reason: 'ok',
          admin_unlocked: false,
        });
      }
      throw new Error(`Unexpected URL ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);

    render(
      <AdminSecurityProvider>
        <Probe />
      </AdminSecurityProvider>,
    );

    await act(async () => {
      await Promise.resolve();
    });
    expect(statusCalls).toBeGreaterThanOrEqual(1);

    const source = MockEventSource.instances[0];
    expect(source).toBeDefined();

    act(() => {
      source.triggerError();
    });

    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
    });

    expect(statusCalls).toBeGreaterThanOrEqual(2);
  });
});
