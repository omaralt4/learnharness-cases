---
name: "rounds-topic-file"
description: "Build or extend a topic JSON file for the LearnHarness rounds case picker: Step 2 topic list, tiers, systems, verified US guideline references."
---

# Rounds topic file builder

Produces a topics/<system>.json for pick_case.py (LearnHarness rounds mode), plus the list of guideline PDFs to download. The user is a med student studying for USMLE Step 2 CK. Be direct, no filler.

## Inputs to get first (ask once, in one message, only for what's missing)
1. System name (file slug, e.g. `pulm`, `gi`, `peds`).
2. Main reference: either chapter files already split into guidelines/<system>/ (ask for the chapter list with page ranges, never the book text) or none (guidelines only).
3. Existing topic ids from other files (`topics/*.json`). Ask the user to paste the id list if you can't read the folder. Needed for shared ids.
4. Scope: how many topics roughly (default 25-40 for an organ system, 60-100 for a complaint-based specialty like EM).

## Topic selection
- Step 2 CK yield first: common presentations, can't-miss diagnoses, next-best-step decisions. Skip trivia and rarities unless classic exam material.
- One topic = one diagnosis or tight cluster a single case can test ("Biliary colic / cholecystitis / cholangitis" is fine; "Abdominal pain" is not).
- `tier`: `common`, `cant_miss` or `rare`. Weights live in scenarios.json (common 3, cant_miss 2, rare 1). Omit tier only if the whole file omits it (then default 1).
- `complaint`: the patient's presenting complaint in lay-ish words, without naming the diagnosis (it is shown before the case). "sudden severe headache", not "SAH".
- `step2_system`: exactly one of `renal_reproductive`, `cardiovascular`, `musculoskeletal_skin`, `behavioral`, `blood_immune`, `gastrointestinal`, `nervous`, `respiratory`, `multisystem`, `endocrine`, `pregnancy`, `human_development`. Eye and ENT: eyes -> nervous, nose/throat -> respiratory. Substance use and abuse -> behavioral. Paediatric-specific (febrile infant, peds sepsis) -> human_development.

- `presentations`: list of how the topic can present, using ONLY this vocabulary: chest pain, dyspnea, palpitations, syncope/collapse, hypotension/shock, abdominal pain, GI bleeding, vomiting/diarrhea, headache, altered mental status, seizure, focal weakness, dizziness, fever, back pain, limb pain/swelling, joint pain, rash/skin, red eye/visual loss, sore throat/ENT, vaginal bleeding/pelvic pain, scrotal pain, urinary symptoms, overdose/poisoning, trauma, unwell child, behavioural disturbance. Include classic atypical routes that are guideline-documented (STEMI: chest pain, dyspnea, syncope/collapse, altered mental status). Used by complaint mode. If a needed presentation isn't in the list, tell the user rather than inventing one.

## Shared topics (important)
A topic that already exists in another file MUST reuse that exact `id` (e.g. `stemi`, `pe`). The picker merges same-id entries when systems are pooled: counts once, unions references, shares history. Never invent a second id for the same diagnosis. Report every reused id in the summary. Keep `step2_system` identical to the existing entry.

## References
Each topic gets `references`: a list of `{file, name, region}` (+ optional `folder`).
- Main-reference chapter files: `region: "UK"` (or whatever region the book is), `name` = book + chapter.
- Add a US guideline only where it changes management or is the source Step 2 grades on. Do not attach a guideline to every topic.
- `folder: "<other system>"` when the PDF already lives in another system's guideline folder (e.g. cardio guidelines reused by EM). Don't make the user download duplicates.
- Filename convention: `<short-slug>-<year>.pdf` (e.g. `sah-2023.pdf`).

### Verifying guidelines (non-negotiable)
- Every US reference must be checked as the current version by search: confirm the year, issuing society, journal and DOI from the publisher, PubMed or the society page. One search per guideline, run independent searches in parallel.
- Check for a newer edition before accepting an older one (search "<topic> guideline <current year>").
- If you can't confirm it, leave it out and say so. Never cite from memory.
- `verified: true` only if the topic has at least one confirmed US reference; otherwise `false`.
- Note free full-text sources (PMC, society site) in the download table when found.

## Optional fields
- `ecg_codes`: PTB-XL SCP codes, only for topics whose diagnosis shows on a 12-lead (e.g. `INJAS` anterior STEMI, `AFIB`, `3AVB`, `WPW`, `LNGQT`, `LVH`). Empty list otherwise. Don't invent codes.
- `ecg_rate`: `[min, max]` bpm (null = no limit) when the rhythm needs a rate (AF with RVR `[110, null]`).

## Output schema
```json
{
 "system": "<slug>",
 "step2_system": "<file-level default>",
 "note": "<one paragraph: source, region rule, shared-id rule, edit freely>",
 "complaints": ["<10-15 short search terms for the case-report picker>"],
 "topics": [
  {
   "id": "snake_case",
   "topic": "Display name",
   "tier": "common",
   "complaint": "presenting complaint",
   "presentations": ["dyspnea", "chest pain", "syncope/collapse"],
   "step2_system": "respiratory",
   "references": [
    {"file": "em-handbook-03-medicine.md", "name": "EM handbook ch 3", "region": "UK"},
    {"file": "pe-2026.pdf", "name": "2026 AHA/ACC ... Acute Pulmonary Embolism in Adults", "region": "US"}
   ],
   "verified": true,
   "ecg_codes": []
  }
 ]
}
```
If the user says their Claude Code version uses different field names, follow theirs.

## Build and validate
Write the JSON with a short Python script (not by hand), then check:
```python
import json, collections
d = json.load(open("topics/<system>.json"))
S = {"renal_reproductive","cardiovascular","musculoskeletal_skin","behavioral","blood_immune","gastrointestinal","nervous","respiratory","multisystem","endocrine","pregnancy","human_development"}
P = {"chest pain","dyspnea","palpitations","syncope/collapse","hypotension/shock","abdominal pain","GI bleeding","vomiting/diarrhea","headache","altered mental status","seizure","focal weakness","dizziness","fever","back pain","limb pain/swelling","joint pain","rash/skin","red eye/visual loss","sore throat/ENT","vaginal bleeding/pelvic pain","scrotal pain","urinary symptoms","overdose/poisoning","trauma","unwell child","behavioural disturbance"}
ids = [t["id"] for t in d["topics"]]
assert len(ids) == len(set(ids)), "duplicate id"
for t in d["topics"]:
    assert t["step2_system"] in S, t["id"]
    assert t.get("tier", "common") in {"common","cant_miss","rare"}, t["id"]
    assert t["references"], t["id"]
    assert t.get("presentations"), t["id"]
    assert set(t["presentations"]) <= P, (t["id"], set(t["presentations"]) - P)
print(len(ids), collections.Counter(t["step2_system"] for t in d["topics"]), collections.Counter(t.get("tier") for t in d["topics"]))
```

## Deliver
1. The JSON file (sent as a file, not pasted).
2. A table of US PDFs to download: filename | guideline | DOI | free link if any.
3. Counts by step2_system and tier, the reused shared ids, and any topic you wanted a guideline for but couldn't verify.
4. Remind: save PDFs to guidelines/<system>/, run Prepare, test one case.

## Don'ts
- Don't edit the user's existing files (cardio.json, scenarios.json, doctrine) without asking; deliver additions as paste blocks.
- Don't reproduce text from copyrighted books; work only from chapter titles and page ranges.
- Don't put the diagnosis in `complaint`.
- Shared-id topics must have the same `presentations` as the existing entry (or a union; tell the user).
- Don't pad with low-yield topics to hit a number.