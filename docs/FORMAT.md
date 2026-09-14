# Data contracts

## Observation input

NullTrace Atlas accepts CSV, JSONL and NDJSON.

### Required fields

`entity`

A non empty identifier for the repeated observation source, station, device, route, telescope, camera, site or other entity being profiled.

`timestamp`

An ISO 8601 timestamp. A trailing `Z` is supported. Timestamps without an explicit timezone are interpreted as UTC.

### Optional fields

`lat` and `lon`

Coordinates used for peer discovery and GeoJSON. They must either both be present or both be absent. Latitude must be in `[-90, 90]`; longitude in `[-180, 180]`.

`source`

Free text provenance metadata. Accepted and preserved on the in memory observation object but not currently used as a scoring channel.

`quality`

A number in `[0, 1]`. It is validated as source metadata but is not currently used as causal evidence or a calibrated confidence value.

Additional CSV or JSON object fields are ignored by the v1 engine.

## Analysis JSON

`nulltrace scan --analysis-json analysis.json` emits one object with four top level keys.

### `profiles`

One entry per entity that had enough timestamps to reconstruct a cadence.

Fields:

* `entity`
* `cadence_seconds`
* `tolerance_seconds`
* `first`
* `last`
* `observations`
* `expected_slots`
* `observed_slots`
* `coverage`
* `regularity`
* optional `lat`, `lon`

### `slots`

One entry per accepted missing expected slot.

Fields:

* `entity`
* `timestamp`
* `slot_index`
* `score`
* `temporal_support`
* nullable `peer_support`
* `regularity`
* `evidence_count`
* `temporal_hits`
* `peer_hits`
* `eligible_peers`
* `cadence_seconds`
* `tolerance_seconds`

### `traces`

Contiguous accepted slots merged per entity.

Fields:

* `trace_id`
* `entity`
* `start`
* `end`
* `missing_slots`
* `duration_seconds`
* `mean_score`
* `max_score`
* `mean_temporal_support`
* nullable `mean_peer_support`
* `regularity`
* `coverage`
* `evidence_count`
* `peer_hits`
* `eligible_peer_slots`
* `evidence_profile`
* `cadence_seconds`
* `tolerance_seconds`
* optional `lat`, `lon`

### `summary`

Run level counts:

* `entities_profiled`
* `candidate_slots`
* `null_traces`
* `entities_with_traces`

## GeoJSON

Every geolocated trace is exported as a GeoJSON `Point` at the entity's median location. Trace fields other than `lat` and `lon` appear under `properties`.

Entities without coordinates remain available in JSON output but are intentionally omitted from GeoJSON.

## Determinism

Given the same observations and configuration, ordering, scores and trace IDs are deterministic. Trace IDs are identifiers for a specific reconstructed trace, not globally authoritative event identifiers.
