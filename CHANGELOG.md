# Changelog

## 1.0.0

First stable public API.

### Added

* robust cadence inference through integer multiple gaps
* timestamp jitter tolerance
* entity coverage and regularity profiling
* reliability weighted spatial peer evidence
* deterministic trace IDs
* slot level evidence output
* complete analysis JSON output
* JSONL and NDJSON input
* `profile` CLI command
* grid size safety bound
* coordinate and input validation
* CLI integration tests
* Python 3.10, 3.12 and 3.13 CI matrix

### Changed

* scoring now combines temporal support, peer support when available, and entity timing regularity
* peer matching is tolerant rather than exact timestamp equality
* documentation now distinguishes evidence channels from causal claims

## 0.1.0

Initial MVP with CSV input, exact cadence grid matching, temporal support, spatial peers, trace merging and JSON or GeoJSON export.
