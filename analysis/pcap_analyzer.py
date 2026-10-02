#!/usr/bin/env python3
"""
analysis/pcap_analyzer.py - Wireshark / tshark PCAP Dissection Engine for NetScope

Viva Concepts & Critical Note on Capture Location:
- SENDER SIDE CAPTURE:
    Packet capture MUST be taken on the SENDER node (the node transmitting file bytes)
    for TCP retransmission metrics (`tcp.analysis.retransmission`) to be accurate.
    When a packet is dropped in transit due to netem loss:
      - The sender retransmits the lost segment after RTO timeout or 3 duplicate ACKs.
      - The receiver never saw the original packet, so on the receiver side the retransmission
        merely appears as a regular incoming packet, not a retransmission!
- Handshake Latency:
    Measured as the time delta between the sender's initial SYN and the completion ACK:
      Handshake Time = Time(ACK) - Time(SYN)
- ACK RTT:
    Wireshark tracks the round-trip time between when data bytes were transmitted and when
    their corresponding acknowledgment was received back (`tcp.analysis.ack_rtt`).
"""

import os
import sys
import json
import argparse
import subprocess
from typing import Dict, Any, Optional, List


def analyze(pcap_path: str, port: int = 5000) -> Dict[str, Any]:
    """
    Dissect a PCAP file using tshark and return structured TCP metrics.
    Never crashes; returns None for metrics that cannot be computed.
    """
    metrics: Dict[str, Any] = {
        "handshake_ms": None,
        "initial_rtt_ms": None,
        "rtt_avg_ms": None,
        "rtt_min_ms": None,
        "rtt_max_ms": None,
        "retransmissions": 0,
        "fast_retransmissions": 0,
        "duplicate_acks": 0,
        "out_of_order": 0,
        "lost_segments": 0,
        "total_packets": 0,
        "total_bytes": 0,
        "fin_seen": False,
        "rst_seen": False,
    }

    if not os.path.isfile(pcap_path):
        metrics["error"] = f"PCAP file not found: {pcap_path}"
        return metrics

    # Tshark fields to query
    fields = [
        "-e", "frame.number",
        "-e", "frame.time_epoch",
        "-e", "frame.len",
        "-e", "tcp.srcport",
        "-e", "tcp.dstport",
        "-e", "tcp.flags.syn",
        "-e", "tcp.flags.ack",
        "-e", "tcp.flags.fin",
        "-e", "tcp.flags.reset",
        "-e", "tcp.analysis.initial_rtt",
        "-e", "tcp.analysis.ack_rtt",
        "-e", "tcp.analysis.retransmission",
        "-e", "tcp.analysis.fast_retransmission",
        "-e", "tcp.analysis.duplicate_ack",
        "-e", "tcp.analysis.out_of_order",
        "-e", "tcp.analysis.lost_segment",
    ]

    cmd = [
        "tshark",
        "-r", pcap_path,
        "-Y", f"tcp.port == {port}",
        "-T", "fields",
        "-E", "separator=\t",
        "-E", "occurrence=f"
    ] + fields

    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    except FileNotFoundError:
        metrics["error"] = "tshark executable not found. Install via: sudo apt install -y tshark"
        return metrics
    except subprocess.CalledProcessError as e:
        metrics["error"] = f"tshark failed: {e.stderr.strip()}"
        return metrics
    except Exception as e:
        metrics["error"] = f"Unexpected error during dissection: {str(e)}"
        return metrics

    lines = proc.stdout.strip().split("\n")
    if not lines or lines == [""]:
        metrics["error"] = "No packets matched TCP filter in PCAP."
        return metrics

    syn_time: Optional[float] = None
    syn_ack_time: Optional[float] = None
    handshake_ack_time: Optional[float] = None
    initial_rtts: List[float] = []
    ack_rtts: List[float] = []

    total_packets = 0
    total_bytes = 0
    retransmissions = 0
    fast_retransmissions = 0
    dup_acks = 0
    out_of_orders = 0
    lost_segments = 0
    fin_seen = False
    rst_seen = False

    for line in lines:
        parts = line.split("\t")
        if len(parts) < 16:
            continue

        (
            f_num, f_time_s, f_len_s,
            srcport_s, dstport_s,
            syn_s, ack_s, fin_s, rst_s,
            init_rtt_s, ack_rtt_s,
            retrans_s, fast_retrans_s,
            dup_ack_s, ooo_s, lost_seg_s
        ) = parts[:16]

        total_packets += 1
        try:
            total_bytes += int(f_len_s) if f_len_s else 0
        except ValueError:
            pass

        try:
            pkt_time = float(f_time_s) if f_time_s else None
        except ValueError:
            pkt_time = None

        # 3-Way Handshake tracking
        is_syn = (syn_s == "1")
        is_ack = (ack_s == "1")
        is_fin = (fin_s == "1")
        is_rst = (rst_s == "1")

        if is_fin:
            fin_seen = True
        if is_rst:
            rst_seen = True

        if is_syn and not is_ack and syn_time is None and pkt_time is not None:
            syn_time = pkt_time
        elif is_syn and is_ack and syn_time is not None and syn_ack_time is None and pkt_time is not None:
            syn_ack_time = pkt_time
        elif not is_syn and is_ack and syn_ack_time is not None and handshake_ack_time is None and pkt_time is not None:
            handshake_ack_time = pkt_time

        # Initial RTT
        if init_rtt_s:
            try:
                initial_rtts.append(float(init_rtt_s) * 1000.0)
            except ValueError:
                pass

        # ACK RTT
        if ack_rtt_s:
            try:
                ack_rtts.append(float(ack_rtt_s) * 1000.0)
            except ValueError:
                pass

        # Anomaly counters
        if retrans_s:
            retransmissions += 1
        if fast_retrans_s:
            fast_retransmissions += 1
        if dup_ack_s:
            dup_acks += 1
        if ooo_s:
            out_of_orders += 1
        if lost_seg_s:
            lost_segments += 1

    # Compute handshake latency
    if syn_time is not None and handshake_ack_time is not None:
        metrics["handshake_ms"] = round((handshake_ack_time - syn_time) * 1000.0, 2)
    elif syn_time is not None and syn_ack_time is not None:
        metrics["handshake_ms"] = round((syn_ack_time - syn_time) * 2000.0, 2)

    # Initial RTT
    if initial_rtts:
        metrics["initial_rtt_ms"] = round(initial_rtts[0], 2)

    # ACK RTT stats
    if ack_rtts:
        metrics["rtt_min_ms"] = round(min(ack_rtts), 2)
        metrics["rtt_max_ms"] = round(max(ack_rtts), 2)
        metrics["rtt_avg_ms"] = round(sum(ack_rtts) / len(ack_rtts), 2)

    metrics["total_packets"] = total_packets
    metrics["total_bytes"] = total_bytes
    metrics["retransmissions"] = retransmissions
    metrics["fast_retransmissions"] = fast_retransmissions
    metrics["duplicate_acks"] = dup_acks
    metrics["out_of_order"] = out_of_orders
    metrics["lost_segments"] = lost_segments
    metrics["fin_seen"] = fin_seen
    metrics["rst_seen"] = rst_seen

    return metrics


def main():
    parser = argparse.ArgumentParser(description="NetScope tshark PCAP Analyzer")
    parser.add_argument("pcap", help="Path to PCAP file to analyze")
    parser.add_argument("--port", type=int, default=5000, help="TCP port to filter (default: 5000)")
    args = parser.parse_args()

    result = analyze(args.pcap, port=args.port)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
