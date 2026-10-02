# TCP Reliability and Performance under Network Impairments

## 1. Project Title

**TCP Reliability and Performance under Network Impairments**

---

## 2. Original Problem Statement

> Introduce controlled delay, packet loss, and bandwidth limits between a client and server. Analyse TCP connection establishment, retransmissions, throughput, and file-transfer completion time.

---

## 3. Enhanced Project Problem Statement

Modern network applications are expected to reliably transfer data even when the underlying network experiences delay, packet loss, congestion, and bandwidth limitations. TCP provides reliable, ordered data delivery using connection establishment, acknowledgements, sequence numbers, retransmissions, and congestion-control mechanisms.

This project develops a TCP-based file-transfer system using two Ubuntu machines, enhanced with a user-friendly GUI and QR/link-based device discovery. One device can create a transfer session and generate a connection link or QR code. Another device can join the session by scanning the QR code or entering the generated link and then select whether to send or receive a file.

The system introduces controlled network impairments such as delay, packet loss, and bandwidth limitations using Linux networking tools. Network traffic is captured and analysed using Wireshark/tshark to identify TCP connection establishment, acknowledgements, retransmissions, duplicate ACKs, and other TCP behaviour.

The project measures and compares RTT, retransmissions, throughput, and file-transfer completion time under normal and impaired network conditions.

---

## 4. Objectives

1. Implement a TCP client-server file-transfer system.
2. Establish communication between two Ubuntu machines.
3. Provide GUI-based session creation and file-transfer controls.
4. Generate a link/QR code for device discovery.
5. Allow connected devices to select Send or Receive.
6. Introduce controlled network delay.
7. Introduce controlled packet loss.
8. Introduce bandwidth limitations.
9. Capture and analyse TCP traffic using Wireshark/tshark.
10. Measure RTT, retransmissions, throughput, and file-transfer completion time.
11. Compare TCP performance under different network conditions.
12. Present results through a monitoring dashboard.

---

## 5. CO Mapping

### Primary CO: CO1

Relevant topics:

- Internet protocol stack
- TCP/UDP sockets
- Socket programming
- Packet capture and analysis
- Protocol-aware networking tools
- Debugging network applications

---

## 6. High-Level Architecture

```mermaid
flowchart TD
    A["TCP File Transfer Application"] --> B["Session & Device Discovery"]
    A --> C["TCP Communication"]
    A --> D["File Transfer"]

    E["Network Impairment Engine"] --> F["Delay"]
    E --> G["Packet Loss"]
    E --> H["Bandwidth Limiting"]

    I["Packet Analysis"] --> J["Wireshark / tshark"]
    I --> K["TCP Metrics"]

    L["Monitoring Dashboard"] --> M["RTT"]
    L --> N["Retransmissions"]
    L --> O["Throughput"]
    L --> P["Completion Time"]

    C --> I
    E --> C
    K --> L
```

---

## 7. Two-Machine Architecture

```mermaid
flowchart LR
    subgraph D1["Ubuntu Machine 1"]
        GUI1["GUI"]
        CLIENT["TCP Client"]
        GUI1 --> CLIENT
    end

    subgraph NET["Network"]
        IMP["tc / netem"]
    end

    subgraph D2["Ubuntu Machine 2"]
        SERVER["TCP Server"]
        GUI2["Analysis Dashboard"]
        CAP["Wireshark / tshark"]
        METRICS["Metrics Engine"]

        SERVER --> CAP
        CAP --> METRICS
        METRICS --> GUI2
    end

    D1 --> IMP
    IMP --> D2
```

---

## 8. QR / Link-Based Connection

The QR code is used for discovery and session joining, not as the TCP transfer mechanism.

```mermaid
sequenceDiagram
    participant A as Device A
    participant S as Server
    participant B as Device B

    A->>S: Create Session
    S->>A: Generate Link + QR
    A->>B: Share QR / Link
    B->>S: Join Session
    S->>B: Session Accepted
    B->>B: Select Send / Receive
    B->>S: Establish TCP Connection
    S-->>B: File Transfer
```

Example connection information (Web Session API on Port 8000, TCP Data on Port 5000):

```text
http://192.168.1.20:8000/join/AB12CD
```

---

## 9. File Transfer Workflow

```mermaid
flowchart TD
    A["Start Application"] --> B["Create / Join Session"]
    B --> C["Generate / Scan QR"]
    C --> D["Establish TCP Connection"]
    D --> E{"Select Operation"}

    E -->|"Send"| F["Select File"]
    E -->|"Receive"| G["Select Available File"]

    F --> H["Transfer File"]
    G --> H

    H --> I["TCP ACK / Retransmission"]
    I --> J["Transfer Complete"]
    J --> K["Calculate Metrics"]
    K --> L["Display Results"]
```

---

## 10. TCP Connection Analysis

```text
Client                         Server

  |                              |
  | -------- SYN --------------> |
  | <------ SYN + ACK ---------- |
  | -------- ACK --------------> |
  |                              |
  | -------- Request ----------> |
  |                              |
  | <------- File Data --------- |
  | ----------- ACK -----------> |
  |                              |
  | <------- File Data --------- |
  |                              |
  | ----------- ACK -----------> |
  |                              |
```

---

## 11. Network Impairments

### Delay

Example values:

```text
50 ms
100 ms
200 ms
```

### Packet Loss

Example values:

```text
1%
2%
5%
```

### Bandwidth

Example values:

```text
10 Mbps
5 Mbps
1 Mbps
```

---

## 12. Experimental Scenarios

| Experiment | Delay | Loss | Bandwidth |
|---|---:|---:|---:|
| Baseline | 0 ms | 0% | Unlimited |
| Delay-1 | 50 ms | 0% | Unlimited |
| Delay-2 | 100 ms | 0% | Unlimited |
| Delay-3 | 200 ms | 0% | Unlimited |
| Loss-1 | 0 ms | 1% | Unlimited |
| Loss-2 | 0 ms | 2% | Unlimited |
| Loss-3 | 0 ms | 5% | Unlimited |
| Bandwidth-1 | 0 ms | 0% | 10 Mbps |
| Bandwidth-2 | 0 ms | 0% | 5 Mbps |
| Bandwidth-3 | 0 ms | 0% | 1 Mbps |
| Combined | 100 ms | 2% | 5 Mbps |

---

## 13. Metrics

The project measures:

- TCP connection establishment time
- RTT
- TCP retransmissions
- Duplicate ACKs
- Throughput
- File-transfer completion time
- File integrity

---

## 14. Wireshark & Packet Capture Analysis

### Where to Impair and Where to Capture

- **Where to Impair:** Impair on the **Client node egress** (`eth0` on Ubuntu Machine 1).
- **Transfer Direction:** Use **Send mode** (Client uploads to Server).
- **Where to Capture:** Capture on the **Client node** (`eth0`).

#### Why Impair on Egress and Capture on the Sender?
1. **One-Way Delay & Expected RTT:**
   Linux `tc netem` applies delay to outgoing (egress) packets. For a one-way delay of $D$ ms and baseline round-trip time $RTT_0$, the forward packet experiences $\frac{RTT_0}{2} + D$, while the returning acknowledgment (ACK) is unimpaired ($\frac{RTT_0}{2}$). The measured RTT is:
   $$\text{Expected } RTT \approx RTT_0 + D$$
2. **Sender-Side Retransmission Visibility:**
   TCP retransmissions originate at the sender when a retransmission timeout (RTO) expires or when 3 duplicate ACKs arrive. The receiving node never observes lost packets—it only sees delayed arrivals or out-of-order data. Therefore, Wireshark/tshark filter `tcp.analysis.retransmission` **must be captured on the sending node** to accurately count retransmitted segments.

### Enabling Non-Root Packet Capture
To allow `tshark` packet sniffing without running the whole python process as root:
```bash
sudo dpkg-reconfigure wireshark-common   # Select <Yes> when prompted
sudo usermod -aG wireshark $USER
```
*Note: Log out and log back in for group permissions to take effect.*

### Useful Wireshark Filters
```text
tcp
tcp.port == 5000
tcp.flags.syn == 1
tcp.analysis.initial_rtt
tcp.analysis.ack_rtt
tcp.analysis.retransmission
tcp.analysis.duplicate_ack
tcp.analysis.out_of_order
tcp.analysis.lost_segment
```

---

## 15. Dashboard

The server/analysis machine should display:

```text
+------------------------------------------------------+
|              TCP NETWORK ANALYZER                    |
+------------------------------------------------------+
| Connection                                           |
| Client: 192.168.1.10                                 |
| Server: 192.168.1.20                                 |
| Status: CONNECTED                                    |
+------------------------------------------------------+
| Network Conditions                                   |
| Delay:       100 ms                                  |
| Packet Loss: 2 %                                     |
| Bandwidth:   5 Mbps                                  |
+------------------------------------------------------+
| TCP Metrics                                          |
| RTT:               108 ms                            |
| Retransmissions:   17                               |
| Duplicate ACKs:    24                               |
| Throughput:        4.31 Mbps                         |
+------------------------------------------------------+
| File Transfer                                        |
| File: testfile.bin                                   |
| Size: 100 MB                                         |
| Progress: █████████████████░░░ 85%                  |
| Completion Time: 184.2 sec                          |
+------------------------------------------------------+
```

---

## 16. Technology Stack

### OS

- Ubuntu Linux

### Application

- Python 3
- TCP sockets
- FastAPI or Flask
- HTML/CSS/JavaScript
- QR code generation

### Networking

- iproute2
- tc
- netem
- iperf3
- ss
- tcpdump

### Packet Analysis

- Wireshark
- tshark

### Visualization

- Matplotlib or Plotly

### Development

- Git
- GitHub
- VS Code

---

## 17. Three-Person Work Distribution

### Member 1 — TCP Application & File Transfer

Responsibilities:

- TCP client
- TCP server
- Socket communication
- File transfer
- Send/Receive
- Session management
- QR/link generation
- File integrity

### Member 2 — Network Impairment & Experimentation

Responsibilities:

- tc/netem
- Delay injection
- Packet-loss injection
- Bandwidth limitation
- Network configuration
- Experiment automation
- Test scenarios
- Performance measurement

### Member 3 — Packet Analysis & Dashboard

Responsibilities:

- Wireshark
- tshark
- tcpdump
- TCP packet analysis
- Retransmission detection
- RTT extraction
- Metrics processing
- Dashboard
- Graphs
- Visualization

All members participate in integration, testing, documentation, presentation, and viva preparation.

---

## 18. Repository Structure

```text
tcp-network-project/
│
├── README.md
├── project.md
├── requirements.txt
│
├── client/
├── server/
├── gui/
├── qr/
├── network/
├── experiments/
├── capture/
├── analysis/
├── visualization/
├── results/
├── docs/
└── tests/
```

---

# 19. Milestones

## Milestone 1 — Environment Setup

### 1. Package Installation (Both Machines)
Run the following on Ubuntu Machine 1 (Client) and Ubuntu Machine 2 (Server/Analyzer):

```bash
sudo apt update && sudo apt install -y python3 iproute2 tcpdump tshark iperf3
```

### 2. Verify Connectivity
Test basic IP reachability between Machine 1 and Machine 2:
```bash
ping -c 4 <SERVER_IP>
```

**Outcome:** Two machines communicate successfully.

---

## Milestone 2 — TCP Communication

- Implemented in `server/tcp_server.py` and `client/tcp_client.py` using length-prefixed framing (`common/protocol.py`).
- Data port: TCP **5000**.
- Measures connection establishment time (SYN -> SYN-ACK -> ACK handshake).

**Outcome:** Working multi-threaded TCP connection.

---

## Milestone 3 — File Transfer

- Chunked binary streaming (64 KB chunks).
- Full end-to-end SHA-256 integrity check.
- Real-time ASCII progress bar and automatic JSONL performance logging to `results/transfers.jsonl`.

### Exact Commands

#### Start Server (Machine 2)
```bash
python3 server/tcp_server.py --host 0.0.0.0 --port 5000 --storage-dir server_storage
```

#### Run Client (Machine 1) - Send File
```bash
python3 client/tcp_client.py send --server <SERVER_IP> --port 5000 --file tests/data/test_10mb.bin --scenario Baseline
```

#### Run Client (Machine 1) - Receive File
```bash
python3 client/tcp_client.py receive --server <SERVER_IP> --port 5000 --file test_10mb.bin --scenario Baseline --dest-dir downloads
```

#### Run Controlled Impairment Experiment (Combined: 100ms delay, 2% loss, 5Mbps)
```bash
# 1. Apply impairment on the egress interface (e.g. eth0)
sudo ./network/impair.sh eth0 apply --delay 100ms --loss 2% --rate 5mbit

# 2. Verify active kernel qdisc
./network/impair.sh eth0 show

# 3. Perform transfer under impairment
python3 client/tcp_client.py send --server <SERVER_IP> --port 5000 --file tests/data/test_10mb.bin --scenario Combined

# 4. Clear impairment
sudo ./network/impair.sh eth0 clear
```

**Outcome:** Reliable file transfer with verified integrity and metrics logging.

---

## Milestone 4 — GUI and QR Session

- Create GUI
- Create session
- Generate session ID
- Generate link
- Generate QR
- Scan/join session
- Send/Receive selection

**Outcome:** User-friendly file-transfer workflow.

---

## Milestone 5 — Packet Capture & Protocol Dissection

Implemented in `capture/sniffer.py` and `analysis/pcap_analyzer.py`:
- Captures live TCP streams via `tshark -i <iface> -f "tcp port 5000" -w <out.pcap>`.
- Gracefully terminates with `SIGINT` to ensure all packet headers and footers flush.
- Dissects packets without external Python frameworks using `tshark -r <file> -T fields`.
- Extracts:
  - 3-way handshake duration (`handshake_ms`)
  - Initial RTT (`initial_rtt_ms`)
  - Continuous ACK RTT (`rtt_min_ms`, `rtt_max_ms`, `rtt_avg_ms`)
  - Retransmission counters (`retransmissions`, `fast_retransmissions`, `duplicate_acks`, `lost_segments`)
  - TCP termination flags (`fin_seen`, `rst_seen`)
- Merges application-level metrics with packet analysis into `results/transfers.jsonl`.

### Commands

#### Standalone Capture
```bash
python3 capture/sniffer.py --iface eth0 --port 5000 --out results/pcaps/test.pcap
```

#### Standalone PCAP Analysis
```bash
python3 analysis/pcap_analyzer.py results/pcaps/test.pcap --port 5000
```

#### Automated Benchmark with Live Packet Capture & Analysis
```bash
# Run 5 repeats per scenario with packet capture & dissection
python3 experiments/run_all.py --server <SERVER_IP> --port 5000 --iface eth0 --file tests/data/test_10mb.bin --capture --repeats 5
```

#### Generate Statistical Summary Table & CSV
```bash
python3 experiments/summarize.py --input results/transfers.jsonl --output results/summary.csv
```

**Outcome:** Complete TCP packet capture, automated protocol dissection, and statistical summary reporting.

---

## Milestone 6 — Network Impairment

Implement:

- Delay
- Packet loss
- Bandwidth limitation

**Outcome:** Controlled network conditions.

---

## Milestone 7 — Performance Measurement

Measure:

- RTT
- Retransmissions
- Duplicate ACKs
- Throughput
- Completion time

**Outcome:** Experimental dataset.

---

## Milestone 8 — Dashboard

Display:

- Connection status
- Network conditions
- Transfer progress
- RTT
- Retransmissions
- Throughput
- Completion time
- Packet events

**Outcome:** Working monitoring dashboard.

---

## Milestone 9 — Experimental Evaluation

Run:

- Baseline
- Delay
- Loss
- Bandwidth
- Delay + Loss
- Delay + Bandwidth
- Combined impairment

Repeat experiments to reduce measurement noise.

---

## Milestone 10 — Final Analysis

Generate:

- Delay vs RTT
- Delay vs Completion Time
- Loss vs Retransmissions
- Loss vs Throughput
- Bandwidth vs Throughput
- Bandwidth vs Completion Time
- Combined conditions vs overall performance

---

## Milestone 11 — Final Demonstration

```mermaid
flowchart LR
    A["Create Session"] --> B["Generate QR"]
    B --> C["Scan QR"]
    C --> D["Join Session"]
    D --> E["Send / Receive"]
    E --> F["TCP File Transfer"]
    F --> G["Network Impairment"]
    G --> H["Wireshark"]
    G --> I["Metrics"]
    H --> J["Packet Analysis"]
    I --> K["Dashboard"]
    J --> K
```

---

# 20. Experimental Data Table

| Experiment | Delay | Loss | Bandwidth | RTT | Retransmissions | Throughput | Completion Time |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 0 ms | 0% | Unlimited | | | | |
| Delay-1 | 50 ms | 0% | Unlimited | | | | |
| Delay-2 | 100 ms | 0% | Unlimited | | | | |
| Delay-3 | 200 ms | 0% | Unlimited | | | | |
| Loss-1 | 0 ms | 1% | Unlimited | | | | |
| Loss-2 | 0 ms | 2% | Unlimited | | | | |
| Loss-3 | 0 ms | 5% | Unlimited | | | | |
| Bandwidth-1 | 0 ms | 0% | 10 Mbps | | | | |
| Bandwidth-2 | 0 ms | 0% | 5 Mbps | | | | |
| Bandwidth-3 | 0 ms | 0% | 1 Mbps | | | | |
| Combined | 100 ms | 2% | 5 Mbps | | | | |

---

# 21. Success Criteria

- [ ] Two Ubuntu machines communicate successfully.
- [ ] TCP client/server works.
- [ ] Files can be transferred reliably.
- [ ] QR/link session joining works.
- [ ] Send/Receive functionality works.
- [ ] Wireshark captures TCP traffic.
- [ ] TCP three-way handshake is identifiable.
- [ ] Network delay can be controlled.
- [ ] Packet loss can be controlled.
- [ ] Bandwidth can be controlled.
- [ ] TCP retransmissions can be observed.
- [ ] RTT can be measured.
- [ ] Throughput can be measured.
- [ ] File-transfer completion time can be measured.
- [ ] Dashboard displays metrics.
- [ ] Experimental results are visualized.
- [ ] Final analysis is documented.

---

# 22. Final Project Outcome

The final system combines:

```text
QR / Link Discovery
        +
GUI File Transfer
        +
TCP Socket Programming
        +
Network Impairment
        +
Wireshark Packet Analysis
        +
Performance Metrics
        +
Visualization
```

The central experimental question is:

> **How do delay, packet loss, and bandwidth limitations affect TCP reliability, retransmissions, throughput, and file-transfer completion time?**

---

# 23. Final Project Statement

> **TCP Reliability and Performance under Network Impairments** is a three-member networking project that implements a TCP-based file-transfer system between Ubuntu devices with QR/link-based session discovery and a monitoring interface. The system introduces controlled delay, packet loss, and bandwidth limitations using Linux networking tools and captures the resulting TCP traffic using Wireshark/tshark. TCP connection establishment, retransmissions, RTT, throughput, and file-transfer completion time are measured and compared across controlled network conditions. The project combines practical TCP socket programming, network emulation, packet analysis, and performance visualization to experimentally evaluate TCP reliability and performance under impaired network conditions.
