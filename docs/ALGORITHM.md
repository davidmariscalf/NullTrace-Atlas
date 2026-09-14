# Detection model

NullTrace Atlas is deliberately conservative about what an absence means. It reconstructs an expected observation process and surfaces absences that are unusually well supported by evidence already present in the data.

## 1. Validate and group observations

Observations are normalised to UTC and grouped by `entity`. Coordinates, when present, must be valid latitude and longitude pairs. Duplicate timestamps do not create duplicate expected slots.

An entity must contain at least `min_observations` distinct timestamps before it is profiled.

## 2. Infer a base cadence

If `cadence_seconds` is supplied, that value is used directly.

Otherwise the engine examines positive time deltas between consecutive observations. For every delta `d`, candidate base cadences `d / k` are considered for integer multiples `k` from 1 through `max_cadence_multiple`.

A candidate receives support when observed deltas are close to integer multiples of that candidate. Ties favour the larger base cadence, preventing an hourly stream from being unnecessarily explained as a 30 minute or 15 minute stream. The winning candidate is then refined from the median implied base interval.

This allows a sequence such as:

```text
00:00, 01:00, 04:00, 05:00
```

to recover a one hour cadence instead of treating the three hour gap as the normal interval.

## 3. Reconstruct a tolerant expected grid

The first observation anchors the grid. Every later observation is mapped to the nearest expected slot when it falls within the configured timestamp tolerance.

By default:

```text
tolerance = cadence * cadence_tolerance_fraction
```

with a default fraction of `0.15`. Tolerance is capped below half a cadence so one observation cannot legitimately belong to two adjacent slots.

This makes the model robust to ordinary timestamp jitter.

The grid never extrapolates before the first observation or beyond the last mapped slot. `max_expected_slots` places a hard safety bound on grid size.

## 4. Profile coverage and regularity

For each entity:

```text
coverage = observed_grid_slots / expected_grid_slots
regularity = observations_that_align_to_grid / observations
```

Coverage describes how complete the reconstructed process is. Regularity describes how strongly the timestamps behave like a cadence driven process.

## 5. Find spatial peers

When coordinates are available, each entity receives peers whose median coordinates lie inside `peer_radius_km` using haversine distance.

A peer is eligible for a candidate slot only when that time lies inside the peer's own observed time range, allowing for its timestamp tolerance.

Peer observations are matched with their own tolerance, not exact timestamp equality.

## 6. Score a missing slot

A grid slot absent for the target entity can receive three evidence channels.

### Temporal support

Within a symmetric window around the missing slot:

```text
temporal_support = observed_neighbour_slots / available_neighbour_slots
```

### Spatial peer support

Eligible nearby peers are weighted by their own coverage and regularity:

```text
peer_reliability = max(0.05, peer_coverage * peer_regularity)
peer_support = reliability_weighted_fraction_of_peers_observed_near_slot
```

If no peer is eligible, peer support is omitted rather than treated as zero.

### Regularity support

The target entity's timing regularity acts as evidence that its expected grid is meaningful. A gap in a highly regular stream is more interpretable than a gap in a chaotic one.

## 7. Combine only available channels

The default weights are:

```text
temporal_weight   = 0.55
peer_weight       = 0.30
regularity_weight = 0.15
```

The score is the weighted mean of available channels. If peer evidence is unavailable, its weight is omitted from both numerator and denominator.

The result is a ranking score, not a calibrated probability.

## 8. Require concrete evidence

A slot is emitted only if:

```text
score >= threshold
and
evidence_count >= min_evidence
```

`evidence_count` contains concrete neighbouring target observations plus peer observations that directly support the slot. Global regularity is not counted as a concrete observation.

## 9. Merge contiguous slots

Adjacent accepted slots for one entity are merged into a null trace. A trace records:

* a deterministic SHA256 derived trace ID
* start and end
* missing slot count and implied duration
* mean and maximum score
* temporal and peer support
* coverage and regularity
* evidence counts
* evidence profile
* cadence and tolerance
* coordinates when available

## Evidence profiles

`mixed` means at least one slot has both temporal and peer hits.

`peer-confirmed` means peer evidence exists without temporal hits.

`temporal-only` means the trace is supported by the entity's own surrounding observations and regularity but no peer hit contributed.

These labels describe evidence channels, not causes.

## Non claims

A high score does not identify why an observation is absent. Plausible explanations include sensor outage, ingestion failure, maintenance, archive loss, filtering, sampling policy changes, deliberate shutdown or a poor model assumption.

NullTrace Atlas also does not claim that an unobserved event occurred. It scores the absence of an expected observation.

## Remaining limitations

* One inferred cadence per entity within a run.
* Static median coordinates per entity.
* No calendar or seasonal cadence model.
* No explicit change point detection when a source changes cadence.
* `quality` and `source` are accepted as input metadata but are not yet causal evidence channels.
* No calibrated probability semantics.
* No causal inference.

These are explicit boundaries rather than hidden assumptions.
