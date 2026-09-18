from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from nulltrace_atlas.core import (
    DetectionConfig,
    Observation,
    analyze_observations,
    detect_null_traces,
    load_csv,
    load_jsonl,
    profile_observations,
    to_geojson,
)


def t(hour: int, seconds: int = 0) -> datetime:
    return datetime(2026, 1, 1, hour, tzinfo=timezone.utc) + timedelta(seconds=seconds)


class NullTraceTests(unittest.TestCase):
    def test_detects_structurally_supported_gap(self):
        observations = []
        for hour in [0, 1, 2, 4, 5]:
            observations.append(Observation("alpha", t(hour), 40.4168, -3.7038))
        for entity, lat, lon in [
            ("beta", 40.4180, -3.7020),
            ("gamma", 40.4200, -3.7000),
        ]:
            for hour in range(6):
                observations.append(Observation(entity, t(hour), lat, lon))

        traces = detect_null_traces(
            observations,
            DetectionConfig(cadence_seconds=3600, threshold=0.70, min_evidence=2),
        )

        alpha = [trace for trace in traces if trace["entity"] == "alpha"]
        self.assertEqual(len(alpha), 1)
        trace = alpha[0]
        self.assertEqual(trace["start"], "2026-01-01T03:00:00Z")
        self.assertEqual(trace["missing_slots"], 1)
        self.assertEqual(trace["mean_score"], 1.0)
        self.assertEqual(trace["evidence_profile"], "mixed")
        self.assertEqual(len(trace["trace_id"]), 16)

    def test_infers_base_cadence_through_consecutive_missing_slots(self):
        observations = [Observation("alpha", t(hour)) for hour in [0, 1, 4, 5]]
        profiles = profile_observations(observations)
        self.assertEqual(profiles[0]["cadence_seconds"], 3600)
        traces = detect_null_traces(
            observations,
            DetectionConfig(threshold=0.5, min_evidence=2),
        )
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0]["missing_slots"], 2)

    def test_timestamp_jitter_does_not_create_false_slots(self):
        observations = [
            Observation("alpha", t(0, 0)),
            Observation("alpha", t(1, 12)),
            Observation("alpha", t(2, -9)),
            Observation("alpha", t(3, 8)),
            Observation("alpha", t(4, -4)),
        ]
        analysis = analyze_observations(observations)
        self.assertEqual(analysis["traces"], [])
        self.assertGreaterEqual(analysis["profiles"][0]["regularity"], 0.99)

    def test_jittered_real_gap_is_detected(self):
        observations = [
            Observation("alpha", t(0, 0)),
            Observation("alpha", t(1, 10)),
            Observation("alpha", t(2, -8)),
            Observation("alpha", t(4, 5)),
            Observation("alpha", t(5, -5)),
        ]
        traces = detect_null_traces(
            observations, DetectionConfig(threshold=0.5, min_evidence=2)
        )
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0]["missing_slots"], 1)

    def test_does_not_extrapolate_outside_observed_range(self):
        observations = [
            Observation("alpha", t(1)),
            Observation("alpha", t(2)),
            Observation("alpha", t(3)),
        ]
        traces = detect_null_traces(
            observations,
            DetectionConfig(cadence_seconds=3600, threshold=0.1, min_evidence=1),
        )
        self.assertEqual(traces, [])

    def test_geojson_omits_unlocated_traces(self):
        traces = [
            {"entity": "a", "start": "x", "end": "y", "lat": 1.0, "lon": 2.0},
            {"entity": "b", "start": "x", "end": "y"},
        ]
        geo = to_geojson(traces)
        self.assertEqual(len(geo["features"]), 1)
        self.assertEqual(geo["features"][0]["geometry"]["coordinates"], [2.0, 1.0])

    def test_entity_longitude_median_handles_antimeridian(self):
        observations = [
            Observation("dateline", t(0), 10.0, 179.0),
            Observation("dateline", t(1), 10.0, -179.0),
            Observation("dateline", t(2), 10.0, -178.0),
        ]
        profiles = profile_observations(
            observations,
            DetectionConfig(cadence_seconds=3600),
        )
        self.assertEqual(len(profiles), 1)
        self.assertAlmostEqual(profiles[0]["lon"], -179.0)
        self.assertAlmostEqual(profiles[0]["lat"], 10.0)

    def test_invalid_coordinate_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "lat must be between"):
            analyze_observations(
                [
                    Observation("x", t(0), 100.0, 0.0),
                    Observation("x", t(1), 100.0, 0.0),
                    Observation("x", t(2), 100.0, 0.0),
                ]
            )

    def test_csv_and_jsonl_loaders(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            csv_path = root / "x.csv"
            csv_path.write_text(
                "entity,timestamp,lat,lon,source,quality\n"
                "a,2026-01-01T00:00:00Z,40,-3,s1,0.8\n",
                encoding="utf-8",
            )
            csv_rows = load_csv(csv_path)
            self.assertEqual(csv_rows[0].source, "s1")
            self.assertEqual(csv_rows[0].quality, 0.8)

            jsonl_path = root / "x.jsonl"
            jsonl_path.write_text(
                json.dumps({"entity": "a", "timestamp": "2026-01-01T00:00:00Z"}) + "\n",
                encoding="utf-8",
            )
            json_rows = load_jsonl(jsonl_path)
            self.assertEqual(json_rows[0].entity, "a")

    def test_analysis_summary_is_consistent(self):
        observations = [Observation("a", t(h)) for h in [0, 1, 3, 4]]
        analysis = analyze_observations(
            observations, DetectionConfig(cadence_seconds=3600, threshold=0.5)
        )
        self.assertEqual(analysis["summary"]["candidate_slots"], len(analysis["slots"]))
        self.assertEqual(analysis["summary"]["null_traces"], len(analysis["traces"]))


if __name__ == "__main__":
    unittest.main()
