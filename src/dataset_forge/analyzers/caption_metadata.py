"""Caption / metadata consistency analyzer.

Inspects common image-adjacent text caption sidecars for deterministic metadata
consistency signals. It does not judge caption quality, rewrite captions,
generate prompts, use ML/LLMs, or modify files.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dataset_forge.analyzers.base import Analyzer
from dataset_forge.context import DatasetContext
from dataset_forge.finding import Finding, Severity

if TYPE_CHECKING:
    from dataset_forge.measurements import ImageMeasurements


BENCHMARK_VERSION = "advisory-metadata-v1"

_UNCALIBRATED_FP_RATE = 0.30
_UNCALIBRATED_MAX_CONFIDENCE = 0.55
_SHORT_TOKEN_THRESHOLD = 2
_LONG_TOKEN_THRESHOLD = 75
_TOKEN_IMBALANCE_MIN_CAPTIONS = 5
_TOKEN_IMBALANCE_RATIO = 0.80
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_']+")
_MONITORED_REPEATED_TERMS = ("masterpiece", "best quality", "8k")


@dataclass(frozen=True)
class _CaptionRecord:
    image_path: Path
    caption_path: Path
    exists: bool
    text: str
    token_count: int

    @property
    def stripped_text(self) -> str:
        return self.text.strip()

    @property
    def is_empty(self) -> bool:
        return self.exists and self.stripped_text == ""

    @property
    def is_non_empty(self) -> bool:
        return self.exists and self.stripped_text != ""

    @property
    def text_sha256(self) -> str:
        return hashlib.sha256(self.stripped_text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _CaptionSummary:
    records: tuple[_CaptionRecord, ...]
    duplicate_groups: dict[str, tuple[_CaptionRecord, ...]]
    imbalanced_terms: tuple[dict[str, Any], ...]


class CaptionMetadataAnalyzer(Analyzer):
    """Inspect caption sidecar presence and consistency."""

    @property
    def name(self) -> str:
        return "caption_metadata_analyzer"

    @property
    def version(self) -> str:
        return "v1"

    @property
    def supported_categories(self) -> tuple[str, ...]:
        return (
            "caption.missing",
            "caption.empty",
            "caption.duplicate",
            "caption.short",
            "caption.long",
            "caption.token_imbalance",
        )

    @property
    def benchmark_version(self) -> str | None:
        return None

    def analyze(
        self,
        image_path: Path,
        context: DatasetContext,
        measurements: ImageMeasurements | None = None,
    ) -> list[Finding]:
        del measurements
        summary = _caption_summary(_context_key(context.image_paths))
        record = _record_for_image(summary, image_path)
        if record is None:
            return []

        findings: list[Finding] = []
        if not record.exists:
            findings.append(_missing_finding(image_path, self.analyzer_id, record))
            return findings
        if record.is_empty:
            findings.append(_empty_finding(image_path, self.analyzer_id, record))
            return findings

        duplicate_group = summary.duplicate_groups.get(record.text_sha256)
        if duplicate_group is not None:
            findings.append(
                _duplicate_finding(
                    image_path,
                    self.analyzer_id,
                    record,
                    duplicate_group,
                )
            )
        if record.token_count <= _SHORT_TOKEN_THRESHOLD:
            findings.append(_short_finding(image_path, self.analyzer_id, record))
        if record.token_count >= _LONG_TOKEN_THRESHOLD:
            findings.append(_long_finding(image_path, self.analyzer_id, record))

        for term_row in summary.imbalanced_terms:
            if _contains_term(record.stripped_text, str(term_row["term"])):
                findings.append(
                    _token_imbalance_finding(
                        image_path,
                        self.analyzer_id,
                        record,
                        term_row,
                    )
                )
        return findings


def _missing_finding(
    image_path: Path,
    analyzer_id: str,
    record: _CaptionRecord,
) -> Finding:
    explanation = (
        "No caption sidecar was found for this image using the common "
        "image-name-plus-.txt convention."
    )
    recommendation = (
        "Review whether this dataset expects image-adjacent caption metadata. "
        "Dataset Forge does not generate, rewrite, or suggest captions."
    )
    return _finding(
        image_path,
        analyzer_id,
        "caption.missing",
        Severity.LOW,
        0.50,
        record,
        {"caption_exists": False},
        explanation,
        recommendation,
    )


def _empty_finding(
    image_path: Path,
    analyzer_id: str,
    record: _CaptionRecord,
) -> Finding:
    explanation = "A caption sidecar exists, but it is empty or whitespace only."
    recommendation = (
        "Review this metadata before training if captions are part of your "
        "workflow. Dataset Forge does not rewrite captions."
    )
    return _finding(
        image_path,
        analyzer_id,
        "caption.empty",
        Severity.LOW,
        0.52,
        record,
        {"caption_exists": True, "caption_empty": True},
        explanation,
        recommendation,
    )


def _duplicate_finding(
    image_path: Path,
    analyzer_id: str,
    record: _CaptionRecord,
    group: tuple[_CaptionRecord, ...],
) -> Finding:
    paths = [_normalized_path(item.image_path) for item in group]
    explanation = (
        f"Exact duplicate caption text appears on {len(group)} images. "
        "This is deterministic text matching only, not semantic similarity."
    )
    recommendation = (
        "Review whether repeated metadata is intentional. Dataset Forge does "
        "not judge caption wording quality or suggest replacements."
    )
    return _finding(
        image_path,
        analyzer_id,
        "caption.duplicate",
        Severity.LOW,
        0.52,
        record,
        {
            "duplicate_count": len(group),
            "matched_image_paths": paths,
            "caption_text_sha256": record.text_sha256,
        },
        explanation,
        recommendation,
    )


def _short_finding(
    image_path: Path,
    analyzer_id: str,
    record: _CaptionRecord,
) -> Finding:
    explanation = (
        f"Caption contains {record.token_count} token(s), at or below the "
        f"conservative short-caption threshold of {_SHORT_TOKEN_THRESHOLD}."
    )
    recommendation = (
        "Treat this as metadata consistency evidence only. Dataset Forge does "
        "not decide whether the caption is good or suggest new wording."
    )
    return _finding(
        image_path,
        analyzer_id,
        "caption.short",
        Severity.LOW,
        0.42,
        record,
        {"short_token_threshold": _SHORT_TOKEN_THRESHOLD},
        explanation,
        recommendation,
    )


def _long_finding(
    image_path: Path,
    analyzer_id: str,
    record: _CaptionRecord,
) -> Finding:
    explanation = (
        f"Caption contains {record.token_count} tokens, at or above the "
        f"conservative long-caption threshold of {_LONG_TOKEN_THRESHOLD}."
    )
    recommendation = (
        "Review this as metadata consistency evidence only. Dataset Forge does "
        "not score prompt quality or recommend prompt engineering."
    )
    return _finding(
        image_path,
        analyzer_id,
        "caption.long",
        Severity.LOW,
        0.40,
        record,
        {"long_token_threshold": _LONG_TOKEN_THRESHOLD},
        explanation,
        recommendation,
    )


def _token_imbalance_finding(
    image_path: Path,
    analyzer_id: str,
    record: _CaptionRecord,
    term_row: dict[str, Any],
) -> Finding:
    term = str(term_row["term"])
    explanation = (
        f"The metadata term '{term}' appears in "
        f"{term_row['caption_frequency_percentage']:.1f}% of non-empty "
        "captions. This may indicate repeated caption boilerplate."
    )
    recommendation = (
        "Review whether the repeated metadata term is intentional. Dataset "
        "Forge does not optimize prompts or rewrite captions."
    )
    return _finding(
        image_path,
        analyzer_id,
        "caption.token_imbalance",
        Severity.LOW,
        0.44,
        record,
        {
            "term": term,
            "term_caption_count": term_row["caption_count"],
            "non_empty_caption_count": term_row["non_empty_caption_count"],
            "caption_frequency_percentage": term_row["caption_frequency_percentage"],
            "threshold_percentage": _TOKEN_IMBALANCE_RATIO * 100,
            "minimum_caption_count": _TOKEN_IMBALANCE_MIN_CAPTIONS,
            "monitored_terms": list(_MONITORED_REPEATED_TERMS),
        },
        explanation,
        recommendation,
    )


def _finding(
    image_path: Path,
    analyzer_id: str,
    category: str,
    severity: Severity,
    confidence: float,
    record: _CaptionRecord,
    extra_evidence: dict[str, Any],
    explanation: str,
    recommendation: str,
) -> Finding:
    evidence = {
        "caption_path": _normalized_path(record.caption_path),
        "caption_exists": record.exists,
        "caption_token_count": record.token_count,
        "caption_character_count": len(record.stripped_text),
        "caption_sidecar_convention": "image_stem_txt",
        "caption_quality_scored": False,
        "caption_rewritten": False,
    }
    evidence.update(extra_evidence)
    return Finding(
        image_path=image_path,
        analyzer=analyzer_id,
        category=category,
        severity=severity,
        confidence=min(confidence, _UNCALIBRATED_MAX_CONFIDENCE),
        false_positive_rate=_UNCALIBRATED_FP_RATE,
        benchmark_version=BENCHMARK_VERSION,
        evidence=evidence,
        explanation=explanation,
        recommendation=recommendation,
    )


def _context_key(image_paths: tuple[Path, ...]) -> tuple[tuple[str, int, int], ...]:
    return tuple(
        sorted(
            (
                str(path.resolve()),
                _caption_path(path).stat().st_mtime_ns if _caption_path(path).exists() else -1,
                _caption_path(path).stat().st_size if _caption_path(path).exists() else -1,
            )
            for path in image_paths
        )
    )


@lru_cache(maxsize=8)
def _caption_summary(
    context_key: tuple[tuple[str, int, int], ...],
) -> _CaptionSummary:
    records = tuple(
        _read_caption_record(Path(path_text))
        for path_text, _mtime, _size in context_key
    )
    duplicate_groups = _duplicate_groups(records)
    imbalanced_terms = _imbalanced_terms(records)
    return _CaptionSummary(
        records=records,
        duplicate_groups=duplicate_groups,
        imbalanced_terms=imbalanced_terms,
    )


def _read_caption_record(image_path: Path) -> _CaptionRecord:
    caption_path = _caption_path(image_path)
    if not caption_path.exists():
        return _CaptionRecord(
            image_path=image_path,
            caption_path=caption_path,
            exists=False,
            text="",
            token_count=0,
        )
    text = caption_path.read_text(encoding="utf-8", errors="replace")
    return _CaptionRecord(
        image_path=image_path,
        caption_path=caption_path,
        exists=True,
        text=text,
        token_count=len(_tokens(text)),
    )


def _duplicate_groups(
    records: tuple[_CaptionRecord, ...],
) -> dict[str, tuple[_CaptionRecord, ...]]:
    by_hash: dict[str, list[_CaptionRecord]] = {}
    for record in records:
        if not record.is_non_empty:
            continue
        by_hash.setdefault(record.text_sha256, []).append(record)
    return {
        digest: tuple(sorted(group, key=lambda item: _normalized_path(item.image_path)))
        for digest, group in by_hash.items()
        if len(group) >= 2
    }


def _imbalanced_terms(records: tuple[_CaptionRecord, ...]) -> tuple[dict[str, Any], ...]:
    non_empty = [record for record in records if record.is_non_empty]
    if len(non_empty) < _TOKEN_IMBALANCE_MIN_CAPTIONS:
        return ()
    rows: list[dict[str, Any]] = []
    for term in _MONITORED_REPEATED_TERMS:
        matching = [
            record for record in non_empty
            if _contains_term(record.stripped_text, term)
        ]
        ratio = len(matching) / len(non_empty)
        if ratio >= _TOKEN_IMBALANCE_RATIO:
            rows.append({
                "term": term,
                "caption_count": len(matching),
                "non_empty_caption_count": len(non_empty),
                "caption_frequency_percentage": round(ratio * 100, 1),
            })
    return tuple(sorted(rows, key=lambda item: str(item["term"])))


def _record_for_image(
    summary: _CaptionSummary,
    image_path: Path,
) -> _CaptionRecord | None:
    resolved = image_path.resolve()
    for record in summary.records:
        if record.image_path.resolve() == resolved:
            return record
    return None


def _caption_path(image_path: Path) -> Path:
    return image_path.with_suffix(".txt")


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(match.group(0).lower() for match in _TOKEN_PATTERN.finditer(text))


def _contains_term(text: str, term: str) -> bool:
    normalized = " ".join(_tokens(text))
    return f" {term.lower()} " in f" {normalized} "


def _normalized_path(path: Path) -> str:
    return path.resolve().as_posix()


__all__ = ["CaptionMetadataAnalyzer"]
