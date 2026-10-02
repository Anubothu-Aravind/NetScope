#!/usr/bin/env python3
"""
experiments/run_all.py - Automated Experiment Runner with Network Namespaces & tshark Capture

Executes Milestone 5 / Milestone 9 workflow:
1. Iterates through all scenarios in network/scenarios.json.
2. Applies kernel-level tc/netem impairments via network/impair.sh (inside ns-client by default).
3. For each run:
   - Starts passive packet capture (capture/sniffer.py) on veth-c inside ns-client.
   - Runs client file transfer (client/tcp_client.py) inside ns-client targeting 10.10.0.2:5000.
   - Stops sniffer with flush delay.
   - Dissects PCAP with analysis/pcap_analyzer.py.
   - Merges application metrics + TCP metrics + PCAP path into ONE row in results/transfers.jsonl.
4. Resets the network interface in a finally block.
"""

import os
import sys
import json
import time
import uuid
import tempfile
import argparse
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from client.tcp_client import run_transfer, log_result
from capture.sniffer import Sniffer
from analysis.pcap_analyzer import analyze


def run_command(cmd, dry_run=False):
    """Execute a shell command or print it in dry-run mode."""
    cmd_str = " ".join(cmd)
    if dry_run:
        print(f"[DRY-RUN] {cmd_str}")
        return True

    print(f"[EXEC] {cmd_str}")
    res = subprocess.run(cmd)
    return res.returncode == 0


def get_impair_script() -> str:
    """Return /opt/netscope/impair.sh if present, else fallback to network/impair.sh."""
    opt_path = "/opt/netscope/impair.sh"
    if os.path.isfile(opt_path):
        return opt_path
    return os.path.join(PROJECT_ROOT, "network", "impair.sh")


def apply_scenario(iface: str, scenario: dict, ns: str = None, dry_run: bool = False) -> bool:
    """Invoke network/impair.sh to apply network parameters."""
    script_path = get_impair_script()
    cmd = ["sudo", "-n", script_path]
    if ns:
        cmd.extend(["--ns", ns])
    cmd.extend([iface, "apply"])

    delay = scenario.get("delay")
    loss = scenario.get("loss")
    bw = scenario.get("bandwidth")

    if delay and delay != "0ms":
        cmd.extend(["--delay", delay])
    if loss and loss != "0%":
        cmd.extend(["--loss", loss])
    if bw and bw != "Unlimited":
        cmd.extend(["--rate", bw])

    return run_command(cmd, dry_run=dry_run)


def clear_scenario(iface: str, ns: str = None, dry_run: bool = False) -> bool:
    """Clear network impairments on the interface."""
    script_path = get_impair_script()
    cmd = ["sudo", "-n", script_path]
    if ns:
        cmd.extend(["--ns", ns])
    cmd.extend([iface, "clear"])
    return run_command(cmd, dry_run=dry_run)


def main():
    parser = argparse.ArgumentParser(description="Automate NetScope benchmark scenarios with namespace testbed and tshark capture")
    parser.add_argument("--server", default=None, help="Target server IP (default: 10.10.0.2 in netns mode, 127.0.0.1 in --no-netns)")
    parser.add_argument("--port", type=int, default=5000, help="Target server TCP port (default: 5000)")
    parser.add_argument("--iface", default=None, help="Network interface for tc and sniffer (default: veth-c in netns, eth0 in --no-netns)")
    parser.add_argument("--ns", default=None, help="Namespace to target (default: ns-client in netns mode, None in --no-netns)")
    parser.add_argument("--no-netns", action="store_true", help="Disable network namespace mode (for two physical machines)")
    parser.add_argument("--file", default="tests/data/test_10mb.bin", help="Test file path (default: tests/data/test_10mb.bin)")
    parser.add_argument("--mode", choices=["send", "receive"], default="send", help="Transfer mode (default: send)")
    parser.add_argument("--repeats", type=int, default=5, help="Number of repetitions per scenario (default: 5)")
    parser.add_argument("--scenarios", default=None, help="Comma-separated scenario names (e.g. 'Baseline,Delay-1') or path to JSON file")
    parser.add_argument("--scenarios-file", default="network/scenarios.json", help="Path to base scenarios JSON file")
    parser.add_argument("--capture", action="store_true", help="Enable tshark packet capture for each transfer")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing tc or client transfers")
    args = parser.parse_args()

    # Determine defaults based on netns mode
    if args.no_netns:
        server_ip = args.server or "127.0.0.1"
        iface_name = args.iface or "eth0"
        ns_name = args.ns or None
    else:
        server_ip = args.server or "10.10.0.2"
        iface_name = args.iface or "veth-c"
        ns_name = args.ns or "ns-client"

    scenarios_file = args.scenarios_file
    requested_names = None

    if args.scenarios:
        if args.scenarios.endswith(".json") or os.path.isfile(args.scenarios):
            scenarios_file = args.scenarios
        else:
            requested_names = [s.strip() for s in args.scenarios.split(",") if s.strip()]

    scenarios_path = scenarios_file if os.path.isabs(scenarios_file) else os.path.join(PROJECT_ROOT, scenarios_file)
    if not os.path.isfile(scenarios_path):
        print(f"[ERROR] Scenarios file '{scenarios_path}' not found.")
        sys.exit(1)

    with open(scenarios_path, "r", encoding="utf-8") as f:
        all_scenarios = json.load(f)

    if requested_names:
        name_map = {s["name"].lower(): s for s in all_scenarios}
        scenarios = []
        for name in requested_names:
            if name.lower() in name_map:
                scenarios.append(name_map[name.lower()])
            else:
                print(f"[WARNING] Scenario '{name}' not found in {scenarios_path}.")
        if not scenarios:
            print(f"[ERROR] None of the requested scenarios {requested_names} could be found.")
            sys.exit(1)
    else:
        scenarios = all_scenarios

    # Validate test file exists (if not in dry-run mode)
    file_path = os.path.abspath(args.file)
    if not args.dry_run and not os.path.isfile(file_path):
        print(f"[ERROR] Test file '{file_path}' does not exist.")
        print("        Run: ./tests/make_testfile.sh tests/data")
        sys.exit(1)

    file_size = os.path.getsize(file_path) if os.path.isfile(file_path) else 10485760

    print("=============================================================")
    print(" NetScope Automated Benchmark Suite")
    print(f" Mode:             {'Namespace Testbed (' + str(ns_name) + ')' if ns_name else 'Direct Machine'}")
    print(f" Total Scenarios:  {len(scenarios)} | Repeats per Scenario: {args.repeats}")
    print(f" Target Server:    {server_ip}:{args.port} | Transfer: {args.mode.upper()}")
    print(f" Network Link:     {iface_name} | Packet Capture: {args.capture}")
    print(f" Payload File:     {file_path} ({file_size / (1024*1024):.2f} MB)")
    print(f" Dry Run Mode:     {args.dry_run}")
    print("=============================================================\n")

    # Refresh sudo timestamp once upfront
    if not args.dry_run:
        try:
            subprocess.run(["sudo", "-n", "-v"], check=False)
        except Exception:
            pass

    pcaps_dir = os.path.join(PROJECT_ROOT, "results", "pcaps")
    os.makedirs(pcaps_dir, exist_ok=True)
    client_py = os.path.join(PROJECT_ROOT, "client", "tcp_client.py")

    try:
        for idx, sc in enumerate(scenarios, start=1):
            sc_name = sc["name"]
            bw = sc.get("bandwidth", "Unlimited")
            print(f"\n[{idx}/{len(scenarios)}] --- Scenario: {sc_name} ({sc.get('description', '')}) ---")
            print(f"     Parameters: Delay={sc.get('delay')} | Loss={sc.get('loss')} | Rate={bw}")

            if file_size > 20 * 1024 * 1024 and bw in ["1mbit", "1Mbps", "1Mbit"]:
                print("     [WARNING] Transferring >20 MB over 1 Mbps link may take >160 seconds!")

            # 1. Apply impairment
            apply_scenario(iface_name, sc, ns=ns_name, dry_run=args.dry_run)
            time.sleep(0.5)

            # 2. Run repeated transfers
            for rep in range(1, args.repeats + 1):
                run_id = uuid.uuid4().hex[:8]
                pcap_file = os.path.join(pcaps_dir, f"{sc_name}_{run_id}.pcap")
                rel_pcap = os.path.relpath(pcap_file, PROJECT_ROOT)

                print(f"\n  >> Run {rep}/{args.repeats} for {sc_name} [Run ID: {run_id}]")

                sniffer = None
                if args.capture:
                    if args.dry_run:
                        print(f"  [DRY-RUN] Start tshark sniffer in [{ns_name or 'host'}] -> {rel_pcap}")
                    else:
                        sniffer = Sniffer(iface=iface_name, port=args.port, out_path=pcap_file, ns=ns_name)
                        sniffer.start()

                # Execute transfer
                if args.dry_run:
                    exec_prefix = f"sudo ip netns exec {ns_name} " if ns_name else ""
                    print(f"  [DRY-RUN] {exec_prefix}python3 client/tcp_client.py {args.mode} --server {server_ip} --file {args.file}")
                    if args.capture:
                        print(f"  [DRY-RUN] Stop tshark sniffer and flush buffers")
                        print(f"  [DRY-RUN] Analyze {rel_pcap} with pcap_analyzer")
                        print(f"  [DRY-RUN] Merge client + TCP metrics -> results/transfers.jsonl")
                else:
                    # Use project results/tmp_runs/ so sudo-spawned processes can write to it.
                    tmp_dir = os.path.join(PROJECT_ROOT, "results", "tmp_runs")
                    os.makedirs(tmp_dir, mode=0o777, exist_ok=True)
                    temp_res = tempfile.NamedTemporaryFile(
                        suffix=".jsonl", dir=tmp_dir, delete=False
                    )
                    temp_res.close()
                    # Ensure root (inside namespace) can write the file.
                    os.chmod(temp_res.name, 0o666)

                    try:
                        if ns_name:
                            # Run client inside namespace
                            nsrun_bin = "/opt/netscope/nsrun.sh" if os.path.isfile("/opt/netscope/nsrun.sh") else os.path.join(PROJECT_ROOT, "network", "nsrun.sh")
                            client_cmd = [
                                "sudo", "-n", nsrun_bin, ns_name,
                                sys.executable, client_py, args.mode,
                                "--server", server_ip,
                                "--port", str(args.port),
                                "--file", file_path,
                                "--scenario", sc_name,
                                "--run-id", run_id,
                                "--results-file", temp_res.name
                            ]
                            subprocess.run(client_cmd, check=True)
                        else:
                            run_transfer(
                                mode=args.mode,
                                server_ip=server_ip,
                                port=args.port,
                                file_arg=file_path,
                                scenario=sc_name,
                                dest_dir="downloads",
                                results_file=temp_res.name,
                                run_id=run_id
                            )

                        with open(temp_res.name, "r", encoding="utf-8") as rf:
                            lines = [ln.strip() for ln in rf if ln.strip()]
                            record = json.loads(lines[-1]) if lines else {}
                    except Exception as e:
                        print(f"  [ERROR] Client transfer failed: {e}")
                        record = {
                            "run_id": run_id,
                            "scenario": sc_name,
                            "mode": args.mode,
                            "error": str(e)
                        }
                    finally:
                        if os.path.isfile(temp_res.name):
                            os.remove(temp_res.name)

                    # Stop sniffer & dissect PCAP
                    if sniffer:
                        sniffer.stop()
                        tcp_metrics = analyze(pcap_file, port=args.port)
                        record["pcap"] = rel_pcap
                        record["tcp"] = tcp_metrics
                    else:
                        record["pcap"] = None
                        record["tcp"] = None

                    # Write single fused record
                    log_result(record, "results/transfers.jsonl")

                time.sleep(0.5)

            # 3. Clear impairment before moving to next scenario
            clear_scenario(iface_name, ns=ns_name, dry_run=args.dry_run)

    except KeyboardInterrupt:
        print("\n[!] Execution interrupted by user.")
    finally:
        print("\n[*] Ensuring network interface is cleared of all impairments...")
        clear_scenario(iface_name, ns=ns_name, dry_run=args.dry_run)
        print("[✔] Benchmark finished. Summary data logged to results/transfers.jsonl.")


if __name__ == "__main__":
    main()
