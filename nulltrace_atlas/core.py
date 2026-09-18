from __future__ import annotations

import bisect
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Observation:
    entity: str
    timestamp: datetime
    lat: float | None = None
    lon: float | None = None
    source: str | None = None
    quality: float = 1.0


@dataclass(frozen=True)
class DetectionConfig:
    cadence_seconds: int | None = None
    cadence_tolerance_seconds: int | None = None
    cadence_tolerance_fraction: float = 0.15
    max_cadence_multiple: int = 12
    threshold: float = 0.70
    temporal_window: int = 2
    peer_radius_km: float = 5.0
    temporal_weight: float = 0.55
    peer_weight: float = 0.30
    regularity_weight: float = 0.15
    min_evidence: int = 2
    min_observations: int = 3
    max_expected_slots: int = 100_000


@dataclass(frozen=True)
class EntityProfile:
    entity: str
    cadence_seconds: int
    tolerance_seconds: int
    first: datetime
    last: datetime
    observations: int
    expected_slots: int
    observed_slots: int
    coverage: float
    regularity: float
    lat: float | None
    lon: float | None


def _parse_timestamp(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _optional_float(value: str | None) -> float | None:
    if value is None or not str(value).strip():
        return None
    return float(value)


def _validate_observation(obs: Observation, row_label: str = "observation") -> Observation:
    entity = obs.entity.strip()
    if not entity:
        raise ValueError(f"{row_label}: entity is required")
    ts = obs.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts = ts.astimezone(timezone.utc)
    lat, lon = obs.lat, obs.lon
    if (lat is None) != (lon is None):
        raise ValueError(f"{row_label}: lat and lon must be provided together")
    if lat is not None and not -90 <= lat <= 90:
        raise ValueError(f"{row_label}: lat must be between -90 and 90")
    if lon is not None and not -180 <= lon <= 180:
        raise ValueError(f"{row_label}: lon must be between -180 and 180")
    if not 0 <= obs.quality <= 1:
        raise ValueError(f"{row_label}: quality must be between 0 and 1")
    return Observation(entity, ts, lat, lon, obs.source, float(obs.quality))


def _observation_from_mapping(row: dict, row_label: str) -> Observation:
    entity = str(row.get("entity") or "").strip()
    timestamp = str(row.get("timestamp") or "").strip()
    if not entity or not timestamp:
        raise ValueError(f"{row_label}: entity and timestamp are required")
    try:
        quality_raw = row.get("quality", 1.0)
        quality = 1.0 if quality_raw in (None, "") else float(quality_raw)
        return _validate_observation(
            Observation(
                entity=entity,
                timestamp=_parse_timestamp(timestamp),
                lat=_optional_float(row.get("lat")),
                lon=_optional_float(row.get("lon")),
                source=(str(row.get("source")).strip() if row.get("source") not in (None, "") else None),
                quality=quality,
            ),
            row_label,
        )
    except (TypeError, ValueError) as exc:
        if str(exc).startswith(f"{row_label}:"):
            raise
        raise ValueError(f"{row_label}: {exc}") from exc


def load_csv(path: str | Path) -> list[Observation]:
    observations: list[Observation] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"entity", "timestamp"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("CSV must contain entity and timestamp columns")
        for row_number, row in enumerate(reader, start=2):
            observations.append(_observation_from_mapping(row, f"row {row_number}"))
    return observations


def load_jsonl(path: str | Path) -> list[Observation]:
    observations: list[Observation] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"line {line_number}: each JSONL record must be an object")
            observations.append(_observation_from_mapping(row, f"line {line_number}"))
    return observations


def load_observations(path: str | Path) -> list[Observation]:
    suffix = Path(path).suffix.lower()
    if suffix in {".jsonl", ".ndjson"}:
        return load_jsonl(path)
    return load_csv(path)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _median_longitude(values: Sequence[float]) -> float:
    """Return a dateline-safe median longitude.

    Longitudes are unwrapped around the first observation before taking the
    median. This keeps nearby values such as 179E and 179W adjacent instead of
    averaging them through Greenwich.
    """
    reference = float(values[0])
    unwrapped = [
        reference + ((float(value) - reference + 180.0) % 360.0 - 180.0)
        for value in values
    ]
    result = float(median(unwrapped))
    normalized = ((result + 180.0) % 360.0) - 180.0
    return 180.0 if normalized == -180.0 and result > 0 else normalized


def _entity_coordinate(observations: Sequence[Observation]) -> tuple[float, float] | None:
    coords = [(o.lat, o.lon) for o in observations if o.lat is not None and o.lon is not None]
    if not coords:
        return None
    return median([x[0] for x in coords]), _median_longitude([x[1] for x in coords])


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _validate_config(cfg: DetectionConfig) -> None:
    if cfg.cadence_seconds is not None and cfg.cadence_seconds < 1:
        raise ValueError("cadence_seconds must be >= 1")
    if cfg.cadence_tolerance_seconds is not None and cfg.cadence_tolerance_seconds < 0:
        raise ValueError("cadence_tolerance_seconds must be >= 0")
    if not 0 <= cfg.cadence_tolerance_fraction < 0.5:
        raise ValueError("cadence_tolerance_fraction must be in [0, 0.5)")
    if cfg.max_cadence_multiple < 1:
        raise ValueError("max_cadence_multiple must be >= 1")
    if not 0 <= cfg.threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")
    if cfg.temporal_window < 1:
        raise ValueError("temporal_window must be >= 1")
    if cfg.peer_radius_km < 0:
        raise ValueError("peer_radius_km must be >= 0")
    if cfg.min_evidence < 0:
        raise ValueError("min_evidence must be >= 0")
    if cfg.min_observations < 2:
        raise ValueError("min_observations must be >= 2")
    if cfg.max_expected_slots < 2:
        raise ValueError("max_expected_slots must be >= 2")
    weights = (cfg.temporal_weight, cfg.peer_weight, cfg.regularity_weight)
    if any(weight < 0 for weight in weights):
        raise ValueError("weights must be non-negative")
    if sum(weights) == 0:
        raise ValueError("at least one weight must be positive")


def _infer_cadence(times: Sequence[datetime], cfg: DetectionConfig) -> int | None:
    if len(times) < 2:
        return None
    deltas = [
        (later - earlier).total_seconds()
        for earlier, later in zip(times, times[1:])
        if later > earlier
    ]
    if not deltas:
        return None

    candidates: set[int] = set()
    for delta in deltas:
        for multiple in range(1, cfg.max_cadence_multiple + 1):
            candidate = int(round(delta / multiple))
            if candidate >= 1:
                candidates.add(candidate)

    best: tuple[float, int] | None = None
    tolerance_fraction = cfg.cadence_tolerance_fraction
    for candidate in candidates:
        hits = 0
        residual_sum = 0.0
        bases: list[float] = []
        for delta in deltas:
            multiple = max(1, int(round(delta / candidate)))
            if multiple > cfg.max_cadence_multiple:
                continue
            residual = abs(delta - multiple * candidate)
            allowed = max(1.0, candidate * tolerance_fraction)
            if residual <= allowed:
                hits += 1
                residual_sum += residual / allowed
                bases.append(delta / multiple)
        support = hits / len(deltas)
        if not bases:
            continue
        mean_residual = residual_sum / hits if hits else 1.0
        score = support - 0.01 * mean_residual
        marker = (score, candidate)
        if best is None or marker > best:
            best = marker

    if best is None or best[0] < 0.50:
        return max(1, int(round(median(deltas))))

    seed = best[1]
    normalized = []
    for delta in deltas:
        multiple = max(1, int(round(delta / seed)))
        if multiple <= cfg.max_cadence_multiple:
            allowed = max(1.0, seed * tolerance_fraction)
            if abs(delta - multiple * seed) <= allowed:
                normalized.append(delta / multiple)
    return max(1, int(round(median(normalized)))) if normalized else seed


def _slot_tolerance(cadence: int, cfg: DetectionConfig) -> int:
    if cfg.cadence_tolerance_seconds is not None:
        return min(cfg.cadence_tolerance_seconds, max(0, cadence // 2 - 1))
    inferred = max(1, int(round(cadence * cfg.cadence_tolerance_fraction)))
    return min(inferred, max(0, cadence // 2 - 1))


def _grid_mapping(
    times: Sequence[datetime], cadence: int, tolerance: int, max_expected_slots: int
) -> tuple[datetime, int, set[int], float]:
    start = times[0]
    observed_indices: set[int] = set()
    residual_hits = 0
    for ts in times:
        offset = (ts - start).total_seconds() / cadence
        index = max(0, int(round(offset)))
        target = start + timedelta(seconds=index * cadence)
        if abs((ts - target).total_seconds()) <= tolerance:
            observed_indices.add(index)
            residual_hits += 1

    if not observed_indices:
        observed_indices.add(0)
    last_idx = max(observed_indices)
    expected_slots = last_idx + 1
    if expected_slots > max_expected_slots:
        raise ValueError(
            f"entity grid would contain {expected_slots} expected slots; "
            f"increase max_expected_slots if this is intentional"
        )
    regularity = residual_hits / len(times) if times else 0.0
    return start, last_idx, observed_indices, regularity


def _nearest_time_hit(times: Sequence[datetime], target: datetime, tolerance: int) -> bool:
    if not times:
        return False
    pos = bisect.bisect_left(times, target)
    for idx in (pos - 1, pos):
        if 0 <= idx < len(times):
            if abs((times[idx] - target).total_seconds()) <= tolerance:
                return True
    return False


def _build_profiles(
    by_entity: dict[str, list[Observation]], cfg: DetectionConfig
) -> tuple[dict[str, EntityProfile], dict[str, set[int]], dict[str, datetime]]:
    profiles: dict[str, EntityProfile] = {}
    mapped_slots: dict[str, set[int]] = {}
    anchors: dict[str, datetime] = {}
    for entity, rows in by_entity.items():
        unique_times = sorted({row.timestamp for row in rows})
        if len(unique_times) < cfg.min_observations:
            continue
        cadence = cfg.cadence_seconds or _infer_cadence(unique_times, cfg)
        if cadence is None:
            continue
        tolerance = _slot_tolerance(cadence, cfg)
        anchor, last_idx, observed_indices, regularity = _grid_mapping(
            unique_times, cadence, tolerance, cfg.max_expected_slots
        )
        expected_slots = last_idx + 1
        coord = _entity_coordinate(rows)
        profiles[entity] = EntityProfile(
            entity=entity,
            cadence_seconds=cadence,
            tolerance_seconds=tolerance,
            first=unique_times[0],
            last=unique_times[-1],
            observations=len(unique_times),
            expected_slots=expected_slots,
            observed_slots=len(observed_indices),
            coverage=len(observed_indices) / expected_slots if expected_slots else 0.0,
            regularity=regularity,
            lat=coord[0] if coord else None,
            lon=coord[1] if coord else None,
        )
        mapped_slots[entity] = observed_indices
        anchors[entity] = anchor
    return profiles, mapped_slots, anchors


def profile_observations(
    observations: Iterable[Observation], config: DetectionConfig | None = None
) -> list[dict]:
    cfg = config or DetectionConfig()
    _validate_config(cfg)
    by_entity: dict[str, list[Observation]] = {}
    for index, raw in enumerate(observations, start=1):
        obs = _validate_observation(raw, f"observation {index}")
        by_entity.setdefault(obs.entity, []).append(obs)
    for rows in by_entity.values():
        rows.sort(key=lambda o: o.timestamp)
    profiles, _, _ = _build_profiles(by_entity, cfg)
    return [_profile_to_dict(profiles[key]) for key in sorted(profiles)]


def _profile_to_dict(profile: EntityProfile) -> dict:
    result = {
        "entity": profile.entity,
        "cadence_seconds": profile.cadence_seconds,
        "tolerance_seconds": profile.tolerance_seconds,
        "first": _iso(profile.first),
        "last": _iso(profile.last),
        "observations": profile.observations,
        "expected_slots": profile.expected_slots,
        "observed_slots": profile.observed_slots,
        "coverage": round(profile.coverage, 6),
        "regularity": round(profile.regularity, 6),
    }
    if profile.lat is not None and profile.lon is not None:
        result["lat"] = profile.lat
        result["lon"] = profile.lon
    return result


def analyze_observations(
    observations: Iterable[Observation], config: DetectionConfig | None = None
) -> dict:
    cfg = config or DetectionConfig()
    _validate_config(cfg)

    by_entity: dict[str, list[Observation]] = {}
    for index, raw in enumerate(observations, start=1):
        obs = _validate_observation(raw, f"observation {index}")
        by_entity.setdefault(obs.entity, []).append(obs)
    for rows in by_entity.values():
        rows.sort(key=lambda o: o.timestamp)
    if not by_entity:
        return {"profiles": [], "slots": [], "traces": [], "summary": _summary([], [], [])}

    profiles, mapped_slots, anchors = _build_profiles(by_entity, cfg)
    coordinates = {
        entity: (profile.lat, profile.lon)
        if profile.lat is not None and profile.lon is not None
        else None
        for entity, profile in profiles.items()
    }
    raw_times = {
        entity: sorted({row.timestamp for row in rows})
        for entity, rows in by_entity.items()
    }

    peers: dict[str, list[str]] = {entity: [] for entity in profiles}
    for entity, coord in coordinates.items():
        if coord is None:
            continue
        for other, other_coord in coordinates.items():
            if other == entity or other_coord is None:
                continue
            if _haversine_km(coord, other_coord) <= cfg.peer_radius_km:
                peers[entity].append(other)

    slots: list[dict] = []
    for entity, profile in profiles.items():
        observed_indices = mapped_slots[entity]
        anchor = anchors[entity]
        for index in range(profile.expected_slots):
            if index in observed_indices:
                continue
            slot = anchor + timedelta(seconds=index * profile.cadence_seconds)

            temporal_possible = 0
            temporal_hits = 0
            for offset in range(1, cfg.temporal_window + 1):
                for neighbor_index in (index - offset, index + offset):
                    if 0 <= neighbor_index < profile.expected_slots:
                        temporal_possible += 1
                        if neighbor_index in observed_indices:
                            temporal_hits += 1
            temporal_support = (
                temporal_hits / temporal_possible if temporal_possible else 0.0
            )

            peer_hits = 0
            eligible_peers = 0
            peer_numerator = 0.0
            peer_denominator = 0.0
            for peer in peers[entity]:
                peer_profile = profiles[peer]
                tolerance = peer_profile.tolerance_seconds
                if not (
                    peer_profile.first - timedelta(seconds=tolerance)
                    <= slot
                    <= peer_profile.last + timedelta(seconds=tolerance)
                ):
                    continue
                reliability = max(
                    0.05, peer_profile.coverage * peer_profile.regularity
                )
                eligible_peers += 1
                peer_denominator += reliability
                if _nearest_time_hit(raw_times[peer], slot, tolerance):
                    peer_hits += 1
                    peer_numerator += reliability
            peer_support = (
                peer_numerator / peer_denominator if peer_denominator else None
            )

            weighted_total = cfg.temporal_weight * temporal_support
            weight_sum = cfg.temporal_weight
            if peer_support is not None:
                weighted_total += cfg.peer_weight * peer_support
                weight_sum += cfg.peer_weight
            weighted_total += cfg.regularity_weight * profile.regularity
            weight_sum += cfg.regularity_weight
            score = weighted_total / weight_sum if weight_sum else 0.0
            evidence_count = temporal_hits + peer_hits

            if score >= cfg.threshold and evidence_count >= cfg.min_evidence:
                slots.append(
                    {
                        "entity": entity,
                        "timestamp": _iso(slot),
                        "slot_index": index,
                        "score": round(score, 6),
                        "temporal_support": round(temporal_support, 6),
                        "peer_support": (
                            round(peer_support, 6) if peer_support is not None else None
                        ),
                        "regularity": round(profile.regularity, 6),
                        "evidence_count": evidence_count,
                        "temporal_hits": temporal_hits,
                        "peer_hits": peer_hits,
                        "eligible_peers": eligible_peers,
                        "cadence_seconds": profile.cadence_seconds,
                        "tolerance_seconds": profile.tolerance_seconds,
                    }
                )

    slots.sort(key=lambda s: (s["entity"], s["timestamp"]))
    traces = _merge_slots(slots, profiles)
    profile_dicts = [_profile_to_dict(profiles[key]) for key in sorted(profiles)]
    return {
        "profiles": profile_dicts,
        "slots": slots,
        "traces": traces,
        "summary": _summary(profile_dicts, slots, traces),
    }


def _merge_slots(slots: list[dict], profiles: dict[str, EntityProfile]) -> list[dict]:
    by_entity: dict[str, list[dict]] = {}
    for slot in slots:
        by_entity.setdefault(slot["entity"], []).append(slot)

    traces: list[dict] = []
    for entity, candidates in by_entity.items():
        candidates.sort(key=lambda s: s["slot_index"])
        run: list[dict] = []
        for candidate in candidates:
            if not run or candidate["slot_index"] == run[-1]["slot_index"] + 1:
                run.append(candidate)
            else:
                traces.append(_trace_from_run(entity, run, profiles[entity]))
                run = [candidate]
        if run:
            traces.append(_trace_from_run(entity, run, profiles[entity]))

    traces.sort(key=lambda t: (-t["max_score"], t["entity"], t["start"]))
    return traces


def _trace_from_run(entity: str, run: list[dict], profile: EntityProfile) -> dict:
    peer_values = [item["peer_support"] for item in run if item["peer_support"] is not None]
    start, end = run[0]["timestamp"], run[-1]["timestamp"]
    trace_id = hashlib.sha256(
        f"{entity}|{start}|{end}|{profile.cadence_seconds}".encode("utf-8")
    ).hexdigest()[:16]
    peer_confirmed = any(item["peer_hits"] > 0 for item in run)
    temporal_confirmed = any(item["temporal_hits"] > 0 for item in run)
    if peer_confirmed and temporal_confirmed:
        evidence_profile = "mixed"
    elif peer_confirmed:
        evidence_profile = "peer-confirmed"
    else:
        evidence_profile = "temporal-only"

    trace = {
        "trace_id": trace_id,
        "entity": entity,
        "start": start,
        "end": end,
        "missing_slots": len(run),
        "duration_seconds": len(run) * profile.cadence_seconds,
        "mean_score": round(sum(item["score"] for item in run) / len(run), 6),
        "max_score": round(max(item["score"] for item in run), 6),
        "mean_temporal_support": round(
            sum(item["temporal_support"] for item in run) / len(run), 6
        ),
        "mean_peer_support": (
            round(sum(peer_values) / len(peer_values), 6) if peer_values else None
        ),
        "regularity": round(profile.regularity, 6),
        "coverage": round(profile.coverage, 6),
        "evidence_count": sum(item["evidence_count"] for item in run),
        "peer_hits": sum(item["peer_hits"] for item in run),
        "eligible_peer_slots": sum(item["eligible_peers"] for item in run),
        "evidence_profile": evidence_profile,
        "cadence_seconds": profile.cadence_seconds,
        "tolerance_seconds": profile.tolerance_seconds,
    }
    if profile.lat is not None and profile.lon is not None:
        trace["lat"], trace["lon"] = profile.lat, profile.lon
    return trace


def _summary(profiles: list[dict], slots: list[dict], traces: list[dict]) -> dict:
    return {
        "entities_profiled": len(profiles),
        "candidate_slots": len(slots),
        "null_traces": len(traces),
        "entities_with_traces": len({trace["entity"] for trace in traces}),
    }


def detect_null_slots(
    observations: Iterable[Observation], config: DetectionConfig | None = None
) -> list[dict]:
    return analyze_observations(observations, config)["slots"]


def detect_null_traces(
    observations: Iterable[Observation], config: DetectionConfig | None = None
) -> list[dict]:
    return analyze_observations(observations, config)["traces"]


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
