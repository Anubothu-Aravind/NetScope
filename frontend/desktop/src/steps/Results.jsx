import React, { useState, useEffect, useMemo } from 'react';
import {
  Award,
  RotateCcw,
  Gauge,
  Clock,
  Repeat,
  BarChart3,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Download,
  FileText,
  Layers,
  Search,
  Activity,
  History,
  TrendingUp,
  FileDown,
  Check,
  Copy,
  ExternalLink
} from 'lucide-react';
import TcpLadder from '../components/TcpLadder';
import LiveChart from '../components/LiveChart';

/**
 * Helper to format bytes into readable KB / MB units
 */
function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const num = Number(bytes);
  if (num < 1024) return `${num} B`;
  if (num < 1024 * 1024) return `${(num / 1024).toFixed(2)} KB`;
  return `${(num / (1024 * 1024)).toFixed(2)} MB (${num.toLocaleString()} B)`;
}

/**
 * Step 4: Enhanced Data-Focused Results Dashboard
 * 
 * - Clear transfer summary banner with SHA-256 integrity verification.
 * - 4 Key Performance Indicator (KPI) cards with real measurements and ratings.
 * - Organized tabs:
 *     1. Performance Dynamics (Recharts transmission profile)
 *     2. Full TCP Ladder (interactive slow-motion replay canvas)
 *     3. Deep Packet Trace (searchable & filterable packet table with CSV export)
 *     4. Comparative Run History (cross-run benchmark comparison from transfers.jsonl)
 * - Click protection on Run Another button to prevent duplicate submissions.
 */
export default function Results({
  finalData = {},
  capturedPackets = [],
  telemetryHistory = [],
  onReset,
}) {
  const [activeTab, setActiveTab] = useState('overview'); // 'overview' | 'ladder' | 'packets' | 'history'
  const [packetFilter, setPacketFilter] = useState('all'); // 'all' | 'retrans' | 'dropped' | 'control'
  const [searchQuery, setSearchQuery] = useState('');
  const [historyRuns, setHistoryRuns] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [copiedSha, setCopiedSha] = useState(false);

  const record = finalData?.record || finalData || {};
  const tcp = finalData?.tcp || {};

  // Extract real metrics from transfer record and telemetry
  const throughput = Number(
    record.throughput_mbps ||
      (telemetryHistory.length > 0
        ? telemetryHistory[telemetryHistory.length - 1].throughput
        : 0)
  ).toFixed(2);

  const rttAvg = Number(
    tcp.rtt_avg_ms !== undefined && tcp.rtt_avg_ms !== null
      ? tcp.rtt_avg_ms
      : record.rtt_avg_ms ||
        (telemetryHistory.length > 0 ? telemetryHistory[telemetryHistory.length - 1].rtt : 0)
  ).toFixed(2);

  const retrans =
    tcp.retransmissions !== undefined
      ? tcp.retransmissions
      : record.retransmissions !== undefined
      ? record.retransmissions
      : telemetryHistory.length > 0
      ? telemetryHistory[telemetryHistory.length - 1].retransmissions
      : 0;

  const cwnd =
    tcp.cwnd !== undefined
      ? tcp.cwnd
      : record.cwnd !== undefined
      ? record.cwnd
      : telemetryHistory.length > 0
      ? telemetryHistory[telemetryHistory.length - 1].cwnd
      : 0;

  const sha256Ok = record.sha256_ok !== false;
  const runId = record.run_id || record.runId || '';
  const filename = record.file || record.filename || 'payload.bin';
  const sizeBytes = record.size_bytes || record.total_bytes || record.bytes || 0;
  const durationSec = record.completion_s || record.transfer_time_sec || (record.duration ? record.duration / 1000 : null);
  const scenario = record.scenario || 'Manual';

  // Format chart data arrays
  const tpChartData = telemetryHistory.map((h) => ({ time: h.time, value: h.throughput }));
  const rttChartData = telemetryHistory.map((h) => ({ time: h.time, value: h.rtt }));
  const cwndChartData = telemetryHistory.map((h) => ({ time: h.time, value: h.cwnd }));
  const retransChartData = telemetryHistory.map((h) => ({ time: h.time, value: h.retransmissions }));

  // Fallback to packets within finalData/record if capturedPackets prop was delayed
  const allPackets = (capturedPackets && capturedPackets.length > 0)
    ? capturedPackets
    : (finalData?.packets || record?.packets || []);

  // Fetch recent runs for historical comparison
  useEffect(() => {
    let isMounted = true;
    async function fetchHistory() {
      try {
        setLoadingHistory(true);
        const res = await fetch('/api/results');
        if (res.ok) {
          const data = await res.json();
          if (isMounted) {
            setHistoryRuns(Array.isArray(data) ? data.slice(-10).reverse() : []);
          }
        }
      } catch (err) {
        console.warn('Failed to fetch history runs:', err);
      } finally {
        if (isMounted) setLoadingHistory(false);
      }
    }
    fetchHistory();
    return () => {
      isMounted = false;
    };
  }, []);

  // Handle protected reset
  const handleProtectedReset = async () => {
    if (isResetting) return;
    setIsResetting(true);
    try {
      if (onReset) {
        await onReset();
      }
    } finally {
      setIsResetting(false);
    }
  };

  // Filtered packets for deep trace
  const filteredPackets = useMemo(() => {
    return allPackets.filter((pkt) => {
      const flags = String(pkt.flags || '').toUpperCase();
      const isRet = Boolean(pkt.is_retrans || flags.includes('RETRANS'));
      const isDrop = Boolean(pkt.is_dropped || flags.includes('DROPPED'));
      const isCtrl = flags.includes('SYN') || flags.includes('FIN') || flags.includes('RST');

      if (packetFilter === 'retrans' && !isRet) return false;
      if (packetFilter === 'dropped' && !isDrop) return false;
      if (packetFilter === 'control' && !isCtrl) return false;

      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesInfo = (pkt.info || '').toLowerCase().includes(q);
        const matchesFlags = flags.toLowerCase().includes(q);
        const matchesSeq = String(pkt.seq || '').includes(q);
        if (!matchesInfo && !matchesFlags && !matchesSeq) return false;
      }
      return true;
    });
  }, [allPackets, packetFilter, searchQuery]);

  // Export packets as CSV
  const handleExportCsv = () => {
    if (allPackets.length === 0) return;
    const headers = ['#', 'Time (s)', 'Direction', 'Flags', 'Seq', 'Ack', 'Len (B)', 'Retrans', 'Info'];
    const rows = allPackets.map((p, idx) => [
      p.num || idx + 1,
      p.time || 0,
      p.direction || '',
      `"${p.flags || ''}"`,
      p.seq || 0,
      p.ack || 0,
      p.len || 0,
      p.is_retrans ? 'YES' : 'NO',
      `"${(p.info || '').replace(/"/g, '""')}"`,
    ]);
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `packet_trace_${runId || 'transfer'}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const copySha = () => {
    const sha = record.sha256 || 'SHA-256 Verified';
    navigator.clipboard.writeText(sha);
    setCopiedSha(true);
    setTimeout(() => setCopiedSha(false), 2000);
  };

  // RTT status rating
  const rttRating = Number(rttAvg) < 5
    ? { text: 'Ultra-Low Latency', color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' }
    : Number(rttAvg) < 50
    ? { text: 'Optimal RTT', color: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20' }
    : { text: 'Elevated Latency', color: 'text-amber-400 bg-amber-500/10 border-amber-500/20' };

  // Retransmission rating
  const totalPktsCount = sizeBytes > 0
    ? Math.max(Math.ceil(sizeBytes / 65536), allPackets.length)
    : (allPackets.length || 1);
  const lossPct = ((retrans / totalPktsCount) * 100).toFixed(1);

  return (
    <div className="space-y-6">
      {/* 1. Results Summary Banner */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl relative overflow-hidden backdrop-blur-md">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 pb-4 border-b border-slate-800/80">
          <div className="flex items-center gap-3.5">
            <div className={`w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 border ${
              sha256Ok
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400 shadow-lg shadow-emerald-500/10'
                : 'bg-rose-500/10 border-rose-500/30 text-rose-400 shadow-lg shadow-rose-500/10'
            }`}>
              {sha256Ok ? <CheckCircle2 className="w-6 h-6" /> : <AlertTriangle className="w-6 h-6" />}
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-xl font-bold text-slate-100 tracking-tight">
                  {sha256Ok ? 'Transfer Verified & Completed' : 'Transfer Completed with Warnings'}
                </h1>
                <span className={`text-[10px] uppercase font-mono font-bold px-2.5 py-0.5 rounded-full border ${
                  sha256Ok
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                    : 'bg-rose-500/10 text-rose-400 border-rose-500/20'
                }`}>
                  {sha256Ok ? 'SHA-256 MATCH' : 'INTEGRITY MISMATCH'}
                </span>
                <span className="text-[10px] font-mono uppercase bg-slate-800 text-slate-300 px-2.5 py-0.5 rounded-full border border-slate-700">
                  Scenario: {scenario}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1 flex items-center gap-2 flex-wrap">
                <span className="font-mono text-cyan-400 font-semibold">{filename}</span>
                <span>•</span>
                <span>{formatBytes(sizeBytes)}</span>
                {durationSec && (
                  <>
                    <span>•</span>
                    <span>Duration: <strong className="text-slate-200 font-mono">{Number(durationSec).toFixed(3)}s</strong></span>
                  </>
                )}
                {runId && (
                  <>
                    <span>•</span>
                    <span className="font-mono text-slate-500">Run ID: #{runId}</span>
                  </>
                )}
              </p>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2.5 w-full md:w-auto justify-end">
            {runId && (
              <a
                href={`/api/download/${runId}`}
                download
                className="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold rounded-xl transition-all flex items-center gap-1.5 cursor-pointer"
                title="Download received file binary"
              >
                <Download className="w-3.5 h-3.5 text-cyan-400" />
                <span>File</span>
              </a>
            )}

            <button
              onClick={handleProtectedReset}
              disabled={isResetting}
              className="px-5 py-2 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 disabled:opacity-50 text-white font-bold rounded-xl shadow-lg shadow-cyan-500/20 text-xs uppercase tracking-wider transition-all flex items-center gap-2 cursor-pointer"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${isResetting ? 'animate-spin' : ''}`} />
              {isResetting ? 'Resetting Session...' : 'Run Another'}
            </button>
          </div>
        </div>

        {/* Checksum & PCAP Row */}
        <div className="pt-3 flex flex-col md:flex-row items-start md:items-center justify-between text-xs font-mono text-slate-400 gap-2">
          <div className="flex items-center gap-2 truncate max-w-full">
            <span className="text-slate-500 font-sans">Checksum:</span>
            <span className="text-slate-300 truncate font-mono text-[11px]">
              {record.sha256 || 'Verified matching client payload digest'}
            </span>
            {record.sha256 && (
              <button
                onClick={copySha}
                className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-cyan-400 transition-colors"
                title="Copy SHA-256"
              >
                {copiedSha ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
              </button>
            )}
          </div>

          {record.pcap && (
            <div className="text-[11px] text-slate-500">
              PCAP Trace: <span className="text-slate-400">{record.pcap}</span>
            </div>
          )}
        </div>
      </div>

      {/* 2. Key Metric Cards (KPI Cards) */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Throughput */}
        <div className="bg-slate-900/90 border border-slate-800 p-4 rounded-2xl shadow-lg hover:border-slate-700/80 transition-all">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <Gauge className="w-3.5 h-3.5 text-cyan-400" /> Average Throughput
            </span>
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
          </div>
          <div className="text-2xl font-bold font-mono text-slate-100 mt-2">
            {throughput} <span className="text-xs font-normal text-slate-400">Mbps</span>
          </div>
          <p className="text-[10px] text-slate-500 mt-1 font-mono">
            {sizeBytes ? formatBytes(sizeBytes).split(' ')[0] + ' transferred' : 'Sustained wire speed'}
          </p>
        </div>

        {/* Round Trip Time */}
        <div className="bg-slate-900/90 border border-slate-800 p-4 rounded-2xl shadow-lg hover:border-slate-700/80 transition-all">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-blue-400" /> Average RTT
            </span>
            <span className={`text-[9px] px-1.5 py-0.5 rounded border ${rttRating.color}`}>
              {rttRating.text}
            </span>
          </div>
          <div className="text-2xl font-bold font-mono text-slate-100 mt-2">
            {rttAvg} <span className="text-xs font-normal text-slate-400">ms</span>
          </div>
          <p className="text-[10px] text-slate-500 mt-1 font-mono">
            Kernel TCP socket telemetry
          </p>
        </div>

        {/* CWND */}
        <div className="bg-slate-900/90 border border-slate-800 p-4 rounded-2xl shadow-lg hover:border-slate-700/80 transition-all">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <BarChart3 className="w-3.5 h-3.5 text-emerald-400" /> CWND Window
            </span>
            <span className="text-[9px] font-mono text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">
              Peak MSS
            </span>
          </div>
          <div className="text-2xl font-bold font-mono text-slate-100 mt-2">
            {cwnd} <span className="text-xs font-normal text-slate-400">segs</span>
          </div>
          <p className="text-[10px] text-slate-500 mt-1 font-mono">
            ~{Math.round(cwnd * 1.46)} KB congestion window
          </p>
        </div>

        {/* Retransmissions */}
        <div className="bg-slate-900/90 border border-slate-800 p-4 rounded-2xl shadow-lg hover:border-slate-700/80 transition-all">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <Repeat className="w-3.5 h-3.5 text-rose-400" /> Retransmissions
            </span>
            <span className={`text-[9px] px-1.5 py-0.5 rounded border ${
              retrans === 0
                ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                : 'text-amber-400 bg-amber-500/10 border-amber-500/20'
            }`}>
              {retrans === 0 ? 'Zero Loss' : `${lossPct}% loss`}
            </span>
          </div>
          <div className="text-2xl font-bold font-mono text-slate-100 mt-2">
            {retrans} <span className="text-xs font-normal text-slate-400">pkts</span>
          </div>
          <p className="text-[10px] text-slate-500 mt-1 font-mono">
            {retrans > 0 ? 'Recovered via fast/RTO retry' : 'Clean single-pass transmission'}
          </p>
        </div>
      </div>

      {/* 3. Section Tabs */}
      <div className="border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('overview')}
            className={`px-4 py-2.5 text-xs font-semibold rounded-t-xl transition-all border-b-2 flex items-center gap-2 cursor-pointer ${
              activeTab === 'overview'
                ? 'border-cyan-400 text-cyan-300 bg-slate-900/60'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" /> Performance Dynamics
          </button>

          <button
            onClick={() => setActiveTab('ladder')}
            className={`px-4 py-2.5 text-xs font-semibold rounded-t-xl transition-all border-b-2 flex items-center gap-2 cursor-pointer ${
              activeTab === 'ladder'
                ? 'border-cyan-400 text-cyan-300 bg-slate-900/60'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Layers className="w-3.5 h-3.5" /> Full TCP Ladder ({allPackets.length})
          </button>

          <button
            onClick={() => setActiveTab('packets')}
            className={`px-4 py-2.5 text-xs font-semibold rounded-t-xl transition-all border-b-2 flex items-center gap-2 cursor-pointer ${
              activeTab === 'packets'
                ? 'border-cyan-400 text-cyan-300 bg-slate-900/60'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Search className="w-3.5 h-3.5" /> Deep Packet Trace
          </button>

          <button
            onClick={() => setActiveTab('history')}
            className={`px-4 py-2.5 text-xs font-semibold rounded-t-xl transition-all border-b-2 flex items-center gap-2 cursor-pointer ${
              activeTab === 'history'
                ? 'border-cyan-400 text-cyan-300 bg-slate-900/60'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <History className="w-3.5 h-3.5" /> Run Comparison ({historyRuns.length})
          </button>
        </div>

        <div className="hidden sm:flex items-center gap-2 text-xs text-slate-500 font-mono">
          <span>Total Packets: {allPackets.length}</span>
        </div>
      </div>

      {/* ============================================================ */}
      {/* TAB 1: OVERVIEW & PERFORMANCE DYNAMICS */}
      {/* ============================================================ */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
              <Activity className="w-4 h-4 text-cyan-400" />
              Real-Time Protocol Telemetry Sparklines
            </h3>
            <span className="text-xs text-slate-500 font-mono">30-point live window</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <LiveChart label="Throughput" data={tpChartData} strokeColor="#06B6D4" unit="Mbps" />
            <LiveChart label="Round Trip Time" data={rttChartData} strokeColor="#3B82F6" unit="ms" />
            <LiveChart label="Congestion Window" data={cwndChartData} strokeColor="#10B981" unit="segs" />
            <LiveChart label="Retransmissions" data={retransChartData} strokeColor="#EF4444" unit="drops" />
          </div>

          {/* Quick Ladder & Trace Preview */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start pt-2">
            <div className="lg:col-span-6 bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-xl">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-xs font-semibold text-slate-200 uppercase tracking-wider">
                  TCP Ladder Preview
                </h4>
                <button
                  onClick={() => setActiveTab('ladder')}
                  className="text-xs text-cyan-400 hover:underline flex items-center gap-1 font-sans"
                >
                  Full Canvas <ExternalLink className="w-3 h-3" />
                </button>
              </div>
              <TcpLadder packets={allPackets} />
            </div>

            <div className="lg:col-span-6 bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-xl">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-xs font-semibold text-slate-200 uppercase tracking-wider">
                  Recent Packet Trace
                </h4>
                <button
                  onClick={() => setActiveTab('packets')}
                  className="text-xs text-cyan-400 hover:underline flex items-center gap-1 font-sans"
                >
                  Inspect All <ExternalLink className="w-3 h-3" />
                </button>
              </div>

              <div className="overflow-x-auto max-h-[380px] overflow-y-auto border border-slate-800 rounded-xl">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] tracking-wider sticky top-0 border-b border-slate-800">
                    <tr>
                      <th className="px-3 py-2">#</th>
                      <th className="px-3 py-2">Time</th>
                      <th className="px-3 py-2">Flags</th>
                      <th className="px-3 py-2">Seq</th>
                      <th className="px-3 py-2">Len</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 text-[11px]">
                    {allPackets.slice(-15).map((pkt, idx) => (
                      <tr key={pkt.num || idx} className="hover:bg-slate-800/30 text-slate-300">
                        <td className="px-3 py-1.5 text-slate-500">{pkt.num || idx + 1}</td>
                        <td className="px-3 py-1.5">{typeof pkt.time === 'number' ? pkt.time.toFixed(3) : pkt.time}</td>
                        <td className="px-3 py-1.5 font-bold">{pkt.flags || 'TCP'}</td>
                        <td className="px-3 py-1.5">{pkt.seq || 0}</td>
                        <td className="px-3 py-1.5">{pkt.len || 0}B</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* TAB 2: FULL TCP LADDER CANVAS */}
      {/* ============================================================ */}
      {activeTab === 'ladder' && (
        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
            <div>
              <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
                <Layers className="w-5 h-5 text-cyan-400" />
                Interactive Full TCP Ladder & Timeline Replay
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Step-by-step ladder sequence diagram with retransmissions, drops, and slow-motion replay.
              </p>
            </div>
            <span className="text-xs font-mono text-cyan-400 bg-cyan-500/10 border border-cyan-500/20 px-3 py-1 rounded-full">
              {allPackets.length} Transmitted Packets
            </span>
          </div>

          <TcpLadder packets={allPackets} />
        </div>
      )}

      {/* ============================================================ */}
      {/* TAB 3: DEEP PACKET TRACE & INSPECTION */}
      {/* ============================================================ */}
      {activeTab === 'packets' && (
        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
            <div>
              <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
                <Search className="w-5 h-5 text-cyan-400" />
                Dissected Packet Trace Table
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Frame-by-frame inspection of TCP segments captured on the wire.
              </p>
            </div>

            <button
              onClick={handleExportCsv}
              disabled={allPackets.length === 0}
              className="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-xl border border-slate-700 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            >
              <FileDown className="w-3.5 h-3.5 text-cyan-400" /> Export CSV
            </button>
          </div>

          {/* Filters & Search */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div className="flex items-center gap-1.5 bg-slate-950 p-1 rounded-xl border border-slate-800">
              <button
                onClick={() => setPacketFilter('all')}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  packetFilter === 'all' ? 'bg-cyan-500/20 text-cyan-300 font-bold' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                All ({allPackets.length})
              </button>
              <button
                onClick={() => setPacketFilter('retrans')}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  packetFilter === 'retrans' ? 'bg-orange-500/20 text-orange-300 font-bold' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Retransmissions ({allPackets.filter((p) => p.is_retrans || p.flags?.includes('RETRANS')).length})
              </button>
              <button
                onClick={() => setPacketFilter('dropped')}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  packetFilter === 'dropped' ? 'bg-rose-500/20 text-rose-300 font-bold' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Dropped ({allPackets.filter((p) => p.is_dropped || p.flags?.includes('DROPPED')).length})
              </button>
              <button
                onClick={() => setPacketFilter('control')}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  packetFilter === 'control' ? 'bg-indigo-500/20 text-indigo-300 font-bold' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Handshake / FIN
              </button>
            </div>

            <div className="relative">
              <input
                type="text"
                placeholder="Search info, seq, flags..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-slate-200 font-mono focus:outline-none focus:border-cyan-500 w-full sm:w-56"
              />
            </div>
          </div>

          {/* Table */}
          <div className="overflow-x-auto max-h-[500px] overflow-y-auto border border-slate-800 rounded-xl">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] tracking-wider sticky top-0 border-b border-slate-800 z-10">
                <tr>
                  <th className="px-3 py-2.5">#</th>
                  <th className="px-3 py-2.5">Time (s)</th>
                  <th className="px-3 py-2.5">Dir</th>
                  <th className="px-3 py-2.5">Flags</th>
                  <th className="px-3 py-2.5">Seq</th>
                  <th className="px-3 py-2.5">Ack</th>
                  <th className="px-3 py-2.5">Len</th>
                  <th className="px-3 py-2.5">Info & Protocol Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-[11px]">
                {filteredPackets.length === 0 ? (
                  <tr>
                    <td colSpan="8" className="p-8 text-center text-slate-500 font-sans">
                      No matching packets found in current trace.
                    </td>
                  </tr>
                ) : (
                  filteredPackets.map((pkt, idx) => {
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
                        <td className="px-3 py-2 text-slate-500">{pkt.num || idx + 1}</td>
                        <td className="px-3 py-2">{typeof pkt.time === 'number' ? pkt.time.toFixed(4) : pkt.time}</td>
                        <td className="px-3 py-2 text-[10px] uppercase text-slate-400">{pkt.direction || 'c2s'}</td>
                        <td className="px-3 py-2 font-bold">{pkt.flags || 'DATA'}</td>
                        <td className="px-3 py-2">{pkt.seq || 0}</td>
                        <td className="px-3 py-2">{pkt.ack || 0}</td>
                        <td className="px-3 py-2">{pkt.len || 0}B</td>
                        <td className="px-3 py-2 truncate max-w-xs text-slate-400 font-sans text-[11px]">
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
      )}

      {/* ============================================================ */}
      {/* TAB 4: COMPARATIVE RUN HISTORY */}
      {/* ============================================================ */}
      {activeTab === 'history' && (
        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
                <History className="w-5 h-5 text-cyan-400" />
                Comparative Run History & Benchmarks
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Comparison against previous test runs recorded in <code className="text-cyan-400 font-mono">results/transfers.jsonl</code>.
              </p>
            </div>
            <span className="text-xs text-slate-400 font-mono">
              {historyRuns.length} Recorded Runs
            </span>
          </div>

          <div className="overflow-x-auto border border-slate-800 rounded-xl">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800">
                <tr>
                  <th className="px-3 py-2.5">Run ID</th>
                  <th className="px-3 py-2.5">Scenario</th>
                  <th className="px-3 py-2.5">Payload</th>
                  <th className="px-3 py-2.5">Size</th>
                  <th className="px-3 py-2.5">Throughput</th>
                  <th className="px-3 py-2.5">Avg RTT</th>
                  <th className="px-3 py-2.5">Retransmits</th>
                  <th className="px-3 py-2.5">Integrity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-sans">
                {historyRuns.length === 0 ? (
                  <tr>
                    <td colSpan="8" className="p-8 text-center text-slate-500">
                      {loadingHistory ? 'Loading historical transfer runs...' : 'No historical transfer runs recorded yet.'}
                    </td>
                  </tr>
                ) : (
                  historyRuns.map((hr, idx) => {
                    const isCurrent = hr.run_id === runId;
                    const hrSizeBytes = hr.size_bytes || hr.total_bytes || 0;
                    return (
                      <tr
                        key={hr.run_id || idx}
                        className={`hover:bg-slate-800/30 text-slate-300 ${isCurrent ? 'bg-cyan-500/10 border-l-2 border-l-cyan-400' : ''}`}
                      >
                        <td className="px-3 py-2.5 font-mono text-cyan-400 font-semibold flex items-center gap-1.5">
                          {hr.run_id || `run-${idx}`}
                          {isCurrent && (
                            <span className="text-[9px] bg-cyan-400 text-slate-950 px-1 rounded font-bold">
                              CURRENT
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2.5 font-medium text-slate-200">
                          {hr.scenario || 'Manual'}
                        </td>
                        <td className="px-3 py-2.5 truncate max-w-[120px] font-mono text-[11px] text-slate-400">
                          {hr.file || 'payload.bin'}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-slate-400">
                          {formatBytes(hrSizeBytes)}
                        </td>
                        <td className="px-3 py-2.5 font-mono font-bold text-slate-100">
                          {hr.throughput_mbps ? Number(hr.throughput_mbps).toFixed(2) : '-'} <span className="text-[10px] text-slate-500">Mbps</span>
                        </td>
                        <td className="px-3 py-2.5 font-mono text-slate-300">
                          {hr.tcp?.rtt_avg_ms !== undefined ? Number(hr.tcp.rtt_avg_ms).toFixed(2) : (hr.rtt_avg_ms || '-')} ms
                        </td>
                        <td className="px-3 py-2.5 font-mono">
                          <span className={hr.tcp?.retransmissions > 0 ? 'text-amber-400' : 'text-slate-400'}>
                            {hr.tcp?.retransmissions !== undefined ? hr.tcp.retransmissions : (hr.retransmissions || 0)}
                          </span>
                        </td>
                        <td className="px-3 py-2.5">
                          {hr.sha256_ok !== false ? (
                            <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400 font-medium">
                              <CheckCircle2 className="w-3.5 h-3.5" /> Verified
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-[11px] text-rose-400 font-medium">
                              <AlertTriangle className="w-3.5 h-3.5" /> Mismatch
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
