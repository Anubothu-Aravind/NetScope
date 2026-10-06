import React from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';

/**
 * LiveChart - Real-time metrics sparkline using Recharts
 * 
 * Props:
 * - label: string (e.g. "Throughput (Mbps)")
 * - data: array of { time: string|number, value: number }
 * - strokeColor: string (hex)
 * - unit: string (e.g. "Mbps", "ms", "pkts")
 */
export default function LiveChart({
  label,
  data = [],
  strokeColor = '#06B6D4',
  unit = '',
}) {
  const latestValue = data.length > 0 ? data[data.length - 1].value : 0;

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 flex flex-col shadow-sm">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          {label}
        </span>
        <span className="text-lg font-bold font-mono text-slate-100">
          {typeof latestValue === 'number' ? latestValue.toFixed(1) : latestValue}
          <span className="text-xs font-normal text-slate-400 ml-1">{unit}</span>
        </span>
      </div>

      <div className="w-full h-36">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid stroke="#1E293B" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="time"
              stroke="#475569"
              tick={{ fontSize: 10, fill: '#64748B' }}
              tickLine={false}
            />
            <YAxis
              stroke="#475569"
              domain={['auto', 'auto']}
              tick={{ fontSize: 10, fill: '#64748B' }}
              tickLine={false}
              allowDecimals={true}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#0F172A',
                borderColor: '#334155',
                borderRadius: '8px',
                fontSize: '11px',
                color: '#F8FAFC',
              }}
              formatter={(val) => [`${Number(val).toFixed(2)} ${unit}`, label]}
              labelFormatter={(lbl) => `Time: ${lbl}s`}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke={strokeColor}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
