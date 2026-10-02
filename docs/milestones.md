# NetScope Project Milestones

This document tracks the milestone roadmap and deliverables for **NetScope: TCP Reliability and Performance under Network Impairments**.

---

## Milestone 1 — Codebase Audit & Cleanup
**Deliverables:**
- Repository audit & structure mapping.
- Identification of working functionality (FastAPI, tshark sniffer, PCAP analyzer, tc netem scripts, network namespaces, SVG QR).
- Definition of control plane vs. data plane architecture.
- Documenting architecture, protocol, and milestones.

**Acceptance Criteria:**
```text
Application starts successfully.
Existing working functionality remains intact.
No unnecessary duplicate implementation exists.
```

---

## Milestone 2 — Session & QR System
**Deliverables:**
- Unique session generation with `NS-` prefix (e.g. `NS-AB12CD`).
- REST endpoints: `POST /api/session`, `GET /api/session/{id}`.
- LAN Join URL (`http://<lan-ip>:8000/join/NS-XXXXXX`).
- Native pure-Python QR code generator using `segno` (SVG output).
- QR contains only session join URL (no file data or sensitive payloads).
- Server session dashboard showing active session details and live status.

**Acceptance Criteria:**
```text
Server creates session.
Another device scans QR.
Join page opens.
Client joins the correct session.
```

---

## Milestone 3 — Client Registration
**Deliverables:**
- Client model with `client_id`, `client_name`, `ip`, `role`, `status`, and `online`.
- REST endpoints: `POST /api/session/{id}/clients` (join), `GET /api/session/{id}/clients` (list), `DELETE /api/session/{id}/clients/{cid}` (leave).
- Real-time client join/leave broadcasts over Server-Sent Events (`/api/events`).
- Join page (`gui/join.html`) prompts for device name and displays connection state.

**Acceptance Criteria:**
```text
Multiple physical devices can join one session.
Server sees every connected client.
```

---

## Milestone 4 — Client Pairing
**Deliverables:**
- Deterministic pairing engine in `app/pairing_manager.py`.
- Roles: `SEND` vs `RECEIVE`.
- Pair state machine:
  `CONNECTED` -> `ROLE_SELECTED` -> `WAITING_FOR_PEER` -> `PAIRING` -> `PAIRED` -> `TCP_CONNECTING` -> `TRANSFERRING` -> `COMPLETED`.
- Failure transitions (`FAILED`, `CANCELLED`, `DISCONNECTED`).
- Prevention of duplicate pairing or race conditions.
- Server dashboard visualizes active pairs and their state.

**Acceptance Criteria:**
```text
Client A = SEND
Client B = RECEIVE

Server shows:
A <---- Pair P-001 ----> B
```

---

## Milestone 5 — Client-to-Client TCP Transfer
**Deliverables:**
- Client data plane: `client/tcp_sender.py` and `client/tcp_receiver.py`.
- Framing: 4-byte big-endian payload length headers.
- 64 KB binary streaming chunks with on-the-fly SHA-256 calculation.
- Transfer metadata exchange (filename, size, transfer_id, pair_id, sha256).
- Verification acknowledgment (`TRANSFER_ACK` / `INTEGRITY_MISMATCH`).
- In single-laptop testbed: Sender runs in `ns-client` (10.10.0.1) and Receiver in `ns-server` (10.10.0.2).

**Acceptance Criteria:**
```text
Client A sends a file.
Client B receives it.
File integrity matches.
Server sees transfer progress.
```

---

## Milestone 6 — Live Server Monitoring
**Deliverables:**
- Server receives progress telemetry from sender/receiver.
- SSE broadcaster (`/api/events`) streams live state, throughput, and progress.
- Dual HTML5 Canvas sparklines (RTT and Throughput).
- Active transfer telemetry card in server dashboard.

**Acceptance Criteria:**
```text
The entire client-to-client workflow can be observed from the server.
```

---

## Milestone 7 — Network Impairment Engine
**Deliverables:**
- Linux Traffic Control (`tc netem`) interface wrapper (`network/impair.sh`).
- Preset scenarios loaded dynamically from `network/scenarios.json`.
- Sliders for Delay (0–200 ms), Loss (0–5%), Bandwidth (1–10 Mbps or Unlimited).
- REST API: `POST /api/impair` and `DELETE /api/impair`.
- Targets `veth-c` inside `ns-client` with `/opt/netscope/` privileged isolation.

**Acceptance Criteria:**
```text
Baseline, Delay, Loss, Bandwidth, Combined experiments can be executed reproducibly.
```

---

## Milestone 8 — Packet Capture & TCP Analysis
**Deliverables:**
- Passive sniffer (`capture/sniffer.py`) capturing on `veth-c` inside `ns-client` with SIGINT flushing.
- Automated PCAP dissector (`analysis/pcap_analyzer.py`) extracting handshake latency, RTT min/max/avg, retransmissions, duplicate ACKs, lost segments, and FIN/RST flags.
- Real-time packet event stream logging for SYN, SYN-ACK, ACK, RETRANS, DUP-ACK, FIN.

**Acceptance Criteria:**
```text
A completed transfer produces a usable PCAP and parsed TCP metrics.
```

---

## Milestone 9 — Experiment Automation
**Deliverables:**
- Automated benchmark runner (`experiments/run_all.py`).
- Supports `--scenarios` filter (comma-separated names) and `--repeats`.
- Statistical summary aggregator (`experiments/summarize.py`) exporting `mean ± stdev` to `results/summary.csv`.
- Single fused record per run logged to `results/transfers.jsonl`.

**Acceptance Criteria:**
```text
Experiments can be reproduced without manually performing every step.
```

---

## Milestone 10 — Dashboard & Visualization
**Deliverables:**
- ConSentinel design system GUI (`gui/index.html`) using `--u` unit scaling.
- Six required comparative metric charts driven by `results/transfers.jsonl`:
  1. Delay vs RTT
  2. Delay vs Completion Time
  3. Loss vs Retransmissions
  4. Loss vs Throughput
  5. Bandwidth vs Throughput
  6. Bandwidth vs Completion Time
- CSV export button (`/results/summary.csv`).

**Acceptance Criteria:**
```text
All visualizations use real recorded data.
```

---

## Milestone 11 — Integration Testing
**Deliverables:**
- End-to-end integration tests:
  - `tests/test_remote_access.py`: Non-loopback client security restrictions.
  - `tests/test_session.py`: Session creation and validation.
  - `tests/test_pairing.py`: Pairing state transitions and edge cases.
  - `tests/test_transfer.py`: Direct TCP transfer with SHA-256 integrity verification.
  - `tests/test_integrity.py`: Tamper detection and hashing validation.
- All tests automated in CI/local runner without contaminating `results/transfers.jsonl`.

---

## Milestone 12 — Final Experimental Evaluation
**Deliverables:**
- Execution of all 11 scenarios across N repetitions.
- Verified correlation: Network Impairment -> TCP Behavior -> RTT/Retransmissions -> Throughput -> Completion Time.
- Dataset verified in `results/transfers.jsonl` and `results/summary.csv`.

---

## Milestone 13 — Final Demonstration
**Deliverables:**
- Desktop window launcher (`python3 netscope.py`).
- Full visual live demonstration:
  Server -> Create Session -> QR Code -> Phone/Laptop join -> SEND/RECEIVE pairing -> Direct TCP transfer -> Packet analysis -> Live Dashboard update.
