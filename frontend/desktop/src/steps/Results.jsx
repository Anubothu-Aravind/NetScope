import React from 'react';
import { Award, RotateCcw, Gauge, Clock, Repeat, BarChart3, ShieldCheck, CheckCircle, Download } from 'lucide-react';
import TcpLadder from '../components/TcpLadder';
import LiveChart from '../components/LiveChart';

/**
 * Step 4: Results Component (Task 7)
 * 
 * - Accept finalData prop from Observer
 * - Show 4 metric values from finalData
 * - Show full packet table from capturedPackets prop
 * - Show TcpLadder canvas with all packets
 * - Show all 4 recharts LineCharts with full telemetryHistory prop
 * - Show Run Another button that calls onReset() prop
 */
export default function Results({
  finalData = {},
  capturedPackets = [],
  telemetryHistory = [],
  onReset,
}) {
  const record = finalData?.record || finalData || {};
  const tcp = finalData?.tcp || {};

  // Extract 4 final metrics from finalData
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

  // Format chart data arrays
  const tpChartData = telemetryHistory.map((h) => ({ time: h.time, value: h.throughput }));
  const rttChartData = telemetryHistory.map((h) => ({ time: h.time, value: h.rtt }));
  const cwndChartData = telemetryHistory.map((h) => ({ time: h.time, value: h.cwnd }));
  const retransChartData = telemetryHistory.map((h) => ({ time: h.time, value: h.retransmissions }));

  // Fallback to packets within finalData/record if capturedPackets prop was delayed
  const allPackets = (capturedPackets && capturedPackets.length > 0)
    ? capturedPackets
    : (finalData?.packets || record?.packets || []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-4">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <Award className="w-5 h-5 text-emerald-400" />
            Final Transfer Results
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Complete PCAP packet trace and statistical performance profile.
          </p>
        </div>

        <button
          onClick={onReset}
          className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-bold rounded-lg shadow-lg shadow-cyan-500/20 text-sm transition-all cursor-pointer"
        >
          <RotateCcw className="w-4 h-4" /> Run Another
        </button>
      </div>

      {/* 4 Metric Cards from finalData */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-slate-900/90 border border-slate-800 p-4 rounded-xl shadow-sm">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Gauge className="w-3.5 h-3.5 text-cyan-400" /> Throughput
          </div>
          <div className="text-2xl font-bold font-mono text-slate-100 mt-1">
            {throughput} <span className="text-xs font-normal text-slate-400">Mbps</span>
          </div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 p-4 rounded-xl shadow-sm">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-blue-400" /> Average RTT
          </div>
          <div className="text-2xl font-bold font-mono text-slate-100 mt-1">
            {rttAvg} <span className="text-xs font-normal text-slate-400">ms</span>
          </div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 p-4 rounded-xl shadow-sm">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <BarChart3 className="w-3.5 h-3.5 text-emerald-400" /> CWND Window
          </div>
          <div className="text-2xl font-bold font-mono text-slate-100 mt-1">
            {cwnd} <span className="text-xs font-normal text-slate-400">segs</span>
          </div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 p-4 rounded-xl shadow-sm">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Repeat className="w-3.5 h-3.5 text-rose-400" /> Retransmits
          </div>
          <div className="text-2xl font-bold font-mono text-slate-100 mt-1">
            {retrans} <span className="text-xs font-normal text-slate-400">pkts</span>
          </div>
        </div>
      </div>

      {/* 4 LineCharts with full telemetryHistory prop */}
      <div>
        <h3 className="text-sm font-semibold text-slate-300 mb-3">Transmission Profile Charts</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <LiveChart label="Throughput" data={tpChartData} strokeColor="#06B6D4" unit="Mbps" />
          <LiveChart label="Round Trip Time" data={rttChartData} strokeColor="#3B82F6" unit="ms" />
          <LiveChart label="Congestion Window" data={cwndChartData} strokeColor="#10B981" unit="segs" />
          <LiveChart label="Retransmissions" data={retransChartData} strokeColor="#EF4444" unit="drops" />
        </div>
      </div>

      {/* Full TcpLadder & Full Packet Table */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Full TcpLadder Canvas */}
        <div className="lg:col-span-6 bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-xl">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-200">Full TCP Ladder Canvas</h3>
            <span className="text-[11px] font-mono text-slate-400">
              {allPackets.length} Total Packets
            </span>
          </div>
          <TcpLadder packets={allPackets} />
        </div>

        {/* Full Packet Table */}
        <div className="lg:col-span-6 bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-xl">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-200">Full Packet Table</h3>
            {record.run_id && (
              <a
                href={`/api/download/${record.run_id}`}
                download
                className="text-xs text-cyan-400 hover:text-cyan-300 flex items-center gap-1 font-mono"
              >
                <Download className="w-3.5 h-3.5" /> Download Decrypted File
              </a>
            )}
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
                {allPackets.length === 0 ? (
                  <tr>
                    <td colSpan="6" className="p-8 text-center text-slate-500 font-sans">
                      Waiting for packets...
                    </td>
                  </tr>
                ) : (
                  allPackets.map((pkt, idx) => (
                    <tr
                      key={pkt.num || idx}
                      className={
                        pkt.is_retrans
                          ? 'bg-rose-500/10 text-rose-300'
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
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
