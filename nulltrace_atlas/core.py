from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Iterable


@dataclass(frozen=True)
class Observation:
    entity: str
    timestamp: datetime
    lat: float | None = None
    lon: float | None = None


@dataclass(frozen=True)
class DetectionConfig:
    cadence_seconds: int | None = None
    threshold: float = 0.70
    temporal_window: int = 2
    peer_radius_km: float = 5.0
    temporal_weight: float = 0.65
    peer_weight: float = 0.35
    min_evidence: int = 2


def _parse_timestamp(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_csv(path: str | Path) -> list[Observation]:
    observations: list[Observation] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"entity", "timestamp"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("CSV must contain entity and timestamp columns")
        for row_number, row in enumerate(reader, start=2):
            entity = (row.get("entity") or "").strip()
            timestamp = (row.get("timestamp") or "").strip()
            if not entity or not timestamp:
                raise ValueError(f"row {row_number}: entity and timestamp are required")
            try:
                lat = _optional_float(row.get("lat"))
                lon = _optional_float(row.get("lon"))
                observations.append(
                    Observation(
                        entity=entity,
                        timestamp=_parse_timestamp(timestamp),
                        lat=lat,
                        lon=lon,
                    )
                )
            except ValueError as exc:
                raise ValueError(f"row {row_number}: {exc}") from exc
    return observations


def _optional_float(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    return float(value)


def _infer_cadence(times: list[datetime]) -> int | None:
    if len(times) < 2:
        return None
    deltas = [
        int((later - earlier).total_seconds())
        for earlier, later in zip(times, times[1:])
        if later > earlier
    ]
    if not deltas:
        return None
    return max(1, int(round(median(deltas))))


def _entity_coordinate(observations: list[Observation]) -> tuple[float, float] | None:
    coords = [(o.lat, o.lon) for o in observations if o.lat is not None and o.lon is not None]
    if not coords:
        return None
    return median([x[0] for x in coords]), median([x[1] for x in coords])


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def detect_null_traces(
    observations: Iterable[Observation], config: DetectionConfig | None = None
) -> list[dict]:
    cfg = config or DetectionConfig()
    if not 0 <= cfg.threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")
    if cfg.temporal_window < 1:
        raise ValueError("temporal_window must be >= 1")
    if cfg.cadence_seconds is not None and cfg.cadence_seconds < 1:
        raise ValueError("cadence_seconds must be >= 1")
    if cfg.temporal_weight < 0 or cfg.peer_weight < 0:
        raise ValueError("weights must be non-negative")
    if cfg.temporal_weight + cfg.peer_weight == 0:
        raise ValueError("at least one weight must be positive")

    by_entity: dict[str, list[Observation]] = {}
    for obs in observations:
        by_entity.setdefault(obs.entity, []).append(obs)
    for rows in by_entity.values():
        rows.sort(key=lambda o: o.timestamp)

    if not by_entity:
        return []

    coordinates = {entity: _entity_coordinate(rows) for entity, rows in by_entity.items()}
    observed_times = {entity: {o.timestamp for o in rows} for entity, rows in by_entity.items()}
    ranges = {
        entity: (rows[0].timestamp, rows[-1].timestamp)
        for entity, rows in by_entity.items()
        if rows
    }

    peers: dict[str, list[str]] = {entity: [] for entity in by_entity}
    for entity, coord in coordinates.items():
        if coord is None:
            continue
        for other, other_coord in coordinates.items():
            if other == entity or other_coord is None:
                continue
            if _haversine_km(coord, other_coord) <= cfg.peer_radius_km:
                peers[entity].append(other)

    candidates_by_entity: dict[str, list[dict]] = {}

    for entity, rows in by_entity.items():
        unique_times = sorted(observed_times[entity])
        cadence = cfg.cadence_seconds or _infer_cadence(unique_times)
        if cadence is None or len(unique_times) < 2:
            continue

        step = timedelta(seconds=cadence)
        start, end = unique_times[0], unique_times[-1]
        expected: list[datetime] = []
        cursor = start
        while cursor <= end:
            expected.append(cursor)
            cursor += step

        observed = observed_times[entity]
        candidates: list[dict] = []
        for idx, slot in enumerate(expected):
            if slot in observed:
                continue

            temporal_possible = 0
            temporal_hits = 0
            for offset in range(1, cfg.temporal_window + 1):
                for neighbor_idx in (idx - offset, idx + offset):
                    if 0 <= neighbor_idx < len(expected):
                        temporal_possible += 1
                        if expected[neighbor_idx] in observed:
                            temporal_hits += 1
            temporal_support = temporal_hits / temporal_possible if temporal_possible else 0.0

            eligible_peers: list[str] = []
            peer_hits = 0
            for peer in peers[entity]:
                peer_start, peer_end = ranges[peer]
                if peer_start <= slot <= peer_end:
                    eligible_peers.append(peer)
                    if slot in observed_times[peer]:
                        peer_hits += 1
            peer_support = peer_hits / len(eligible_peers) if eligible_peers else None

            weighted_total = cfg.temporal_weight * temporal_support
            weight_sum = cfg.temporal_weight
            if peer_support is not None:
                weighted_total += cfg.peer_weight * peer_support
                weight_sum += cfg.peer_weight
            score = weighted_total / weight_sum if weight_sum else 0.0
            evidence_count = temporal_hits + peer_hits

            if score >= cfg.threshold and evidence_count >= cfg.min_evidence:
                candidates.append(
                    {
                        "timestamp": slot,
                        "score": score,
                        "temporal_support": temporal_support,
                        "peer_support": peer_support,
                        "evidence_count": evidence_count,
                        "cadence_seconds": cadence,
                    }
                )

        candidates_by_entity[entity] = candidates

    traces: list[dict] = []
    for entity, candidates in candidates_by_entity.items():
        if not candidates:
            continue
        cadence = candidates[0]["cadence_seconds"]
        step = timedelta(seconds=cadence)
        run: list[dict] = []
        for candidate in candidates:
            if not run or candidate["timestamp"] - run[-1]["timestamp"] == step:
                run.append(candidate)
            else:
                traces.append(_trace_from_run(entity, run, coordinates[entity]))
                run = [candidate]
        if run:
            traces.append(_trace_from_run(entity, run, coordinates[entity]))

    traces.sort(key=lambda t: (-t["max_score"], t["entity"], t["start"]))
    return traces


def _trace_from_run(
    entity: str, run: list[dict], coord: tuple[float, float] | None
) -> dict:
    peer_values = [item["peer_support"] for item in run if item["peer_support"] is not None]
    trace = {
        "entity": entity,
        "start": _iso(run[0]["timestamp"]),
        "end": _iso(run[-1]["timestamp"]),
        "missing_slots": len(run),
        "mean_score": round(sum(item["score"] for item in run) / len(run), 6),
        "max_score": round(max(item["score"] for item in run), 6),
        "mean_temporal_support": round(
            sum(item["temporal_support"] for item in run) / len(run), 6
        ),
        "mean_peer_support": (
            round(sum(peer_values) / len(peer_values), 6) if peer_values else None
        ),
        "evidence_count": sum(item["evidence_count"] for item in run),
        "cadence_seconds": run[0]["cadence_seconds"],
    }
    if coord is not None:
        trace["lat"], trace["lon"] = coord
    return trace


def to_geojson(traces: Iterable[dict]) -> dict:
    features = []
    for trace in traces:
        if "lat" not in trace or "lon" not in trace:
            continue
        properties = {k: v for k, v in trace.items() if k not in {"lat", "lon"}}
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [trace["lon"], trace["lat"]],
                },
                "properties": properties,
            }
        )
    return {"type": "FeatureCollection", "features": features}
