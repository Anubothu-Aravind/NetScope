# NetScope: TCP Reliability and Performance under Network Impairments

## Product Overview
NetScope evaluates TCP performance, reliability, and flow control behaviors under controlled kernel-level network impairments (latency, loss, bandwidth limits).

### Control Plane vs. Data Plane Architecture
```text
SERVER (Host: 127.0.0.1:8000 / LAN IP:8000)
  | Control & Monitoring Plane
  | - Session Management (Session ID: NS-XXXXXX)
  | - Discovery & SVG QR Code Generation
  | - Deterministic Client Pairing (Pair ID: P-XXX)
  | - Telemetry Collection & SSE Broadcaster (/api/events)
  | - Sniffer & PCAP Analysis Coordinator
  | - Impairment Orchestration (tc netem)
  v
CLIENT A (Sender) <==== Direct TCP Data Channel ====> CLIENT B (Receiver)
  (e.g., in ns-client 10.10.0.1)                    (e.g., in ns-server 10.10.0.2)
  - 4-byte framed binary streaming
  - 64 KB chunk pipeline
  - Cryptographic SHA-256 verification
  - Live socket telemetry reporting
```

### Team Work Distribution (3 Members)
1. **Member 1 — Application & Session:**
   - TCP client/server, Session management, QR/link generation, Client registration, Send/Receive, Pairing, File transfer, File integrity.
2. **Member 2 — Networking & Experiments:**
   - tc/netem, Delay, Packet loss, Bandwidth, Network namespaces, Experiment runner, Scenario definitions, Repeated experiments.
3. **Member 3 — Packet Analysis & Dashboard:**
   - tshark, Wireshark, PCAP analysis, RTT, Retransmissions, Metrics, Dashboard, Charts, Visualization.
