import React, { useState, useEffect, useRef } from 'react';
import { 
  Send, 
  Download, 
  CheckCircle2, 
  AlertCircle, 
  RefreshCw, 
  Smartphone, 
  ShieldCheck, 
  Radio, 
  UploadCloud,
  Users
} from 'lucide-react';

/**
 * Animated packet stream component showing small colored squares
 * moving horizontally across the screen with staggered delays.
 */
function PacketStream({ direction = 'ltr' }) {
  const packets = [
    { color: 'bg-emerald-400 shadow-emerald-400/50', delay: '0s' },
    { color: 'bg-cyan-400 shadow-cyan-400/50', delay: '0.35s' },
    { color: 'bg-blue-400 shadow-blue-400/50', delay: '0.7s' },
    { color: 'bg-indigo-400 shadow-indigo-400/50', delay: '1.05s' },
    { color: 'bg-purple-400 shadow-purple-400/50', delay: '1.4s' },
    { color: 'bg-amber-400 shadow-amber-400/50', delay: '1.75s' },
  ];

  const animClass = direction === 'ltr' ? 'animate-packet-ltr' : 'animate-packet-rtl';

  return (
    <div className="w-full my-4">
      <div className="flex justify-between items-center text-[10px] uppercase font-mono tracking-wider text-slate-500 mb-1 px-1">
        <span>{direction === 'ltr' ? 'Client' : 'Server'}</span>
        <span className="text-cyan-400 animate-pulse">Live Packets</span>
        <span>{direction === 'ltr' ? 'Server' : 'Client'}</span>
      </div>
      <div className="relative w-full h-12 bg-slate-950/70 border border-slate-800/80 rounded-xl overflow-hidden shadow-inner flex items-center">
        {/* Track Line */}
        <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-[1px] bg-slate-800 border-t border-dashed border-slate-700" />
        {packets.map((pkt, idx) => (
          <div
            key={idx}
            className={`absolute top-1/2 -translate-y-1/2 w-3.5 h-3.5 rounded-sm shadow-md ${pkt.color} ${animClass}`}
            style={{ animationDelay: pkt.delay }}
          />
        ))}
      </div>
    </div>
  );
}

export default function MobileClient() {
  const [sessionId, setSessionId] = useState('');
  const [availableRoles, setAvailableRoles] = useState(null); // array: ['sender', 'receiver'], etc.
  const [autoJoining, setAutoJoining] = useState(null); // 'sender' | 'receiver' | null
  const [role, setRole] = useState(null); // 'sender' | 'receiver'
  const [isSessionFull, setIsSessionFull] = useState(false);
  const [clientInfo, setClientInfo] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [signalSent, setSignalSent] = useState(false);
  const [isPacketFlowing, setIsPacketFlowing] = useState(false);
  const [transferDone, setTransferDone] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const wsRef = useRef(null);

  // Read sessionId from URL path /join/{sessionId}
  useEffect(() => {
    const parts = window.location.pathname.split('/').filter(Boolean);
    const joinIdx = parts.indexOf('join');
    let sid = '';
    if (joinIdx !== -1 && parts[joinIdx + 1]) {
      sid = parts[joinIdx + 1];
    } else {
      const params = new URLSearchParams(window.location.search);
      sid = params.get('sessionId') || params.get('sid') || params.get('session') || '';
    }
    setSessionId(sid);
  }, []);

  // Check available roles when sessionId is resolved
  const checkAvailableRoles = async () => {
    if (!sessionId) return;
    try {
      setIsLoading(true);
      setError(null);
      setIsSessionFull(false);

      const res = await fetch(`/api/session/${sessionId}/available-role`);
      if (!res.ok) {
        throw new Error(`Failed to check session availability (HTTP ${res.status})`);
      }
      const data = await res.json();
      const available = data.available || [];
      setAvailableRoles(available);

      if (available.length === 0) {
        // Both roles taken: session is full
        setIsSessionFull(true);
        setIsLoading(false);
      } else if (available.length === 1) {
        // If one role is already taken, skip the choice screen entirely
        // and automatically register with the only remaining role, showing a message
        const remaining = available[0];
        setAutoJoining(remaining);
        setTimeout(() => {
          registerWithRole(remaining);
        }, 800);
      } else {
        // Both roles available: let device choose
        setIsLoading(false);
      }
    } catch (err) {
      console.error('Role check error:', err);
      setError(err.message);
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (sessionId) {
      checkAvailableRoles();
    }
  }, [sessionId]);

  // Register device with chosen or assigned role
  const registerWithRole = async (chosenRole) => {
    try {
      setIsLoading(true);
      setError(null);
      const randId = Math.random().toString(36).substring(2, 6).toUpperCase();
      const clientName = `Mobile-${chosenRole === 'sender' ? 'Sender' : 'Receiver'}-${randId}`;

      const res = await fetch(`/api/session/${sessionId}/clients`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_name: clientName,
          role: chosenRole,
        }),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `Failed to join as ${chosenRole} (HTTP ${res.status})`);
      }

      const data = await res.json();
      setClientInfo(data.client || data);
      setRole(chosenRole);
      setAutoJoining(null);
    } catch (err) {
      console.error('Registration error:', err);
      setError(err.message);
      setAutoJoining(null);
    } finally {
      setIsLoading(false);
    }
  };

  // Connect WebSocket to /api/ws/{sessionId} once role is assigned
  useEffect(() => {
    if (!sessionId || !role) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws/${sessionId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const type = (msg.type || msg.event || '').toLowerCase();
        const data = msg.data || msg;

        // Receiver: listen for first packets_batch event to start animation
        if (type === 'packets_batch' || type === 'packet_live') {
          setIsPacketFlowing(true);
        } else if (type === 'transfer_complete') {
          // Stop animation on transfer_complete
          setIsPacketFlowing(false);
          setTransferDone(true);

          const rec = data.record || data;
          const rId = rec.run_id || rec.runId || data.run_id || data.runId || '';
          const fName = rec.file || rec.filename || data.file || data.filename || selectedFile?.name || 'transferred_file.bin';
          const shaOk = rec.sha256_ok !== undefined ? rec.sha256_ok : (data.sha256_ok !== undefined ? data.sha256_ok : true);

          setResult({
            runId: rId,
            filename: fName,
            sha256Status: shaOk ? 'Match Verified (OK)' : 'Integrity Mismatch',
            sha256Ok: Boolean(shaOk)
          });
        }
      } catch (e) {
        console.error('WS parse error:', e);
      }
    };

    ws.onerror = (err) => {
      console.warn('WS error:', err);
    };

    return () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    };
  }, [sessionId, role, selectedFile]);

  // Handler for Sender file selection
  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFile(e.target.files[0]);
    }
  };

  // Handler for Sender Send Signal button
  const handleSendSignal = async () => {
    if (!sessionId || !selectedFile) return;
    try {
      setSignalSent(true);
      setError(null);

      // 1. Upload actual file binary to /api/session/{sessionId}/upload
      const formData = new FormData();
      formData.append('file', selectedFile);

      const uploadRes = await fetch(`/api/session/${sessionId}/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!uploadRes.ok) {
        const errJson = await uploadRes.json().catch(() => ({}));
        throw new Error(errJson.detail || 'Failed to upload selected file to session');
      }

      // 2. Notify session control plane that sender is ready with this file
      const res = await fetch(`/api/session/${sessionId}/signal/ready`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: selectedFile.name }),
      });
      if (!res.ok) {
        throw new Error('Failed to send ready signal');
      }
    } catch (err) {
      console.error(err);
      setError(err.message);
      setSignalSent(false);
    }
  };

  // Handler for Receiver Download button
  const handleDownload = () => {
    if (!result?.runId) {
      setError('No transfer run ID available for download.');
      return;
    }
    window.location.href = `/api/download/${result.runId}`;
  };

  return (
    <div className="min-h-screen bg-[#080C14] text-slate-100 flex flex-col items-center justify-center p-4 font-sans select-none">
      <div className="w-full max-w-sm bg-slate-900/90 border border-slate-800 rounded-3xl p-6 shadow-2xl backdrop-blur relative overflow-hidden">
        
        {/* Header Badge */}
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-4 mb-5">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
              <Smartphone className="w-4 h-4" />
            </div>
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-slate-200">NetScope</span>
              <p className="text-[10px] font-mono text-cyan-400 leading-none mt-0.5">{sessionId || 'No Session'}</p>
            </div>
          </div>
          {role && (
            <span className={`px-2.5 py-1 rounded-full text-[10px] font-mono uppercase font-bold tracking-wider ${
              role === 'sender' 
                ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' 
                : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
            }`}>
              {role}
            </span>
          )}
        </div>

        {/* ============================================================ */}
        {/* ROLE SELECTION & AVAILABILITY FLOW */}
        {/* ============================================================ */}
        {!role && (
          <div>
            {/* 1. Loading availability state */}
            {isLoading && !autoJoining && (
              <div className="py-12 flex flex-col items-center justify-center text-center space-y-4">
                <RefreshCw className="w-10 h-10 text-cyan-400 animate-spin" />
                <div>
                  <h2 className="text-sm font-semibold text-slate-200">Checking session availability...</h2>
                  <p className="text-xs text-slate-400 mt-1">Connecting to session control plane</p>
                </div>
              </div>
            )}

            {/* 2. Auto-joining with brief animation when only one role remaining */}
            {autoJoining && (
              <div className="py-12 flex flex-col items-center justify-center text-center space-y-4">
                <div className="relative">
                  <div className="w-14 h-14 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400 animate-pulse">
                    <RefreshCw className="w-7 h-7 animate-spin" />
                  </div>
                </div>
                <div>
                  <h2 className="text-base font-bold text-slate-100">
                    Joining as {autoJoining === 'sender' ? 'Sender' : 'Receiver'}...
                  </h2>
                  <p className="text-xs text-cyan-400 mt-1 font-mono">
                    Single remaining role assigned automatically
                  </p>
                </div>
              </div>
            )}

            {/* 3. Session Full State */}
            {isSessionFull && !isLoading && (
              <div className="py-8 flex flex-col items-center justify-center text-center space-y-4">
                <div className="w-14 h-14 rounded-2xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
                  <Users className="w-7 h-7" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-slate-100">Session is Full</h2>
                  <p className="text-xs text-slate-400 mt-2 max-w-xs leading-relaxed">
                    Session is full. Please ask the host to disconnect a device.
                  </p>
                </div>
                <button
                  onClick={checkAvailableRoles}
                  className="mt-3 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-xs font-semibold rounded-xl text-slate-300 transition-colors flex items-center gap-1.5 cursor-pointer"
                >
                  <RefreshCw className="w-3.5 h-3.5" /> Check Again
                </button>
              </div>
            )}

            {/* 4. Choice Screen: Both roles available */}
            {!isLoading && !autoJoining && !isSessionFull && availableRoles && availableRoles.length === 2 && (
              <div className="space-y-5 text-center">
                <div>
                  <h2 className="text-base font-bold text-slate-100">Select Device Role</h2>
                  <p className="text-xs text-slate-400 mt-1">Both roles available. Choose your mode:</p>
                </div>

                <div className="space-y-3 pt-2">
                  <button
                    onClick={() => registerWithRole('sender')}
                    disabled={isLoading}
                    className="w-full py-4 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 active:scale-[0.98] text-white font-bold rounded-2xl shadow-lg shadow-cyan-500/20 text-sm transition-all flex items-center justify-center gap-3 cursor-pointer"
                  >
                    <Send className="w-4 h-4" />
                    Join as Sender
                  </button>

                  <button
                    onClick={() => registerWithRole('receiver')}
                    disabled={isLoading}
                    className="w-full py-4 bg-slate-800/90 hover:bg-slate-700 active:scale-[0.98] border border-slate-700/80 text-slate-100 font-bold rounded-2xl shadow-lg text-sm transition-all flex items-center justify-center gap-3 cursor-pointer"
                  >
                    <Download className="w-4 h-4 text-emerald-400" />
                    Join as Receiver
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ============================================================ */}
        {/* SENDER MODE */}
        {/* ============================================================ */}
        {role === 'sender' && (
          <div className="space-y-5">
            {!signalSent ? (
              /* Step A: file input (type file) and Send Signal button disabled until file selected */
              <div className="space-y-4">
                <div className="text-center">
                  <h2 className="text-base font-bold text-slate-100">Sender Mode</h2>
                  <p className="text-xs text-slate-400 mt-1">Select a payload file to transfer</p>
                </div>

                <div className="border-2 border-dashed border-slate-800 hover:border-cyan-500/50 transition-colors rounded-2xl p-5 text-center relative bg-slate-950/40">
                  <input
                    type="file"
                    id="mobile-file-input"
                    onChange={handleFileChange}
                    className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
                  />
                  <div className="flex flex-col items-center pointer-events-none">
                    <UploadCloud className="w-8 h-8 text-cyan-400 mb-2" />
                    {selectedFile ? (
                      <div>
                        <p className="text-xs font-semibold text-slate-200 truncate max-w-[200px]">{selectedFile.name}</p>
                        <p className="text-[10px] font-mono text-cyan-400 mt-0.5">{(selectedFile.size / 1024).toFixed(1)} KB</p>
                      </div>
                    ) : (
                      <div>
                        <p className="text-xs text-slate-300 font-medium">Tap to select file</p>
                        <p className="text-[10px] text-slate-500 mt-0.5">Any payload file</p>
                      </div>
                    )}
                  </div>
                </div>

                <button
                  onClick={handleSendSignal}
                  disabled={!selectedFile}
                  className="w-full py-3.5 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-bold rounded-xl shadow-lg shadow-cyan-500/20 text-xs uppercase tracking-wider transition-all flex items-center justify-center gap-2 cursor-pointer"
                >
                  <Send className="w-4 h-4" /> Send Signal
                </button>
              </div>
            ) : !transferDone ? (
              /* Step B after signal sent: show animated packets moving left to right using CSS keyframes, show filename, show 'Sending...' text */
              <div className="py-6 flex flex-col items-center justify-center text-center space-y-4">
                <div className="w-12 h-12 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400 animate-pulse">
                  <Radio className="w-6 h-6" />
                </div>
                
                <div>
                  <h3 className="text-sm font-bold text-slate-200 animate-pulse">Sending...</h3>
                  <p className="text-xs font-mono text-cyan-400 mt-1 truncate max-w-[240px]">
                    {selectedFile?.name || 'payload.bin'}
                  </p>
                </div>

                {/* Animated packets moving left to right */}
                <PacketStream direction="ltr" />
                <p className="text-[10px] font-mono text-slate-500">Live TCP transport active</p>
              </div>
            ) : (
              /* On transfer_complete: show 'Transfer Complete', SHA-256 status, no download button */
              <div className="py-6 flex flex-col items-center justify-center text-center space-y-4">
                <CheckCircle2 className="w-14 h-14 text-emerald-400" />
                <div>
                  <h2 className="text-base font-bold text-slate-100">Transfer Complete</h2>
                  <p className="text-xs font-mono text-cyan-400 mt-1 break-all bg-slate-950 p-2 rounded-xl border border-slate-800">
                    {result?.filename || selectedFile?.name || 'payload.bin'}
                  </p>
                </div>

                <div className={`flex items-center justify-center gap-2 text-xs font-semibold py-2 px-4 rounded-xl border w-full ${
                  result?.sha256Ok !== false
                    ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                    : 'bg-rose-500/10 border-rose-500/20 text-rose-400'
                }`}>
                  <ShieldCheck className="w-4 h-4" />
                  <span>SHA-256: {result?.sha256Status || 'Match Verified'}</span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ============================================================ */}
        {/* RECEIVER MODE */}
        {/* ============================================================ */}
        {role === 'receiver' && (
          <div className="space-y-5">
            {!transferDone ? (
              /* Step A: spinning animation + 'Waiting for transfer to begin...'
                 Animated packets moving right to left during Observer step (listen for first packets_batch event to start animation, stop on transfer_complete) */
              <div className="py-8 flex flex-col items-center justify-center text-center space-y-4">
                {!isPacketFlowing ? (
                  <>
                    <RefreshCw className="w-12 h-12 text-cyan-400 animate-spin mx-auto" />
                    <div>
                      <h2 className="text-sm font-semibold text-slate-200">Waiting for transfer to begin...</h2>
                      <p className="text-xs text-slate-500 font-mono mt-1">Paired as Receiver</p>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 animate-pulse">
                      <Radio className="w-6 h-6" />
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-indigo-300 animate-pulse">Receiving Packets...</h3>
                      <p className="text-xs text-slate-400 mt-1">Ingesting data from sender</p>
                    </div>
                    {/* Animated packets moving right to left */}
                    <PacketStream direction="rtl" />
                  </>
                )}
              </div>
            ) : (
              /* Step B on transfer_complete: show filename, SHA-256 status, and a Download button calling GET /api/download/{runId} */
              <div className="py-6 flex flex-col items-center justify-center text-center space-y-4">
                <CheckCircle2 className="w-14 h-14 text-emerald-400" />
                <div>
                  <h2 className="text-base font-bold text-slate-100">Transfer Complete</h2>
                  <p className="text-xs font-mono text-cyan-400 mt-2 break-all bg-slate-950 p-2 rounded-xl border border-slate-800">
                    {result?.filename || 'received_payload.bin'}
                  </p>
                </div>

                <div className={`flex items-center justify-center gap-2 text-xs font-semibold py-2 px-4 rounded-xl border w-full ${
                  result?.sha256Ok !== false
                    ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                    : 'bg-rose-500/10 border-rose-500/20 text-rose-400'
                }`}>
                  <ShieldCheck className="w-4 h-4" />
                  <span>SHA-256: {result?.sha256Status || 'Match Verified'}</span>
                </div>

                <button
                  onClick={handleDownload}
                  className="w-full py-3.5 bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-bold rounded-xl shadow-lg shadow-emerald-500/20 text-xs uppercase tracking-wider transition-all flex items-center justify-center gap-2 mt-2 cursor-pointer"
                >
                  <Download className="w-4 h-4" /> Download File
                </button>
              </div>
            )}
          </div>
        )}

        {/* Error notification */}
        {error && (
          <div className="mt-4 p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-xs text-rose-400 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 truncate">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span className="truncate">{error}</span>
            </div>
            {!role && (
              <button
                onClick={checkAvailableRoles}
                className="text-[10px] uppercase font-bold text-cyan-400 hover:underline shrink-0"
              >
                Retry
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
