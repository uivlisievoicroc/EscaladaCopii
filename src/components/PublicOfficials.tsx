import React, { FC, useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

// Public pages are opened from phones/tablets on the LAN.
// We derive the API base URL from the current host and talk to the API on port 8000.
const API_PROTOCOL = window.location.protocol === 'https:' ? 'https' : 'http';
const API_BASE = `${API_PROTOCOL}://${window.location.hostname}:8000/api/public`;

// Response shape for GET `/api/public/officials`.
type Officials = {
  federalOfficial: string;
  judgeChief: string;
  competitionDirector: string;
  chiefRoutesetter: string;
};

const PublicOfficials: FC = () => {
  const navigate = useNavigate();

  // UI state: current officials data + loading/error flags.
  const [officials, setOfficials] = useState<Officials>({
    federalOfficial: '',
    judgeChief: '',
    competitionDirector: '',
    chiefRoutesetter: '',
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchOfficials = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const res = await fetch(`${API_BASE}/officials`);
      if (!res.ok) throw new Error('Failed to fetch officials');
      const data = await res.json();
      setOfficials({
        federalOfficial: data.federalOfficial || '',
        judgeChief: data.judgeChief || '',
        competitionDirector: data.competitionDirector || '',
        chiefRoutesetter: data.chiefRoutesetter || '',
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Initial load on mount; manual refresh is available in the header.
    fetchOfficials();
  }, [fetchOfficials]);

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950">
      <header className="sticky top-0 z-50 bg-slate-900/95 backdrop-blur border-b border-slate-800 p-4">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <button
            onClick={() => navigate('/public')}
            className="flex items-center gap-2 text-slate-400 hover:text-white transition-colors"
          >
            <span>←</span>
            <span>Back</span>
          </button>
          <h1 className="text-xl font-bold text-white">👥 Competition Officials</h1>
          <button
            onClick={fetchOfficials}
            className="text-slate-400 hover:text-white transition-colors text-sm"
            type="button"
          >
            Refresh
          </button>
        </div>
      </header>

      <main className="max-w-3xl mx-auto p-6">
        {/* Error message (network/API failures) */}
        {error && (
          <div className="mb-4 p-4 bg-red-900/50 border border-red-500 rounded-lg text-red-200">
            {error}
          </div>
        )}
        {loading ? (
          <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/40 text-slate-300">
            {/* Loading state (single fetch; no live streaming required for officials) */}
            Loading…
          </div>
        ) : (
          <div className="grid gap-4">
            {/* Data state: render the official roles as cards */}
            <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/40">
              <div className="text-xs uppercase tracking-wider text-slate-400">
                Federal Official
              </div>
              <div className="mt-2 text-2xl font-semibold text-white">
                {officials.federalOfficial || '—'}
              </div>
            </div>
            <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/40">
              <div className="text-xs uppercase tracking-wider text-slate-400">
                Event Director
              </div>
              <div className="mt-2 text-2xl font-semibold text-white">
                {officials.competitionDirector || '—'}
              </div>
            </div>
            <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/40">
              <div className="text-xs uppercase tracking-wider text-slate-400">
                Chief Routesetter
              </div>
              <div className="mt-2 text-2xl font-semibold text-white">
                {officials.chiefRoutesetter || '—'}
              </div>
            </div>
            <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/40">
              <div className="text-xs uppercase tracking-wider text-slate-400">Chief Judge</div>
              <div className="mt-2 text-2xl font-semibold text-white">
                {officials.judgeChief || '—'}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default PublicOfficials;
