import json
from pathlib import Path
import tempfile
import unittest

from nulltrace_atlas.cli import main


DEMO = """entity,timestamp,lat,lon
alpha,2026-01-01T00:00:00Z,40.4168,-3.7038
alpha,2026-01-01T01:00:00Z,40.4168,-3.7038
alpha,2026-01-01T03:00:00Z,40.4168,-3.7038
alpha,2026-01-01T04:00:00Z,40.4168,-3.7038
beta,2026-01-01T00:00:00Z,40.4180,-3.7020
beta,2026-01-01T01:00:00Z,40.4180,-3.7020
beta,2026-01-01T02:00:00Z,40.4180,-3.7020
beta,2026-01-01T03:00:00Z,40.4180,-3.7020
beta,2026-01-01T04:00:00Z,40.4180,-3.7020
"""


class CliTests(unittest.TestCase):
    def test_scan_writes_all_machine_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "demo.csv"
            source.write_text(DEMO, encoding="utf-8")
            traces = root / "out" / "traces.json"
            slots = root / "out" / "slots.json"
            geo = root / "out" / "traces.geojson"
            analysis = root / "out" / "analysis.json"
            code = main([
                "scan", str(source), "--cadence", "3600", "--threshold", "0.5",
                "--json", str(traces), "--slots-json", str(slots),
                "--geojson", str(geo), "--analysis-json", str(analysis), "--quiet",
            ])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(traces.read_text())[0]["entity"], "alpha")
            self.assertEqual(json.loads(geo.read_text())["type"], "FeatureCollection")
            self.assertIn("summary", json.loads(analysis.read_text()))
            self.assertTrue(json.loads(slots.read_text()))

    def test_profile_writes_profiles(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "demo.csv"
            source.write_text(DEMO, encoding="utf-8")
            output = root / "profiles.json"
            code = main(["profile", str(source), "--cadence", "3600", "--json", str(output)])
            self.assertEqual(code, 0)
            rows = json.loads(output.read_text())
            self.assertEqual({row["entity"] for row in rows}, {"alpha", "beta"})


if __name__ == "__main__":
    unittest.main()
