import React, { useState, useEffect, useRef } from 'react';
import { Activity, Gauge, Clock, BarChart3, Repeat, ArrowRight, CheckCircle, Radio } from 'lucide-react';
import TcpLadder from '../components/TcpLadder';
import LiveChart from '../components/LiveChart';

/**
 * Step 3: Observer Component
 * 
 * - Real-time TCP socket telemetry and dissected packet flow diagram.
 * - Displays active transmission states (Initializing, Connection Handshake,
 *   Sending Packets, Pacing Bandwidth, Retrying Transmission, Processing Results).
 * - Smooth visual progress bar and indeterminate shimmer for slow networks.
 * - Interactive replayable TCP Ladder Canvas with slow motion.
 */
export default function Observer({
  ws,
  onAdvance,
  capturedPackets = [],
  setCapturedPackets,
  telemetryHistory = [],
  setTelemetryHistory,
}) {
  const [metrics, setMetrics] = useState({
    throughput: 0,
    rtt: 0,
    cwnd: 0,
    retransmissions: 0,
    pct: 0,
  });

  const [transferState, setTransferState] = useState('Initializing simulation');
  const [isCompleted, setIsCompleted] = useState(false);
  const [finalData, setFinalData] = useState(null);
  const [isAdvancing, setIsAdvancing] = useState(false);
  const advanceTimeoutRef = useRef(null);

  // Listen to WebSocket passed as prop from App.jsx
  useEffect(() => {
    if (!ws) return;

    const handleMessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const type = (msg.type || msg.event || '').toLowerCase();
        const data = msg.data || msg;

        // 1. telemetry_update: update 4 metric cards and append to charts
        if (type === 'telemetry_update') {
          const tp = Number(data.throughput || 0);
          const rtt = Number(data.rtt || 0);
          const cwnd = Number(data.cwnd || 0);
          const retrans = Number(data.retransmissions || 0);
          const pct = Number(data.pct || 0);
          const stateMsg = data.state || 'Sending packets';

          setTransferState(stateMsg);
          setMetrics({
            throughput: tp,
            rtt,
            cwnd,
            retransmissions: retrans,
            pct,
          });

          const timeLabel = new Date().toLocaleTimeString().split(' ')[0];

          if (setTelemetryHistory) {
            setTelemetryHistory((prev) => [
              ...prev.slice(-30),
              {
                time: timeLabel,
                throughput: tp,
                rtt,
                cwnd,
                retransmissions: retrans,
              },
            ]);
          }
        }

        // Also update progress percentage from transfer_progress if emitted
        if (type === 'transfer_progress') {
          if (data.pct !== undefined) {
            setMetrics((prev) => ({
              ...prev,
              pct: Number(data.pct),
              throughput: data.mbps !== undefined ? Number(data.mbps) : prev.throughput,
            }));
          }
          if (data.state) {
            setTransferState(data.state);
          }
        }

        // 2. packets_batch: append rows to packet table, redraw TcpLadder canvas
        if (type === 'packets_batch') {
          const batch = data.packets || [];
          if (batch.length > 0 && setCapturedPackets) {
            setCapturedPackets((prev) => {
              const seen = new Set(prev.map((p) => p.num || p.frame));
              const unique = batch.filter((p) => !seen.has(p.num || p.frame));
              return [...prev, ...unique];
            });
          }
        }

        // 3. transfer_complete: set finalData and allow user review of live diagram
        if (type === 'transfer_complete') {
          setIsCompleted(true);
          setTransferState('Simulation completed');
          setMetrics((prev) => ({ ...prev, pct: 100 }));
          const fullPackets = (data.packets && data.packets.length > 0) ? data.packets : capturedPackets;
          const completionData = {
            ...data,
            packets: fullPackets
          };
          setFinalData(completionData);
          if (data.packets && data.packets.length > 0 && setCapturedPackets) {
            setCapturedPackets(data.packets);
          }
          if (advanceTimeoutRef.current) clearTimeout(advanceTimeoutRef.current);
          advanceTimeoutRef.current = setTimeout(() => {
            onAdvance(completionData);
          }, 3500);
        }
      } catch (err) {
        console.error('[Observer WS Error]', err);
      }
    };

    ws.addEventListener('message', handleMessage);
    return () => {
      ws.removeEventListener('message', handleMessage);
      if (advanceTimeoutRef.current) clearTimeout(advanceTimeoutRef.current);
    };
  }, [ws, setCapturedPackets, setTelemetryHistory]);

  const handleManualAdvance = () => {
    if (isAdvancing) return;
    setIsAdvancing(true);
    if (advanceTimeoutRef.current) clearTimeout(advanceTimeoutRef.current);
    onAdvance(finalData);
  };

  // Format histories for individual charts
  const tpChartData = telemetryHistory.map((h) => ({ time: h.time, value: h.throughput }));
  const rttChartData = telemetryHistory.map((h) => ({ time: h.time, value: h.rtt }));
  const cwndChartData = telemetryHistory.map((h) => ({ time: h.time, value: h.cwnd }));
  const retransChartData = telemetryHistory.map((h) => ({ time: h.time, value: h.retransmissions }));

  return (
    <div className="space-y-6">
      {/* Step Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-4">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <Activity className="w-5 h-5 text-cyan-400" />
            Live Observer
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Real-time kernel TCP socket telemetry and dissected packet flow diagram.
          </p>
        </div>

        {/* Action Button: Visible once transfer completed */}
        {isCompleted && (
          <button
            onClick={handleManualAdvance}
            disabled={isAdvancing}
            className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-emerald-500 to-cyan-500 hover:from-emerald-400 hover:to-cyan-400 text-white font-bold rounded-lg shadow-lg shadow-emerald-500/20 text-sm transition-all cursor-pointer disabled:opacity-50"
          >
            <CheckCircle className="w-4 h-4" /> View Results <ArrowRight className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Progress Bar & Informative State Indicator */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-sm">
        <div className="flex flex-wrap justify-between items-center text-xs mb-2 gap-2">
          <div className="flex items-center gap-2">
            <span className="flex h-2 w-2 relative">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${isCompleted ? 'bg-emerald-400 opacity-75' : 'bg-cyan-400 opacity-75'}`}></span>
              <span className={`relative inline-flex rounded-full h-2 w-2 ${isCompleted ? 'bg-emerald-500' : 'bg-cyan-500'}`}></span>
            </span>
            <span className="font-semibold text-slate-200">
              {transferState}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-slate-400 font-mono text-[11px]">
              {capturedPackets.length} Packets
            </span>
            <span className="font-mono text-cyan-400 font-bold text-sm">
              {metrics.pct.toFixed(1)}%
            </span>
          </div>
        </div>

        {/* Visual Progress Bar with Active Shimmer on Low Bandwidth */}
        <div className="w-full h-2.5 bg-slate-950 rounded-full overflow-hidden border border-slate-800 relative">
          <div
            className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 transition-all duration-300"
            style={{ width: `${Math.min(metrics.pct, 100)}%` }}
          />
          {!isCompleted && (
            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent animate-pulse" />
          )}
        </div>
      </div>

      {/* 4 Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-slate-900/90 border border-slate-800 p-4 rounded-xl flex items-center gap-3 shadow-sm">
          <div className="p-2.5 bg-cyan-500/10 rounded-lg text-cyan-400">
            <Gauge className="w-5 h-5" />
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Throughput</div>
            <div className="text-xl font-bold font-mono text-slate-100">
              {metrics.throughput.toFixed(1)} <span className="text-xs font-normal text-slate-400">Mbps</span>
            </div>
          </div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 p-4 rounded-xl flex items-center gap-3 shadow-sm">
          <div className="p-2.5 bg-blue-500/10 rounded-lg text-blue-400">
            <Clock className="w-5 h-5" />
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">RTT</div>
            <div className="text-xl font-bold font-mono text-slate-100">
              {metrics.rtt.toFixed(1)} <span className="text-xs font-normal text-slate-400">ms</span>
            </div>
          </div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 p-4 rounded-xl flex items-center gap-3 shadow-sm">
          <div className="p-2.5 bg-emerald-500/10 rounded-lg text-emerald-400">
            <BarChart3 className="w-5 h-5" />
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">CWND</div>
            <div className="text-xl font-bold font-mono text-slate-100">
              {metrics.cwnd} <span className="text-xs font-normal text-slate-400">segs</span>
            </div>
          </div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 p-4 rounded-xl flex items-center gap-3 shadow-sm">
          <div className="p-2.5 bg-rose-500/10 rounded-lg text-rose-400">
            <Repeat className="w-5 h-5" />
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Retransmits</div>
            <div className="text-xl font-bold font-mono text-slate-100">
              {metrics.retransmissions} <span className="text-xs font-normal text-slate-400">pkts</span>
            </div>
          </div>
        </div>
      </div>

      {/* 4 LineCharts */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <LiveChart label="Throughput" data={tpChartData} strokeColor="#06B6D4" unit="Mbps" />
        <LiveChart label="Round Trip Time" data={rttChartData} strokeColor="#3B82F6" unit="ms" />
        <LiveChart label="Congestion Window" data={cwndChartData} strokeColor="#10B981" unit="segs" />
        <LiveChart label="Retransmissions" data={retransChartData} strokeColor="#EF4444" unit="drops" />
      </div>

      {/* TCP Ladder Canvas & Dissected Packet Table */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* TCP Ladder Canvas with Playback Controls */}
        <div className="lg:col-span-6 bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-xl flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-200">TCP Ladder Diagram</h3>
            <span className="text-[11px] font-mono text-slate-400">
              {capturedPackets.length} Captured
            </span>
          </div>
          <div className="flex-1 min-h-[400px]">
            <TcpLadder packets={capturedPackets} isLive={!isCompleted} />
          </div>
        </div>

        {/* Packet Table */}
        <div className="lg:col-span-6 bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-xl flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-200">Dissected Packets</h3>
            <span className="text-[11px] font-mono text-slate-400">
              {capturedPackets[0]?.dst_port ? `Port ${capturedPackets[0].dst_port}` : 'TCP Stream'}
            </span>
          </div>
          <div className="overflow-x-auto max-h-[460px] overflow-y-auto border border-slate-800 rounded-xl">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] tracking-wider sticky top-0 border-b border-slate-800">
                <tr>
                  <th className="px-3 py-2">#</th>
                  <th className="px-3 py-2">Time</th>
                  <th className="px-3 py-2">Flags</th>
                  <th className="px-3 py-2">Seq</th>
                  <th className="px-3 py-2">Len</th>
                  <th className="px-3 py-2">Info</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-[11px]">
                {capturedPackets.length === 0 ? (
                  <tr>
                    <td colSpan="6" className="p-8 text-center text-slate-500 font-sans">
                      Waiting for packets...
                    </td>
                  </tr>
                ) : (
                  capturedPackets.slice(-100).map((pkt, idx) => {
                    const isRet = pkt.is_retrans || pkt.flags?.includes('RETRANS');
                    const isDrop = pkt.is_dropped || pkt.flags?.includes('DROPPED');
                    const isTimeout = pkt.is_timeout || pkt.flags?.includes('TIMEOUT');
                    return (
                      <tr
                        key={pkt.num || idx}
                        className={
                          isDrop
                            ? 'bg-rose-500/15 text-rose-300'
                            : isTimeout
                            ? 'bg-amber-500/15 text-amber-300'
                            : isRet
                            ? 'bg-orange-500/15 text-orange-300'
                            : pkt.flags?.includes('SYN')
                            ? 'bg-emerald-500/10 text-emerald-300'
                            : 'hover:bg-slate-800/30 text-slate-300'
                        }
                      >
                        <td className="px-3 py-1.5 text-slate-500">{pkt.num || idx + 1}</td>
                        <td className="px-3 py-1.5">{typeof pkt.time === 'number' ? pkt.time.toFixed(3) : pkt.time}</td>
                        <td className="px-3 py-1.5 font-bold">{pkt.flags || 'TCP'}</td>
                        <td className="px-3 py-1.5">{pkt.seq || 0}</td>
                        <td className="px-3 py-1.5">{pkt.len || 0}B</td>
                        <td className="px-3 py-1.5 truncate max-w-[150px] text-slate-400 font-sans text-[10px]">
                          {pkt.info}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
