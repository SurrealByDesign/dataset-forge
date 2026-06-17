"""One-off: scan anthropomorph dataset with CrystallineFacetingAnalyzer."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dataset_forge.analyzers.crystalline import CrystallineFacetingAnalyzer
from dataset_forge.context import (
    CONTEXT_SCHEMA_VERSION, AspectRatioStats, DatasetContext,
    FrequencyDistributions, ResolutionStats, TextureDistributions,
)

DATASET = Path("C:/Users/someo/Desktop/ANTHROPOMORPHS")
KNOWN_MISSED = {
    "thefallofthedamnhotdogs.jpg", "thesleepofreason.jpg", "donutbutcher.jpg",
    "CARROTNINJA.jpg", "alice.jpg", "foxmusketeer.jpg", "bagel.jpg",
    "danzighalberd.jpg", "bananapunk.jpg", "abesteak.jpg", "appledoctor.jpg",
}

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

caught = []
false_positives = []

for img in images:
    findings = analyzer.analyze(img, ctx)
    faceting = [f for f in findings if f.category == "artifact.crystalline_faceting"]
    if not faceting:
        continue
    ev = faceting[0].evidence
    is_known = img.name in KNOWN_MISSED
    tag = "<<KNOWN MISSED>>" if is_known else "NEW / possible FP"
    print(
        f"  {tag:<20}  {img.name:<44}  "
        f"grain={ev['pencil_grain_score']:5.1f}  "
        f"smooth={ev['watercolor_smoothness_score']:5.1f}  "
        f"micro={ev['microtexture_density_score']:5.1f}"
    )
    if is_known:
        caught.append(img.name)
    else:
        false_positives.append(img.name)

print()
print(f"Known missed cases caught : {len(caught)} / {len(KNOWN_MISSED)}")
print(f"New findings (FP risk)    : {len(false_positives)}")
print(f"Total findings            : {len(caught) + len(false_positives)} / {len(images)}")

not_caught = KNOWN_MISSED - set(caught)
if not_caught:
    print()
    print("Known missed but NOT caught:")
    for n in sorted(not_caught):
        print(f"  {n}")
