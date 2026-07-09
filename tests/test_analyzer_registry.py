"""Tests for the internal built-in analyzer registry."""

from __future__ import annotations

import unittest

from dataset_forge.analyzers.crystalline import CrystallineFacetingAnalyzer
from dataset_forge.analyzers.duplicates import DuplicateDetectionAnalyzer
from dataset_forge.analyzers.high_frequency_isolated import (
    HighFrequencyIsolatedArtifactAnalyzer,
)
from dataset_forge.analyzers.oversharpening import OversharpeningHaloAnalyzer
from dataset_forge.analyzers.registry import (
    ANALYZER_CLASSES,
    analyzer_versions,
    create_analyzer_registry,
    create_analyzers,
)
from dataset_forge.analyzers.texture import TextureAnalyzer


class TestAnalyzerRegistry(unittest.TestCase):
    def test_registry_includes_exactly_current_analyzers_in_order(self):
        self.assertEqual(
            ANALYZER_CLASSES,
            (
                TextureAnalyzer,
                CrystallineFacetingAnalyzer,
                OversharpeningHaloAnalyzer,
                HighFrequencyIsolatedArtifactAnalyzer,
                DuplicateDetectionAnalyzer,
            ),
        )

    def test_create_analyzers_returns_fresh_instances(self):
        first = create_analyzers()
        second = create_analyzers()

        self.assertEqual(
            [analyzer.analyzer_id for analyzer in first],
            [
                "texture_analyzer/v1",
                "crystalline_faceting_analyzer/v1",
                "oversharpening_halo_analyzer/v1",
                "high_frequency_isolated_artifact_analyzer/v1",
                "duplicate_detection_analyzer/v1",
            ],
        )
        self.assertIsNot(first[0], second[0])

    def test_analyzer_versions_are_complete(self):
        self.assertEqual(
            analyzer_versions(),
            {
                "texture_analyzer": "v1",
                "crystalline_faceting_analyzer": "v1",
                "oversharpening_halo_analyzer": "v1",
                "high_frequency_isolated_artifact_analyzer": "v1",
                "duplicate_detection_analyzer": "v1",
            },
        )

    def test_create_analyzer_registry_keys(self):
        self.assertEqual(
            tuple(create_analyzer_registry()),
            (
                "texture_analyzer/v1",
                "crystalline_faceting_analyzer/v1",
                "oversharpening_halo_analyzer/v1",
                "high_frequency_isolated_artifact_analyzer/v1",
                "duplicate_detection_analyzer/v1",
            ),
        )


if __name__ == "__main__":
    unittest.main()
