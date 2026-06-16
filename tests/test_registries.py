import unittest
from pathlib import Path

from dataset_forge.exporters import Exporter, ExporterRegistry
from dataset_forge.transforms import Transform, TransformRegistry


class SampleTransform(Transform):
    name = "sample_transform"
    description = "Test transform."
    input_requirements = ("image",)
    output_type = "image"
    parameters = {"strength": "number"}

    def run(
        self,
        input_path: Path,
        output_path: Path,
        **parameters: object,
    ) -> object:
        return output_path


class SampleExporter(Exporter):
    name = "sample_exporter"
    description = "Test exporter."
    input_requirements = ("manifest",)
    output_type = "directory"
    parameters = {"archive": "boolean"}

    def run(
        self,
        input_path: Path,
        output_path: Path,
        **parameters: object,
    ) -> object:
        return output_path


class RegistryTests(unittest.TestCase):
    def test_transform_registry_discovers_by_name(self) -> None:
        registry = TransformRegistry()

        registered = registry.register(SampleTransform)

        self.assertIs(registered, SampleTransform)
        self.assertIs(registry.get("sample_transform"), SampleTransform)
        self.assertEqual(registry.names(), ("sample_transform",))

    def test_transform_registry_rejects_duplicate_names(self) -> None:
        registry = TransformRegistry()
        registry.register(SampleTransform)

        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register(SampleTransform)

    def test_exporter_registry_discovers_by_name(self) -> None:
        registry = ExporterRegistry()

        registered = registry.register(SampleExporter)

        self.assertIs(registered, SampleExporter)
        self.assertIs(registry.get("sample_exporter"), SampleExporter)
        self.assertEqual(registry.names(), ("sample_exporter",))

    def test_exporter_registry_rejects_unknown_name(self) -> None:
        registry = ExporterRegistry()

        with self.assertRaisesRegex(KeyError, "Unknown exporter"):
            registry.get("missing")


if __name__ == "__main__":
    unittest.main()

