"""Cross-reference crystalline findings with decision_review.json."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dataset_forge.analyzers.crystalline import CrystallineFacetingAnalyzer
from dataset_forge.context import (
    CONTEXT_SCHEMA_VERSION, AspectRatioStats, DatasetContext,
    FrequencyDistributions, ResolutionStats, TextureDistributions,
)

DATASET = Path("C:/Users/someo/Desktop/ANTHROPOMORPHS")
REVIEW_PATH = Path("C:/Users/someo/Desktop/ANTHROPOMORPHS/decision_review.json")
REPORT_PATH = Path("C:/Users/someo/Desktop/ANTHROPOMORPHS/inspect_output/inspection_report.json")

review = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
reviews = review.get("reviews", {})  # filename -> {review: AGREE/DISAGREE/UNSURE}

report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
findings_index = {Path(f["image_path"]).name for f in report.get("findings", [])}

ctx = DatasetContext(
    schema_version=CONTEXT_SCHEMA_VERSION,
    analyzer_versions={"crystalline_faceting_analyzer": "v1"},
    image_paths=(), image_count=100, error_count=0,
    resolution_stats=ResolutionStats(512, 512, 0, 0, 512, 512, 512, 512, 100),
    aspect_ratio_stats=AspectRatioStats(1.0, 0, 1, 1, 100),
    texture_distributions=TextureDistributions(38.59, 11.62, 20.0, 55.0, 100),
    frequency_distributions=FrequencyDistributions(0.1, 0.02, 100),
    duplicate_hashes=frozenset(),
    duplicate_groups=(),
)
analyzer = CrystallineFacetingAnalyzer()

images = sorted(
    p for p in DATASET.iterdir()
    if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
)
print(f"Scanning {len(images)} images ...\n")

# groups: agreed_finding=A, missed_clean=B, agreed_clean=C, unsure=U, no_review=?
counts = dict(A=0, B=0, C=0, U=0, unknown=0)
true_positives = []   # caught, group B (missed by texture, caught by crystalline)
extended = []         # caught, group A (both analyzers flag — expected overlap)
false_positives = []  # caught, group C (agreed clean — actual FP)
unsure_caught = []    # caught, group U

for img in images:
    findings = analyzer.analyze(img, ctx)
    faceting = [f for f in findings if f.category == "artifact.crystalline_faceting"]
    if not faceting:
        continue
    ev = faceting[0].evidence

    rv = reviews.get(img.name, {})
    verdict = rv.get("review", "")
    is_finding = img.name in findings_index

    if is_finding and verdict == "AGREE":
        group = "A"
        extended.append((img.name, ev))
    elif not is_finding and verdict == "DISAGREE":
        group = "B"
        true_positives.append((img.name, ev))
    elif not is_finding and verdict == "AGREE":
        group = "C"
        false_positives.append((img.name, ev))
    elif verdict == "UNSURE":
        group = "U"
        unsure_caught.append((img.name, ev))
    else:
        group = "unknown"
    counts[group] += 1

print("Results by review group:")
print(f"  A (agreed finding — TextureAnalyzer already caught): {counts['A']}")
print(f"  B (missed clean — NEW catch by crystalline):         {counts['B']}")
print(f"  C (agreed clean — FALSE POSITIVE):                   {counts['C']}")
print(f"  U (unsure — needs review):                           {counts['U']}")
print(f"  ? (not in review):                                   {counts['unknown']}")

print()
print("NEW catches (Group B — crystalline catches what texture missed):")
for name, ev in sorted(true_positives, key=lambda x: -x[1]["pencil_grain_score"]):
    print(f"  {name:<44}  grain={ev['pencil_grain_score']:5.1f}  smooth={ev['watercolor_smoothness_score']:5.1f}  micro={ev['microtexture_density_score']:5.1f}")

print()
print("FALSE POSITIVES (Group C — agreed clean but crystalline flags):")
for name, ev in sorted(false_positives, key=lambda x: -x[1]["pencil_grain_score"]):
    print(f"  {name:<44}  grain={ev['pencil_grain_score']:5.1f}  smooth={ev['watercolor_smoothness_score']:5.1f}  micro={ev['microtexture_density_score']:5.1f}")

print()
print("UNSURE cases caught (may be TP or FP — needs re-review):")
for name, ev in sorted(unsure_caught, key=lambda x: -x[1]["pencil_grain_score"]):
    print(f"  {name:<44}  grain={ev['pencil_grain_score']:5.1f}  smooth={ev['watercolor_smoothness_score']:5.1f}  micro={ev['microtexture_density_score']:5.1f}")
