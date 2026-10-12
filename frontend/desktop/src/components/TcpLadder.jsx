import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Play, Pause, RotateCcw, SkipForward, SkipBack } from 'lucide-react';

/**
 * TcpLadder - Interactive HTML Canvas TCP Ladder and Sequence Diagram
 * 
 * Supports:
 * - Live real-time packet rendering as packets stream in.
 * - Timeline-based replay with slow-motion speeds (0.25x, 0.5x, 1x, 2x).
 * - Play, Pause, Step Forward, Step Backward, and Scrubber controls.
 * - Distinct styling for:
 *     * Original transmissions vs Retransmissions (amber-orange retry wave)
 *     * Dropped packets (dashed line terminating at mid-way drop marker with 'X')
 *     * RTO Timeout events (amber timer badge in sender lane)
 *     * 3-Way Handshake (SYN, SYN-ACK, ACK) and Teardown (FIN, ACK)
 * - Traveling packet animations between Client and Server lanes.
 * - Synchronized event description banner explaining the TCP mechanism.
 */
export default function TcpLadder({ packets = [], isLive = false }) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const animFrameRef = useRef(null);
  const lastTimeRef = useRef(null);

  // Playback state
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackIndex, setPlaybackIndex] = useState(packets.length > 0 ? packets.length - 1 : 0);
  const [speed, setSpeed] = useState(1); // 0.25, 0.5, 1, 2
  const [packetProgress, setPacketProgress] = useState(1.0); // 0.0 -> 1.0 across current line

  // Track total packets length changes (e.g. live stream or new simulation)
  const prevLenRef = useRef(packets.length);
  useEffect(() => {
    if (packets.length === 0) {
      setPlaybackIndex(0);
      setPacketProgress(1.0);
      setIsPlaying(false);
    } else if (packets.length !== prevLenRef.current) {
      if (!isPlaying) {
        // Auto-follow latest packet when streaming or when new batch arrives
        setPlaybackIndex(packets.length - 1);
        setPacketProgress(1.0);
      }
    }
    prevLenRef.current = packets.length;
  }, [packets.length, isPlaying]);

  // Current active packet for inspection
  const activePacket = useMemo(() => {
    if (!packets || packets.length === 0) return null;
    const idx = Math.min(Math.max(playbackIndex, 0), packets.length - 1);
    return packets[idx];
  }, [packets, playbackIndex]);

  // Generate explanatory text for current packet/event
  const eventExplanation = useMemo(() => {
    if (!activePacket) return 'Awaiting TCP packets...';
    const flags = String(activePacket.flags || '').toUpperCase();
    const isRetrans = Boolean(activePacket.is_retrans || flags.includes('RETRANS'));
    const isDropped = Boolean(activePacket.is_dropped || flags.includes('DROPPED'));
    const isTimeout = Boolean(activePacket.is_timeout || flags.includes('TIMEOUT'));
    const isDupAck = Boolean(activePacket.is_dup_ack || flags.includes('DUP ACK'));
    const retryNum = activePacket.retry || 1;

    if (isTimeout) {
      return `RTO Timeout expired (${activePacket.rto_ms || 200}ms). Sender detects unacknowledged segment and triggers Retransmission #${retryNum}.`;
    }
    if (isDropped) {
      return `Data segment dropped in transit due to network loss impairment (Seq=${activePacket.seq}, Len=${activePacket.len}B).`;
    }
    if (isRetrans) {
      return `Retransmission #${retryNum}: Sender retransmits segment (Seq=${activePacket.seq}, Len=${activePacket.len}B) after timeout.`;
    }
    if (isDupAck) {
      return `Duplicate ACK: Receiver signals missing segment at Ack=${activePacket.ack}.`;
    }
    if (flags.includes('SYN') && flags.includes('ACK')) {
      return `Connection Handshake: Server responds with SYN-ACK (Seq=${activePacket.seq}, Ack=${activePacket.ack}).`;
    }
    if (flags.includes('SYN')) {
      return `Connection Handshake: Client initiates connection with SYN (Seq=${activePacket.seq}).`;
    }
    if (flags.includes('FIN')) {
      return `Connection Teardown: Sender initiates graceful closure with FIN (Seq=${activePacket.seq}).`;
    }
    if (flags.includes('ACK') && activePacket.len === 0) {
      return `Acknowledgment: Receiver confirms delivery up to byte ${activePacket.ack}. Pending timers cancelled.`;
    }
    return `Data Transmission: Transmitting ${activePacket.len || 65536} bytes (Seq=${activePacket.seq}).`;
  }, [activePacket]);

  // Step controls
  const handlePlayPause = useCallback(() => {
    if (packets.length === 0) return;
    if (isPlaying) {
      setIsPlaying(false);
    } else {
      if (playbackIndex >= packets.length - 1) {
        // Replay from beginning if already at end
        setPlaybackIndex(0);
        setPacketProgress(0.0);
      }
      setIsPlaying(true);
    }
  }, [isPlaying, playbackIndex, packets.length]);

  const handleReplay = useCallback(() => {
    if (packets.length === 0) return;
    setPlaybackIndex(0);
    setPacketProgress(0.0);
    setIsPlaying(true);
  }, [packets.length]);

  const handleStepForward = useCallback(() => {
    if (packets.length === 0) return;
    setIsPlaying(false);
    setPlaybackIndex((prev) => Math.min(prev + 1, packets.length - 1));
    setPacketProgress(1.0);
  }, [packets.length]);

  const handleStepBack = useCallback(() => {
    if (packets.length === 0) return;
    setIsPlaying(false);
    setPlaybackIndex((prev) => Math.max(prev - 1, 0));
    setPacketProgress(1.0);
  }, [packets.length]);

  const handleScrub = useCallback((e) => {
    const val = parseInt(e.target.value, 10);
    setIsPlaying(false);
    setPlaybackIndex(val);
    setPacketProgress(1.0);
  }, []);

  // Animation Loop for Playback
  useEffect(() => {
    if (!isPlaying) {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      lastTimeRef.current = null;
      return;
    }

    // Base duration per packet in seconds at 1x speed: ~0.45s (450ms)
    // At 0.25x (slow-mo): 1.80s, at 0.5x: 0.90s, at 2x: 0.22s
    const baseDuration = 0.45 / speed;

    const animate = (timestamp) => {
      if (!lastTimeRef.current) lastTimeRef.current = timestamp;
      const dt = (timestamp - lastTimeRef.current) / 1000.0;
      lastTimeRef.current = timestamp;

      setPacketProgress((prevProgress) => {
        const nextProgress = prevProgress + dt / baseDuration;
        if (nextProgress >= 1.0) {
          // Move to next packet
          setPlaybackIndex((prevIdx) => {
            if (prevIdx >= packets.length - 1) {
              setIsPlaying(false);
              return packets.length - 1;
            }
            return prevIdx + 1;
          });
          return 0.0;
        }
        return nextProgress;
      });

      animFrameRef.current = requestAnimationFrame(animate);
    };

    animFrameRef.current = requestAnimationFrame(animate);

    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [isPlaying, speed, packets.length]);

  // Canvas Rendering
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const width = canvas.parentElement?.clientWidth || 550;
    const rowHeight = 36;
    const headerHeight = 52;
    const totalToRender = packets.length > 0 ? playbackIndex + 1 : 0;
    const height = Math.max(headerHeight + totalToRender * rowHeight + 40, 340);

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    ctx.scale(dpr, dpr);

    // Deep slate background
    ctx.fillStyle = '#080C14';
    ctx.fillRect(0, 0, width, height);

    const clientX = width * 0.22;
    const serverX = width * 0.78;

    // Draw vertical dashed lines for Client and Server
    ctx.strokeStyle = '#1E293B';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 4]);

    ctx.beginPath();
    ctx.moveTo(clientX, headerHeight);
    ctx.lineTo(clientX, height - 15);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(serverX, headerHeight);
    ctx.lineTo(serverX, height - 15);
    ctx.stroke();
    ctx.setLineDash([]); // Reset dash for arrows

    // Client and Server Header Badges
    ctx.font = 'bold 12px Inter, system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    // Client Badge
    ctx.fillStyle = '#0F172A';
    ctx.beginPath();
    ctx.roundRect(clientX - 45, 12, 90, 28, 6);
    ctx.fill();
    ctx.strokeStyle = '#38BDF8';
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.fillStyle = '#38BDF8';
    ctx.fillText('Client', clientX, 26);

    // Server Badge
    ctx.fillStyle = '#0F172A';
    ctx.beginPath();
    ctx.roundRect(serverX - 45, 12, 90, 28, 6);
    ctx.fill();
    ctx.strokeStyle = '#34D399';
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.fillStyle = '#34D399';
    ctx.fillText('Server', serverX, 26);

    if (packets.length === 0) {
      ctx.fillStyle = '#64748B';
      ctx.font = 'italic 12px Inter, sans-serif';
      ctx.fillText('Awaiting TCP packets...', width / 2, headerHeight + 60);
      return;
    }

    // Render packets up to playbackIndex
    for (let index = 0; index <= playbackIndex; index++) {
      const pkt = packets[index];
      if (!pkt) continue;

      const y = headerHeight + index * rowHeight + 20;
      const flags = String(pkt.flags || '').toUpperCase();
      const isRetrans = Boolean(pkt.is_retrans || flags.includes('RETRANS'));
      const isDropped = Boolean(pkt.is_dropped || flags.includes('DROPPED'));
      const isTimeout = Boolean(pkt.is_timeout || flags.includes('TIMEOUT'));
      const isDupAck = Boolean(pkt.is_dup_ack || flags.includes('DUP ACK'));
      const isCurrent = index === playbackIndex;

      // Handle Direction
      const srcStr = String(pkt.src || '').toLowerCase();
      const isClientToServer =
        pkt.direction === 'c2s' ||
        srcStr.includes('client') ||
        srcStr.includes('10.10.0.1') ||
        pkt.dst_port === 5000 ||
        pkt.dst_port === 5001 ||
        pkt.dst_port === 5002;

      const startX = isClientToServer ? clientX : serverX;
      const endX = isClientToServer ? serverX : clientX;

      // Current animated travel position
      const travelFrac = isCurrent ? Math.min(Math.max(packetProgress, 0.0), 1.0) : 1.0;

      // 1. TIMEOUT EVENT BADGE (Rendered at Sender lane)
      if (isTimeout) {
        const timeoutX = startX;
        ctx.fillStyle = '#451A03';
        ctx.strokeStyle = '#F59E0B';
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.roundRect(timeoutX - 110, y - 11, 220, 22, 6);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = '#FBBF24';
        ctx.font = 'bold 10px monospace';
        ctx.textAlign = 'center';
        ctx.fillText(`RTO Timeout (${pkt.rto_ms || 200}ms) | Retry #${pkt.retry || 1}`, timeoutX, y);
        continue;
      }

      // 2. DROPPED PACKET (Stops halfway at ~52% with a red 'X')
      if (isDropped) {
        const dropRatio = 0.52;
        const dropX = startX + (endX - startX) * dropRatio;
        const currentLineEndX = isCurrent ? startX + (dropX - startX) * travelFrac : dropX;

        // Dashed Red Line to drop point
        ctx.strokeStyle = '#EF4444';
        ctx.lineWidth = 2.0;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(startX, y);
        ctx.lineTo(currentLineEndX, y);
        ctx.stroke();
        ctx.setLineDash([]);

        // Drop 'X' symbol and badge
        if (!isCurrent || travelFrac >= 0.95) {
          ctx.fillStyle = '#7F1D1D';
          ctx.beginPath();
          ctx.arc(dropX, y, 9, 0, 2 * Math.PI);
          ctx.fill();
          ctx.strokeStyle = '#EF4444';
          ctx.lineWidth = 1.5;
          ctx.stroke();

          ctx.fillStyle = '#FFFFFF';
          ctx.font = 'bold 11px sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText('X', dropX, y + 1);

          // Dropped Label
          ctx.font = '10px monospace';
          ctx.fillStyle = '#F87171';
          ctx.fillText(`[DROPPED] Seq=${pkt.seq || 'data'}`, (startX + dropX) / 2, y - 6);
        }

        // Animated traveling marker
        if (isCurrent && travelFrac < 0.95) {
          ctx.fillStyle = '#F87171';
          ctx.beginPath();
          ctx.arc(currentLineEndX, y, 4, 0, 2 * Math.PI);
          ctx.fill();
        }
        continue;
      }

      // 3. RETRANSMISSION (Bold Amber-Orange with retry pulse)
      // 4. NORMAL SEGMENT, ACK, SYN, SYN-ACK, FIN
      let color = '#F8FAFC'; // Default data = white
      if (isRetrans) {
        color = '#F97316'; // Orange / Amber for Retransmissions
      } else if (isDupAck) {
        color = '#C084FC'; // Purple for Duplicate ACKs
      } else if (flags.includes('SYN') && flags.includes('ACK')) {
        color = '#38BDF8'; // Sky Blue
      } else if (flags.includes('SYN')) {
        color = '#34D399'; // Emerald Green
      } else if (flags.includes('FIN')) {
        color = '#F43F5E'; // Rose Pink
      } else if (flags.includes('ACK') && (pkt.len === 0 || (!flags.includes('DATA') && !flags.includes('PSH')))) {
        color = '#94A3B8'; // Slate Gray for ACKs
      }

      const currentEndX = isCurrent ? startX + (endX - startX) * travelFrac : endX;

      // Draw horizontal line
      ctx.strokeStyle = color;
      ctx.lineWidth = isRetrans ? 2.4 : 1.6;

      if (isRetrans) {
        // Subtle dash pattern for retry line
        ctx.setLineDash([8, 3]);
      } else {
        ctx.setLineDash([]);
      }

      ctx.beginPath();
      ctx.moveTo(startX, y);
      ctx.lineTo(currentEndX, y);
      ctx.stroke();
      ctx.setLineDash([]);

      // Draw Arrowhead at destination
      if (!isCurrent || travelFrac >= 0.98) {
        const arrowSize = isRetrans ? 6 : 5;
        const dir = isClientToServer ? 1 : -1;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(endX, y);
        ctx.lineTo(endX - dir * arrowSize * 1.6, y - arrowSize);
        ctx.lineTo(endX - dir * arrowSize * 1.6, y + arrowSize);
        ctx.closePath();
        ctx.fill();
      }

      // Animated traveling glowing packet dot
      if (isCurrent && isPlaying) {
        ctx.fillStyle = isRetrans ? '#FB923C' : '#38BDF8';
        ctx.beginPath();
        ctx.arc(currentEndX, y, isRetrans ? 5 : 4, 0, 2 * Math.PI);
        ctx.fill();
      }

      // Segment Label
      let labelText = '';
      if (isRetrans) {
        labelText = `[RETRANS #${pkt.retry || 1}] Seq=${pkt.seq} (${pkt.len || 65536}B)`;
      } else if (isDupAck) {
        labelText = `[DUP ACK] Ack=${pkt.ack}`;
      } else if (flags.includes('SYN') && flags.includes('ACK')) {
        labelText = `SYN-ACK Seq=${pkt.seq} Ack=${pkt.ack}`;
      } else if (flags.includes('SYN')) {
        labelText = `SYN Seq=${pkt.seq}`;
      } else if (flags.includes('FIN')) {
        labelText = `FIN-ACK Seq=${pkt.seq}`;
      } else if (flags.includes('ACK') && pkt.len === 0) {
        labelText = `ACK Ack=${pkt.ack}`;
      } else {
        labelText = `DATA Seq=${pkt.seq} (${pkt.len ? `${pkt.len}B` : '64KB'})`;
      }

      ctx.font = isRetrans ? 'bold 10px monospace' : '10px monospace';
      ctx.textAlign = 'center';
      ctx.fillStyle = color;
      ctx.fillText(labelText, (clientX + serverX) / 2, y - 5);
    }

    // Auto-scroll container to keep active line in view
    if (containerRef.current) {
      const activeY = headerHeight + playbackIndex * rowHeight;
      const targetScroll = activeY - containerRef.current.clientHeight / 2;
      containerRef.current.scrollTop = Math.max(targetScroll, 0);
    }
  }, [packets, playbackIndex, packetProgress, isPlaying]);

  return (
    <div className="flex flex-col h-full bg-[#080C14] rounded-xl border border-slate-800 overflow-hidden shadow-xl">
      {/* Playback Control Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 bg-slate-900/90 border-b border-slate-800 text-xs">
        {/* Playback Buttons */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={handleReplay}
            title="Replay from start"
            className="p-1.5 text-slate-400 hover:text-cyan-400 hover:bg-slate-800 rounded transition-colors"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
          <button
            onClick={handleStepBack}
            title="Step backward"
            disabled={playbackIndex <= 0}
            className="p-1.5 text-slate-400 hover:text-cyan-400 hover:bg-slate-800 disabled:opacity-40 rounded transition-colors"
          >
            <SkipBack className="w-4 h-4" />
          </button>
          <button
            onClick={handlePlayPause}
            title={isPlaying ? 'Pause' : 'Play'}
            className="flex items-center gap-1 px-3 py-1.5 bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 font-semibold rounded-lg border border-cyan-500/30 transition-all"
          >
            {isPlaying ? (
              <>
                <Pause className="w-3.5 h-3.5" /> Pause
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5" /> Play
              </>
            )}
          </button>
          <button
            onClick={handleStepForward}
            title="Step forward"
            disabled={playbackIndex >= packets.length - 1}
            className="p-1.5 text-slate-400 hover:text-cyan-400 hover:bg-slate-800 disabled:opacity-40 rounded transition-colors"
          >
            <SkipForward className="w-4 h-4" />
          </button>
        </div>

        {/* Speed Selector (0.25x, 0.5x, 1x, 2x) */}
        <div className="flex items-center gap-1 bg-slate-950 px-2 py-1 rounded-lg border border-slate-800">
          <span className="text-[10px] text-slate-500 uppercase font-semibold mr-1">Speed</span>
          {[0.25, 0.5, 1, 2].map((s) => (
            <button
              key={s}
              onClick={() => setSpeed(s)}
              className={`px-1.5 py-0.5 rounded text-[11px] font-mono transition-colors ${
                speed === s
                  ? 'bg-cyan-500 text-slate-950 font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {s}x
            </button>
          ))}
        </div>

        {/* Scrubber / Step Counter */}
        <div className="flex items-center gap-2 flex-1 max-w-[240px]">
          <input
            type="range"
            min="0"
            max={Math.max(packets.length - 1, 0)}
            value={playbackIndex}
            onChange={handleScrub}
            className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400"
          />
          <span className="text-[11px] font-mono text-slate-400 whitespace-nowrap">
            {packets.length > 0 ? playbackIndex + 1 : 0}/{packets.length}
          </span>
        </div>
      </div>

      {/* Synchronized Event Inspector Banner */}
      <div className="px-4 py-2 bg-slate-950/80 border-b border-slate-800/80 text-xs flex items-center gap-2">
        <span className="px-2 py-0.5 bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 rounded text-[10px] font-mono font-bold uppercase">
          Step {packets.length > 0 ? playbackIndex + 1 : 0}
        </span>
        <span className="text-slate-300 truncate font-mono text-[11px]">
          {eventExplanation}
        </span>
      </div>

      {/* Canvas Viewport */}
      <div
        ref={containerRef}
        className="flex-1 w-full max-h-[460px] overflow-y-auto bg-[#080C14] shadow-inner"
      >
        <canvas ref={canvasRef} className="block w-full" />
      </div>

      {/* Legend Footer */}
      <div className="px-4 py-2 bg-slate-950 border-t border-slate-800/80 flex flex-wrap items-center gap-4 text-[10px] text-slate-400">
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
          <span>SYN</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-sky-400"></span>
          <span>SYN-ACK</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-slate-400"></span>
          <span>ACK</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-slate-100"></span>
          <span>DATA</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-rose-500"></span>
          <span>DROPPED</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-amber-500"></span>
          <span>TIMEOUT</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-orange-500"></span>
          <span>RETRANS</span>
        </div>
      </div>
    </div>
  );
}
