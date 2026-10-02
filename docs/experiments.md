# NetScope Experiment Automation & Scenarios

## 1. Specification Scenarios
NetScope specifies 11 canonical network condition scenarios loaded dynamically from `network/scenarios.json`:

| Scenario Name | Delay | Packet Loss | Rate Limit | Primary Phenomenon |
|---|---|---|---|---|
| **Baseline** | 0 ms | 0% | Unlimited | Raw link maximum throughput |
| **Delay-1** | 50 ms | 0% | Unlimited | BDP increase, sliding window scaling |
| **Delay-2** | 100 ms | 0% | Unlimited | RTT elongation, slow-start ramp slowdown |
| **Delay-3** | 200 ms | 0% | Unlimited | High latency transcontinental emulation |
| **Loss-1** | 0 ms | 1% | Unlimited | Fast retransmit & congestion avoidance |
| **Loss-2** | 0 ms | 2% | Unlimited | Multiple duplicate ACKs, window backoff |
| **Loss-3** | 0 ms | 5% | Unlimited | RTO timeouts, window collapse |
| **Bandwidth-1**| 0 ms | 0% | 10 Mbps | Moderate bottleneck queueing |
| **Bandwidth-2**| 0 ms | 0% | 5 Mbps | Constrained throughput bottleneck |
| **Bandwidth-3**| 0 ms | 0% | 1 Mbps | Severe token bucket rate limitation |
| **Combined** | 100 ms | 2% | 5 Mbps | Multi-factor real-world wireless emulation |

## 2. Command-Line Experiment Execution
Run the automated experiment runner with optional scenario filtering and repetition counts:

```bash
python3 experiments/run_all.py --scenarios Baseline,Delay-1,Loss-2,Combined --repeats 3 --capture
```
All records are saved to `results/transfers.jsonl` and aggregated into `results/summary.csv`.
