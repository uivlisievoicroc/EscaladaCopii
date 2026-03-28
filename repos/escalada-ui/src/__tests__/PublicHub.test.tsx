import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import PublicHub from '../components/PublicHub';

const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('PublicHub', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders actions and fetches boxes without token params', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ boxes: [] }),
    });

    render(
      <BrowserRouter>
        <PublicHub />
      </BrowserRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('Live Rankings')).toBeInTheDocument();
      expect(screen.getByText('Live Climbing')).toBeInTheDocument();
    });

    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/api/public/boxes'));
    expect(String(mockFetch.mock.calls[0][0])).not.toContain('token=');
  });

  it('shows dropdown with initiated boxes when Live Climbing is clicked', async () => {
    const mockBoxes = [
      { boxId: 0, label: 'Youth', initiated: true, timerState: 'idle' },
      { boxId: 1, label: 'Adults', initiated: true, timerState: 'running', currentClimber: 'Alex' },
    ];

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ boxes: mockBoxes }),
    });

    render(
      <BrowserRouter>
        <PublicHub />
      </BrowserRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/2 active categor/i)).toBeInTheDocument();
    });

    const liveClimbingButton = screen.getByText('Live Climbing').closest('button');
    fireEvent.click(liveClimbingButton!);

    await waitFor(() => {
      expect(screen.getByText('Choose a category:')).toBeInTheDocument();
      expect(screen.getByText('Youth')).toBeInTheDocument();
      expect(screen.getByText('Adults')).toBeInTheDocument();
    });
  });

  it('shows error when no boxes are initiated', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ boxes: [] }),
    });

    render(
      <BrowserRouter>
        <PublicHub />
      </BrowserRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/0 active categor/i)).toBeInTheDocument();
    });

    const liveClimbingButton = screen.getByText('Live Climbing').closest('button');
    fireEvent.click(liveClimbingButton!);

    await waitFor(() => {
      expect(screen.getByText(/hasn't started yet/i)).toBeInTheDocument();
    });
  });
});
