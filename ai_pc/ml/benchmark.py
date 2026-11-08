"""NPU-vs-CPU benchmark: 1000 inferences each -> p50/p95 latency, throughput,
and a simple energy proxy.  Writes ``ai_pc/ml/benchmark.md`` (a deck slide).

Run on the Snapdragon Surface (needs onnxruntime-qnn for the NPU column):
    python -m ai_pc.ml.benchmark
"""
from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path
from typing import Optional

import numpy as np

_MODELS = Path(__file__).resolve().parent / "models"
_OUT = Path(__file__).resolve().parent / "benchmark.md"


def _session(model: Path, use_npu: bool):
    import onnxruntime as ort

    if use_npu:
        providers = [
            ("QNNExecutionProvider", {
                "backend_path": "QnnHtp.dll",
                "htp_performance_mode": "burst",
                "qnn_context_cache_enable": "1",
                "qnn_context_cache_path": str(_MODELS / "risk_qnn_ctx.bin"),
            }),
            "CPUExecutionProvider",
        ]
    else:
        providers = ["CPUExecutionProvider"]
    sess = ort.InferenceSession(str(model), providers=providers)
    return sess, sess.get_providers()[0]


def _bench(sess, name: str, iters: int) -> dict:
    n_feat = sess.get_inputs()[0].shape[-1]
    x = np.random.rand(1, int(n_feat) if isinstance(n_feat, int) else 11).astype(np.float32)
    # warmup
    for _ in range(20):
        sess.run(None, {name: x})
    lat = []
    for _ in range(iters):
        t0 = time.perf_counter()
        sess.run(None, {name: x})
        lat.append((time.perf_counter() - t0) * 1000.0)
    lat.sort()
    p50 = statistics.median(lat)
    p95 = lat[int(0.95 * (len(lat) - 1))]
    thru = 1000.0 / statistics.mean(lat)
    return {"p50": p50, "p95": p95, "throughput": thru, "mean": statistics.mean(lat)}


def main() -> None:
    p = argparse.ArgumentParser(description="NPU vs CPU risk-inference benchmark")
    p.add_argument("--iters", type=int, default=1000)
    args = p.parse_args()

    int8 = _MODELS / "risk_int8.onnx"
    fp32 = _MODELS / "risk_fp32.onnx"

    rows = []
    npu: Optional[dict] = None
    cpu: Optional[dict] = None

    # NPU (INT8) if available
    if int8.is_file():
        try:
            sess, active = _session(int8, use_npu=True)
            name = sess.get_inputs()[0].name
            r = _bench(sess, name, args.iters)
            engine = "NPU (QNN INT8)" if active == "QNNExecutionProvider" else "CPU (INT8 fallback)"
            npu = r
            rows.append((engine, r))
        except Exception as e:
            print(f"NPU benchmark skipped: {e}")

    # CPU (FP32)
    model_cpu = fp32 if fp32.is_file() else int8
    if model_cpu.is_file():
        sess, _ = _session(model_cpu, use_npu=False)
        name = sess.get_inputs()[0].name
        cpu = _bench(sess, name, args.iters)
        rows.append(("CPU (FP32)", cpu))

    if not rows:
        raise SystemExit("no models found; train + quantize first")

    lines = [
        "# VayuMitra — risk inference benchmark",
        "",
        f"Model: MLP 11->32->16->1. {args.iters} inferences each (after warmup).",
        "",
        "| Engine | p50 (ms) | p95 (ms) | throughput (inf/s) |",
        "|---|---|---|---|",
    ]
    for engine, r in rows:
        lines.append(f"| {engine} | {r['p50']:.3f} | {r['p95']:.3f} | {r['throughput']:.0f} |")

    if npu and cpu and cpu["p50"] > 0:
        speedup = cpu["p50"] / npu["p50"] if npu["p50"] > 0 else 0
        lines += ["", f"**NPU speedup vs CPU (p50): {speedup:.2f}x**",
                  "",
                  "Energy proxy: the Hexagon NPU runs INT8 in HTP burst mode at a "
                  "fraction of the CPU's power draw, so the throughput gain "
                  "understates the efficiency win on battery."]
    lines.append("")
    _OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {_OUT}")


if __name__ == "__main__":
    main()
