import json
from pathlib import Path

data = json.loads(Path("C:/Users/someo/Desktop/ANTHROPOMORPHS/decision_review.json").read_text(encoding="utf-8"))
reviews = data["reviews"]

counts = {"AGREE": 0, "DISAGREE": 0, "UNSURE": 0}
finding_agree = finding_disagree = finding_unsure = 0
clean_agree = clean_disagree = clean_unsure = 0

for r in reviews.values():
    rv  = r["review"]
    dec = r["df_decision"]
    counts[rv] += 1
    if dec == "FINDING":
        if rv == "AGREE":     finding_agree    += 1
        elif rv == "DISAGREE": finding_disagree += 1
        else:                  finding_unsure   += 1
    else:
        if rv == "AGREE":     clean_agree    += 1
        elif rv == "DISAGREE": clean_disagree += 1
        else:                  clean_unsure   += 1

total    = len(reviews)
findings = finding_agree + finding_disagree + finding_unsure
cleans   = clean_agree   + clean_disagree   + clean_unsure

print(f"Total reviewed : {total}")
print(f"Overall        : AGREE={counts['AGREE']}  DISAGREE={counts['DISAGREE']}  UNSURE={counts['UNSURE']}")
print()
print(f"FINDING images ({findings} flagged by analyzer):")
print(f"  AGREE={finding_agree}  DISAGREE={finding_disagree}  UNSURE={finding_unsure}")
print()
print(f"CLEAN images ({cleans} not flagged by analyzer):")
print(f"  AGREE={clean_agree}  DISAGREE={clean_disagree}  UNSURE={clean_unsure}")
print()

if findings:
    precision = finding_agree / findings
    print(f"Precision  (flagged and correct)      : {finding_agree}/{findings} = {precision:.0%}")

if cleans:
    missed = clean_disagree
    print(f"Missed     (not flagged, should have) : {missed}/{cleans} = {missed/cleans:.0%}")

if counts["DISAGREE"]:
    print()
    print("DISAGREE breakdown by severity:")
    sev_counts = {}
    for r in reviews.values():
        if r["review"] == "DISAGREE":
            sev = r.get("severity") or "none"
            sev_counts[sev] = sev_counts.get(sev, 0) + 1
    for sev, n in sorted(sev_counts.items()):
        print(f"  {sev:8s} : {n}")
