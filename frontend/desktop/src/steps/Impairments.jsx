import React, { useState } from 'react';
import { Sliders, Clock, AlertTriangle, Gauge, ArrowRight, AlertCircle, RefreshCw } from 'lucide-react';

/**
 * Step 2: Impairments Component (Task 5)
 * 
 * - Three number inputs: Delay (ms), Loss (%), Bandwidth (kbps, 0 = unlimited)
 * - One "Save and Start Transfer" button
 * - On click: first POST /api/impair with the values, then POST /api/transfer, then call onAdvance() prop
 * - Show error message inline if either call fails
 */
export default function Impairments({ onAdvance, ws, session }) {
  const [delay, setDelay] = useState(0); // ms
  const [loss, setLoss] = useState(0); // %
  const [bandwidth, setBandwidth] = useState(0); // kbps (0 = unlimited)
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Listen to WebSocket for errors or completion broadcasts
  React.useEffect(() => {
    if (!ws) return;
    const handleWs = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        const type = (msg.type || msg.event || '').toLowerCase();
        if (type === 'error') {
          setError(msg.message || msg.data?.message || 'Network impairment error');
          setLoading(false);
        } else if (type === 'transfer_started') {
          onAdvance();
        }
      } catch (e) {
        // ignore
      }
    };
    ws.addEventListener('message', handleWs);
    return () => ws.removeEventListener('message', handleWs);
  }, [ws, onAdvance]);

  const handleSaveAndStart = async () => {
    setLoading(true);
    setError(null);

    const delayStr = delay > 0 ? `${delay}ms` : '0ms';
    const lossStr = loss > 0 ? `${loss}%` : '0%';
    const rateStr = bandwidth > 0 ? `${bandwidth}kbit` : 'Unlimited';

    try {
      // 1. POST /api/impair
      const impairRes = await fetch('/api/impair', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          delay: delayStr,
          loss: lossStr,
          rate: rateStr,
          name: 'Manual',
        }),
      });

      if (!impairRes.ok) {
        const errJson = await impairRes.json().catch(() => ({}));
        throw new Error(errJson.detail || 'Failed to apply network impairment.');
      }

      // 2. POST /api/transfer with session_id
      const transferRes = await fetch('/api/transfer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: 'send',
          scenario: 'Manual',
          session_id: session?.session_id,
        }),
      });

      if (!transferRes.ok) {
        const errJson = await transferRes.json().catch(() => ({}));
        throw new Error(errJson.detail || 'Failed to initiate TCP file transfer.');
      }

      // 3. Immediately transition to Observer step
      onAdvance();
    } catch (err) {
      console.error(err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8 max-w-2xl mx-auto">
      {/* Header */}
      <div className="text-center space-y-2">
        <h2 className="text-2xl font-bold text-white tracking-tight flex items-center justify-center gap-2">
          <Sliders className="w-6 h-6 text-cyan-400" />
          Network Impairments
        </h2>
        <p className="text-sm text-slate-400">
          Configure kernel netem traffic control parameters prior to starting the TCP transfer.
        </p>
      </div>

      {error && (
        <div className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-400 text-sm flex items-center gap-3">
          <AlertCircle className="w-5 h-5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Inputs Card */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
        {/* Delay Input */}
        <div className="space-y-2">
          <label className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <Clock className="w-4 h-4 text-cyan-400" />
            Delay (ms)
          </label>
          <input
            type="number"
            min="0"
            max="2000"
            value={delay}
            onChange={(e) => setDelay(Math.max(0, Number(e.target.value)))}
            placeholder="0"
            className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-slate-100 font-mono text-sm focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 transition-all"
          />
          <p className="text-xs text-slate-500">Injects artificial packet propagation latency (0 = none).</p>
        </div>

        {/* Loss Input */}
        <div className="space-y-2">
          <label className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            Loss (%)
          </label>
          <input
            type="number"
            min="0"
            max="100"
            step="0.5"
            value={loss}
            onChange={(e) => setLoss(Math.max(0, Math.min(100, Number(e.target.value))))}
            placeholder="0"
            className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-slate-100 font-mono text-sm focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-all"
          />
          <p className="text-xs text-slate-500">Simulates random packet drops on the interface (0–100%).</p>
        </div>

        {/* Bandwidth Input */}
        <div className="space-y-2">
          <label className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <Gauge className="w-4 h-4 text-emerald-400" />
            Bandwidth (kbps, 0 = unlimited)
          </label>
          <input
            type="number"
            min="0"
            step="100"
            value={bandwidth}
            onChange={(e) => setBandwidth(Math.max(0, Number(e.target.value)))}
            placeholder="0"
            className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-slate-100 font-mono text-sm focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-all"
          />
          <p className="text-xs text-slate-500">Rate limits egress traffic rate in kilobits per second (0 = unconstrained).</p>
        </div>

        {/* Save and Start Transfer Button */}
        <button
          onClick={handleSaveAndStart}
          disabled={loading}
          className="w-full py-3.5 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 disabled:opacity-50 text-white font-bold rounded-xl shadow-lg shadow-cyan-500/20 text-sm transition-all flex items-center justify-center gap-2 mt-4 cursor-pointer"
        >
          {loading ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              Applying Impairments & Initiating Transfer...
            </>
          ) : (
            <>
              Save and Start Transfer <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </div>
    </div>
  );
}
