# NetScope — TCP Reliability and Performance under Network Impairments

> **How do delay, packet loss, and bandwidth limitations affect TCP reliability,
> retransmissions, throughput, and file-transfer completion time?**

NetScope is a self-contained single-laptop testbed that:

- Creates a **two-node network namespace testbed** (ns-client ↔ ns-server via a veth pair)
- Applies **controlled tc/netem impairments** (delay, loss, bandwidth limit)
- Runs a **TCP file transfer** between the namespaces and captures the traffic with tshark
- Extracts **TCP metrics** (RTT, retransmissions, throughput, completion time) from the pcap
- Serves a **real-time monitoring dashboard** (FastAPI + SSE) with QR-based device discovery

---

## Quick Start

```bash
# 1. Install system dependencies and set up the venv
./setup.sh          # run once; requires sudo for namespace scripts

# 2. Start the dashboard
./run.sh            # opens http://localhost:8000
```

---

## Requirements

- Linux with `iproute2`, `tc`, `tshark`, `ethtool` installed
- Python 3.8+
- Internet connection for the first `pip install` (or install from `requirements.txt` offline)

Install Python dependencies manually if needed:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

---

## Project Structure

```
NetScope/
├── app/                # FastAPI control plane
│   ├── main.py         # All API endpoints, SSE, session/pair management
│   ├── session_manager.py
│   ├── pairing_manager.py
│   ├── models.py
│   ├── events.py
│   ├── server.py       # Re-export shim: uvicorn app.server:app
│   ├── tcp_client.py   # Re-export shim
│   └── protocol.py     # Re-export shim → common/protocol.py
├── client/
│   ├── tcp_sender.py   # Canonical sender (64 KB chunks, SHA-256, timed)
│   ├── tcp_receiver.py # Canonical receiver (writes file, verifies SHA-256)
│   └── tcp_client.py   # CLI wrapper around sender/receiver
├── server/
│   └── tcp_server.py   # Legacy standalone server (kept for unit tests)
├── common/
│   └── protocol.py     # Length-prefixed framing shared by sender and receiver
├── capture/
│   └── sniffer.py      # tshark wrapper (starts/stops capture on veth-c)
├── analysis/
│   └── pcap_analyzer.py # Extracts RTT, retransmissions, throughput from .pcap
├── network/
│   ├── netns_setup.sh  # Create/destroy ns-client + ns-server namespaces
│   ├── nsrun.sh        # Run a command inside a namespace
│   ├── impair.sh       # Apply/clear tc netem rules on veth-c
│   ├── scenarios.json  # 11 experiment scenarios
│   └── install_sudoers.sh  # Install /etc/sudoers.d/netscope
├── experiments/
│   ├── run_all.py      # Automated benchmark runner
│   └── summarize.py    # Print ASCII table from results/transfers.jsonl
├── gui/
│   ├── index.html      # Single-page monitoring dashboard
│   └── join.html       # Mobile join page (QR scan → role select)
├── tests/
│   ├── check_env.sh    # Pre-flight environment check
│   └── *.py            # Unit + integration tests
├── results/
│   └── transfers.jsonl # Experiment results (one JSON object per line)
├── setup.sh            # One-time setup script
├── run.sh              # Launch the dashboard
├── requirements.txt
└── .gitignore
```

---

## Running Experiments

```bash
# Run all 11 scenarios (5 repeats each, with tshark capture):
.venv/bin/python3 experiments/run_all.py --capture --repeats 5

# Run specific scenarios:
.venv/bin/python3 experiments/run_all.py --capture --repeats 3 \
    --scenarios Baseline,Delay-1,Loss-1,Combined

# Print summary table:
.venv/bin/python3 experiments/summarize.py
```

---

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full design, including the
rationale for placing tc netem and tshark capture on the **sender side** (veth-c in
ns-client).

---

## License

Academic project — MTech, DCNIP.
