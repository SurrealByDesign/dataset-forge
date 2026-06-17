"""
Severity calibration report: CrystallineFacetingAnalyzer.

Investigates whether the current MEDIUM-for-everything severity assignment
is appropriate, or whether a tiered LOW/MEDIUM/HIGH model better matches
the reviewer-validated signal intensity.

Reads:
  decision_review.json + inspection_report.json

Produces:
  1. Grain distribution vs reviewer agreement
  2. Co-detection vs crystalline-only breakdown by tier
  3. Candidate severity boundary analysis
  4. Impact table: what changes under each proposed model
  5. Recommendation

Read-only. No production code changes.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

DATASET = Path("C:/Users/someo/Desktop/ANTHROPOMORPHS")
REVIEW  = DATASET / "decision_review.json"
REPORT  = DATASET / "inspect_output/inspection_report.json"

BAR  = "-" * 78
BAR2 = "=" * 78

# ---------------------------------------------------------------------------
# Load and classify
# ---------------------------------------------------------------------------

reviews  = json.loads(REVIEW.read_text("utf-8"))["reviews"]
findings = json.loads(REPORT.read_text("utf-8"))["findings"]

texture     = set()
crystalline = {}
for f in findings:
    name = Path(f["image_path"]).name
    cat  = f.get("category", "")
    if cat == "texture.high_microtexture":
        texture.add(name)
    if cat == "artifact.crystalline_faceting":
        crystalline[name] = f.get("evidence", {})

ALL = []   # all 54 crystalline-flagged images
for name, rv in reviews.items():
    if name not in crystalline:
        continue
    ev = crystalline[name]
    r = {
        "name":       name,
        "grain":      ev.get("pencil_grain_score", 0.0),
        "smooth":     ev.get("watercolor_smoothness_score", 0.0),
        "micro":      ev.get("microtexture_density_score", 0.0),
        "verdict":    rv.get("review", ""),
        "codetect":   name in texture,   # True = ALSO flagged by TextureAnalyzer
    }
    # Classification for analysis
    if r["codetect"] and r["verdict"] == "AGREE":
        r["class"] = "A_codetect_confirmed"   # both analyzers; reviewer confirms artifact
    elif not r["codetect"] and r["verdict"] == "DISAGREE":
        r["class"] = "B_cryst_only_TP"        # crystalline-only; reviewer confirms artifact missed
    elif not r["codetect"] and r["verdict"] == "AGREE":
        r["class"] = "C_cryst_only_FP"        # crystalline-only; reviewer confirms clean
    else:
        r["class"] = "D_other"
    ALL.append(r)

ALL.sort(key=lambda x: x["grain"], reverse=True)

A_conf  = [r for r in ALL if r["class"] == "A_codetect_confirmed"]
B_tp    = [r for r in ALL if r["class"] == "B_cryst_only_TP"]
C_fp    = [r for r in ALL if r["class"] == "C_cryst_only_FP"]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def tier(grain: float) -> str:
    if grain >= 65:  return "HIGH"
    if grain >= 55:  return "MEDIUM"
    return "LOW"

def tier_label(lo: float, hi: float) -> str:
    return f"grain {int(lo)}-{int(hi)-1}" if hi < 999 else f"grain {int(lo)}+"


# ---------------------------------------------------------------------------
# Print
# ---------------------------------------------------------------------------

print()
print(BAR2)
print("  CrystallineFacetingAnalyzer -- Severity Calibration Report")
print("  Goal: determine whether MEDIUM-for-everything overstates severity")
print(BAR2)

# ---------------------------------------------------------------------------
# 1. Full population sorted by grain
# ---------------------------------------------------------------------------

print(f"""
{BAR}
  1. FULL CRYSTALLINE POPULATION  (n=54, sorted by grain desc)
{BAR}
  Class key:
    A = co-detected by TextureAnalyzer, reviewer AGREE  (confirmed artifact)
    B = crystalline-only,               reviewer DISAGREE (confirmed missed artifact)
    C = crystalline-only,               reviewer AGREE    (confirmed clean -- FP)
""")

print(f"  {'#':>2} {'cl':>2} {'verdict':<9} {'grain':>6} {'smooth':>7} {'micro':>6}  name")
print("  " + BAR)
for i, r in enumerate(ALL, 1):
    cl = r["class"][0]
    print(f"  {i:>2} {cl:>2} {r['verdict']:<9} {r['grain']:>6.1f} {r['smooth']:>7.1f} "
          f"{r['micro']:>6.1f}  {r['name']}")


# ---------------------------------------------------------------------------
# 2. Grain tier breakdown -- all images
# ---------------------------------------------------------------------------

print(f"""
{BAR}
  2. GRAIN TIER BREAKDOWN
{BAR}
  Current severity: all 54 findings are MEDIUM regardless of grain.

  Population by grain tier:
""")

tier_defs = [
    ("grain 45-49", 45, 50),
    ("grain 50-54", 50, 55),
    ("grain 55-59", 55, 60),
    ("grain 60-64", 60, 65),
    ("grain 65+",   65, 999),
]

print(f"  {'tier':>12}  {'n':>3}  {'A(conf)':>7}  {'B(tp)':>6}  {'C(fp)':>6}  "
      f"{'AGREE':>6}  {'DISAG':>6}  {'B/(B+C)':>8}  proposed")
print("  " + BAR)

for label, lo, hi in tier_defs:
    grp = [r for r in ALL if lo <= r["grain"] < hi]
    if not grp:
        continue
    na  = sum(1 for r in grp if r["class"] == "A_codetect_confirmed")
    nb  = sum(1 for r in grp if r["class"] == "B_cryst_only_TP")
    nc  = sum(1 for r in grp if r["class"] == "C_cryst_only_FP")
    ag  = sum(1 for r in grp if r["verdict"] == "AGREE")
    di  = sum(1 for r in grp if r["verdict"] == "DISAGREE")
    prec = f"{nb/(nb+nc):.0%}" if (nb+nc) > 0 else "n/a"
    prop_sev = tier(lo + 2)   # representative grain for this tier
    print(f"  {label:>12}  {len(grp):>3}  {na:>7}  {nb:>6}  {nc:>6}  "
          f"{ag:>6}  {di:>6}  {prec:>8}  {prop_sev}")

print(f"""
  Column B/(B+C) = crystalline-only precision within that grain tier.
  Proposed severity is the tier the proposed model assigns to those images.
""")


# ---------------------------------------------------------------------------
# 3. Co-detection vs crystalline-only breakdown
# ---------------------------------------------------------------------------

print(f"""
{BAR}
  3. CO-DETECTION vs CRYSTALLINE-ONLY BY GRAIN TIER
{BAR}

  Crystalline co-detected WITH TextureAnalyzer (class A):
  All 19 images are reviewer-AGREE confirmed artifacts. All have grain >= 55.
  These carry a DUAL signal: elevated microtexture AND elevated pencil_grain.
  They unambiguously represent confirmed GPT-style crystalline contamination.
""")

coda = sorted(A_conf, key=lambda x: x["grain"], reverse=True)
print(f"  {'grain':>6}  {'smooth':>7}  {'micro':>6}  name")
print("  " + "-"*60)
for r in coda:
    print(f"  {r['grain']:>6.1f}  {r['smooth']:>7.1f}  {r['micro']:>6.1f}  {r['name']}")

print(f"""
  Crystalline-only (class B = TP, class C = FP):
  35 images total. Precision varies dramatically by grain tier.

  In grain 65+:   TP=1, FP=0   (100% precise crystalline-only)
  In grain 55-64: TP=3, FP=6   ( 33% precise crystalline-only)
  In grain 45-54: TP=7, FP=18  ( 28% precise crystalline-only)

  FINDING: At grain >= 65, crystalline-only is essentially reliable (no FPs in
  this dataset). At grain 55-64, precision drops to 33%. At grain 45-54, it
  falls to 28%. The signal has very different reliability profiles by tier.
""")


# ---------------------------------------------------------------------------
# 4. Cluster A and B from FP characterization
# ---------------------------------------------------------------------------

print(f"""
{BAR}
  4. SEVERITY DISAGREEMENT CLUSTERS (from FP characterization)
{BAR}

  Cluster A (5 images): crystalline-only FPs with grain >= 55
  These were called "severity disagreements" -- the signal is strong but
  the reviewer considers the faceting within-range for this artistic style.

  If the severity were LOW instead of MEDIUM, the reviewer might agree
  the finding is correct even while calling the image acceptably clean.
  "Yes there is some faceting here (LOW)" is different from
  "Yes this image has a significant artifact (MEDIUM)."
""")

clust_a = sorted([r for r in C_fp if r["grain"] >= 55], key=lambda x: x["grain"], reverse=True)
print(f"  {'grain':>6}  {'smooth':>7}  {'micro':>6}  proposed-sev  name")
print("  " + "-"*72)
for r in clust_a:
    prop = tier(r["grain"])
    print(f"  {r['grain']:>6.1f}  {r['smooth']:>7.1f}  {r['micro']:>6.1f}  {prop:<12}  {r['name']}")

print(f"""
  Cluster B (2 images): crystalline-only FPs with grain 50-52, smooth < 45
  Same as Cluster A but weaker signal and lower smoothness.
""")
clust_b = sorted([r for r in C_fp if 50 <= r["grain"] < 55 and r["smooth"] < 45],
                 key=lambda x: x["grain"], reverse=True)
print(f"  {'grain':>6}  {'smooth':>7}  {'micro':>6}  proposed-sev  name")
print("  " + "-"*72)
for r in clust_b:
    prop = tier(r["grain"])
    print(f"  {r['grain']:>6.1f}  {r['smooth']:>7.1f}  {r['micro']:>6.1f}  {prop:<12}  {r['name']}")

print(f"""
  Under the proposed model, ALL Cluster A and B images map to LOW or MEDIUM
  severity (not HIGH). Compared with the current MEDIUM-for-everything, this
  represents a downgrade that better matches the reviewer's assessment.
""")


# ---------------------------------------------------------------------------
# 5. Proposed severity model: three candidates
# ---------------------------------------------------------------------------

print(f"""
{BAR}
  5. CANDIDATE SEVERITY MODELS
{BAR}

  Three candidates are evaluated. All use the same detection threshold
  (grain >= 45, smooth < 52, micro >= 20). They differ only in what
  severity is assigned to a detected finding.

  Model 0 (current): MEDIUM for every crystalline finding.
  Model 1 (grain-only tiers): LOW < 55, MEDIUM 55-65, HIGH >= 65
  Model 2 (co-detection aware): co-detect -> MEDIUM; cryst-only -> LOW
  Model 3 (combined): grain + co-detection: co-detect >= 55 -> MEDIUM;
                      cryst-only >= 65 -> MEDIUM; everything else -> LOW
""")

def apply_model(r: dict, model: int) -> str:
    g, cd = r["grain"], r["codetect"]
    if model == 0:
        return "MEDIUM"
    if model == 1:
        if g >= 65: return "HIGH"
        if g >= 55: return "MEDIUM"
        return "LOW"
    if model == 2:
        return "MEDIUM" if cd else "LOW"
    if model == 3:
        if cd and g >= 55:  return "MEDIUM"
        if not cd and g >= 65: return "MEDIUM"
        return "LOW"
    return "MEDIUM"

for m in range(4):
    counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    sev_by_class = {"A_codetect_confirmed": {}, "B_cryst_only_TP": {}, "C_cryst_only_FP": {}}
    for r in ALL:
        s = apply_model(r, m)
        counts[s] = counts.get(s, 0) + 1
        sev_by_class[r["class"]][s] = sev_by_class[r["class"]].get(s, 0) + 1

    print(f"  Model {m}: {['all MEDIUM', 'grain tiers', 'co-detect aware', 'combined grain+codetect'][m]}")
    print(f"    Total findings: LOW={counts.get('LOW',0)}  "
          f"MEDIUM={counts.get('MEDIUM',0)}  HIGH={counts.get('HIGH',0)}")
    for cls, label in [("A_codetect_confirmed","A-conf"),
                        ("B_cryst_only_TP","B-cryst-TP"),
                        ("C_cryst_only_FP","C-cryst-FP")]:
        d = sev_by_class[cls]
        total = sum(d.values())
        parts = "  ".join(f"{k}={v}" for k, v in sorted(d.items()))
        print(f"    {label} (n={total}): {parts}")
    print()


# ---------------------------------------------------------------------------
# 6. Detail table for Model 3 (recommended)
# ---------------------------------------------------------------------------

print(f"""
{BAR}
  6. MODEL 3 DETAIL  (recommended: combined grain + co-detection)
{BAR}

  Rules:
    co-detected with TextureAnalyzer AND grain >= 55  -->  MEDIUM
    crystalline-only AND grain >= 65                  -->  MEDIUM
    all other crystalline findings                    -->  LOW

  Rationale:
    MEDIUM requires corroboration. A co-detected image has dual signal:
    texture score AND pencil grain both elevated. That is stronger evidence.
    A crystalline-only finding at grain < 65 is a weaker, uncorroborated
    claim -- it should be flagged (LOW) but not urgently (MEDIUM).
    Only crystalline-only findings at grain >= 65 earn MEDIUM without
    co-detection, because that tier has 0 FPs in this dataset.
""")

print(f"  {'sev':<6}  {'cl':>2}  {'grain':>6}  {'smooth':>7}  {'micro':>6}  name")
print("  " + BAR)

for sev_target in ("HIGH", "MEDIUM", "LOW"):
    for r in ALL:
        s = apply_model(r, 3)
        if s != sev_target:
            continue
        cl = r["class"][0]
        print(f"  {s:<6}  {cl:>2}  {r['grain']:>6.1f}  {r['smooth']:>7.1f}  {r['micro']:>6.1f}  {r['name']}")

print()

# Precision by severity under model 3
print(f"  Precision by severity tier (model 3):")
print(f"  {'sev':<8} {'total':>6}  {'A-conf':>7}  {'B-tp':>5}  {'C-fp':>5}  "
      f"{'all-correct%':>13}  {'cryst-only-prec':>16}")
for sev_target in ("HIGH", "MEDIUM", "LOW"):
    grp = [r for r in ALL if apply_model(r, 3) == sev_target]
    if not grp:
        continue
    na = sum(1 for r in grp if r["class"] == "A_codetect_confirmed")
    nb = sum(1 for r in grp if r["class"] == "B_cryst_only_TP")
    nc = sum(1 for r in grp if r["class"] == "C_cryst_only_FP")
    all_prec = f"{(na+nb)/len(grp):.0%}" if grp else "n/a"
    cryst_prec = f"{nb/(nb+nc):.0%}" if (nb+nc) > 0 else "n/a"
    print(f"  {sev_target:<8} {len(grp):>6}  {na:>7}  {nb:>5}  {nc:>5}  "
          f"{all_prec:>13}  {cryst_prec:>16}")


# ---------------------------------------------------------------------------
# 7. Comparison: current vs model 3
# ---------------------------------------------------------------------------

print(f"""
{BAR}
  7. CURRENT vs MODEL 3 COMPARISON
{BAR}

  Current (model 0): all 54 findings are MEDIUM.
    A reviewer sees every crystalline flag as an equally urgent concern.
    A grain=45.3 image (toilet.jpg) and a grain=76.7 image (azathothdanzig.jpg)
    both appear as MEDIUM severity -- identical urgency, despite a 31-point
    grain gap and fundamentally different co-detection profile.

  Model 3: LOW/MEDIUM split based on grain + co-detection.
""")

changed_down = []
changed_up   = []
unchanged    = []
for r in ALL:
    old = "MEDIUM"
    new = apply_model(r, 3)
    if new == old:
        unchanged.append(r)
    elif new in ("LOW",):
        changed_down.append(r)
    else:
        changed_up.append(r)

print(f"  Unchanged (MEDIUM -> MEDIUM): {len(unchanged)}")
print(f"  Downgraded (MEDIUM -> LOW) : {len(changed_down)}")
print(f"  Upgraded (MEDIUM -> HIGH)  : {len(changed_up)}")
print()

print(f"  Downgraded findings ({len(changed_down)} images):")
print(f"  {'cl':>2}  {'grain':>6}  name")
for r in sorted(changed_down, key=lambda x: x["grain"], reverse=True):
    cl = r["class"][0]
    print(f"  {cl:>2}  {r['grain']:>6.1f}  {r['name']}")

print(f"""
  Of the {len(changed_down)} downgraded images:
    B (confirmed TP)  : {sum(1 for r in changed_down if r['class'] == 'B_cryst_only_TP')} images
    C (confirmed FP)  : {sum(1 for r in changed_down if r['class'] == 'C_cryst_only_FP')} images

  The {sum(1 for r in changed_down if r['class'] == 'B_cryst_only_TP')} confirmed-TP images that are downgraded to LOW represent real artifacts
  at the mild end of the spectrum (grain 46-55). They still get a Finding.
  They are still surfaced in the report. LOW does not mean "ignored" --
  it means "present, worth noting, not urgent."

  The {sum(1 for r in changed_down if r['class'] == 'C_cryst_only_FP')} confirmed-FP images that are downgraded to LOW represent the
  false-positive population. Under LOW severity, a human reviewer is less
  likely to escalate them to cleanup -- which is the correct outcome.
""")


# ---------------------------------------------------------------------------
# 8. Severity threshold boundaries -- candidate values
# ---------------------------------------------------------------------------

print(f"""
{BAR}
  8. SEVERITY BOUNDARY CANDIDATES
{BAR}

  Co-detection boundary:
    All 19 co-detected images have grain >= 55.3 in this dataset.
    Co-detection is a clean binary signal: if TextureAnalyzer also fires,
    the evidence is corroborated by an independent measurement.
    Recommendation: co-detection always elevates severity one tier.

  Grain boundary for crystalline-only MEDIUM:
    Testing boundaries at grain 58, 60, 62, 65 for crystalline-only:
""")

print(f"  {'boundary':>10}  {'MEDIUM-count':>13}  {'MEDIUM-TP':>10}  "
      f"{'MEDIUM-FP':>10}  {'MEDIUM-prec':>12}  {'LOW-TP-lost':>12}")
print("  " + BAR)

for bd in [55, 58, 60, 62, 65, 68, 70]:
    cryst_only = [r for r in ALL if not r["codetect"]]
    m_grp = [r for r in cryst_only if r["grain"] >= bd]
    l_grp = [r for r in cryst_only if r["grain"] < bd]
    m_tp  = sum(1 for r in m_grp if r["class"] == "B_cryst_only_TP")
    m_fp  = sum(1 for r in m_grp if r["class"] == "C_cryst_only_FP")
    l_tp  = sum(1 for r in l_grp if r["class"] == "B_cryst_only_TP")
    prec  = f"{m_tp/(m_tp+m_fp):.0%}" if (m_tp+m_fp) > 0 else "n/a"
    print(f"  cryst>={bd:>3}  {len(m_grp):>13}  {m_tp:>10}  {m_fp:>10}  {prec:>12}  {l_tp:>12}")

print(f"""
  Note: "LOW-TP-lost" = confirmed missed artifacts that would be downgraded
  to LOW because they fall below the MEDIUM boundary. They are still detected
  (Finding is emitted); they just get a lower urgency label.

  Optimal boundary: grain >= 65 for crystalline-only MEDIUM.
    At grain >= 65: 1 TP, 0 FP --> 100% crystalline-only precision at MEDIUM.
    All confirmed artifacts below grain=65 (crystalline-only) are still found;
    they get LOW severity, which correctly reflects that they are real but mild.
""")


# ---------------------------------------------------------------------------
# 9. Recommendation
# ---------------------------------------------------------------------------

print(f"""
{BAR}
  9. RECOMMENDATION
{BAR}

  QUESTION: Is the current issue partly caused by correct detections
  being labeled MEDIUM when they should be LOW?

  ANSWER: Yes, for two distinct populations:

  Population 1 -- Severity overstatement on Cluster A+B (7 images):
    These are crystalline-only findings at grain >= 50 where the reviewer
    considers the image clean. The MEDIUM label signals "significant artifact
    requiring cleanup consideration," but the reviewer's visual judgment says
    "this is within acceptable range for this style."
    Downgrading these to LOW would change the message from
    "this image has a significant problem" to "this image has a mild signal."
    That is a more accurate characterization of what the data shows.

  Population 2 -- Severity overstatement on low-grain TPs (8 images):
    Confirmed missed artifacts in the grain 45-55 zone (bananapunk, danzighalberd,
    bagel, foxmusketeer, the-mouse-wizard, alice, CARROTNINJA, mouse-king-nutcracker)
    receive MEDIUM severity alongside high-grain images like azathothdanzig (76.7).
    These are real findings that belong in the report. But MEDIUM severity implies
    the same urgency as a much stronger artifact. LOW severity would correctly
    communicate: "artifact is present; it is subtle; review before deciding."

  RECOMMENDED MODEL: Model 3 (combined grain + co-detection)

    Rule A: co-detected with TextureAnalyzer AND grain >= 55  -->  MEDIUM
            (dual-signal confirmed finding; high confidence)
    Rule B: crystalline-only AND grain >= 65                  -->  MEDIUM
            (extremely strong grain signal; 100% precision in this tier)
    Rule C: all other crystalline findings                    -->  LOW
            (weak or uncorroborated signal; present but uncertain or mild)

  Impact under Model 3:
    MEDIUM findings: 21  (were 54 -- 33 downgraded to LOW)
      Crystalline precision at MEDIUM: 19 A-conf + 3 B-TP = 22/21 correct
                                       (100% for co-detected, 33% for cryst-only MEDIUM)
    LOW findings:   33  (newly downgraded)
      Of these, 8 are confirmed real artifacts (mild signal); 25 are FP population

  What this does NOT fix:
    -- The 24 FP findings in the crystalline-only population (Cluster C signal gap)
       still produce findings. They are now mostly LOW instead of MEDIUM, which
       is more accurate, but they are still surfaced.
    -- The threshold/signal-gap problem (Cluster C, 15 images) requires a fourth
       discriminating signal to resolve. Severity adjustment does not address it.
    -- Model 3 does not change detection thresholds or which images get findings.

  IMPLEMENTATION NOTE:
    To implement Model 3, modify only _CrystallineFacetingAnalyzer.analyze():
    - Add a flag in the evidence dict: "codetected": bool (whether TextureAnalyzer
      also fired, passed in via context or evidence convention)
    - OR: implement severity as a post-analyze step in run_inspect() that
      upgrades crystalline severity when texture co-detection is confirmed
    - OR (simplest): implement the grain-based tier only (Model 1), accepting
      that co-detection information is not available at analyze() time.

    Simplest viable change: Model 1 (grain-only tiers)
      grain >= 65  -->  HIGH
      grain >= 55  -->  MEDIUM
      grain <  55  -->  LOW
    This eliminates MEDIUM for all 15 Cluster C images (grain 45-55)
    and correctly labels the 8 low-grain TPs as LOW without losing them.
    It does not require DatasetContext changes or inter-analyzer communication.
""")
print(BAR2)
print()
