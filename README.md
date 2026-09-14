# NullTrace Atlas

**Map what should have been observed, but was not.**

NullTrace Atlas is an explainable negative evidence engine for sparse spatiotemporal event streams. It reconstructs an expected observation process, identifies missing slots that are unusually well supported by surrounding evidence, merges contiguous gaps into deterministic **null traces**, and exports the evidence behind every result.

It is designed for cases where the *shape of missing data* matters: environmental sensors, biodiversity observations, transit telemetry, telescope logs, infrastructure monitoring, archival feeds, citizen science and other repeated observation systems.

## What makes it unusual

A normal missing data tool starts with rows that already exist and asks which fields are null. NullTrace Atlas starts with the observation process itself and asks:

> Given this entity's cadence, timing regularity, neighbouring observations and nearby peers, where should an observation probably have existed but did not?

It never turns absence into an event and never claims to know the cause of a gap.

## Core concepts

* **Expected slot**: a timestamp implied by the inferred or configured cadence.
* **Supported absence**: an expected slot that is missing but has enough surrounding evidence.
* **Null trace**: one or more consecutive supported absences for the same entity.
* **Evidence profile**: whether a trace is supported temporally, by nearby peers, or by both.

## Version 1.0

The v1 engine includes:

* robust cadence inference that can recover the base cadence through multi slot gaps
* timestamp jitter tolerance instead of exact timestamp matching
* temporal evidence around each missing slot
* geodesic peer discovery with reliability weighted peer support
* entity coverage and timing regularity profiles
* deterministic trace IDs
* contiguous trace merging
* CSV, JSONL and NDJSON input
* JSON, slot level JSON, full analysis JSON and GeoJSON output
* a dependency free Python API and CLI
* bounded grid reconstruction to prevent accidental memory explosions
* validation for timestamps, coordinates and quality fields

## Installation

Requires Python 3.10 or newer and has no runtime dependencies.

```bash
python -m pip install -e .
```

## Input

CSV:

```csv
entity,timestamp,lat,lon,source,quality
alpha,2026-01-01T00:00:00Z,40.4168,-3.7038,station-feed,1.0
alpha,2026-01-01T01:00:12Z,40.4168,-3.7038,station-feed,1.0
beta,2026-01-01T00:00:04Z,40.4200,-3.7000,station-feed,0.9
```

JSONL is also accepted:

```json
{"entity":"alpha","timestamp":"2026-01-01T00:00:00Z","lat":40.4168,"lon":-3.7038}
{"entity":"alpha","timestamp":"2026-01-01T01:00:08Z","lat":40.4168,"lon":-3.7038}
```

Required fields are `entity` and `timestamp`. `lat` and `lon` are optional but must appear together. `source` and `quality` are optional metadata; quality must be between 0 and 1.

## Quick start

Let NullTrace infer cadence and tolerance:

```bash
nulltrace scan examples/demo.csv
```

Use an explicit hourly cadence and export every representation:

```bash
nulltrace scan examples/demo.csv \
  --cadence 3600 \
  --threshold 0.70 \
  --json traces.json \
  --slots-json slots.json \
  --geojson traces.geojson \
  --analysis-json analysis.json
```

Inspect the reconstructed observation process without flagging gaps:

```bash
nulltrace profile examples/demo.csv
```

## Detection model

For each entity, NullTrace Atlas:

1. infers a base cadence from integer multiples of observed time deltas, unless cadence is supplied explicitly;
2. maps observations onto an expected grid with a bounded timestamp tolerance;
3. measures how consistently observations align to that grid;
4. scores missing slots from temporal support, optional nearby peer support and source regularity;
5. requires both a score threshold and a concrete evidence count;
6. merges adjacent accepted slots into a trace.

The default score is a weighted mean of available evidence channels:

```text
55% temporal support
30% spatial peer support, when available
15% entity timing regularity
```

Peer observations are weighted by the peer's own coverage and timing regularity. Scores are ranking signals, not calibrated probabilities.

See [`docs/ALGORITHM.md`](docs/ALGORITHM.md) for the exact mechanics and [`docs/FORMAT.md`](docs/FORMAT.md) for input and output contracts.

## Programmatic API

```python
from nulltrace_atlas import DetectionConfig, Observation, analyze_observations

analysis = analyze_observations(
    observations,
    DetectionConfig(threshold=0.75, peer_radius_km=3.0),
)

print(analysis["profiles"])
print(analysis["slots"])
print(analysis["traces"])
print(analysis["summary"])
```

Convenience functions are also available: `profile_observations`, `detect_null_slots`, `detect_null_traces`, `load_csv`, `load_jsonl`, `load_observations` and `to_geojson`.

## Trace output

A trace includes:

* deterministic `trace_id`
* entity, start and end
* missing slot count and implied duration
* mean and maximum score
* temporal and peer support
* timing regularity and coverage
* evidence count and peer hits
* evidence profile
* cadence and timestamp tolerance used
* median entity coordinates when available

GeoJSON represents geolocated traces as points with the complete trace evidence in `properties`.

## Safety of interpretation

A high score means **the missing observation is structurally surprising under this observation model**. It does not identify why it is missing.

Possible causes include sensor outage, maintenance, ingestion failure, filtering, archive loss, deliberate shutdown, sampling policy changes or a bad cadence model. NullTrace Atlas is an investigation and data quality tool, not causal inference.

It should not be the sole basis for forensic, medical, emergency, compliance or safety critical decisions.

## Novelty note

There are established missingness visualisation tools and research methods for modelling structured missing data. NullTrace Atlas focuses on a narrower operational object: **contiguous, scored, evidence bearing absences reconstructed from an expected spatiotemporal observation process**. That is a distinct design combination, not a provable claim that no similar idea has ever existed.

## Development

```bash
python -m unittest discover -s tests -v
python -m compileall -q nulltrace_atlas
```

CI runs the package on Python 3.10, 3.12 and 3.13 and exercises both unit tests and real CLI flows.

## License

MIT
