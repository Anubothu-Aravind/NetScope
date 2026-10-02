#!/usr/bin/env python3
"""
experiments/summarize.py - Statistical Aggregation and Summary for NetScope

Viva Concepts:
- Statistical Reporting in Networks:
    Single-run measurements are susceptible to random burst losses, kernel scheduling,
    and cross-traffic. Running N repetitions and calculating Mean and Standard Deviation (stdev)
    provides high experimental confidence:
      Mean (μ) = (Σ x) / N
      StDev (s) = sqrt( (Σ (x - μ)²) / (N - 1) )  (for N > 1)
- Reads: results/transfers.jsonl
- Writes: results/summary.csv
"""

import os
import sys
import csv
import json
import math
import argparse
from typing import List, Dict, Any, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def mean_stdev(values: List[float]) -> (Optional[float], Optional[float]):
    """Calculate mean and sample standard deviation for a list of floats."""
    clean_vals = [v for v in values if v is not None and not math.isnan(v)]
    n = len(clean_vals)
    if n == 0:
        return None, None
    m = sum(clean_vals) / n
    if n == 1:
        return round(m, 2), 0.0
    variance = sum((x - m) ** 2 for x in clean_vals) / (n - 1)
    s = math.sqrt(variance)
    return round(m, 2), round(s, 2)


def format_stat(m: Optional[float], s: Optional[float], unit: str = "") -> str:
    """Format mean ± stdev string for table printing."""
    if m is None:
        return "N/A"
    if s is None or s == 0.0:
        return f"{m:.2f} {unit}".strip()
    return f"{m:.2f} ± {s:.2f} {unit}".strip()


def summarize(input_file: str = "results/transfers.jsonl",
              output_csv: str = "results/summary.csv") -> List[Dict[str, Any]]:
    """Aggregate transfer logs by scenario and export summary table and CSV."""
    abs_input = input_file if os.path.isabs(input_file) else os.path.join(PROJECT_ROOT, input_file)
    abs_output = output_csv if os.path.isabs(output_csv) else os.path.join(PROJECT_ROOT, output_csv)

    if not os.path.isfile(abs_input):
        print(f"[!] Input file '{abs_input}' not found. No results to summarize.")
        return []

    # Group runs by scenario
    grouped: Dict[str, Dict[str, list]] = {}

    with open(abs_input, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            sc = row.get("scenario", "Unknown")
            if sc not in grouped:
                grouped[sc] = {
                    "completion_s": [],
                    "throughput_mbps": [],
                    "rtt_avg_ms": [],
                    "retransmissions": [],
                    "duplicate_acks": [],
                    "count": 0
                }

            grouped[sc]["count"] += 1
            if row.get("completion_s") is not None:
                grouped[sc]["completion_s"].append(float(row["completion_s"]))
            if row.get("throughput_mbps") is not None:
                grouped[sc]["throughput_mbps"].append(float(row["throughput_mbps"]))

            # Extract TCP metrics either from top-level or 'tcp' sub-object
            tcp = row.get("tcp") or {}
            rtt = tcp.get("rtt_avg_ms") if "rtt_avg_ms" in tcp else row.get("rtt_avg_ms")
            retrans = tcp.get("retransmissions") if "retransmissions" in tcp else row.get("retransmissions")
            dups = tcp.get("duplicate_acks") if "duplicate_acks" in tcp else row.get("duplicate_acks")

            if rtt is not None:
                grouped[sc]["rtt_avg_ms"].append(float(rtt))
            if retrans is not None:
                grouped[sc]["retransmissions"].append(float(retrans))
            if dups is not None:
                grouped[sc]["duplicate_acks"].append(float(dups))

    if not grouped:
        print("[!] No valid records found in results file.")
        return []

    # Print Table Header
    print("\n" + "=" * 98)
    print(f" NetScope Benchmark Summary ({len(grouped)} Scenarios)")
    print("=" * 98)
    print(f"{'Scenario':<16} | {'Runs':<4} | {'Duration (s)':<16} | {'Throughput (Mbps)':<18} | {'RTT Avg (ms)':<16} | {'Retrans':<10} | {'Dup ACKs':<10}")
    print("-" * 98)

    summary_rows = []

    for sc, data in grouped.items():
        dur_m, dur_s = mean_stdev(data["completion_s"])
        tp_m, tp_s = mean_stdev(data["throughput_mbps"])
        rtt_m, rtt_s = mean_stdev(data["rtt_avg_ms"])
        ret_m, ret_s = mean_stdev(data["retransmissions"])
        dup_m, dup_s = mean_stdev(data["duplicate_acks"])

        print(f"{sc:<16} | {data['count']:<4} | {format_stat(dur_m, dur_s):<16} | {format_stat(tp_m, tp_s):<18} | {format_stat(rtt_m, rtt_s):<16} | {format_stat(ret_m, ret_s):<10} | {format_stat(dup_m, dup_s):<10}")

        summary_rows.append({
            "scenario": sc,
            "runs": data["count"],
            "completion_s_mean": dur_m,
            "completion_s_stdev": dur_s,
            "throughput_mbps_mean": tp_m,
            "throughput_mbps_stdev": tp_s,
            "rtt_avg_ms_mean": rtt_m,
            "rtt_avg_ms_stdev": rtt_s,
            "retransmissions_mean": ret_m,
            "retransmissions_stdev": ret_s,
            "duplicate_acks_mean": dup_m,
            "duplicate_acks_stdev": dup_s,
        })

    print("=" * 98 + "\n")

    # Write summary CSV
    os.makedirs(os.path.dirname(abs_output), exist_ok=True)
    fieldnames = [
        "scenario", "runs",
        "completion_s_mean", "completion_s_stdev",
        "throughput_mbps_mean", "throughput_mbps_stdev",
        "rtt_avg_ms_mean", "rtt_avg_ms_stdev",
        "retransmissions_mean", "retransmissions_stdev",
        "duplicate_acks_mean", "duplicate_acks_stdev"
    ]
    with open(abs_output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"[✔] Summary CSV written to: {abs_output}\n")
    return summary_rows


def main():
    parser = argparse.ArgumentParser(description="NetScope Benchmark Results Summarizer")
    parser.add_argument("--input", default="results/transfers.jsonl", help="Input JSONL file (default: results/transfers.jsonl)")
    parser.add_argument("--output", default="results/summary.csv", help="Output CSV file (default: results/summary.csv)")
    args = parser.parse_args()

    summarize(input_file=args.input, output_csv=args.output)


if __name__ == "__main__":
    main()
