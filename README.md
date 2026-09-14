# NullTrace Atlas

**Map what should have been observed, but was not.**

NullTrace Atlas is an experimental **negative-evidence cartography** engine for sparse spatiotemporal event streams. Instead of treating missing rows as ordinary null values, it asks a narrower question:

> Given this source's own temporal behaviour and nearby peer observations, where is an absence unusually well-supported?

It turns those structured absences into explainable **null traces** that can be exported as JSON or GeoJSON.

This is useful when the *shape of missing data* matters: environmental sensor networks, biodiversity observations, transit telemetry, archival datasets, telescope logs, citizen-science feeds, infrastructure monitoring, and other systems where an expected observation can fail to appear.

## The important distinction

NullTrace Atlas never claims that an unobserved event happened.

It separates:

- **missing data** — a record is absent;
- **expected observation** — surrounding evidence suggests a record would normally exist;
- **null trace** — a contiguous absence with enough explicit support to be interesting.

A null trace is a data-quality or investigation signal, **not proof of a cause**.

## Why this is different from a missingness heatmap

Conventional missingness tools show where values are null. NullTrace Atlas reconstructs the expected observation grid, scores absent slots using multiple independent forms of support, joins contiguous candidates into traces, and emits evidence for every score.

The MVP deliberately uses a transparent model rather than a black-box anomaly detector.

## Input

CSV with one observation per row:

```csv
entity,timestamp,lat,lon,value
alpha,2026-01-01T00:00:00Z,40.4168,-3.7038,12.2
alpha,2026-01-01T01:00:00Z,40.4168,-3.7038,12.4
beta,2026-01-01T00:00:00Z,40.4200,-3.7000,8.1
```

Required columns: `entity`, `timestamp`.

Optional `lat` and `lon` allow spatial peer evidence and GeoJSON export. Other columns are ignored by the core engine.

## Detection model

For each entity, the engine creates an expected time grid using either a user-provided cadence or the entity's median observed interval.

For every absent slot it computes:

1. **temporal support** — how consistently the same entity is observed in neighbouring expected slots;
2. **peer support** — when coordinates exist, how many nearby entities are observed at the same slot;
3. **evidence count** — how many concrete neighbouring observations support the score.

The score is intentionally simple and inspectable:

```text
score = temporal_weight * temporal_support
      + peer_weight     * peer_support
```

Only absences above the threshold and minimum evidence become candidates. Consecutive candidates for one entity are merged into a null trace.

## Quick start

Requires Python 3.10+ and has no runtime dependencies.

```bash
python -m pip install -e .
nulltrace scan examples/demo.csv --cadence 3600 --threshold 0.70 --json traces.json
nulltrace scan examples/demo.csv --cadence 3600 --threshold 0.70 --geojson traces.geojson
```

Or just inspect the demo:

```bash
nulltrace scan examples/demo.csv --cadence 3600 --threshold 0.65
```

## Example interpretation

If station `alpha` normally reports every hour, reports immediately before and after 03:00, and several nearby stations also report at 03:00, then an absent `alpha@03:00` can receive a high null-trace score.

That means **"this missing observation is structurally surprising"**, not **"the sensor definitely failed"**.

## Output

Each trace contains:

- entity
- start and end timestamps
- number of missing slots
- mean and maximum score
- temporal and peer support
- evidence count
- cadence used
- coordinates when available

GeoJSON output represents each trace as a point at the entity location with the trace evidence in `properties`.

## Design principles

1. **Negative evidence must stay explicit.** Absence is not silently converted into an event.
2. **Every score must be explainable.** No opaque model is required for the MVP.
3. **Do not confuse coverage with reality.** A trace may indicate instrumentation, sampling, ingestion or archival behaviour.
4. **No imputation by default.** The tool identifies surprising gaps; it does not fabricate replacement measurements.
5. **Reproducible first.** Same input and parameters produce the same traces.

## Repository status

This is an early research/engineering prototype. It is not a forensic, safety-critical, compliance, medical, or scientific-proof system. Real deployments need source-specific calibration and independent validation.

## Novelty note

There are established tools for visualising missingness and research code for simulating structured missing-data mechanisms. NullTrace Atlas targets a different operational object: **contiguous, scored, evidence-bearing absences in an expected spatiotemporal observation process**. The claim here is a distinct design combination, not a provable claim that no prior implementation anywhere has ever explored a similar idea.

## License

MIT
