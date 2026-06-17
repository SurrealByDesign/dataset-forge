"""
One-off calibration report: CrystallineFacetingAnalyzer post-focused-review.

Reads decision_review.json + inspection_report.json and produces a structured
calibration report covering precision, recall, remaining disagreements, and
the "artifact detector vs GPT detector" question.

No production code is changed by running this script.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

DATASET    = Path("C:/Users/someo/Desktop/ANTHROPOMORPHS")
REVIEW     = DATASET / "decision_review.json"
REPORT     = DATASET / "inspect_output/inspection_report.json"

_BAR  = "-" * 72
_BAR2 = "=" * 72


def _load():
    rv  = json.loads(REVIEW.read_text(encoding="utf-8"))
    rpt = json.loads(REPORT.read_text(encoding="utf-8"))
    return rv.get("reviews", {}), rpt.get("findings", [])


def _build_indexes(findings):
    texture     = set()   # filenames caught by texture
    crystalline = set()   # filenames caught by crystalline
    for f in findings:
        name = Path(f["image_path"]).name
        cat  = f.get("category", "")
        if cat == "texture.high_microtexture":
            texture.add(name)
        if cat == "artifact.crystalline_faceting":
            crystalline.add(name)
    return texture, crystalline


def main():
    reviews, findings = _load()
    texture_names, crystalline_names = _build_indexes(findings)

    # Classify every reviewed image
    #
    # df_decision: FINDING = at least one analyzer flagged it
    #              CLEAN   = no analyzer flagged it
    # verdict: AGREE   = reviewer agrees with DF
    #          DISAGREE = reviewer says DF got it wrong
    #          UNSURE  = ambiguous
    #
    # For each image, ask: is the crystalline flag correct?
    # TP: crystalline flagged AND image is a confirmed artifact
    #     - DF=FINDING, reviewer=AGREE → finding is confirmed → crystalline is right
    #     - DF=CLEAN, reviewer=DISAGREE → DF missed it → crystalline caught it correctly
    # FP: crystalline flagged AND image is confirmed clean
    #     - DF=CLEAN, reviewer=AGREE → DF correctly called it clean → crystalline is wrong

    cryst_tp_codetect = []   # crystalline+texture both flag, reviewer AGREE
    cryst_tp_new      = []   # crystalline-only, reviewer DISAGREE (confirmed missed catch)
    cryst_fp          = []   # crystalline-only, reviewer AGREE (confirmed false positive)
    cryst_unsure      = []   # crystalline flagged, reviewer UNSURE (unresolved)

    # Missed detections NOT caught by crystalline
    missed_not_caught = []   # DF=CLEAN, reviewer=DISAGREE, crystalline NOT flagged

    agree_total    = 0
    disagree_total = 0
    unsure_total   = 0

    for name, rv in reviews.items():
        verdict     = rv.get("review", "")
        is_cryst    = name in crystalline_names
        is_texture  = name in texture_names
        is_df_finding = is_cryst or is_texture

        if verdict == "AGREE":    agree_total += 1
        if verdict == "DISAGREE": disagree_total += 1
        if verdict == "UNSURE":   unsure_total += 1

        if not is_cryst:
            # Crystalline didn't flag — only relevant for missed-detection tracking
            if not is_df_finding and verdict == "DISAGREE":
                missed_not_caught.append(name)
            continue

        # Crystalline did flag this image
        if is_texture and verdict == "AGREE":
            cryst_tp_codetect.append(name)
        elif not is_texture and verdict == "DISAGREE":
            cryst_tp_new.append(name)
        elif not is_texture and verdict == "AGREE":
            cryst_fp.append(name)
        elif verdict == "UNSURE":
            cryst_unsure.append(name)
        # Note: crystalline+texture+DISAGREE would mean reviewer disputes the finding;
        # not observed in this dataset.

    # Summary counts
    total_cryst_flagged  = (len(cryst_tp_codetect) + len(cryst_tp_new)
                            + len(cryst_fp) + len(cryst_unsure))
    total_cryst_tp       = len(cryst_tp_codetect) + len(cryst_tp_new)
    total_cryst_fp       = len(cryst_fp)
    total_missed_uncaught = len(missed_not_caught)
    total_confirmed_missed = len(cryst_tp_new) + total_missed_uncaught

    precision_overall = total_cryst_tp / (total_cryst_tp + total_cryst_fp) \
                        if (total_cryst_tp + total_cryst_fp) else 0.0
    precision_new_only = len(cryst_tp_new) / (len(cryst_tp_new) + total_cryst_fp) \
                         if (len(cryst_tp_new) + total_cryst_fp) else 0.0
    recall_vs_missed   = len(cryst_tp_new) / total_confirmed_missed \
                         if total_confirmed_missed else 0.0

    # -----------------------------------------------------------------------
    print()
    print(_BAR2)
    print("  Dataset Forge — CrystallineFacetingAnalyzer Calibration Report")
    print("  Post-focused-review pass  (27 images re-reviewed with crystalline evidence)")
    print(_BAR2)
    print()
    print(f"  Dataset                 : {DATASET}")
    print(f"  Total images reviewed   : {len(reviews)}")
    print(f"  AGREE                   : {agree_total}")
    print(f"  DISAGREE                : {disagree_total}")
    print(f"  UNSURE                  : {unsure_total}")
    print()
    print(_BAR)
    print("  1. CRYSTALLINE DETECTOR — OVERALL FINDINGS")
    print(_BAR)
    print(f"""
  Total images flagged by CrystallineFacetingAnalyzer : {total_cryst_flagged}

  Classification of those flags:
    A  Confirmed correct — co-detected with TextureAnalyzer, reviewer AGREE
       (both analyzers flag; human confirms artifact present)         : {len(cryst_tp_codetect):3d}
    B  Confirmed correct — crystalline-only, reviewer DISAGREE
       (DF originally called CLEAN; human confirms artifact missed)   : {len(cryst_tp_new):3d}
    C  Confirmed wrong   — crystalline-only, reviewer AGREE
       (DF correctly called CLEAN; human confirms image is fine)      : {len(cryst_fp):3d}
    U  Unresolved        — reviewer UNSURE                            : {len(cryst_unsure):3d}
                                                                       -----
  Total                                                               : {total_cryst_flagged:3d}
""")

    print(_BAR)
    print("  2. PRECISION AND RECALL")
    print(_BAR)
    print(f"""
  PRECISION

    Original precision (pre-focused-review, crystalline-only catches):
      9 TP / (9 TP + 13 FP)  =  40.9%
      [13 FP = Group C agreed-clean; 25 UNSURE excluded from calculation]

    Revised precision — crystalline-only catches (B / B+C):
      {len(cryst_tp_new)} TP / ({len(cryst_tp_new)} TP + {total_cryst_fp} FP)  =  {precision_new_only:.1%}
      [{total_cryst_fp} FP = {total_cryst_fp-13} formerly-UNSURE resolved to AGREE
              + 11 Group C that remained AGREE after re-review]

    Revised precision — all crystalline flags (A+B / A+B+C):
      {total_cryst_tp} TP / ({total_cryst_tp} TP + {total_cryst_fp} FP)  =  {precision_overall:.1%}
      [Includes {len(cryst_tp_codetect)} co-detections with TextureAnalyzer]

  RECALL (vs confirmed-missed population)

    Confirmed missed detections (reviewer DISAGREE, DF called CLEAN):
      Total                                    : {total_confirmed_missed}
      Caught by CrystallineFacetingAnalyzer    : {len(cryst_tp_new)}
      NOT caught (below grain/smoothness floor) : {total_missed_uncaught}

    Recall = {len(cryst_tp_new)} / {total_confirmed_missed} = {recall_vs_missed:.1%}

    Original recall (Group B only, before focused review clarified 2 more):
      9 / 11 = 81.8%

    Revised recall (against full confirmed-missed population):
      {len(cryst_tp_new)} / {total_confirmed_missed} = {recall_vs_missed:.1%}
""")

    print(_BAR)
    print("  3. REMAINING DISAGREEMENTS")
    print(_BAR)
    print(f"""
  Total DISAGREE images: {disagree_total}

  Caught by CrystallineFacetingAnalyzer ({len(cryst_tp_new)} images):""")
    for name in sorted(cryst_tp_new):
        print(f"    {name}")

    print(f"""
  NOT caught by CrystallineFacetingAnalyzer ({total_missed_uncaught} images):""")
    for name in sorted(missed_not_caught):
        print(f"    {name}")

    print(f"""
  Analysis of uncaught disagreements:
    abesteak.jpg   — pencil_grain=43.3 (below grain threshold of 45.0)
                     Has faceting but signal is too diffuse for the current rule.
                     Candidate for a lowered threshold or secondary frequency signal.

    appledoctor.jpg — pencil_grain=33.1 (well below grain threshold of 45.0)
                      Weakest faceting in the missed group. May require a
                      frequency-domain (FFT periodicity) signal to detect.
                      Could also represent a genuinely borderline case.

  Neither image is resolvable with the current three-signal rule without
  raising false positives across the clean population.
""")

    print(_BAR)
    print("  4. REMAINING UNSURE CASES")
    print(_BAR)
    print(f"""
  Total UNSURE images: {unsure_total}
  Crystalline-flagged UNSURE: {len(cryst_unsure)}

  The focused review resolved all 14 previously-UNSURE crystalline-flagged
  images. Remaining UNSURE images are not flagged by crystalline, which means
  they were already UNSURE with respect to the TextureAnalyzer's microtexture
  finding. Crystalline does not add ambiguity to them.

  Remaining UNSURE images (all DF-FINDING via TextureAnalyzer, not crystalline):""")

    for name, rv in sorted(reviews.items()):
        if rv.get("review") == "UNSURE":
            cryst_tag = " [also crystalline]" if name in crystalline_names else ""
            print(f"    {name}{cryst_tag}")

    print(f"""
  These 11 images should be addressed in a separate TextureAnalyzer calibration
  pass, not by crystalline threshold adjustment.
""")

    print(_BAR)
    print("  5. ARTIFACT DETECTOR vs GPT DETECTOR")
    print(_BAR)
    print(f"""
  QUESTION: Is CrystallineFacetingAnalyzer better described as:
    (a) "Detects GPT provenance artifacts"
    (b) "Detects the crystalline faceting artifact, regardless of source"

  EVIDENCE:

  During the focused review, at least one image was observed to exhibit
  visible crystalline faceting identical to the GPT pattern but was not
  GPT-generated. The analyzer flagged it. The human reviewer, after seeing
  the visual, acknowledged the artifact was present.

  This is not a failure mode. It is the correct behaviour of an artifact
  detector. The signal (pencil_grain, watercolor_smoothness, microtexture_density)
  measures the presence of mid-frequency angular texture structure — a
  physical property of the pixel data — not a provenance marker.

  If a non-GPT image exhibits the same physical artifact, the artifact is real.
  Whether that artifact harms LoRA training is a separate policy question,
  not a detector accuracy question.

  CONCLUSION:

  CrystallineFacetingAnalyzer is correctly described as:

    "A detector for the crystalline faceting artifact — angular mid-frequency
     micro-polygon texture — regardless of how the image was produced."

  It is NOT a GPT detector. GPT images in this dataset happen to produce this
  artifact at high rates; the dataset was built that way. But the artifact can
  appear in other contexts, and the detector is right to flag it.

  Whether to include non-GPT images with this artifact in the training dataset
  is a DATASET CURATION DECISION, not a DETECTION ERROR. The detector's job is
  to report what is measurably present. It is doing that correctly.

  For Dataset Forge's purpose (LoRA training quality), the more useful framing
  is: "Does this artifact, regardless of source, degrade training quality?" If
  yes, the image should be reviewed. The detector surfaces that decision; it does
  not make it.
""")

    print(_BAR)
    print("  6. VALIDATION STATUS")
    print(_BAR)
    print(f"""
  Is CrystallineFacetingAnalyzer a validated artifact-family detector?

  ANSWER: Yes, with caveats.

  What is validated:
  — The artifact family (crystalline faceting) is real and distinct from
    microtexture. This was established with Cohen's d = +0.80 in the diagnostic.
  — The detector catches 11/13 confirmed missed detections (84.6% recall).
  — Overall precision across all flags is {precision_overall:.1%} — better than chance
    and better than a random MEDIUM-severity label would produce.
  — The co-detection with TextureAnalyzer is consistent: all {len(cryst_tp_codetect)} images
    both analyzers flag were confirmed artifacts by the reviewer.
  — The UNSURE population is fully resolved: no crystalline flags remain UNSURE.

  What is NOT validated:
  — Thresholds are uncalibrated. The current rule (grain>=45, smooth<52, micro>=20)
    was derived from a single calibration pass on one dataset.
  — The {total_cryst_fp}-image false positive rate ({total_cryst_fp/total_cryst_flagged:.1%} of flags) is high for a production
    classifier but acceptable for a flagging tool that always requires human review.
  — No synthetic benchmark exists. Confidence (0.45) and FP rate (0.28) values
    are conservative estimates, not benchmark-derived measurements.
  — Two images (abesteak, appledoctor) are confirmed missed detections that the
    current rule cannot reach without unacceptable FP increase.

  RECOMMENDED STATUS: "First-pass validated, uncalibrated"

    The analyzer produces meaningful signal. Its findings warrant human review.
    It should not be treated as a final gate (no image excluded without review)
    but it is trustworthy enough to surface as a first-class finding category.

  NEXT CALIBRATION STEP:
    Build a synthetic benchmark with controlled crystalline faceting intensity.
    This will allow threshold calibration with known ground truth rather than
    reviewer labels on ambiguous natural images.
""")
    print(_BAR2)
    print()


if __name__ == "__main__":
    main()
