from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__
from .core import DetectionConfig, analyze_observations, load_observations, to_geojson


def _add_detection_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cadence", type=int, default=None, help="expected cadence in seconds")
    parser.add_argument(
        "--tolerance",
        type=int,
        default=None,
        help="timestamp tolerance in seconds (default: inferred from cadence)",
    )
    parser.add_argument(
        "--tolerance-fraction",
        type=float,
        default=0.15,
        help="automatic tolerance as fraction of cadence (default: 0.15)",
    )
    parser.add_argument(
        "--max-cadence-multiple",
        type=int,
        default=12,
        help="largest missing interval multiple considered during cadence inference",
    )
    parser.add_argument("--threshold", type=float, default=0.70)
    parser.add_argument("--window", type=int, default=2, help="temporal evidence window in slots")
    parser.add_argument("--peer-radius-km", type=float, default=5.0)
    parser.add_argument("--min-evidence", type=int, default=2)
    parser.add_argument("--min-observations", type=int, default=3)
    parser.add_argument("--temporal-weight", type=float, default=0.55)
    parser.add_argument("--peer-weight", type=float, default=0.30)
    parser.add_argument("--regularity-weight", type=float, default=0.15)
    parser.add_argument(
        "--max-expected-slots",
        type=int,
        default=100_000,
        help="safety bound for reconstructed grids per entity",
    )


def _config_from_args(args: argparse.Namespace) -> DetectionConfig:
    return DetectionConfig(
        cadence_seconds=args.cadence,
        cadence_tolerance_seconds=args.tolerance,
        cadence_tolerance_fraction=args.tolerance_fraction,
        max_cadence_multiple=args.max_cadence_multiple,
        threshold=args.threshold,
        temporal_window=args.window,
        peer_radius_km=args.peer_radius_km,
        temporal_weight=args.temporal_weight,
        peer_weight=args.peer_weight,
        regularity_weight=args.regularity_weight,
        min_evidence=args.min_evidence,
        min_observations=args.min_observations,
        max_expected_slots=args.max_expected_slots,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nulltrace",
        description="Detect explainable, structurally surprising absences in spatiotemporal observations.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="detect null traces in CSV or JSONL observations")
    scan.add_argument("input", type=Path)
    _add_detection_options(scan)
    scan.add_argument("--json", dest="json_path", type=Path, help="write traces as JSON")
    scan.add_argument("--geojson", dest="geojson_path", type=Path, help="write geocoded traces")
    scan.add_argument("--slots-json", dest="slots_path", type=Path, help="write scored missing slots")
    scan.add_argument(
        "--analysis-json",
        dest="analysis_path",
        type=Path,
        help="write profiles, slots, traces and summary in one JSON document",
    )
    scan.add_argument("--quiet", action="store_true", help="suppress human-readable output")

    profile = subparsers.add_parser(
        "profile", help="infer cadence, tolerance, coverage and regularity without flagging gaps"
    )
    profile.add_argument("input", type=Path)
    _add_detection_options(profile)
    profile.add_argument("--json", dest="json_path", type=Path)

    return parser


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _print_traces(traces: list[dict], summary: dict) -> None:
    if not traces:
        print("No null traces met the configured threshold.")
        return
    print(
        f"Detected {summary['null_traces']} null trace(s) across "
        f"{summary['entities_with_traces']} entit(ies):"
    )
    for trace in traces:
        peer = trace["mean_peer_support"]
        peer_text = "n/a" if peer is None else f"{peer:.2f}"
        print(
            f"- {trace['entity']}  {trace['start']} -> {trace['end']}  "
            f"slots={trace['missing_slots']} score={trace['mean_score']:.3f} "
            f"temporal={trace['mean_temporal_support']:.2f} peer={peer_text} "
            f"regularity={trace['regularity']:.2f} evidence={trace['evidence_count']} "
            f"profile={trace['evidence_profile']} id={trace['trace_id']}"
        )


def _print_profiles(profiles: list[dict]) -> None:
    if not profiles:
        print("No entities had enough observations to profile.")
        return
    print(f"Profiled {len(profiles)} entit(ies):")
    for profile in profiles:
        print(
            f"- {profile['entity']} cadence={profile['cadence_seconds']}s "
            f"tolerance={profile['tolerance_seconds']}s "
            f"coverage={profile['coverage']:.3f} regularity={profile['regularity']:.3f} "
            f"observed={profile['observed_slots']}/{profile['expected_slots']}"
        )


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    observations = load_observations(args.input)
    analysis = analyze_observations(observations, _config_from_args(args))

    if args.command == "profile":
        _print_profiles(analysis["profiles"])
        if args.json_path:
            _write_json(args.json_path, analysis["profiles"])
            print(f"JSON written to {args.json_path}")
        return 0

    if not args.quiet:
        _print_traces(analysis["traces"], analysis["summary"])

    if args.json_path:
        _write_json(args.json_path, analysis["traces"])
        if not args.quiet:
            print(f"JSON written to {args.json_path}")
    if args.geojson_path:
        _write_json(args.geojson_path, to_geojson(analysis["traces"]))
        if not args.quiet:
            print(f"GeoJSON written to {args.geojson_path}")
    if args.slots_path:
        _write_json(args.slots_path, analysis["slots"])
        if not args.quiet:
            print(f"Slot evidence written to {args.slots_path}")
    if args.analysis_path:
        _write_json(args.analysis_path, analysis)
        if not args.quiet:
            print(f"Analysis written to {args.analysis_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
