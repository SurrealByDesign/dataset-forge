"""Tests for the internal analyzer descriptor contract."""

from __future__ import annotations

import unittest

from dataset_forge.analyzer_descriptors import (
    CALIBRATION_ADVISORY,
    DISPLAY_VISIBLE,
    EXECUTION_ENABLED,
    FAMILY_DATASET_STRUCTURE,
    FAMILY_TECHNICAL_QUALITY,
    TRIAGE_INCLUDED,
    built_in_descriptors,
    descriptor_for_analyzer,
    descriptor_for_id,
)
from dataset_forge.analyzers.registry import create_analyzers


class TestAnalyzerDescriptors(unittest.TestCase):
    def test_every_registered_analyzer_has_exactly_one_descriptor(self):
        analyzers = create_analyzers()
        descriptors = built_in_descriptors()

        self.assertEqual(
            {descriptor.id for descriptor in descriptors},
            {analyzer.name for analyzer in analyzers},
        )
        self.assertEqual(
            len(descriptors),
            len({descriptor.id for descriptor in descriptors}),
        )

    def test_every_descriptor_points_to_registered_analyzer(self):
        analyzers = {analyzer.name: analyzer for analyzer in create_analyzers()}

        for descriptor in built_in_descriptors():
            self.assertIn(descriptor.id, analyzers)

    def test_descriptor_identity_matches_analyzer_contract(self):
        analyzers = {analyzer.name: analyzer for analyzer in create_analyzers()}

        for descriptor in built_in_descriptors():
            analyzer = analyzers[descriptor.id]
            self.assertEqual(descriptor.id, analyzer.name)
            self.assertEqual(descriptor.version, analyzer.version)
            self.assertEqual(
                descriptor.categories_emitted,
                analyzer.supported_categories,
            )

    def test_current_descriptors_use_default_metadata(self):
        for descriptor in built_in_descriptors():
            self.assertEqual(descriptor.calibration_status, CALIBRATION_ADVISORY)
            self.assertTrue(descriptor.deterministic)
            self.assertEqual(descriptor.default_execution_policy, EXECUTION_ENABLED)
            self.assertEqual(descriptor.default_display_policy, DISPLAY_VISIBLE)
            self.assertEqual(descriptor.default_triage_policy, TRIAGE_INCLUDED)

    def test_duplicate_descriptor_uses_dataset_structure_family(self):
        descriptor = descriptor_for_id("duplicate_detection_analyzer")

        self.assertIsNotNone(descriptor)
        self.assertEqual(descriptor.family, FAMILY_DATASET_STRUCTURE)
        self.assertEqual(descriptor.categories_emitted, ("dataset.duplicate.exact",))
        self.assertFalse(descriptor.requires_image_measurements)

    def test_image_encoding_descriptor_uses_technical_quality_family(self):
        descriptor = descriptor_for_id("image_encoding_analyzer")

        self.assertIsNotNone(descriptor)
        self.assertEqual(descriptor.family, FAMILY_TECHNICAL_QUALITY)
        self.assertEqual(
            descriptor.categories_emitted,
            (
                "source_encoding.jpeg_compression",
                "source_encoding.jpeg_blocking",
                "source_encoding.jpeg_ringing",
                "source_encoding.chroma_artifact",
                "source_encoding.banding",
                "source_encoding.low_source_quality",
            ),
        )
        self.assertFalse(descriptor.requires_dataset_context)
        self.assertFalse(descriptor.requires_image_measurements)

    def test_current_quality_descriptors_keep_technical_quality_family(self):
        for descriptor in built_in_descriptors():
            if descriptor.id == "duplicate_detection_analyzer":
                continue
            self.assertEqual(descriptor.family, FAMILY_TECHNICAL_QUALITY)

    def test_descriptor_lookup_helpers(self):
        analyzer = create_analyzers()[0]

        self.assertIs(descriptor_for_id(analyzer.name), descriptor_for_analyzer(analyzer))
        self.assertIsNone(descriptor_for_id("unknown_analyzer"))


if __name__ == "__main__":
    unittest.main()
