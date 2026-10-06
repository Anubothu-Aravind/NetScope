import React, { useEffect, useRef } from 'react';

/**
 * TcpLadder - HTML Canvas TCP Ladder / Sequence Diagram (Task 8)
 * 
 * - HTML canvas element
 * - Two vertical dashed lines: left labeled Client, right labeled Server
 * - For each packet in packets prop draw a horizontal arrow
 * - Arrow direction: left to right if src contains client IP, right to left if src contains server IP
 * - Colors: SYN = green, SYN-ACK = blue, ACK = gray, retransmission = red, data = white
 * - Label each arrow with flags and length
 * - Redraw entire canvas every time packets prop changes using useEffect
 */
export default function TcpLadder({ packets = [] }) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const render = () => {
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const dpr = window.devicePixelRatio || 1;
      const width = canvas.parentElement?.clientWidth || 550;
      const rowHeight = 32;
      const headerHeight = 45;
      const height = Math.max(headerHeight + packets.length * rowHeight + 30, 320);

      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;

      ctx.scale(dpr, dpr);

      // Dark canvas background
      ctx.fillStyle = '#080C14';
      ctx.fillRect(0, 0, width, height);

      const clientX = width * 0.22;
      const serverX = width * 0.78;

      // Draw two vertical dashed lines
      ctx.strokeStyle = '#334155';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([5, 5]);

      // Left dashed line: Client
      ctx.beginPath();
      ctx.moveTo(clientX, headerHeight);
      ctx.lineTo(clientX, height - 15);
      ctx.stroke();

      // Right dashed line: Server
      ctx.beginPath();
      ctx.moveTo(serverX, headerHeight);
      ctx.lineTo(serverX, height - 15);
      ctx.stroke();
      ctx.setLineDash([]); // Reset dash for arrows

      // Labels at top of dashed lines
      ctx.font = 'bold 12px Inter, system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      // Left: Client label
      ctx.fillStyle = '#1E293B';
      ctx.beginPath();
      ctx.roundRect(clientX - 45, 10, 90, 26, 6);
      ctx.fill();
      ctx.strokeStyle = '#38BDF8';
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.fillStyle = '#38BDF8';
      ctx.fillText('Client', clientX, 23);

      // Right: Server label
      ctx.fillStyle = '#1E293B';
      ctx.beginPath();
      ctx.roundRect(serverX - 45, 10, 90, 26, 6);
      ctx.fill();
      ctx.strokeStyle = '#34D399';
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.fillStyle = '#34D399';
      ctx.fillText('Server', serverX, 23);

      if (packets.length === 0) {
        ctx.fillStyle = '#64748B';
        ctx.font = 'italic 12px Inter, sans-serif';
        ctx.fillText('Awaiting TCP packets...', width / 2, headerHeight + 50);
        return;
      }

      // Draw packets
      packets.forEach((pkt, index) => {
        const y = headerHeight + index * rowHeight + 18;

        const srcStr = String(pkt.src || '').toLowerCase();
        const isClientToServer =
          srcStr.includes('client') ||
          srcStr.includes('10.10.0.1') ||
          pkt.direction === 'c2s' ||
          pkt.dst_port === 5000;

        const startX = isClientToServer ? clientX : serverX;
        const endX = isClientToServer ? serverX : clientX;

        const flags = String(pkt.flags || '').toUpperCase();
        const isRetrans = pkt.is_retrans || flags.includes('RETRANS');

        let color = '#F9FAFB'; // default data = white
        if (isRetrans) {
          color = '#EF4444'; // red
        } else if (flags.includes('SYN') && flags.includes('ACK')) {
          color = '#3B82F6'; // blue
        } else if (flags.includes('SYN')) {
          color = '#10B981'; // green
        } else if (flags.includes('ACK') && (pkt.len === 0 || (!flags.includes('DATA') && !flags.includes('PSH')))) {
          color = '#9CA3AF'; // gray
        } else {
          color = '#F9FAFB'; // white
        }

        // Draw horizontal arrow line
        ctx.strokeStyle = color;
        ctx.lineWidth = isRetrans ? 2.2 : 1.5;

        ctx.beginPath();
        ctx.moveTo(startX, y);
        ctx.lineTo(endX, y);
        ctx.stroke();

        // Draw arrowhead at endX
        const arrowSize = 5;
        const dir = isClientToServer ? 1 : -1;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(endX, y);
        ctx.lineTo(endX - dir * arrowSize * 1.6, y - arrowSize);
        ctx.lineTo(endX - dir * arrowSize * 1.6, y + arrowSize);
        ctx.closePath();
        ctx.fill();

        // Label each arrow with flags and length
        const lengthLabel = pkt.len !== undefined ? `${pkt.len}B` : '';
        const flagLabel = isRetrans ? `${flags || 'DATA'} [RETRANS]` : (flags || 'DATA');
        const labelText = `${flagLabel} ${lengthLabel}`.trim();

        ctx.font = '10px monospace';
        ctx.textAlign = 'center';
        ctx.fillStyle = color;
        ctx.fillText(labelText, (clientX + serverX) / 2, y - 5);
      });

      // Auto-scroll container as new packets arrive
      if (containerRef.current) {
        containerRef.current.scrollTop = containerRef.current.scrollHeight;
      }
    };

    render();

    let ro;
    if (typeof ResizeObserver !== 'undefined' && canvas.parentElement) {
      ro = new ResizeObserver(() => {
        render();
      });
      ro.observe(canvas.parentElement);
    }

    return () => {
      if (ro) ro.disconnect();
    };
  }, [packets]);

  return (
    <div
      ref={containerRef}
      className="w-full h-full max-h-[460px] overflow-y-auto rounded-xl border border-slate-800 bg-[#080C14] shadow-inner"
    >
      <canvas ref={canvasRef} className="block w-full" />
    </div>
  );
}
