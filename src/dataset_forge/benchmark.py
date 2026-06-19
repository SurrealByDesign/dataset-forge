"""Benchmark framework for Dataset Forge analyzers.

Loads a benchmark manifest (JSON), runs each case through the registered
analyzers, and reports pass/fail/skip per expectation.

Does not implement cleanup, AI, new analyzers, or new contracts.

Schema:  benchmarks/benchmark_manifest.json
Runner:  scripts/run_benchmarks.py
"""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dataset_forge.analysis.metrics import extract_image_metrics
from dataset_forge.analyzers.base import Analyzer
from dataset_forge.analyzers.crystalline import CrystallineFacetingAnalyzer
from dataset_forge.analyzers.texture import TextureAnalyzer
from dataset_forge.context import (
    CONTEXT_SCHEMA_VERSION,
    AspectRatioStats,
    DatasetContext,
    FrequencyDistributions,
    ResolutionStats,
    TextureDistributions,
)
from dataset_forge.measurements import ImageMeasurements, measure_image

BENCHMARK_SCHEMA_VERSION = 1

# Registry: manifest analyzer_id -> Analyzer instance
_ANALYZER_REGISTRY: dict[str, Analyzer] = {
    "texture_analyzer/v1": TextureAnalyzer(),
    "crystalline_faceting_analyzer/v1": CrystallineFacetingAnalyzer(),
}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BenchmarkExpectation:
    """A single expected outcome for one analyzer on one image."""

    analyzer_id: str           # e.g. "texture_analyzer/v1"
    category: str              # e.g. "texture.high_microtexture"
    should_detect: bool        # True = expect a matching finding
    expected_severity: str | None  # None = don't check severity
    notes: str = ""


@dataclass(frozen=True)
class BenchmarkCase:
    """One image with one or more analyzer expectations."""

    id: str
    image_path: str            # relative to project root, or absolute
    provenance: str            # "synthetic" | "real" | "private"
    private: bool              # if True and image missing, skip (not FAIL)
    source_description: str
    context_group: str         # cases sharing a group share a DatasetContext
    expectations: tuple[BenchmarkExpectation, ...]


@dataclass
class ExpectationResult:
    """Outcome of evaluating one BenchmarkExpectation."""

    case_id: str
    image_path: str
    expectation: BenchmarkExpectation
    passed: bool
    skipped: bool
    skip_reason: str           # "" when not skipped
    actual_found: bool
    actual_severity: str | None
    actual_confidence: float | None


@dataclass
class BenchmarkRun:
    """Aggregate results of a full benchmark run."""

    manifest_path: str
    timestamp: str
    total: int
    passed: int
    failed: int
    skipped: int
    results: list[ExpectationResult]

    @property
    def success(self) -> bool:
        return self.failed == 0


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------

def load_manifest(path: Path) -> tuple[str, list[BenchmarkCase]]:
    """Parse a benchmark manifest. Returns (suite_name, cases).

    Raises ValueError if schema_version is not supported.
    """
    data = json.loads(path.read_text("utf-8"))
    version = data.get("schema_version", 0)
    if version != BENCHMARK_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported benchmark schema_version {version!r} "
            f"(expected {BENCHMARK_SCHEMA_VERSION})"
        )
    suite_name = data.get("name", "Unnamed Suite")
    cases: list[BenchmarkCase] = []
    for raw in data.get("cases", []):
        expectations = tuple(
            BenchmarkExpectation(
                analyzer_id=e["analyzer_id"],
                category=e["category"],
                should_detect=e["should_detect"],
                expected_severity=e.get("expected_severity"),
                notes=e.get("notes", ""),
            )
            for e in raw.get("expectations", [])
        )
        cases.append(BenchmarkCase(
            id=raw["id"],
            image_path=raw["image_path"],
            provenance=raw.get("provenance", "unknown"),
            private=raw.get("private", True),
            source_description=raw.get("source_description", ""),
            context_group=raw.get("context_group", "default"),
            expectations=expectations,
        ))
    return suite_name, cases


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def _build_context_for_group(
    image_paths: list[Path],
) -> tuple[DatasetContext, dict[Path, ImageMeasurements]]:
    """Build a DatasetContext from a list of images (benchmark group)."""
    widths: list[int] = []
    heights: list[int] = []
    aspects: list[float] = []
    microtextures: list[float] = []
    file_hashes: dict[str, list[Path]] = {}
    measurements_by_path: dict[Path, ImageMeasurements] = {}
    error_count = 0

    for path in image_paths:
        measurements = measure_image(path)
        measurements_by_path[path] = measurements

        try:
            m = extract_image_metrics(path)
            widths.append(m.width)
            heights.append(m.height)
            aspects.append(m.aspect_ratio)
            file_hashes.setdefault(m.file_hash, []).append(path)
        except Exception:
            error_count += 1
            continue
        tex = measurements.texture
        if tex.status == "analyzed":
            microtextures.append(tex.microtexture_density_score)

    if widths:
        res = ResolutionStats(
            mean_w=statistics.mean(widths),
            mean_h=statistics.mean(heights),
            stddev_w=statistics.pstdev(widths),
            stddev_h=statistics.pstdev(heights),
            min_w=min(widths),
            min_h=min(heights),
            max_w=max(widths),
            max_h=max(heights),
            sample_count=len(widths),
        )
        ar = AspectRatioStats(
            mean=statistics.mean(aspects),
            stddev=statistics.pstdev(aspects),
            min=min(aspects),
            max=max(aspects),
            sample_count=len(aspects),
        )
    else:
        res = ResolutionStats.empty()
        ar = AspectRatioStats.empty()

    if microtextures:
        n = len(microtextures)
        sorted_mt = sorted(microtextures)
        tex_dist = TextureDistributions(
            mean=statistics.mean(microtextures),
            stddev=statistics.pstdev(microtextures),
            p10=sorted_mt[max(0, int(math.floor(n * 0.10)))],
            p90=sorted_mt[min(n - 1, int(math.floor(n * 0.90)))],
            sample_count=n,
        )
    else:
        tex_dist = TextureDistributions.empty()

    dup_groups = tuple(
        tuple(ps) for ps in file_hashes.values() if len(ps) > 1
    )

    context = DatasetContext(
        schema_version=CONTEXT_SCHEMA_VERSION,
        analyzer_versions={
            "texture_analyzer": "v1",
            "crystalline_faceting_analyzer": "v1",
        },
        image_paths=tuple(image_paths),
        image_count=len(image_paths),
        error_count=error_count,
        resolution_stats=res,
        aspect_ratio_stats=ar,
        texture_distributions=tex_dist,
        frequency_distributions=FrequencyDistributions.empty(),
        duplicate_hashes=frozenset(file_hashes.keys()),
        duplicate_groups=dup_groups,
    )
    return context, measurements_by_path


# ---------------------------------------------------------------------------
# Expectation evaluation
# ---------------------------------------------------------------------------

def _evaluate_expectation(
    exp: BenchmarkExpectation,
    actual_found: bool,
    actual_severity: str | None,
) -> bool:
    """Return True if actual outcome matches expectation."""
    if exp.should_detect != actual_found:
        return False
    if actual_found and exp.expected_severity is not None:
        return actual_severity == exp.expected_severity
    return True


def _run_expectation(
    case: BenchmarkCase,
    img_path: Path,
    exp: BenchmarkExpectation,
    context: DatasetContext,
    measurements: ImageMeasurements | None = None,
    registry: dict[str, Analyzer] | None = None,
) -> ExpectationResult:
    if registry is None:
        registry = _ANALYZER_REGISTRY
    analyzer = registry.get(exp.analyzer_id)
    if analyzer is None:
        return ExpectationResult(
            case_id=case.id,
            image_path=case.image_path,
            expectation=exp,
            passed=False,
            skipped=True,
            skip_reason=f"unknown analyzer {exp.analyzer_id!r}",
            actual_found=False,
            actual_severity=None,
            actual_confidence=None,
        )

    findings = analyzer.analyze(img_path, context, measurements=measurements)
    matching = [f for f in findings if f.category == exp.category]
    actual_found = len(matching) > 0
    actual_severity = matching[0].severity.name if matching else None
    actual_confidence = matching[0].confidence if matching else None
    passed = _evaluate_expectation(exp, actual_found, actual_severity)

    return ExpectationResult(
        case_id=case.id,
        image_path=case.image_path,
        expectation=exp,
        passed=passed,
        skipped=False,
        skip_reason="",
        actual_found=actual_found,
        actual_severity=actual_severity,
        actual_confidence=actual_confidence,
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_benchmark(
    manifest_path: Path,
    project_root: Path | None = None,
    registry: dict[str, Analyzer] | None = None,
) -> BenchmarkRun:
    """Run all benchmark cases defined in manifest_path.

    Missing images for private=True cases are skipped, not failed.
    Missing images for private=False cases are also skipped (not tracked in git).
    """
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent.parent

    _, cases = load_manifest(manifest_path)

    # Resolve image paths
    resolved: dict[str, Path | None] = {}
    for case in cases:
        p = Path(case.image_path)
        if not p.is_absolute():
            p = project_root / p
        resolved[case.id] = p if p.exists() else None

    # Collect available images per context_group
    group_images: dict[str, list[Path]] = {}
    for case in cases:
        p = resolved[case.id]
        if p is not None:
            group_images.setdefault(case.context_group, []).append(p)

    # Build one DatasetContext per group (so z-scores are group-relative)
    group_data: dict[str, tuple[DatasetContext, dict[Path, ImageMeasurements]]] = {
        g: _build_context_for_group(paths)
        for g, paths in group_images.items()
    }

    # Evaluate each expectation
    all_results: list[ExpectationResult] = []
    for case in cases:
        img_path = resolved[case.id]

        if img_path is None:
            reason = "image not found" + (" (private)" if case.private else "")
            for exp in case.expectations:
                all_results.append(ExpectationResult(
                    case_id=case.id,
                    image_path=case.image_path,
                    expectation=exp,
                    passed=False,
                    skipped=True,
                    skip_reason=reason,
                    actual_found=False,
                    actual_severity=None,
                    actual_confidence=None,
                ))
            continue

        context_data = group_data.get(case.context_group)
        if context_data is None:
            context_data = _build_context_for_group([img_path])
        context, measurements_by_path = context_data
        measurements = measurements_by_path.get(img_path)

        for exp in case.expectations:
            all_results.append(
                _run_expectation(
                    case, img_path, exp, context, measurements, registry
                )
            )

    total = len(all_results)
    skipped = sum(1 for r in all_results if r.skipped)
    failed = sum(1 for r in all_results if not r.skipped and not r.passed)
    passed_count = total - skipped - failed

    return BenchmarkRun(
        manifest_path=str(manifest_path),
        timestamp=datetime.now(timezone.utc).isoformat(),
        total=total,
        passed=passed_count,
        failed=failed,
        skipped=skipped,
        results=all_results,
    )


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def write_json_results(run: BenchmarkRun, path: Path) -> None:
    data: dict[str, Any] = {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "manifest_path": run.manifest_path,
        "timestamp": run.timestamp,
        "summary": {
            "total": run.total,
            "passed": run.passed,
            "failed": run.failed,
            "skipped": run.skipped,
            "success": run.success,
        },
        "results": [
            {
                "case_id": r.case_id,
                "image_path": r.image_path,
                "analyzer_id": r.expectation.analyzer_id,
                "category": r.expectation.category,
                "should_detect": r.expectation.should_detect,
                "expected_severity": r.expectation.expected_severity,
                "passed": r.passed,
                "skipped": r.skipped,
                "skip_reason": r.skip_reason,
                "actual_found": r.actual_found,
                "actual_severity": r.actual_severity,
                "actual_confidence": r.actual_confidence,
                "notes": r.expectation.notes,
            }
            for r in run.results
        ],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def write_txt_results(run: BenchmarkRun, path: Path) -> None:
    lines: list[str] = [
        "Dataset Forge Benchmark Results",
        "=" * 60,
        f"Timestamp : {run.timestamp}",
        f"Manifest  : {run.manifest_path}",
        "",
        f"Total     : {run.total}",
        f"Passed    : {run.passed}",
        f"Failed    : {run.failed}",
        f"Skipped   : {run.skipped}",
        f"Status    : {'PASS' if run.success else 'FAIL'}",
        "",
        "-" * 60,
    ]
    for r in run.results:
        status = "SKIP" if r.skipped else ("PASS" if r.passed else "FAIL")
        detail = ""
        if r.skipped:
            detail = f"  ({r.skip_reason})"
        elif not r.passed:
            exp_tag = "found" if r.expectation.should_detect else "no-find"
            act_tag = "found" if r.actual_found else "no-find"
            sev_tag = ""
            if r.expectation.expected_severity and r.actual_severity:
                sev_tag = (
                    f" sev={r.actual_severity!r}"
                    f" (expected {r.expectation.expected_severity!r})"
                )
            detail = f"  [expected={exp_tag} actual={act_tag}{sev_tag}]"
        lines.append(
            f"[{status}] {r.case_id} / {r.expectation.analyzer_id}"
            f" / {r.expectation.category}{detail}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
