import React, { useState, useEffect } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { RefreshCw, Trash2, Smartphone, Monitor, CheckCircle, Wifi } from 'lucide-react';

/**
 * Step 1: Pair Component (Task 4)
 * 
 * - On mount: POST /api/session to create session, then connect WebSocket to /api/ws/{sessionId}
 * - Show QR code using qrcode.react and session join URL
 * - Show connected peers table: Name, Role, Status, Disconnect button
 * - Listen to WebSocket for client_joined and client_left events
 * - Show animated waiting message based on peer count:
 *     0 peers: spinning circle + 'Waiting for devices to connect...'
 *     1 peer sender only: 'Sender connected — waiting for receiver...'
 *     1 peer receiver only: 'Receiver connected — waiting for sender...'
 *     2 peers: 'Both connected — waiting for sender signal...'
 * - Listen for sender_ready WebSocket event and call onAdvance() prop automatically
 * - No confirm button needed
 */
export default function Pair({ onAdvance, ws, session, setSession }) {
  const [peers, setPeers] = useState([]);
  const [loading, setLoading] = useState(!session);

  // Initialize session on mount if not already present
  useEffect(() => {
    let isMounted = true;
    if (session?.session_id) {
      if (session.clients) {
        setPeers(Object.values(session.clients));
      }
      return;
    }

    async function createSession() {
      try {
        setLoading(true);
        const res = await fetch('/api/session', { method: 'POST' });
        if (!res.ok) throw new Error('Failed to create session');
        const data = await res.json();
        if (isMounted) {
          setSession(data);
          if (data.clients) {
            setPeers(Object.values(data.clients));
          }
        }
      } catch (err) {
        console.error(err);
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    createSession();

    return () => {
      isMounted = false;
    };
  }, [session, setSession]);

  // Listen to WebSocket events on the passed `ws` prop
  useEffect(() => {
    if (!ws) return;

    const handleMessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const type = (msg.type || msg.event || '').toLowerCase();
        const data = msg.data || msg;

        // client_joined
        if (type === 'client_joined') {
          const client = data.client || msg.client;
          if (client) {
            setPeers((prev) => {
              const filtered = prev.filter((p) => p.client_id !== client.client_id);
              return [...filtered, client];
            });
          }
        }

        // client_left
        if (type === 'client_left') {
          const cid = data.client_id || msg.client_id;
          if (cid) {
            setPeers((prev) => prev.filter((p) => p.client_id !== cid));
          }
        }

        // sender_ready: auto-advance
        if (type === 'sender_ready') {
          console.log('[Pair] Received sender_ready, advancing...');
          onAdvance();
        }
      } catch (e) {
        console.error('[Pair WS parse error]', e);
      }
    };

    ws.addEventListener('message', handleMessage);
    return () => {
      ws.removeEventListener('message', handleMessage);
    };
  }, [ws, onAdvance]);

  // Handle client disconnect button
  const handleDisconnect = async (clientId) => {
    if (!session?.session_id) return;
    try {
      await fetch(`/api/session/${session.session_id}/clients/${clientId}`, {
        method: 'DELETE',
      });
      setPeers((prev) => prev.filter((p) => p.client_id !== clientId));
    } catch (e) {
      console.error('Failed to disconnect client', e);
    }
  };

  // Join URL pointing to the mobile app port 5174
  const host = session?.server_ip || window.location.hostname;
  const joinUrl = `http://${host}:5174/join/${session?.session_id || ''}`;

  // Animated waiting status text
  const senderPeer = peers.find((p) => p.role === 'send' || p.role === 'sender');
  const receiverPeer = peers.find((p) => p.role === 'receive' || p.role === 'receiver');

  let waitingText = 'Waiting for devices to connect...';
  if (peers.length === 0) {
    waitingText = 'Waiting for devices to connect...';
  } else if (peers.length === 1) {
    if (senderPeer && !receiverPeer) {
      waitingText = 'Sender connected — waiting for receiver...';
    } else if (receiverPeer && !senderPeer) {
      waitingText = 'Receiver connected — waiting for sender...';
    } else {
      waitingText = 'Device connected — waiting for peer...';
    }
  } else if (peers.length >= 2) {
    waitingText = 'Both connected — waiting for sender signal...';
  }

  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      {/* Title */}
      <div className="text-center space-y-2">
        <h2 className="text-2xl font-bold text-white tracking-tight flex items-center justify-center gap-2">
          <Wifi className="w-6 h-6 text-cyan-400" />
          Pair Devices
        </h2>
        <p className="text-sm text-slate-400">
          Scan the QR code with mobile devices on your local network to initiate peer-to-peer pairing.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-start">
        {/* QR Code Card */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 flex flex-col items-center text-center shadow-xl">
          <span className="text-xs font-mono font-bold px-3 py-1 bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 rounded-full mb-5">
            SESSION ID: {session?.session_id || 'Generating...'}
          </span>

          <div className="p-4 bg-white rounded-2xl shadow-2xl mb-4">
            {session?.session_id ? (
              <QRCodeSVG value={joinUrl} size={200} level="M" />
            ) : (
              <div className="w-[200px] h-[200px] flex items-center justify-center bg-slate-100 rounded-xl">
                <RefreshCw className="w-8 h-8 text-slate-400 animate-spin" />
              </div>
            )}
          </div>

          <p className="text-xs font-mono text-slate-400 bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800/80 break-all max-w-xs">
            {joinUrl}
          </p>
        </div>

        {/* Connected Peers Table & Status */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col justify-between space-y-6">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-slate-200">Connected Peers</h3>
              <span className="text-xs font-mono px-2.5 py-0.5 rounded bg-slate-800 text-slate-300">
                {peers.length} Device{peers.length === 1 ? '' : 's'}
              </span>
            </div>

            {/* Peers Table */}
            <div className="overflow-x-auto border border-slate-800 rounded-xl">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950 text-slate-400 uppercase font-mono text-[10px] tracking-wider border-b border-slate-800">
                  <tr>
                    <th className="px-3 py-2.5">Name</th>
                    <th className="px-3 py-2.5">Role</th>
                    <th className="px-3 py-2.5">Status</th>
                    <th className="px-3 py-2.5 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-sans">
                  {peers.length === 0 ? (
                    <tr>
                      <td colSpan="4" className="p-6 text-center text-slate-500">
                        No peers connected yet.
                      </td>
                    </tr>
                  ) : (
                    peers.map((peer) => (
                      <tr key={peer.client_id} className="hover:bg-slate-800/30">
                        <td className="px-3 py-2.5 font-medium text-slate-200 flex items-center gap-1.5">
                          {peer.device_type?.toLowerCase().includes('phone') ? (
                            <Smartphone className="w-3.5 h-3.5 text-cyan-400" />
                          ) : (
                            <Monitor className="w-3.5 h-3.5 text-blue-400" />
                          )}
                          {peer.client_name || peer.client_id}
                        </td>
                        <td className="px-3 py-2.5 font-mono uppercase text-[11px] text-slate-300">
                          {peer.role || 'Auto'}
                        </td>
                        <td className="px-3 py-2.5 text-emerald-400 font-medium">
                          <span className="inline-flex items-center gap-1">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                            Connected
                          </span>
                        </td>
                        <td className="px-3 py-2.5 text-right">
                          <button
                            onClick={() => handleDisconnect(peer.client_id)}
                            className="p-1 text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 rounded transition-colors"
                            title="Disconnect device"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Animated Waiting Status */}
          <div className="bg-slate-950 p-4 rounded-xl border border-slate-800/80 flex items-center gap-3">
            <RefreshCw className="w-5 h-5 text-cyan-400 animate-spin shrink-0" />
            <span className="text-xs font-medium text-cyan-300">{waitingText}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
