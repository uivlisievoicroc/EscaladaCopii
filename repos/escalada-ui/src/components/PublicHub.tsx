import React, { FC, useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

/**
 * API Configuration
 * Uses same-origin relative API paths.
 */
const API_BASE = '/api/public';

type PublicBoxInfo = {
  boxId: number;
  label: string;
  initiated: boolean;
  timerState?: string | null;
  currentClimber?: string | null;
  categorie?: string | null;
};

/**
 * PublicHub: Main entry point for spectators (unauthenticated public access).
 * 
 * Purpose:
 * - Landing page for spectators with three main navigation options:
 *   1. Live Rankings: Real-time leaderboard across all categories
 *   2. Live Climbing: Watch specific category in progress (box selection dropdown)
 *   3. Competition Officials: View chief judge and event director info
 * 
 * API Integration:
 * - Fetches initiated boxes from GET /api/public/boxes
 * - Auto-refreshes boxes list every 30 seconds
 * 
 * UI Features:
 * - Gradient hero layout with large action buttons
 * - Live Climbing button shows active category count + dropdown on click
 * - Dropdown displays current climber + timer status for each box
 * - Error messages with retry button for API failures
 * - Loading states for async operations
 * 
 * Routing:
 * - /public/rankings → PublicRankings component
 * - /public/live-climbing/:boxId → PublicLiveClimbing component
 * - /public/officials → CompetitionOfficials component
 * 
 * State Management:
 * - Local state only (no global context)
 * - Boxes list refreshed via polling (no WS connection on hub page)
 * - Selected box ID tracked for dropdown interaction
 * 
 * Accessibility:
 * - Disabled states for loading/empty boxes
 * - Keyboard-navigable dropdown
 * - Clear error messages with recovery actions
 * 
 * @component
 */
const PublicHub: FC = () => {
  const navigate = useNavigate(); // React Router navigation hook
  
  // Boxes list: initiated boxes fetched from API (only initiated boxes visible to spectators)
  const [boxes, setBoxes] = useState<PublicBoxInfo[]>([]);
  
  // Loading state: true during initial fetch and refresh attempts
  const [loading, setLoading] = useState(true);
  
  // Error message: displayed above main buttons with retry option
  const [error, setError] = useState<string | null>(null);
  
  // Selected box: tracks user choice in dropdown (before navigation)
  const [selectedBox, setSelectedBox] = useState<number | null>(null);
  
  // Dropdown visibility: controlled by Live Climbing button click
  const [showDropdown, setShowDropdown] = useState(false);

  /**
   * Fetch initiated boxes from backend.
   * 
   * Flow:
   * 1. Call GET /api/public/boxes
   * 2. Parse response.boxes array (only initiated boxes returned by backend)
   * 
   * Error Handling:
   * - Network errors: caught and displayed in error banner
   * - Non-2xx responses: generic "Failed to fetch boxes" error
   * 
   * Called:
   * - On component mount (initial load)
   * - Every 30 seconds (polling interval)
   * - Manually via Retry button in error banner
   */
  const fetchBoxes = useCallback(async () => {
    try {
      setLoading(true); // Show loading state in UI
      setError(null); // Clear previous errors

      const response = await fetch(`${API_BASE}/boxes`);

      if (!response.ok) {
        // HTTP error
        throw new Error('Failed to fetch boxes');
      }

      // Success: parse boxes array
      const data = await response.json();
      setBoxes(data.boxes || []); // Fallback to empty array if missing
    } catch (err) {
      // Network errors, JSON parse errors, or thrown errors from above
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false); // Hide loading state regardless of success/failure
    }
  }, []);

  /**
   * Initial fetch + polling setup.
   * 
   * On mount:
   * - Fetch boxes immediately (shows loading state)
   * - Start 30-second polling interval (keeps list fresh)
   * 
   * Cleanup:
   * - Clear interval on unmount (prevents memory leaks)
   * 
   * Note: fetchBoxes is stable (useCallback with no deps) so effect runs once.
   */
  useEffect(() => {
    fetchBoxes(); // Initial fetch
    // Polling: refresh boxes every 30 seconds to show new initiated categories
    const interval = setInterval(fetchBoxes, 30000);
    return () => clearInterval(interval); // Cleanup on unmount
  }, [fetchBoxes]);

  /**
   * Navigate to live rankings page (all categories leaderboard).
   */
  const handleLiveRankings = () => {
    navigate('/public/rankings');
  };

  /**
   * Navigate to competition officials page (chief judge + event director info).
   */
  const handleCompetitionOfficials = () => {
    navigate('/public/officials');
  };

  /**
   * Handle Live Climbing button click.
   * 
   * If no boxes initiated yet, show error message.
   * Otherwise, open dropdown for box selection.
   */
  const handleLiveClimbing = () => {
    if (boxes.length === 0) {
      // No initiated categories yet - show user-friendly message
      setError("The competition hasn't started yet. Please check back later.");
      return;
    }
    // Show dropdown for category selection
    setShowDropdown(true);
  };

  /**
   * Navigate to live climbing page for selected box.
   * 
   * Called when user clicks a box in dropdown.
   * Closes dropdown and navigates to /public/live-climbing/:boxId.
   */
  const handleSelectBox = (boxId: number) => {
    setSelectedBox(boxId); // Track selection (not currently used but may be useful for history)
    setShowDropdown(false); // Close dropdown
    navigate(`/public/live-climbing/${boxId}`); // Navigate to live climbing page
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 flex flex-col items-center justify-center p-6">
      {/* Hero Header: Branding + tagline */}
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold text-white mb-2">🧗 Escalada Live</h1>
        <p className="text-slate-400">Follow the competition live</p>
      </div>

      {/* Error Banner: Displayed when API fetch fails or no boxes available */}
      {error && (
        <div className="mb-6 p-4 bg-red-900/50 border border-red-500 rounded-lg text-red-200 max-w-md text-center">
          {error}
          {/* Retry button: clears error + refetches boxes */}
          <button
            onClick={() => {
              setError(null);
              fetchBoxes();
            }}
            className="ml-4 underline hover:text-red-100"
          >
            Retry
          </button>
        </div>
      )}

      {/* Main Navigation: Two large action buttons side-by-side (stacked on mobile) */}
      <div className="flex flex-col sm:flex-row gap-6 w-full max-w-lg">
        {/* Live Rankings Button: Navigate to full leaderboard page */}
        <button
          onClick={handleLiveRankings}
          className="flex-1 p-8 bg-gradient-to-br from-cyan-600 to-cyan-700 hover:from-cyan-500 hover:to-cyan-600 text-white rounded-2xl shadow-xl transition-all duration-200 transform hover:scale-105 active:scale-95"
        >
          <div className="text-5xl mb-4">🏆</div>
          <div className="text-2xl font-semibold">Live Rankings</div>
          <div className="text-cyan-200 mt-2 text-sm">Real-time leaderboard</div>
        </button>

        {/* Live Climbing Button: Opens dropdown for box selection */}
        <div className="flex-1 relative">
          <button
            onClick={handleLiveClimbing}
            disabled={loading} // Disabled during initial fetch
            className="w-full p-8 bg-gradient-to-br from-emerald-600 to-emerald-700 hover:from-emerald-500 hover:to-emerald-600 text-white rounded-2xl shadow-xl transition-all duration-200 transform hover:scale-105 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <div className="text-5xl mb-4">🧗</div>
            <div className="text-2xl font-semibold">Live Climbing</div>
            {/* Dynamic subtitle: shows active category count or loading state */}
            <div className="text-emerald-200 mt-2 text-sm">
              {loading
                ? 'Loading...'
                : `${boxes.length} active ${boxes.length === 1 ? 'category' : 'categories'}`}
            </div>
          </button>

          {/* 
            Dropdown: Category selection menu (only shown when showDropdown=true)
            
            Structure:
            - Header: "Choose a category" label
            - Scrollable list: Each box button shows:
              - Box label (e.g. "Seniori M")
              - Current climber name (if someone climbing)
              - Green pulse indicator (if timer running)
            - Footer: Cancel button to close dropdown
            
            Interaction:
            - Click box → navigate to /public/live-climbing/:boxId
            - Click Cancel → close dropdown without navigation
          */}
          {showDropdown && boxes.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-2 bg-slate-800 border border-slate-600 rounded-xl shadow-2xl z-50 overflow-hidden">
              {/* Dropdown header */}
              <div className="p-3 border-b border-slate-700 text-slate-300 text-sm font-medium">
                Choose a category:
              </div>
              {/* Box list: scrollable if >4 boxes */}
              <div className="max-h-64 overflow-y-auto">
                {boxes.map((box) => (
                  <button
                    key={box.boxId}
                    onClick={() => handleSelectBox(box.boxId)}
                    className="w-full p-4 text-left hover:bg-slate-700 transition-colors border-b border-slate-700 last:border-b-0"
                  >
                    {/* Box label (category name) */}
                    <div className="text-white font-medium">{box.label}</div>
                    {/* Current climber + timer status (only if someone climbing) */}
                    {box.currentClimber && (
                      <div className="text-slate-400 text-sm mt-1">
                        🧗 {box.currentClimber}
                        {/* Green pulse: indicates timer is running for this climber */}
                        {box.timerState === 'running' && (
                          <span className="ml-2 inline-block w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                        )}
                      </div>
                    )}
                  </button>
                ))}
              </div>
              {/* Cancel button: close dropdown without action */}
              <button
                onClick={() => setShowDropdown(false)}
                className="w-full p-3 text-slate-400 hover:text-white hover:bg-slate-700 text-sm"
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Secondary Action: Competition Officials (lower visual hierarchy) */}
      <div className="w-full max-w-lg mt-6">
        <button
          onClick={handleCompetitionOfficials}
          className="w-full p-4 bg-slate-800/60 hover:bg-slate-700/70 text-white rounded-2xl border border-slate-700 shadow-lg transition-all duration-200"
        >
          <div className="flex items-center justify-between">
            <div>
              <div className="text-lg font-semibold">Competition Officials</div>
              <div className="text-slate-300 mt-1 text-sm">Chief Judge & Event Director</div>
            </div>
            <div className="text-2xl">👥</div>
          </div>
        </button>
      </div>

      {/* Footer: Auto-update status indicator */}
      <div className="mt-12 text-slate-500 text-sm">
        {loading ? (
          // Initial load or manual refresh in progress
          <span className="flex items-center gap-2">
            <span className="animate-spin">⟳</span> Loading...
          </span>
        ) : (
          // Idle state: indicates 30-second polling is active
          <span>Auto-updating</span>
        )}
      </div>
    </div>
  );
};

export default PublicHub;
