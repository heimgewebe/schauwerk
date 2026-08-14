from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

from PIL import features

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SCRIPT = ROOT / "scripts" / "fundus_adapter_benchmark.py"
SPEC = importlib.util.spec_from_file_location("fundus_adapter_benchmark", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class FundusAdapterBenchmarkTests(unittest.TestCase):
    def test_fixture_corpus_manifest_is_semantic_stable_and_digest_bound(self) -> None:
        first = benchmark.fixture_corpus_manifest()
        second = benchmark.fixture_corpus_manifest()
        self.assertEqual(first, second)
        self.assertEqual(1, first["schema_version"])
        self.assertEqual(
            {"gradient_alpha", "fine_line_alpha", "deterministic_texture"},
            set(first["raster"]),
        )
        self.assertEqual(
            {"flat_shapes", "fine_lines", "nested_contours"},
            set(first["trace"]),
        )
        for family in ("raster", "trace"):
            for record in first[family].values():
                self.assertEqual(64, len(record["canonical_png_sha256"]))
                self.assertGreater(record["width"], 0)
                self.assertGreater(record["height"], 0)

    def test_raster_encoding_matrix_covers_every_semantic_fixture(self) -> None:
        fixtures = benchmark._raster_fixtures()
        semantic = set(benchmark._raster_fixture_images())
        self.assertEqual(
            semantic,
            {name.removesuffix(".png") for name in fixtures if name.endswith(".png")},
        )
        self.assertEqual(
            semantic,
            {name.removesuffix(".jpeg") for name in fixtures if name.endswith(".jpeg")},
        )
        webp = {name.removesuffix(".webp") for name in fixtures if name.endswith(".webp")}
        self.assertEqual(semantic if features.check("webp") else set(), webp)
        self.assertEqual(len(fixtures), len(semantic) * (3 if features.check("webp") else 2))

    def test_trace_fixtures_are_distinct_and_digest_bound(self) -> None:
        fixtures = benchmark._trace_fixtures()
        self.assertEqual(
            {"flat_shapes", "fine_lines", "nested_contours"},
            set(fixtures),
        )
        digests = {
            benchmark.hashlib.sha256(payload).hexdigest() for payload in fixtures.values()
        }
        self.assertEqual(len(fixtures), len(digests))
        manifest = benchmark.fixture_corpus_manifest()["trace"]
        for name, payload in fixtures.items():
            self.assertEqual(
                benchmark.hashlib.sha256(payload).hexdigest(),
                manifest[name]["canonical_png_sha256"],
            )

    def test_public_trace_profile_contract_returns_an_independent_settings_copy(self) -> None:
        first = benchmark.trace_profile_contract(benchmark.TRACE_PROFILE)
        self.assertEqual("vtracer", first["adapter"])
        self.assertEqual("svg.decorative.v1", first["sanitizer_profile"])
        settings = first["settings"]
        self.assertIsInstance(settings, dict)
        settings["path_precision"] = 99
        second = benchmark.trace_profile_contract(benchmark.TRACE_PROFILE)
        self.assertEqual(3, second["settings"]["path_precision"])

    def test_trace_quality_equivalence_is_corpus_strict(self) -> None:
        base = {
            "sanitizer_fixed_point": True,
            "path_count": 7,
            "roundtrip": {"max_channel_error": 255, "mean_channel_error": 2.0},
        }
        close = {
            "sanitizer_fixed_point": True,
            "path_count": 7,
            "roundtrip": {"max_channel_error": 255, "mean_channel_error": 2.009},
        }
        self.assertTrue(benchmark._trace_fixture_quality_equivalent(base, close))

        too_far = {
            **close,
            "roundtrip": {"max_channel_error": 255, "mean_channel_error": 2.011},
        }
        self.assertFalse(benchmark._trace_fixture_quality_equivalent(base, too_far))
        self.assertFalse(
            benchmark._trace_fixture_quality_equivalent(base, {**close, "path_count": 8})
        )
        self.assertFalse(
            benchmark._trace_fixture_quality_equivalent(base, {**close, "roundtrip": None})
        )
        self.assertFalse(
            benchmark._trace_fixture_quality_equivalent(
                {**base, "sanitizer_fixed_point": False}, close
            )
        )


if __name__ == "__main__":
    unittest.main()
