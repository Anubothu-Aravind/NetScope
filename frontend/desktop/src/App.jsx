import React, { useState, useEffect, useRef } from 'react';
import Pair from './steps/Pair';
import Impairments from './steps/Impairments';
import Observer from './steps/Observer';
import Results from './steps/Results';
import { Activity } from 'lucide-react';

/**
 * App Component (Tasks 3 & 11)
 * 
 * - Steps in header are numbers only, not clickable buttons
 * - currentStep only changes programmatically, never by clicking
 * - Create WebSocket connection once in App.jsx when session is created
 * - Pass ws as prop to all step components
 * - Maintain capturedPackets array and telemetryHistory array in App.jsx state
 * - Update them from WebSocket messages, and pass them as props to Observer and Results
 */
export default function App() {
  const [currentStep, setCurrentStep] = useState(1);
  const [session, setSession] = useState(null);
  const [ws, setWs] = useState(null);

  // Global telemetry history and captured packets (Task 11)
  const [capturedPackets, setCapturedPackets] = useState([]);
  const [telemetryHistory, setTelemetryHistory] = useState([]);
  const [finalData, setFinalData] = useState(null);

  const wsRef = useRef(null);

  // Initialize or fetch default session on mount
  useEffect(() => {
    let isMounted = true;

    async function initSession() {
      try {
        const res = await fetch('/api/session', { method: 'POST' });
        if (!res.ok) throw new Error('Failed to create session');
        const data = await res.json();
        if (isMounted) {
          setSession(data);
        }
      } catch (err) {
        console.error('Failed to init session in App.jsx:', err);
      }
    }

    initSession();

    return () => {
      isMounted = false;
    };
  }, []);

  // Connect WebSocket once when session is created (Task 11)
  useEffect(() => {
    if (!session?.session_id) return;
    const sid = session.session_id;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws/${sid}`;

    const socket = new WebSocket(wsUrl);
    wsRef.current = socket;
    setWs(socket);

    socket.onopen = () => {
      console.log('[App] WebSocket connected to session:', sid);
    };

    socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const type = (msg.type || msg.event || '').toLowerCase();
        const data = msg.data || msg;

        // Reset arrays on new transfer
        if (type === 'transfer_started') {
          setCapturedPackets([]);
          setTelemetryHistory([]);
          setFinalData(null);
        }

        // Packets batch
        if (type === 'packets_batch') {
          const batch = data.packets || [];
          if (batch.length > 0) {
            setCapturedPackets((prev) => {
              const seen = new Set(prev.map((p) => p.num || p.frame));
              const unique = batch.filter((p) => !seen.has(p.num || p.frame));
              return [...prev, ...unique];
            });
          }
        }

        // Telemetry update
        if (type === 'telemetry_update') {
          const timeLabel = new Date().toLocaleTimeString().split(' ')[0];
          setTelemetryHistory((prev) => [
            ...prev.slice(-30),
            {
              time: timeLabel,
              throughput: Number(data.throughput || 0),
              rtt: Number(data.rtt || 0),
              cwnd: Number(data.cwnd || 0),
              retransmissions: Number(data.retransmissions || 0),
            },
          ]);
        }

        // Final completion and packets list
        if (type === 'transfer_complete') {
          const pkts = data.packets || data.record?.packets || [];
          if (pkts.length > 0) {
            setCapturedPackets((prev) => (prev.length >= pkts.length ? prev : pkts));
          }
          setFinalData(data);
        }
      } catch (e) {
        console.error('[App WS Error]', e);
      }
    };

    return () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.close();
      }
    };
  }, [session?.session_id]);

  const stepLabels = [
    { num: 1, label: 'Pair' },
    { num: 2, label: 'Impairments' },
    { num: 3, label: 'Observer' },
    { num: 4, label: 'Results' },
  ];

  const handleReset = () => {
    setCapturedPackets([]);
    setTelemetryHistory([]);
    setFinalData(null);
    setCurrentStep(1);
  };

  return (
    <div className="min-h-screen bg-[#080C14] text-slate-100 flex flex-col font-sans">
      {/* Header with Non-Clickable Step Indicators (Task 3) */}
      <header className="border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 flex items-center justify-center font-bold">
              <Activity className="w-4 h-4" />
            </div>
            <div>
              <span className="font-bold text-base tracking-tight text-white">NetScope</span>
              <span className="text-[11px] text-slate-400 block -mt-0.5">TCP Diagnostic Suite</span>
            </div>
          </div>

          {/* Steps are numbers only, not buttons (Task 3) */}
          <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-xl">
            {stepLabels.map((s, idx) => {
              const isActive = currentStep === s.num;
              const isPast = currentStep > s.num;
              return (
                <React.Fragment key={s.num}>
                  <div
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium select-none pointer-events-none ${
                      isActive
                        ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                        : isPast
                        ? 'text-emerald-400 font-semibold'
                        : 'text-slate-600'
                    }`}
                  >
                    <span
                      className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-bold ${
                        isActive
                          ? 'bg-cyan-400 text-slate-950'
                          : isPast
                          ? 'bg-emerald-400/20 text-emerald-300'
                          : 'bg-slate-800 text-slate-500'
                      }`}
                    >
                      {s.num}
                    </span>
                    <span>{s.label}</span>
                  </div>
                  {idx < stepLabels.length - 1 && (
                    <span className="text-slate-700 text-xs">/</span>
                  )}
                </React.Fragment>
              );
            })}
          </div>

          {session?.session_id && (
            <div className="text-xs font-mono text-slate-400 bg-slate-900 border border-slate-800 px-2.5 py-1 rounded-lg">
              {session.session_id}
            </div>
          )}
        </div>
      </header>

      {/* Main Wizard Area */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-8">
        {currentStep === 1 && (
          <Pair
            session={session}
            setSession={setSession}
            ws={ws}
            onAdvance={() => setCurrentStep(2)}
          />
        )}

        {currentStep === 2 && (
          <Impairments
            ws={ws}
            session={session}
            onAdvance={() => setCurrentStep(3)}
          />
        )}

        {currentStep === 3 && (
          <Observer
            ws={ws}
            capturedPackets={capturedPackets}
            setCapturedPackets={setCapturedPackets}
            telemetryHistory={telemetryHistory}
            setTelemetryHistory={setTelemetryHistory}
            onAdvance={(data) => {
              if (data?.packets && data.packets.length > 0) {
                setCapturedPackets(data.packets);
              }
              setFinalData(data);
              setCurrentStep(4);
            }}
          />
        )}

        {currentStep === 4 && (
          <Results
            finalData={finalData}
            capturedPackets={capturedPackets}
            telemetryHistory={telemetryHistory}
            onReset={handleReset}
          />
        )}
      </main>
    </div>
  );
}
