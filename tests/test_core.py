from datetime import datetime, timezone
import unittest

from nulltrace_atlas.core import DetectionConfig, Observation, detect_null_traces, to_geojson


def t(hour: int) -> datetime:
    return datetime(2026, 1, 1, hour, tzinfo=timezone.utc)


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

        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertEqual(trace["entity"], "alpha")
        self.assertEqual(trace["start"], "2026-01-01T03:00:00Z")
        self.assertEqual(trace["end"], "2026-01-01T03:00:00Z")
        self.assertEqual(trace["missing_slots"], 1)
        self.assertEqual(trace["mean_score"], 1.0)
        self.assertGreaterEqual(trace["evidence_count"], 6)

    def test_does_not_invent_grid_outside_observed_range(self):
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

    def test_merges_consecutive_candidates(self):
        observations = [
            Observation("alpha", t(0)),
            Observation("alpha", t(1)),
            Observation("alpha", t(4)),
            Observation("alpha", t(5)),
        ]
        traces = detect_null_traces(
            observations,
            DetectionConfig(
                cadence_seconds=3600,
                threshold=0.5,
                temporal_window=2,
                min_evidence=2,
            ),
        )
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0]["missing_slots"], 2)
        self.assertEqual(traces[0]["start"], "2026-01-01T02:00:00Z")
        self.assertEqual(traces[0]["end"], "2026-01-01T03:00:00Z")

    def test_geojson_omits_traces_without_coordinates(self):
        traces = [
            {"entity": "a", "start": "x", "end": "y", "lat": 1.0, "lon": 2.0},
            {"entity": "b", "start": "x", "end": "y"},
        ]
        geo = to_geojson(traces)
        self.assertEqual(len(geo["features"]), 1)
        self.assertEqual(geo["features"][0]["geometry"]["coordinates"], [2.0, 1.0])


if __name__ == "__main__":
    unittest.main()
