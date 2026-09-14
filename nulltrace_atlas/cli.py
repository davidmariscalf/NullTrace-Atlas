from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import DetectionConfig, detect_null_traces, load_csv, to_geojson


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nulltrace",
        description="Detect explainable, structurally surprising absences in spatiotemporal observations.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan = subparsers.add_parser("scan", help="scan a CSV for null traces")
    scan.add_argument("input", type=Path)
    scan.add_argument("--cadence", type=int, default=None, help="expected cadence in seconds")
    scan.add_argument("--threshold", type=float, default=0.70)
    scan.add_argument("--window", type=int, default=2, help="temporal evidence window in slots")
    scan.add_argument("--peer-radius-km", type=float, default=5.0)
    scan.add_argument("--min-evidence", type=int, default=2)
    scan.add_argument("--temporal-weight", type=float, default=0.65)
    scan.add_argument("--peer-weight", type=float, default=0.35)
    scan.add_argument("--json", dest="json_path", type=Path)
    scan.add_argument("--geojson", dest="geojson_path", type=Path)
    return parser


def _print_traces(traces: list[dict]) -> None:
    if not traces:
        print("No null traces met the configured threshold.")
        return
    print(f"Detected {len(traces)} null trace(s):")
    for trace in traces:
        peer = trace["mean_peer_support"]
        peer_text = "n/a" if peer is None else f"{peer:.2f}"
        print(
            f"- {trace['entity']}  {trace['start']} -> {trace['end']}  "
            f"slots={trace['missing_slots']} score={trace['mean_score']:.3f} "
            f"temporal={trace['mean_temporal_support']:.2f} peer={peer_text} "
            f"evidence={trace['evidence_count']}"
        )


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command != "scan":
        return 2

    observations = load_csv(args.input)
    config = DetectionConfig(
        cadence_seconds=args.cadence,
        threshold=args.threshold,
        temporal_window=args.window,
        peer_radius_km=args.peer_radius_km,
        temporal_weight=args.temporal_weight,
        peer_weight=args.peer_weight,
        min_evidence=args.min_evidence,
    )
    traces = detect_null_traces(observations, config)
    _print_traces(traces)

    if args.json_path:
        args.json_path.write_text(json.dumps(traces, indent=2) + "\n", encoding="utf-8")
        print(f"JSON written to {args.json_path}")
    if args.geojson_path:
        args.geojson_path.write_text(
            json.dumps(to_geojson(traces), indent=2) + "\n", encoding="utf-8"
        )
        print(f"GeoJSON written to {args.geojson_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
