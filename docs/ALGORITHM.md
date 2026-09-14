# Detection model

NullTrace Atlas is deliberately conservative about what an absence means.

## 1. Reconstruct an expected observation grid

For each entity, the engine uses either an explicit cadence or the median positive interval between observations. The grid is bounded by the first and last observation; the MVP never extrapolates before or after that range.

## 2. Score missing slots

A missing slot receives two possible evidence channels.

### Temporal support

Within a symmetric window around the missing slot, count how many expected neighbouring slots are actually observed for the same entity.

```text
temporal_support = observed_neighbor_slots / available_neighbor_slots
```

### Spatial peer support

If entity coordinates exist, find peers inside the configured radius. A peer is eligible only if the candidate time lies inside that peer's observed time range.

```text
peer_support = peers_observed_at_slot / eligible_peers
```

If there are no eligible spatial peers, peer evidence is omitted rather than treated as zero.

## 3. Combine only available evidence

```text
score = weighted_mean(temporal_support, peer_support)
```

The default weights are 0.65 temporal and 0.35 peer. The result is a ranking score, not a calibrated probability.

## 4. Require concrete evidence

A candidate must satisfy both the score threshold and `min_evidence`. Evidence count is the number of neighbouring same-entity observations plus nearby peer observations that directly support the candidate.

## 5. Merge consecutive candidates

Adjacent missing slots for the same entity are merged into one null trace. Each trace reports duration in missing slots, mean/max score, support values, evidence count, cadence and coordinates when available.

## Non-claims

A high score does not identify the cause of a gap. It can result from sensor outage, ingestion failure, maintenance, sampling rules, archive loss, filtering, deliberate shutdown, or other source-specific processes. NullTrace Atlas surfaces the pattern; source-specific investigation must explain it.

## Known MVP limitations

- One cadence per entity.
- Exact timestamp alignment; no tolerance window yet.
- Static median coordinate per entity.
- No seasonality model.
- No cross-source reliability weighting.
- No causal inference.
- No calibrated probability semantics.

These limitations are intentional: the first version prioritizes inspectability and falsifiability over model complexity.
