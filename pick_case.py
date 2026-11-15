#!/usr/bin/env python3
"""Make unseen cases for LearnHarness rounds mode. Standard library only (Python 3.9+).

Two kinds of case, plus a tracker:

  common   A seed for a typical presentation of a core topic, built by the
           agent from the current guideline. This is the main mode.
             python pick_case.py common --system cardio
             python pick_case.py common --system cardio --batch 5

  report   A real open-access case report from Europe PMC. Good for variety,
           but reports lean toward unusual cases.
             python pick_case.py report --system cardio
             python pick_case.py report --complaint "chest pain" --ed

  prepare  Convert the guideline PDFs to searchable text, once. Cases then
           read only the sections they need instead of the whole PDF.
             python pick_case.py prepare --system cardio
           Needs: python -m pip install pymupdf pymupdf4llm
           A book (over 150 pages, with bookmarks) becomes one text file per
           chapter, listed in guidelines/<system>/chapters.txt.

  review   Weak topics and weak spots from finished cases (logged by the Rounds
           tools plugin). Also writes review.md.
             python pick_case.py review

  status   What you have covered so far, and which guideline PDFs are missing.
             python pick_case.py status --system cardio

Nothing about a case's content is printed, only file names.

Mixed practice: --system takes several systems separated by commas, or "all".
Their topics are pooled, and the case file never names the system. The same id
in two topic lists is one shared topic with one history.
             python pick_case.py common --system cardio,gi,pulm

Complaint mode: --mode complaint picks by presenting complaint instead of by
system. Topics carry a "presentations" list; a presentation is drawn (or given
with --complaint), then a topic that can present that way. The learner is told
neither the topic nor the system.
             python pick_case.py common --system all --mode complaint
             python pick_case.py common --system all --mode complaint --complaint "chest pain"
             python pick_case.py presentations --system cardio,em

Every command also takes --json, which prints one JSON object instead of text.
The Cases page of the Rounds tools plugin in LearnHarness uses it.

Each case rolls an encounter type (ED, ward, handover, clinic...) and a set of
extras (full history and exam, exam sign, ethics, recall questions, exam-style questions, ECG)
using the percentages in scenarios.json. Edit that file to change the mix.

ECGs come from PTB-XL (PhysioNet, CC BY 4.0). Only the files a case needs are
downloaded, and they are cached in data/ptbxl/. Drawing them needs:
  python -m pip install numpy matplotlib

Folder layout (next to this script):
  scenarios.json          encounter and extra percentages (created if missing)
  topics/cardio.json      topic list for a system, with ECG codes per topic
  guidelines/cardio/      guideline PDFs, named as in topics/cardio.json
  cases/                  generated cases and their ECG images
  data/ptbxl/             cached ECG files
  progress.json           tracker (created automatically)
"""
import argparse
import glob
import json
import random
import re
import secrets
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
CASES = BASE / "cases"
PROGRESS = BASE / "progress.json"
SCENARIOS = BASE / "scenarios.json"
PTBXL_CACHE = BASE / "data" / "ptbxl"
PTBXL_URL = "https://physionet.org/files/ptb-xl/1.0.3/"
API = "https://www.ebi.ac.uk/europepmc/webservices/rest"

AGE_BANDS = ["20s", "30s", "40s", "50s", "60s", "70s", "80s"]

ENCOUNTER_LABELS = {
    "ed_first_presentation": "Emergency department, first presentation",
    "ward_called_by_nurse": "Ward, called by the nurse",
    "ward_round_day_2": "Ward round, day 2",
    "handover": "Handover",
    "clinic_follow_up": "Clinic follow-up",
    "clinic_new_referral": "Clinic new referral",
}
EXTRA_LABELS = {
    "full_history_and_exam": "Full history and exam",
    "exam_sign_deep_dive": "Exam sign deep dive",
    "ethics_or_communication": "Ethics or communication",
    "recall_questions": "Recall questions",
    "exam_style_questions": "Exam-style questions",
}
DEFAULT_SCENARIOS = {
    "encounters": {"ed_first_presentation": 35, "ward_called_by_nurse": 15, "ward_round_day_2": 15,
                   "handover": 10, "clinic_follow_up": 15, "clinic_new_referral": 10},
    "extras": {"full_history_and_exam": 0.25, "exam_sign_deep_dive": 0.30, "ethics_or_communication": 0.10,
               "recall_questions": 0.20, "exam_style_questions": 0.50, "ecg_when_topic_has_one": 0.80, "handover_contains_an_error": 0.50,
               "atypical_presentation": 0.20},
    "review": {"weak_below": 0.7, "after_days": 2, "order": "unseen_first"},
    # Relative weight of a topic's optional "tier". A topic with no tier has weight 1.
    "tiers": {"common": 3, "cant_miss": 2, "rare": 1},
    # Step 2 CK content weights by system (midpoints of the USMLE ranges), used when several
    # systems are mixed. "untagged" is the bucket for topics with no step2_system.
    "step2_systems": {"renal_reproductive": 10, "cardiovascular": 9, "musculoskeletal_skin": 9, "behavioral": 7.5,
                      "blood_immune": 7.5, "gastrointestinal": 7.5, "nervous": 7.5, "respiratory": 7.5,
                      "multisystem": 6, "endocrine": 5, "pregnancy": 5, "human_development": 3, "untagged": 5},
}
STEP2_LABELS = {
    "renal_reproductive": "Renal, urinary and reproductive", "cardiovascular": "Cardiovascular",
    "musculoskeletal_skin": "Musculoskeletal and skin", "behavioral": "Behavioral health",
    "blood_immune": "Blood and immune", "gastrointestinal": "Gastrointestinal",
    "nervous": "Nervous system and special senses", "respiratory": "Respiratory",
    "multisystem": "Multisystem processes", "endocrine": "Endocrine",
    "pregnancy": "Pregnancy, childbirth and puerperium", "human_development": "Human development",
    "untagged": "Untagged",
}
UNTAGGED = "untagged"

# The only values a topic's "presentations" list may hold. Complaint mode picks among these.
PRESENTATIONS = [
    "chest pain", "dyspnea", "palpitations", "syncope/collapse", "hypotension/shock", "abdominal pain",
    "GI bleeding", "vomiting/diarrhea", "headache", "altered mental status", "seizure", "focal weakness",
    "dizziness", "fever", "back pain", "limb pain/swelling", "joint pain", "rash/skin", "red eye/visual loss",
    "sore throat/ENT", "vaginal bleeding/pelvic pain", "scrotal pain", "urinary symptoms", "overdose/poisoning",
    "trauma", "unwell child", "behavioural disturbance",
]
PRESENTATION_NAME = {p.lower(): p for p in PRESENTATIONS}

# Instructions that go into a seed, not into 10-doctrine.md (which only says to follow them).
ATYPICAL_TEXT = (
    "Atypical presentation. Present the diagnosis the way it gets missed in real life and on exams. For example, "
    "MI in an elderly diabetic or a woman with dyspnoea or fatigue and no chest pain, PE as syncope, appendicitis "
    "in pregnancy, meningitis in an older adult as confusion. It must still be a recognised, guideline-documented "
    "presentation, not a contrivance. At conclusion, name why it was atypical and the clue that should have caught it."
)
COMPLAINT_TEXT = (
    "Complaint mode. The learner doesn't know the system. Open with the presenting complaint only. The differential "
    "is the teaching point. At conclusion, ask the learner for the 2\u20133 look-alikes for this complaint and the "
    "finding that separated them, then grade it."
)


# ---------- shared ----------

NOTES = []  # side notes for the learner; also returned under "notes" with --json


def note(msg: str) -> None:
    NOTES.append(msg.strip())
    print(msg)


def load_topics(system: str) -> dict:
    path = BASE / "topics" / f"{system}.json"
    if not path.exists():
        sys.exit(f"No topic list at {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))  # utf-8-sig: Notepad may add a BOM
    except json.JSONDecodeError as e:
        sys.exit(f"topics/{path.name} is not valid JSON ({e}). A missing comma or quote is the usual cause.")
    if not isinstance(data, dict) or not isinstance(data.get("topics"), list):
        sys.exit(f"topics/{path.name} needs a \"topics\" list, like topics/cardio.json.")
    for t in data["topics"]:
        if not isinstance(t, dict) or not t.get("id") or not t.get("topic"):
            sys.exit(f"topics/{path.name}: every topic needs an \"id\" and a \"topic\".")
        if not isinstance(t["id"], str) or "/" in t["id"]:
            sys.exit(f"topics/{path.name}: the id '{t['id']}' must be text without a slash.")
    return data


def all_systems() -> list:
    return sorted(p.stem for p in (BASE / "topics").glob("*.json"))


def parse_systems(value, need_topics: bool = True) -> list:
    """'cardio' or 'cardio,gi,pulm' or 'all' -> list of system names, each with a topic list.
    With need_topics=False (prepare), a system that only has a guidelines folder is accepted too."""
    if not value:
        return []
    names = [s.strip() for s in value.split(",") if s.strip()]
    if "all" in names:
        names = all_systems()
    names = list(dict.fromkeys(names))
    if not names:
        sys.exit("Give at least one system, e.g. --system cardio (there are no topic lists in topics/).")
    for s in names:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", s):
            sys.exit(f"'{s}' is not a system name. Use the file names in topics/ without .json, separated by commas.")
        if need_topics or not (BASE / "guidelines" / s).is_dir():
            load_topics(s)  # exits with a clear message if the list is missing
    return names


def load_pool(systems: list, tiers: dict = None) -> list:
    """The topics of the chosen systems in one list. The same id in two topic files is the same
    topic, so every entry with that id is merged into one (merge_topics), including entries from
    topic files that were not chosen: a shared topic made from one system is the full topic.
    Each topic gets '_key' (its id; everything in progress.json is keyed by it), '_system' (the
    first chosen file it came from), '_step2', '_refs' (its references with resolved paths) and
    '_legacy' (True when it is in one file only and has just the old guideline/guideline_file
    pair, which keeps the old seed text)."""
    def entries_of(system: str, chosen: bool) -> list:
        data = load_topics(system)
        # A topic's own step2_system wins; otherwise the file's top-level default applies.
        return [{**t, "_system": system, "_key": t["id"], "_chosen": chosen,
                 "_step2": t.get("step2_system") or data.get("step2_system"),
                 "_refs": topic_references(system, t), "_legacy": "references" not in t}
                for t in data["topics"]]

    groups = {}
    for system in systems:
        for t in entries_of(system, True):
            groups.setdefault(t["_key"], []).append(t)
    for system in all_systems():
        if system in systems:
            continue
        try:
            others = entries_of(system, False)
        except SystemExit:
            continue  # a broken list that wasn't asked for must not stop this one; status reports it
        for t in others:
            if t["_key"] in groups:
                groups[t["_key"]].append(t)
    return [merge_topics(entries, tiers or {}) if len(entries) > 1 else entries[0] for entries in groups.values()]


def merge_topics(entries: list, tiers: dict) -> dict:
    """One topic from the entries that share an id (chosen systems first): every reference once
    (by file), every ECG code once, and each other field from the first entry that has it. The
    tier is the heaviest among the chosen systems' entries only, so ticking one system weights
    its topics the way its own list says."""
    merged = {}
    for e in entries:
        for k, v in e.items():
            merged.setdefault(k, v)
    refs, seen = [], set()
    for e in entries:
        for r in e["_refs"]:
            if str(r["path"]).lower() not in seen:
                seen.add(str(r["path"]).lower())
                refs.append(r)
    merged["_refs"] = refs
    merged["_legacy"] = False
    merged["ecg_codes"] = list(dict.fromkeys(c for e in entries for c in e.get("ecg_codes") or []))
    merged["presentations"] = [p for e in entries for p in (e.get("presentations") or [])]  # every file's, once
    tiered = [e for e in entries if e["_chosen"] and isinstance(e.get("tier"), str)]
    merged.pop("tier", None)
    if tiered:
        merged["tier"] = max(tiered, key=lambda e: topic_weight(e, tiers))["tier"]  # first wins a tie
    merged["_step2"] = next((e["_step2"] for e in entries if e["_step2"]), None)  # first file that says
    return merged


def step2_bucket(topic: dict, table: dict) -> str:
    """The Step 2 system a topic is drawn under: its step2_system when the table in
    scenarios.json has it, else the shared 'untagged' bucket."""
    name = topic.get("_step2")
    return name if isinstance(name, str) and name in table and name != UNTAGGED else UNTAGGED


def migrate_progress(p: dict) -> bool:
    """Topic history is keyed by topic id alone, so a topic two systems share has one history.
    A progress.json from when keys were system/id is re-keyed: counts of the same id are added
    together. (The oldest files already used bare ids.) Returns True if anything changed."""
    changed = False
    built = p.get("built", {})
    for k in [k for k in built if "/" in k]:
        new = k.rsplit("/", 1)[1]
        built[new] = built.get(new, 0) + built.pop(k)
        changed = True
    for meta in p.get("cases", {}).values():
        t = meta.get("topic")
        if t and "/" in t:
            meta["topic"] = t.rsplit("/", 1)[1]
            changed = True
    return changed


def load_progress() -> dict:
    if not PROGRESS.exists():
        return {"built": {}, "reports": []}
    raw = PROGRESS.read_text(encoding="utf-8")
    p = json.loads(raw)
    if migrate_progress(p):
        backup = PROGRESS.with_name(PROGRESS.name + ".system-keys.bak")
        if not backup.exists():
            backup.write_text(raw, encoding="utf-8")
        save_progress(p)
    return p


def save_progress(p: dict) -> None:
    PROGRESS.write_text(json.dumps(p, indent=2), encoding="utf-8")


def new_case_path() -> Path:
    CASES.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return CASES / f"case_{stamp}_{secrets.token_hex(2)}.md"


def opening_message(paths: list) -> str:
    if len(paths) == 1:
        return (f"Rounds. Run the case at {paths[0]}. I haven't read it, so don't reveal anything "
                "from it until I ask for it.")
    listed = "\n".join(str(p) for p in paths)
    return ("Rounds. Run these cases one after another, in this order. I haven't read them, so don't "
            f"reveal anything from them until I ask for it.\n{listed}")


def copy_to_clipboard(text: str) -> bool:
    import subprocess
    import platform
    system = platform.system()
    try:
        if system == "Windows":
            subprocess.run("clip", input=text.encode("utf-16"), check=True, shell=True)
        elif system == "Darwin":
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
        else:
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode("utf-8"), check=True)
        return True
    except Exception:
        return False


def finish(paths: list, clip: bool) -> dict:
    """Copies the opening message if asked. Returns the fields --json reports for new cases."""
    out = {"cases": [str(p) for p in paths], "message": opening_message(paths) if paths else "", "copied": False}
    if not clip or not paths:
        return out
    msg = out["message"]
    if copy_to_clipboard(msg):
        out["copied"] = True
        print("\nCopied the opening message. Start a Practice session in LearnHarness and paste it.")
    else:
        print("\nCouldn't reach the clipboard. Paste this into a Practice session:\n\n" + msg)
    return out



def topic_references(system: str, topic: dict) -> list:
    """Everything a topic points at, as [{'name', 'file', 'region', 'path'}]: the old
    'guideline' + 'guideline_file' pair first (when present), then each entry of 'references'.
    'file' is a PDF (read through its converted .md) or a chapter .md written by prepare. It lives
    in guidelines/<system>/ unless the reference has "folder": "<other system>", which puts it in
    guidelines/<other system>/ ('othersystem/file' as the file name means the same)."""
    refs = []
    if topic.get("guideline_file"):
        refs.append({"name": topic.get("guideline", ""), "file": topic["guideline_file"], "region": "", "folder": ""})
    for r in topic.get("references") or []:
        if isinstance(r, dict) and isinstance(r.get("file"), str) and r["file"].strip():
            refs.append({"name": str(r.get("name") or ""), "file": r["file"].strip(),
                         "region": str(r.get("region") or "").strip(), "folder": str(r.get("folder") or "").strip()})
    for r in refs:
        inline, _, name = r["file"].replace("\\", "/").rpartition("/")
        folder = r["folder"] or inline or system
        if not re.fullmatch(r"[A-Za-z0-9_-]+", folder):
            sys.exit(f"topics/{system}.json, topic '{topic.get('id')}': the reference folder '{folder}' must be "
                     "the name of a folder in guidelines/.")
        r["folder"] = folder
        r["path"] = BASE / "guidelines" / folder / name
    return refs


def referenced_paths() -> set:
    """Every file any topic list points at, as lower-case full paths. A reference can live in
    another system's folder, so what a folder's files are used for is a question for all lists."""
    paths = set()
    for system in all_systems():
        try:
            topics = load_topics(system)["topics"]
        except SystemExit:
            continue
        paths.update(str(r["path"]).lower() for t in topics for r in topic_references(system, t))
    return paths


def is_us(region: str) -> bool:
    return region.upper() in ("", "US", "USA")


def region_note(region: str) -> str:
    return (f"This reference reflects {region} practice. Step 2 tests current US practice: where they differ "
            "(drugs, doses, thresholds, pathways), grade against US practice, use US drug names, and name the "
            "difference at conclusion.")


def neutral_link(src: Path, dest: Path) -> Path:
    """Give the guideline a per-case name with no topic in it. The learner sees file paths in
    tool-call headlines, so 'svt-2015.md' would give the diagnosis away. A hard link costs no disk
    space; if the drive doesn't support it, fall back to a copy."""
    import shutil
    if dest.exists():
        dest.unlink()
    try:
        import os
        os.link(src, dest)
    except OSError:
        shutil.copyfile(src, dest)
    return dest


def guideline_reference(gpath: Path, case_path: Path, number: int = 1) -> tuple:
    """(seed text, state) where state is 'text', 'pdf' or 'missing'. Each reference of a case gets
    its own neutral link: case_..._ref.md, case_..._ref2.md, ..."""
    md = gpath.with_suffix(".md")
    if md.exists():
        ref = neutral_link(md, case_path.with_name(f"{case_path.stem}_ref{'' if number == 1 else number}.md"))
        return (
            f"Reference guideline text: {ref}\n"
            "The top of the file is a contents list giving each section's line number. Read the contents "
            "first, then read only the sections this case needs (read with offset and limit). To find a specific "
            "threshold or drug as it comes up, use the search_case_ref tool with this case file's path; do not use "
            "grep or find, because the learner sees what those tools search for. "
            "Never read the whole file. '--- Page N ---' markers give the page for citing. If a table or "
            "figure came through garbled, work from the surrounding text; do not use the pdf tool during the case.",
            "text",
        )
    if gpath.exists():
        return (
            "Reference guideline: not converted to text yet, so it cannot be read during the case without "
            "showing the learner the answer (pdf tool results are displayed). Use the guideline named above "
            "from your own knowledge, and at the case's conclusion say which recommendations you could not "
            "check against the text.",
            "pdf",
        )
    return (
        "Reference guideline file: MISSING. Use the guideline named above from your own knowledge, and at "
        "the case's conclusion say which recommendations you could not check against the text.",
        "missing",
    )


# ---------- prepare: PDF guidelines -> searchable text ----------

def _norm(line: str) -> str:
    return re.sub(r"\d+", "#", line.strip().lower())


def pdf_pages(pdf: Path) -> list:
    """[(page number, markdown text)] for every page of the PDF."""
    import pymupdf4llm
    chunks = pymupdf4llm.to_markdown(str(pdf), page_chunks=True, use_ocr=False)
    return [(c["metadata"].get("page_number") or i + 1, c["text"]) for i, c in enumerate(chunks)]


def convert_guideline(pdf: Path, md_path: Path) -> dict:
    return write_guideline_text(pdf_pages(pdf), f"# {pdf.stem} (text version of {pdf.name})", md_path)


def write_guideline_text(pages: list, title_line: str, md_path: Path, deep: bool = False) -> dict:
    """pages is [(page label, markdown text)]. The contents list indexes headings down to level 3.
    With deep=True (book chapters, whose section titles sit at level 4 or lower) it goes as deep
    as it can while staying under two entries per page."""
    # Running headers and footers ("Downloaded from...", author line, page numbers) repeat on most
    # pages. Drop any short line that appears on 60% or more of pages. Headings and table rows are
    # never dropped: numbered headings look alike once digits are ignored.
    from collections import Counter

    def strippable(line: str) -> bool:
        s = line.lstrip()
        return bool(s) and not s.startswith(("#", "|"))

    seen = Counter()
    for _, text in pages:
        seen.update({_norm(l) for l in text.splitlines() if strippable(l)})
    cutoff = max(3, int(0.6 * len(pages)))
    repeated = {k for k, v in seen.items() if v >= cutoff and len(k) < 120} if len(pages) >= 4 else set()

    body, headings, weak = [], [], []
    for num, text in pages:
        kept = [l.rstrip() for l in text.splitlines() if not (strippable(l) and _norm(l) in repeated)]
        content = "\n".join(kept).strip()
        content = re.sub(r"\n{3,}", "\n\n", content)
        if len(content) < 300:
            weak.append(num)
        body.append(f"--- Page {num} ---")
        body.append("")
        for line in content.splitlines():
            m = re.match(r"^(#{1,6})\s+(.*\S)", line)
            if m:
                headings.append((len(body), num, len(m.group(1)), m.group(2).strip("* ")))
            body.append(line)
        body.append("")

    depth = 3
    if deep:
        for level in (4, 5, 6):
            if sum(1 for h in headings if h[2] <= level) > 2 * len(pages):
                break
            depth = level
    headings = [h for h in headings if h[2] <= depth]
    top = min((h[2] for h in headings), default=1) if deep else 1

    head = [
        title_line,
        "",
        "Contents: line number, page, section. Read a section with read(offset=line, limit=...).",
        "",
    ]
    contents_len = len(head) + len(headings) + 2
    for idx, num, level, title in headings:
        head.append(f"L{contents_len + idx + 1}  p{num}  {'  ' * (level - top)}{title}")
    head += ["", "=" * 40]
    assert len(head) == contents_len, "contents length mismatch"
    md_path.write_text("\n".join(head + body) + "\n", encoding="utf-8")
    words = sum(len(t.split()) for _, t in pages)
    return {"pages": len(pages), "headings": len(headings), "weak": weak, "words": words}


# A big reference (a handbook) is written as one text file per top-level bookmark, so a case reads
# one chapter's contents list instead of the whole book's.
SPLIT_OVER_PAGES = 150
MIN_CHAPTER_PAGES = 3  # shorter bookmarks (cover, title page, copyright) get no file
CHAPTER_LIST = "chapters.txt"
INVISIBLE = re.compile("[­​-‏⁠﻿]")  # soft hyphens and zero-width marks in bookmark titles


def chapter_plan(pdf: Path) -> list:
    """Top-level bookmarks as [{'title', 'first', 'last', 'file' or None}]. Pages are 1-based PDF
    pages; 'file' is None for a bookmark too short to be worth a file. Returns [] when the PDF is
    not one to split (150 pages or fewer, or fewer than two top-level bookmarks)."""
    import pymupdf
    with pymupdf.open(str(pdf)) as doc:
        count = doc.page_count
        tops = [(INVISIBLE.sub("", title).strip(), page) for level, title, page, *_ in doc.get_toc()
                if level == 1 and 1 <= page <= count]
        if count <= SPLIT_OVER_PAGES or len(tops) < 2:
            return []
        printed = {i + 1: (doc[i].get_label() or "").strip() for i in range(count)}  # PDF page -> printed page
    plan, taken = [], set()
    for i, (title, first) in enumerate(tops):
        last = max(first, tops[i + 1][1] - 1 if i + 1 < len(tops) else count)
        name = None
        if last - first + 1 >= MIN_CHAPTER_PAGES:
            m = re.match(r"(\d+)[\s.:)-]+(.*)", title)
            number, words = (f"{int(m.group(1)):02d}-", m.group(2)) if m else ("", title)
            slug = re.sub(r"[^a-z0-9]+", "-", words.lower()).strip("-")[:50].strip("-") or "section"
            base = f"{pdf.stem}-{number}{slug}"
            name, n = base + ".md", 2
            while name in taken:
                name, n = f"{base}-{n}.md", n + 1
            taken.add(name)
        plan.append({"title": title, "first": first, "last": last, "file": name,
                     "labels": {n: printed[n] for n in range(first, last + 1) if printed[n]}})
    return plan


def chapter_pages(ch: dict) -> str:
    """'pages 187-226' in the book's own numbering when the PDF has it, else 'PDF pages 206-245'."""
    a, b = ch["labels"].get(ch["first"]), ch["labels"].get(ch["last"])
    return f"pages {a}-{b}" if a and b else f"PDF pages {ch['first']}-{ch['last']}"


def convert_chapters(pdf: Path, plan: list) -> dict:
    pages = pdf_pages(pdf)
    total = {"pages": len(pages), "headings": 0, "weak": [], "words": 0, "chapters": 0}
    for ch in plan:
        if not ch["file"]:
            continue
        # Page markers carry the book's printed page number, which is what its cross-references
        # ("see p. 225") and a citation use.
        part = [(ch["labels"].get(num, num), text) for num, text in pages if ch["first"] <= num <= ch["last"]]
        r = write_guideline_text(
            part, f"# {ch['title']} (text version of {pdf.name}, {chapter_pages(ch)})",
            pdf.with_name(ch["file"]), deep=True)
        total["headings"] += r["headings"]
        total["weak"] += r["weak"]
        total["words"] += r["words"]
        total["chapters"] += 1
    return total


def write_chapter_list(folder: Path, plans: dict) -> None:
    """chapters.txt: every chapter file in this folder with its page range and title."""
    lines = ["Chapter files written by 'prepare'. Use a file name as \"file\" in a topic's \"references\".",
             "Pages are the book's printed page numbers where the PDF has them, as in the '--- Page N ---' "
             "markers inside each file.", ""]
    for pdf_name, plan in plans.items():
        lines.append(pdf_name)
        written = [ch for ch in plan if ch["file"]]
        width = max((len(ch["file"]) for ch in written), default=0)
        for ch in written:
            lines.append(f"  {ch['file']:{width}}  {chapter_pages(ch):18}  {ch['title']}")
        skipped = [ch["title"] for ch in plan if not ch["file"]]
        if skipped:
            lines.append(f"  no file (under {MIN_CHAPTER_PAGES} pages): " + ", ".join(skipped))
        lines.append("")
    (folder / CHAPTER_LIST).write_text("\n".join(lines), encoding="utf-8")


def borrowed_pdfs(system: str) -> list:
    """PDFs this system's topics use from other systems' folders ("folder" on a reference)."""
    if not (BASE / "topics" / f"{system}.json").exists():
        return []
    own = BASE / "guidelines" / system
    found = {r["path"] for t in load_topics(system)["topics"] for r in topic_references(system, t)
             if r["path"].suffix.lower() == ".pdf" and r["path"].parent != own and r["path"].exists()}
    return sorted(found)


def cmd_prepare(args, rng):
    try:
        import pymupdf4llm  # noqa: F401
    except ImportError:
        sys.exit("Needs PyMuPDF. Run: python -m pip install pymupdf pymupdf4llm")
    several = len(args.systems) > 1
    done = 0
    files = []
    # A PDF that any topic names as a whole file is never split, whichever folder it is in.
    whole = {f for f in referenced_paths() if f.endswith(".pdf")}
    handled = set()
    for system in args.systems:
        folder = BASE / "guidelines" / system
        # The system's own folder, then any PDF its topics use from another system's folder.
        pdfs = (sorted(folder.glob("*.pdf")) if folder.exists() else []) + borrowed_pdfs(system)
        pdfs = [f for f in pdfs if f not in handled]
        handled.update(pdfs)
        if not pdfs:
            if not several:
                sys.exit(f"No PDFs in {folder}")
            note(f"{system}: no PDFs in {folder}")
            continue
        if several:
            print(f"{system}:")
        plans = {}
        for pdf in pdfs:
            md = pdf.with_suffix(".md")
            shown = pdf.name if pdf.parent == folder else f"{pdf.parent.name}/{pdf.name}"
            entry = {"system": system, "file": shown}
            files.append(entry)
            try:
                plan = [] if str(pdf).lower() in whole else chapter_plan(pdf)
            except Exception as e:  # a damaged or empty PDF must not stop the other files
                entry.update(state="failed", error=f"{type(e).__name__}: {e}")
                print(f"  {shown}: FAILED ({type(e).__name__}: {e}).")
                continue
            if plan:
                plans[pdf.name] = plan
                outs = [pdf.with_name(ch["file"]) for ch in plan if ch["file"]]
                entry["chapters"] = len(outs)
                if all(o.exists() and o.stat().st_mtime >= pdf.stat().st_mtime for o in outs) and not args.force:
                    entry["state"] = "already_converted"
                    print(f"  {pdf.name}: already converted ({len(outs)} chapter files, listed in {CHAPTER_LIST})")
                    continue
                print(f"  {pdf.name}: splitting into {len(outs)} chapter files; a big book takes a while...", flush=True)
                try:
                    r = convert_chapters(pdf, plan)
                except Exception as e:
                    entry.update(state="failed", error=f"{type(e).__name__}: {e}")
                    print(f"  {pdf.name}: FAILED ({type(e).__name__}: {e}).")
                    continue
                done += 1
                entry.update(state="converted", pages=r["pages"], words=r["words"], sections=r["headings"],
                             thin_pages=r["weak"])
                print(f"  {pdf.name}: {r['pages']} pages, {r['words']:,} words, {r['headings']} sections indexed, "
                      f"in {r['chapters']} chapter files (listed in {CHAPTER_LIST})")
                continue
            if md.exists() and md.stat().st_mtime >= pdf.stat().st_mtime and not args.force:
                entry["state"] = "already_converted"
                print(f"  {pdf.name}: already converted")
                continue
            if str(pdf).lower() not in whole:
                import pymupdf
                with pymupdf.open(str(pdf)) as doc:
                    count = doc.page_count
                if count > SPLIT_OVER_PAGES:
                    msg = (f"{pdf.name} has {count} pages but no top-level bookmarks to split it by chapter, so "
                           "it was not converted. Add bookmarks to the PDF, or name it as a whole file in the "
                           "topic list to convert it as one file.")
                    entry.update(state="failed", error=msg)
                    note(f"  {msg}")
                    continue
            try:
                r = convert_guideline(pdf, md)
            except Exception as e:
                entry.update(state="failed", error=f"{type(e).__name__}: {e}")
                print(f"  {pdf.name}: FAILED ({type(e).__name__}: {e}). Cases will use the PDF instead.")
                continue
            done += 1
            entry.update(state="converted", pages=r["pages"], words=r["words"], sections=r["headings"],
                         thin_pages=r["weak"])
            msg = f"  {pdf.name}: {r['pages']} pages, {r['words']:,} words, {r['headings']} sections indexed"
            if r["headings"] < 5:
                msg += "  <- few headings found, the contents list will be thin"
            if r["weak"]:
                shown = ", ".join(map(str, r["weak"][:12])) + (" ..." if len(r["weak"]) > 12 else "")
                msg += f"\n      little or no text on pages {shown} (usually figures or algorithm charts; normal in small numbers)"
            print(msg)
        if plans:
            write_chapter_list(folder, plans)
    print(f"\nConverted {done} file(s). Spot-check one: open a .md in Notepad and skim a page or two.")
    return {"converted": done, "files": files}


# ---------- scenario settings ----------

def load_scenarios() -> dict:
    if not SCENARIOS.exists():
        SCENARIOS.write_text(json.dumps(DEFAULT_SCENARIOS, indent=2), encoding="utf-8")
        note(f"Created {SCENARIOS.name} with default percentages; edit it to change the mix.")
    try:
        s = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"{SCENARIOS.name} is not valid JSON ({e}). A missing comma or quote is the usual cause.")
    enc = {k: v for k, v in s.get("encounters", {}).items() if not k.startswith("_")}
    if not enc or any(not isinstance(v, (int, float)) or v < 0 for v in enc.values()) or sum(enc.values()) <= 0:
        sys.exit(f"{SCENARIOS.name}: 'encounters' needs numbers of 0 or more, at least one above 0.")
    extras = {**DEFAULT_SCENARIOS["extras"], **{k: v for k, v in s.get("extras", {}).items() if not k.startswith("_")}}
    for k, v in extras.items():
        if not isinstance(v, (int, float)) or not 0 <= v <= 1:
            sys.exit(f"{SCENARIOS.name}: extra '{k}' must be between 0 and 1 (it is {v}).")
    review = {**DEFAULT_SCENARIOS["review"], **{k: v for k, v in s.get("review", {}).items() if not k.startswith("_")}}
    if not isinstance(review["weak_below"], (int, float)) or not 0 <= review["weak_below"] <= 1:
        sys.exit(f"{SCENARIOS.name}: review 'weak_below' must be between 0 and 1.")
    if not isinstance(review["after_days"], (int, float)) or review["after_days"] < 0:
        sys.exit(f"{SCENARIOS.name}: review 'after_days' must be 0 or more.")
    if review["order"] not in ("unseen_first", "review_first"):
        sys.exit(f"{SCENARIOS.name}: review 'order' must be \"unseen_first\" or \"review_first\".")
    tiers = {**DEFAULT_SCENARIOS["tiers"], **{k: v for k, v in s.get("tiers", {}).items() if not k.startswith("_")}}
    for k, v in tiers.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
            sys.exit(f"{SCENARIOS.name}: tier '{k}' needs a weight above 0 (it is {v}).")
    step2 = {**DEFAULT_SCENARIOS["step2_systems"],
             **{k: v for k, v in s.get("step2_systems", {}).items() if not k.startswith("_")}}
    for k, v in step2.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            sys.exit(f"{SCENARIOS.name}: Step 2 system '{k}' needs a weight of 0 or more (it is {v}).")
    return {"encounters": enc, "extras": extras, "review": review, "tiers": tiers, "step2_systems": step2}


def roll_scenario(sc: dict, rng: random.Random) -> dict:
    keys = list(sc["encounters"])
    encounter = rng.choices(keys, weights=[sc["encounters"][k] for k in keys])[0]
    x = sc["extras"]
    rolled = {k: rng.random() < x.get(k, 0) for k in EXTRA_LABELS}
    return {
        "encounter": encounter,
        "extras": rolled,
        "handover_error": encounter == "handover" and rng.random() < x["handover_contains_an_error"],
        "want_ecg": rng.random() < x["ecg_when_topic_has_one"],
    }


def encounter_label(key: str) -> str:
    # Unknown keys you add to scenarios.json are passed through as plain words.
    return ENCOUNTER_LABELS.get(key, key.replace("_", " ").capitalize())


# ---------- PTB-XL ECGs ----------

def ptbxl_file(rel: str) -> Path:
    """Download one PTB-XL file on first use, then reuse the cached copy."""
    dest = PTBXL_CACHE / rel
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(get(PTBXL_URL + rel))
        tmp.replace(dest)
    return dest


def ptbxl_tables():
    import csv
    import ast
    db_path = ptbxl_file("ptbxl_database.csv")
    scp_path = ptbxl_file("scp_statements.csv")
    with open(scp_path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    header = rows[0]
    desc_col = header.index("description")
    scp = {r[0]: r[desc_col] for r in rows[1:] if r}
    records = []
    with open(db_path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            try:
                r["codes"] = ast.literal_eval(r["scp_codes"])
            except (ValueError, SyntaxError):
                continue
            records.append(r)
    return records, scp


def pick_ecg(codes: list, rng: random.Random, used: set):
    """A record carrying one of the codes, adult, preferring human-validated high-quality folds."""
    records, scp = ptbxl_tables()
    wanted = set(codes)

    def matches(r):
        hit = [c for c, lik in r["codes"].items() if c in wanted and (lik == 0 or lik >= 80)]
        try:
            age = float(r["age"])
        except ValueError:
            return False
        return bool(hit) and age >= 18 and r["ecg_id"] not in used

    pool = [r for r in records if matches(r)]
    best = [r for r in pool if r.get("validated_by_human") == "True" and r.get("strat_fold") in ("9", "10")]
    rng.shuffle(best)
    rest = [r for r in pool if r not in best]
    rng.shuffle(rest)
    return best + rest, scp  # candidates in preference order


def heart_rate(base_rel: str):
    """Ventricular rate in beats/min from lead II over the 10 s recording (counts beats, so it also
    works for irregular rhythms like AF). Returns None if the signal is too noisy to count."""
    import numpy as np
    fs, names, sig = read_wfdb(base_rel)
    idx = {n.upper(): i for i, n in enumerate(names)}
    x = sig[:, idx.get("II", 0)]
    x = x - np.convolve(x, np.ones(int(0.6 * fs)) / int(0.6 * fs), mode="same")  # remove baseline wander
    energy = np.convolve(np.diff(x) ** 2, np.ones(int(0.12 * fs)) / int(0.12 * fs), mode="same")
    if energy.max() <= 0:
        return None
    thresh = 0.45 * np.percentile(energy, 99)
    refractory = int(0.30 * fs)  # skips T waves; caps the count at 200/min
    beats, last = 0, -refractory
    above = energy > thresh
    for i in range(1, len(above)):
        if above[i] and not above[i - 1] and i - last >= refractory:
            beats += 1
            last = i
    seconds = len(x) / fs
    bpm = round(beats * 60 / seconds)
    return bpm if 20 <= bpm <= 200 else None


def read_wfdb(base_rel: str):
    """Minimal reader for PTB-XL's WFDB format 16 files. Returns (fs, leads, signals in mV)."""
    import numpy as np
    hea = ptbxl_file(base_rel + ".hea").read_text(encoding="utf-8").splitlines()
    first = hea[0].split()
    n_sig, fs, n_samp = int(first[1]), float(first[2]), int(first[3])
    gains, baselines, names = [], [], []
    for line in hea[1:1 + n_sig]:
        parts = line.split()
        m = re.match(r"([\d.]+)(?:\((-?\d+)\))?", parts[2])
        gain = float(m.group(1)) if m else 200.0
        base = int(m.group(2)) if m and m.group(2) else int(parts[4])
        gains.append(gain or 200.0)
        baselines.append(base)
        names.append(parts[-1])
    raw = np.frombuffer(ptbxl_file(base_rel + ".dat").read_bytes(), dtype="<i2")
    raw = raw[: n_samp * n_sig].reshape(-1, n_sig).astype(float)
    sig = (raw - np.array(baselines)) / np.array(gains)
    return fs, names, sig


def render_ecg(base_rel: str, out_png: Path) -> None:
    """Standard 12-lead layout (3x4, 2.5 s each) with a 10 s lead II rhythm strip, on ECG paper."""
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fs, names, sig = read_wfdb(base_rel)
    idx = {n.upper(): i for i, n in enumerate(names)}
    sig = sig - np.median(sig, axis=0)  # remove DC offset per lead
    layout = [["I", "AVR", "V1", "V4"], ["II", "AVL", "V2", "V5"], ["III", "AVF", "V3", "V6"]]
    seg = int(2.5 * fs)
    row_gap = 3.0  # mV between rows
    rows = 4
    width_s, height_mv = 10.0, row_gap * rows
    # 25 mm/s and 10 mm/mV
    fig = plt.figure(figsize=(width_s * 25 / 25.4, height_mv * 10 / 25.4), dpi=150)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, width_s)
    ax.set_ylim(-height_mv + row_gap / 2, row_gap / 2)
    for x in np.arange(0, width_s + 1e-9, 0.04):
        ax.axvline(x, color="#f4c7c7" if round(x / 0.04) % 5 else "#e58f8f", lw=0.3 if round(x / 0.04) % 5 else 0.6, zorder=0)
    for y in np.arange(-height_mv + row_gap / 2, row_gap / 2 + 1e-9, 0.1):
        major = round((y - row_gap / 2) / 0.1) % 5 == 0
        ax.axhline(y, color="#e58f8f" if major else "#f4c7c7", lw=0.6 if major else 0.3, zorder=0)
    for r, row in enumerate(layout):
        y0 = -r * row_gap
        for c, lead in enumerate(row):
            if lead not in idx:
                continue
            s = sig[c * seg:(c + 1) * seg, idx[lead]]
            t = c * 2.5 + np.arange(len(s)) / fs
            ax.plot(t, s + y0, color="black", lw=0.7)
            ax.text(c * 2.5 + 0.05, y0 + 0.9, {"AVR": "aVR", "AVL": "aVL", "AVF": "aVF"}.get(lead, lead), fontsize=8)
            if c:
                ax.plot([c * 2.5] * 2, [y0 - 0.3, y0 + 0.3], color="black", lw=0.7)
    if "II" in idx:
        s = sig[: int(width_s * fs), idx["II"]]
        y0 = -3 * row_gap
        ax.plot(np.arange(len(s)) / fs, s + y0, color="black", lw=0.7)
        ax.text(0.05, y0 + 0.9, "II", fontsize=8)
    ax.text(width_s - 0.05, -height_mv + row_gap / 2 + 0.15, "25 mm/s   10 mm/mV", fontsize=7, ha="right")
    ax.axis("off")
    fig.savefig(out_png)
    plt.close(fig)


def attach_ecg(topic: dict, dest: Path, rng: random.Random, progress: dict):
    """Returns (seed text block, frame or None), or (None, None) if no ECG could be attached."""
    try:
        import numpy  # noqa: F401
        import matplotlib  # noqa: F401
    except ImportError:
        note("Note: ECGs skipped. Run 'python -m pip install numpy matplotlib' to enable them.")
        return None, None
    used = set(progress.setdefault("ecgs", []))
    lo, hi = topic.get("ecg_rate", [None, None]) if isinstance(topic.get("ecg_rate"), list) else (None, None)
    try:
        candidates, scp = pick_ecg(topic["ecg_codes"], rng, used)
        rec = bpm = None
        for cand in candidates[:12]:  # each check downloads one ~120 KB recording
            rate = heart_rate(cand["filename_hr"])
            if rate is None:
                continue
            if (lo is not None and rate < lo) or (hi is not None and rate > hi):
                continue
            rec, bpm = cand, rate
            break
        if rec is None:
            return None, None
        png = dest.with_name(dest.stem + "_ecg.png")
        render_ecg(rec["filename_hr"], png)
    except Exception as e:
        note(f"Note: ECG skipped for one case ({type(e).__name__}: {e}).")
        return None, None
    progress["ecgs"].append(rec["ecg_id"])
    labels = [f"{scp.get(c, c)} ({c}{'' if lik == 0 else f', {lik:.0f}%'})" for c, lik in rec["codes"].items()]
    age = float(rec["age"])
    age_txt = "90 or older" if age > 89 else f"{age:.0f}"
    sex = {"0": "male", "1": "female"}.get(rec["sex"], "unknown sex")
    block = (
        f"Image: 12-lead ECG at {png}\n"
        f"ECG ground truth (PTB-XL, cardiologist-coded SCP-ECG statements): {'; '.join(labels)}\n"
        f"Heart axis code: {rec.get('heart_axis') or 'not recorded'}\n"
        f"Ventricular rate on this tracing: about {bpm} beats/min (measured by the script). The vitals at the "
        "time this ECG is taken must match this rate; build the case's timeline around it.\n"
        "Recorded 1989-1996. Release it only when the learner orders an ECG. Grade interpretation against "
        "these statements, not your own reading. The patient frame above comes from this ECG's patient.\n"
    )
    return block, f"{age_txt}, {sex}"


# ---------- common: guideline-built seeds ----------

LOG = BASE / "case_log.jsonl"


def read_log() -> dict:
    """case id -> latest logged result (the plugin appends one line per finished case)."""
    results = {}
    if not LOG.exists():
        return results
    for line in LOG.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(e, dict) and e.get("case"):
            results[e["case"]] = e
    return results


def topic_history(progress: dict, log: dict) -> dict:
    """topic id -> {'last_built': datetime, 'last_score': float|None} from the case index and the log."""
    hist = {}
    for case_id, meta in progress.get("cases", {}).items():
        tid = meta.get("topic")
        if not tid:
            continue
        h = hist.setdefault(tid, {"last_built": None, "last_score": None, "last_logged": None})
        made = datetime.fromisoformat(meta["made"]) if meta.get("made") else None
        if made and (h["last_built"] is None or made > h["last_built"]):
            h["last_built"] = made
        res = log.get(case_id)
        if res:
            when = datetime.fromisoformat(res["logged"].replace("Z", "+00:00")).replace(tzinfo=None)
            if h["last_logged"] is None or when > h["last_logged"]:
                h["last_logged"], h["last_score"] = when, res.get("score")
    return hist


def topic_weight(topic: dict, tiers: dict) -> float:
    """Weight of the topic's tier from scenarios.json; 1 for a topic with no tier (or an unknown one)."""
    return tiers.get(topic.get("tier"), 1) if isinstance(topic.get("tier"), str) else 1


def pick_topics(topics: list, built: dict, n: int, rng: random.Random, hist: dict = None, review: dict = None,
                tiers: dict = None) -> list:
    """Never-seen topics (heavier tier first) and weak topics that are due again (weakest first),
    in the order the 'review' settings choose; then the least-covered, meaning the lowest cases
    built divided by tier weight. Random among ties. With every weight 1 the tier changes nothing."""
    hist, review = hist or {}, review or DEFAULT_SCENARIOS["review"]
    tiers = tiers or {}
    now = datetime.now()
    pool = topics[:]
    rng.shuffle(pool)

    def key(t):
        h = hist.get(t["_key"], {})
        score, last = h.get("last_score"), h.get("last_built")
        due = last is None or (now - last).total_seconds() >= review["after_days"] * 86400
        unseen_rank, weak_rank = (0, 1) if review.get("order", "unseen_first") == "unseen_first" else (1, 0)
        weight = topic_weight(t, tiers)
        if built.get(t["_key"], 0) == 0:
            return (unseen_rank, -weight, 0)
        if score is not None and score < review["weak_below"] and due:
            return (weak_rank, score, 0)
        return (2, 0.0, built.get(t["_key"], 0) / weight)

    pool.sort(key=key)
    return pool[:n]


def pick_mixed(topics: list, built: dict, n: int, rng: random.Random, hist: dict, review: dict, tiers: dict,
               table: dict) -> list:
    """Mixed systems: each case first draws a Step 2 system, weighted by the table in
    scenarios.json but only among the systems that still have a topic in the pool, then picks
    the topic inside it with the usual rules (pick_topics)."""
    left, chosen = topics[:], []
    for _ in range(n):
        buckets = {}
        for t in left:
            buckets.setdefault(step2_bucket(t, table), []).append(t)
        if not buckets:
            break
        names = sorted(b for b in buckets if table.get(b, 0) > 0) or sorted(buckets)
        weights = [table.get(b, 0) or 1 for b in names]
        bucket = rng.choices(names, weights=weights)[0]
        topic = pick_topics(buckets[bucket], built, 1, rng, hist, review, tiers)[0]
        chosen.append(topic)
        left.remove(topic)
    return chosen


def presentations_of(topic: dict) -> list:
    """The topic's presentations that are in the vocabulary, spelled as the vocabulary spells them."""
    listed = topic.get("presentations")
    names = [PRESENTATION_NAME.get(str(p).strip().lower()) for p in (listed if isinstance(listed, list) else [])]
    return list(dict.fromkeys(n for n in names if n))


def available_presentations(topics: list) -> list:
    """Presentations that at least one of these topics has, in vocabulary order."""
    have = {p for t in topics for p in presentations_of(t)}
    return [p for p in PRESENTATIONS if p in have]


def match_presentation(text: str, topics: list) -> str:
    """--complaint as typed -> a vocabulary name that has a topic in the pool, or a plain error."""
    typed = " ".join(str(text).lower().split())
    name = PRESENTATION_NAME.get(typed)
    if not name:
        close = [p for p in PRESENTATIONS if typed and typed in p.lower()]
        if len(close) != 1:
            sys.exit(f"'{text}' is not a presentation. Use one of: {', '.join(PRESENTATIONS)}.")
        name = close[0]
    have = available_presentations(topics)
    if name not in have:
        sys.exit(f"No topic in the chosen systems is tagged '{name}'. "
                 + (f"These have topics: {', '.join(have)}." if have else "None of their topics has a presentations list."))
    return name


def pick_by_complaint(topics: list, built: dict, n: int, rng: random.Random, hist: dict, review: dict, tiers: dict,
                      wanted: str = None) -> list:
    """Complaint mode: each case takes a presentation (the one asked for, else one drawn evenly
    among those that still have a topic in the pool), then picks a topic that can present that
    way with the usual rules (pick_topics). Step 2 system weights play no part.
    Returns (topic, presentation) pairs."""
    left, chosen = topics[:], []
    for _ in range(n):
        groups = {}
        for t in left:
            for p in presentations_of(t):
                groups.setdefault(p, []).append(t)
        names = [p for p in PRESENTATIONS if p in groups and wanted in (None, p)]
        if not names:
            break
        name = wanted or rng.choice(names)
        topic = pick_topics(groups[name], built, 1, rng, hist, review, tiers)[0]
        chosen.append((topic, name))
        left.remove(topic)
    return chosen


def cmd_presentations(args, rng):
    """The presentations complaint mode can use with these systems. Names come from the topic
    lists and the fixed vocabulary only, never from cases."""
    topics = load_pool(args.systems, load_scenarios()["tiers"])
    names = available_presentations(topics)
    untagged = sum(1 for t in topics if not presentations_of(t))
    print("Presentations with at least one topic:" if names else "No topic here has a presentations list.")
    for p in names:
        print(f"  {p}")
    if untagged:
        print(f"{untagged} topic{'s have' if untagged != 1 else ' has'} no presentation, so complaint mode never picks "
              f"{'them' if untagged != 1 else 'it'}.")
    return {"presentations": names, "untagged": untagged}


def cmd_common(args, rng):
    scenarios = load_scenarios()
    topics = load_pool(args.systems, scenarios["tiers"])
    progress = load_progress()
    built = progress.setdefault("built", {})
    enc_counts = progress.setdefault("encounters", {})
    hist = topic_history(progress, read_log())
    complaint_mode = args.mode == "complaint" or bool(args.complaint)
    if complaint_mode:
        wanted = match_presentation(args.complaint, topics) if args.complaint else None
        picks = pick_by_complaint(topics, built, args.batch, rng, hist, scenarios["review"], scenarios["tiers"], wanted)
        if not picks:
            sys.exit("None of the chosen systems' topics has a presentations list, so complaint mode has nothing to pick.")
    elif len(args.systems) > 1:
        chosen = pick_mixed(topics, built, args.batch, rng, hist, scenarios["review"], scenarios["tiers"],
                            scenarios["step2_systems"])
        picks = [(t, None) for t in chosen]
    else:  # one system: no Step 2 draw, so its picks are what they always were
        chosen = pick_topics(topics, built, args.batch, rng, hist, scenarios["review"], scenarios["tiers"])
        picks = [(t, None) for t in chosen]
    # The atypical roll has its own generator, so adding it left every other roll of a given
    # --seed (topic, encounter, extras, ECG, patient frame) where it was.
    side = random.Random(None if args.seed is None else f"atypical:{args.seed}")
    missing = unconverted = 0
    made = []
    with_ecg = []
    for topic, presentation in picks:
        sc = roll_scenario(scenarios, rng)
        # Not rolled in complaint mode: the presentations list already covers the atypical routes.
        atypical = not complaint_mode and side.random() < scenarios["extras"]["atypical_presentation"]
        dest = new_case_path()
        refs = topic["_refs"]
        states, blocks = [], []
        for i, r in enumerate(refs, 1):
            text, state = guideline_reference(r["path"], dest, i)
            states.append(state)
            if topic["_legacy"]:
                blocks.append(f"Current guideline: {r['name']}\n{text}\n")  # the old single-guideline seed, unchanged
                continue
            label = "Current guideline" if is_us(r["region"]) else f"Reference ({r['region']})"
            blocks.append(f"{label}: {r['name']}\n{text}\n" + ("" if is_us(r["region"]) else region_note(r["region"]) + "\n"))
        if not refs:
            blocks.append("Reference: none given for this topic. Work from current US practice, and at the case's "
                          "conclusion say which recommendations you could not check against a text.\n")
        missing += "missing" in states
        unconverted += "pdf" in states
        has_us = topic["_legacy"] or any(is_us(r["region"]) for r in refs)
        complaint = topic.get("complaint")

        ecg_block, ecg_frame = (None, None)
        if sc["want_ecg"] and topic.get("ecg_codes"):
            ecg_block, ecg_frame = attach_ecg(topic, dest, rng, progress)
        frame = ecg_frame or f"{rng.choice(AGE_BANDS)}, {rng.choice(['male', 'female'])}"

        enc_line = encounter_label(sc["encounter"])
        if sc["encounter"] == "handover":
            enc_line += " (contains one planted error)" if sc["handover_error"] else " (accurate, no planted error)"
        extras = "\n".join(f"- {label}: {'ON' if sc['extras'][k] else 'off'}" for k, label in EXTRA_LABELS.items())

        if presentation:  # the topic's own complaint may not be the route this case takes
            complaint_line = (f"Presentation: {presentation} (open the case with this as the presenting complaint, "
                              "in the patient's own words)\n")
            special = COMPLAINT_TEXT
            build = ("Build a presentation of this topic that arrives with the complaint above, as a Step 2 question "
                     "or a real patient would show it. If that complaint is not this topic's textbook route, it must "
                     "still be a recognised, documented presentation. ")
        elif atypical:
            complaint_line = (f"Usual presenting complaint: {complaint} (this case is atypical, so open with the complaint "
                              "that fits the atypical presentation described below)\n" if complaint else "")
            special = ATYPICAL_TEXT
            build = "Build the atypical presentation described above instead of the common, typical one. "
        else:
            complaint_line = f"Presenting complaint: {complaint} (open the case with this complaint)\n" if complaint else ""
            special = ""
            build = "Build a common, typical presentation of this topic as a Step 2 question or a real patient would show it. "

        dest.write_text(
            "# Case seed (for the agent only)\n\n"
            "This is a built case. Follow the 'Built cases' rules in rounds mode.\n\n"
            f"Topic: {topic['topic']}\n"
            + complaint_line
            + f"Patient frame: {frame}\n"
            f"Encounter: {enc_line}\n"
            f"Extras:\n{extras}\n\n"
            + (special + "\n\n" if special else "")
            + "\n".join(blocks) + "\n"
            + (ecg_block + "\n" if ecg_block else "")
            + build + "Grade all management against "
            + ("the current guideline.\n" if has_us else "current US practice.\n"),
            encoding="utf-8",
        )
        built[topic["_key"]] = built.get(topic["_key"], 0) + 1
        progress.setdefault("cases", {})[dest.stem] = {
            "system": topic["_system"], "topic": topic["_key"], "encounter": sc["encounter"],
            "made": datetime.now().isoformat(timespec="seconds"),
            **({"mode": "complaint", "presentation": presentation} if presentation else {}),
            **({"atypical": True} if atypical else {}),
        }
        enc_counts[sc["encounter"]] = enc_counts.get(sc["encounter"], 0) + 1
        save_progress(progress)
        print(f"Saved {dest.relative_to(BASE)}" + ("  (+ ECG)" if ecg_block else ""))
        made.append(dest)
        with_ecg.append(bool(ecg_block))
        time.sleep(1.1)  # keeps timestamps in file names distinct and in order
    if missing:
        note(f"Note: {missing} of these cases have no guideline PDF saved yet. "
             f"Run 'status --system {args.system}' to see which files are missing.")
    if unconverted:
        note(f"Note: {unconverted} of these cases point at a PDF that hasn't been converted to text. "
             "Run 'Prepare guidelines' first to make them cheaper.")
    out = finish(made, args.clip)
    out["with_ecg"] = sum(with_ecg)
    return out


# ---------- report: Europe PMC case reports ----------

CASE_TITLE = re.compile(r"case|patient|presentation|clinical (history|summary|description)", re.I)
SKIP_TITLE = re.compile(r"discussion|conclusion|introduction|background|literature|review|consent|"
                        r"acknowledg|abbreviation|funding|competing|declaration|availability|contribution", re.I)
POPULATION = {
    "adult": '(MESH:"Adult" OR MESH:"Middle Aged" OR MESH:"Aged" OR MESH:"Young Adult")',
    "child": '(MESH:"Child" OR MESH:"Child, Preschool" OR MESH:"Infant" OR MESH:"Adolescent" OR MESH:"Infant, Newborn")',
}


def get(url: str, retries: int = 3) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "learnharness-case-picker/1.1"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def any_of(field: str, words) -> str:
    return "(" + " OR ".join(f'{field}:"{w}"' for w in words) + ")"


def build_query(args, complaints, year: int) -> str:
    parts = ['PUB_TYPE:"case-report"', "OPEN_ACCESS:y", "IN_EPMC:y", "LANG:eng", f"PUB_YEAR:{year}"]
    if complaints:
        parts.append(any_of("ABSTRACT", complaints))
    if args.topic:
        parts.append(any_of("TITLE", args.topic))
    if args.ed:
        parts.append('("emergency department" OR "emergency room")')
    if args.journal:
        parts.append(f'JOURNAL:"{args.journal}"')
    if args.population:
        parts.append(POPULATION[args.population])
    return " AND ".join(parts)


def search(query: str) -> list:
    params = urllib.parse.urlencode({"query": query, "format": "json", "resultType": "lite", "pageSize": 1000})
    data = json.loads(get(f"{API}/search?{params}"))
    return [r for r in data.get("resultList", {}).get("result", []) if r.get("pmcid")]


def text_of(el) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def section_text(sec) -> str:
    out = []
    for child in sec:
        tag = child.tag.split("}")[-1]
        if tag == "title":
            continue
        if tag == "sec":
            t = child.find("title")
            if t is not None and text_of(t):
                out.append(f"### {text_of(t)}")
            out.append(section_text(child))
        elif tag in ("p", "list", "table-wrap", "disp-quote"):
            out.append(text_of(child))
    return "\n\n".join(x for x in out if x)


def parse_article(xml_bytes: bytes) -> dict:
    root = ET.fromstring(xml_bytes)
    title = root.find(".//article-meta//article-title")
    journal = root.find(".//journal-title")
    lic = root.find(".//permissions/license")
    lic_url = None
    if lic is not None:
        lic_url = next((v for k, v in lic.attrib.items() if k.endswith("href")), None)
    abstract = root.find(".//article-meta/abstract")
    body = root.find(".//body")
    case, rest = [], []
    if body is not None:
        for sec in body.findall("sec"):
            t = sec.find("title")
            name = text_of(t) if t is not None else ""
            content = section_text(sec)
            (case if CASE_TITLE.search(name) and not SKIP_TITLE.search(name) else rest).append((name, content))
    return {
        "title": text_of(title) if title is not None else "",
        "journal": text_of(journal) if journal is not None else "",
        "license": lic_url or (text_of(lic) if lic is not None else "not stated"),
        "abstract": text_of(abstract) if abstract is not None else "",
        "case": case,
        "rest": rest,
    }


def render_report(art: dict, pmcid: str) -> str:
    lines = [
        "# Case source (for the agent only)", "",
        "This is a published case report. Grade management against the current US guideline, "
        "not against what the report's authors did.", "",
        f"Article: {art['title']}",
        f"Journal: {art['journal']}",
        f"PMCID: {pmcid}  (https://europepmc.org/article/PMC/{pmcid})",
        f"License: {art['license']}", "",
        "## Abstract", "", art["abstract"], "",
    ]
    for name, content in art["case"]:
        lines += [f"## {name}", "", content, ""]
    for name, content in art["rest"]:
        if name and content:
            lines += [f"## {name}", "", content, ""]
    return "\n".join(lines)


def cmd_report(args, rng):
    progress = load_progress()
    scenarios = load_scenarios()
    used = set(progress.setdefault("reports", []))
    presets = {s: load_topics(s).get("complaints", []) for s in args.systems}
    y0, y1 = (int(x) for x in args.years.split("-"))
    saved = 0
    made = []
    for _ in range(args.batch):
        # With several systems, each case draws its system first. With a system preset and no
        # --complaint, each case gets a fresh random complaint.
        system = (args.systems[0] if len(args.systems) == 1 else rng.choice(args.systems)) if args.systems else ""
        preset = presets.get(system, [])
        complaints = args.complaint or ([rng.choice(preset)] if preset else [])
        years = list(range(y0, y1 + 1))
        rng.shuffle(years)
        done, tries = False, 0
        for year in years:
            hits = [h for h in search(build_query(args, complaints, year)) if h["pmcid"] not in used]
            rng.shuffle(hits)
            for hit in hits[:5]:
                tries += 1
                pmcid = hit["pmcid"]
                time.sleep(0.3)
                try:
                    art = parse_article(get(f"{API}/{pmcid}/fullTextXML"))
                except Exception:
                    continue
                words = sum(len(c.split()) for _, c in art["case"])
                if words < args.min_words:
                    continue
                dest = new_case_path()
                sc = roll_scenario(scenarios, rng)
                extras = "\n".join(f"- {label}: {'ON' if sc['extras'][k] else 'off'}" for k, label in EXTRA_LABELS.items())
                dest.write_text(f"Extras for this case:\n{extras}\n\n" + render_report(art, pmcid), encoding="utf-8")
                used.add(pmcid)
                progress["reports"].append(pmcid)
                progress.setdefault("cases", {})[dest.stem] = {
                    "system": system, "report": pmcid, "made": datetime.now().isoformat(timespec="seconds"),
                }
                save_progress(progress)
                print(f"Saved {dest.relative_to(BASE)} (case section: {words} words)")
                made.append(dest)
                saved += 1
                done = True
                time.sleep(1.1)
                break
            if done or tries >= 40:
                break
        if not done:
            note("One case could not be found with these filters; skipped.")
    if not saved:
        sys.exit("No usable case found. Loosen the filters or widen --years.")
    return finish(made, args.clip)


# ---------- review ----------

def cmd_review(args, rng):
    progress = load_progress()
    log = read_log()
    index = progress.get("cases", {})
    names = {}
    for sysname in all_systems():
        try:
            for t in load_topics(sysname)["topics"]:
                names.setdefault(t["id"], t["topic"])
        except SystemExit:
            pass
    # A topic belongs to every system whose list has its id, whichever system its case was made from.
    wanted = {t["id"] for s in args.systems for t in load_topics(s)["topics"]}
    rows = []
    for case_id, e in log.items():
        meta = index.get(case_id, {})
        if args.systems and meta.get("topic") in names:
            if meta["topic"] not in wanted:
                continue
        elif args.systems and meta.get("system") and meta["system"] not in args.systems:
            continue
        label = names.get(meta.get("topic"), "Case report" if meta.get("report") else meta.get("topic", "Unknown"))
        rows.append((e.get("logged", ""), label, e))
    if not rows:
        print("No finished cases logged yet. Cases are logged at the end of each practice session.")
        return {"finished": 0, "topics": [], "weak_spots": [], "recent": []}
    rows.sort(key=lambda r: r[0], reverse=True)

    by_topic = {}
    for _, label, e in rows:
        by_topic.setdefault(label, []).append(e.get("score", 0))
    ranked = sorted(by_topic.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
    lines = ["# Case review", "", f"{len(rows)} finished cases logged.", "", "## By topic (weakest first)", ""]
    for label, scores in ranked:
        lines.append(f"- {label}: {len(scores)} case(s), last {scores[0]:.0%}, average {sum(scores) / len(scores):.0%}")
    lines += ["", "## Weak spots, most recent first", ""]
    weak_spots = []
    for when, label, e in rows[: args.last]:
        spots = e.get("weak_spots") or []
        if not spots:
            continue
        lines.append(f"### {when[:10]} · {label} · {e.get('diagnosis', '')} · {e.get('score', 0):.0%}")
        lines += [f"- {w}" for w in spots]
        lines.append("")
        weak_spots.append({"date": when[:10], "topic": label, "diagnosis": e.get("diagnosis", ""),
                           "score": e.get("score", 0), "spots": spots})
    out = BASE / "review.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[: 6 + len(by_topic)]))
    print(f"\nFull list of weak spots written to {out.name} (open it in Notepad).")
    # Only finished cases appear here, so naming their topic and diagnosis spoils nothing.
    return {
        "finished": len(rows),
        "topics": [{"topic": label, "cases": len(s), "last": s[0], "average": sum(s) / len(s)} for label, s in ranked],
        "weak_spots": weak_spots,
        "recent": [{"date": when[:10], "topic": label, "diagnosis": e.get("diagnosis", ""), "score": e.get("score", 0)}
                   for when, label, e in rows[: args.last]],
    }


# ---------- status ----------

def system_status(system: str, built: dict, show_topics: bool) -> dict:
    topics = load_topics(system)["topics"]

    def count(t):  # by id alone: a topic shared with another system counts wherever its case was made
        return built.get(t["id"], 0)

    done = [t for t in topics if count(t) > 0]
    refs = [r for t in topics for r in topic_references(system, t)]
    missing = {}
    for r in refs:
        if not r["path"].exists():
            missing.setdefault(r["file"], r["name"])
    unconverted = sorted({r["file"] for r in refs
                          if r["path"].exists() and not r["path"].with_suffix(".md").exists()})
    folder = BASE / "guidelines" / system
    expected = referenced_paths()  # another system's topics may use a PDF in this folder
    # A PDF that prepare split into chapter files is in use even though no topic names the PDF itself.
    strays = sorted(p.name for p in folder.glob("*.pdf") if str(p).lower() not in expected
                    and not any(folder.glob(glob.escape(p.stem) + "-*.md"))) if folder.exists() else []
    out = {
        "system": system,
        "topics_total": len(topics),
        "topics_covered": len(done),
        "built": sum(built.get(i, 0) for i in {t["id"] for t in topics}),
        "missing": [{"file": f, "guideline": g} for f, g in missing.items()],
        "unconverted": unconverted,
        "strays": strays,
    }
    if show_topics:
        # Counts a case as covered when it is picked, so this also names cases you haven't run yet.
        out["topics"] = [{"topic": t["topic"], "count": count(t)} for t in sorted(done, key=lambda t: -count(t))]
    return out


def step2_mix(systems: list, progress: dict, log: dict, table: dict, everything: bool, tiers: dict = None) -> list:
    """Built cases per Step 2 system, with the share the weights aim for among the systems these
    topic lists cover. Counts finished cases only, because a count that moves when a case is made
    tells which system that unrun case came from; everything=True (--show-topics) counts them all."""
    pool = load_pool(systems, tiers)
    bucket_of = {t["_key"]: step2_bucket(t, table) for t in pool}
    present = sorted(set(bucket_of.values()))
    counts = dict.fromkeys(present, 0)
    for case_id, meta in progress.get("cases", {}).items():
        b = bucket_of.get(meta.get("topic"))
        if b and (everything or case_id in log):
            counts[b] += 1
    live = [b for b in present if table.get(b, 0) > 0] or present
    total_weight = sum(table.get(b, 0) or 1 for b in live)
    rows = [{"key": b, "label": STEP2_LABELS.get(b, b.replace("_", " ").capitalize()), "count": counts[b],
             "target": ((table.get(b, 0) or 1) / total_weight if b in live else 0.0)} for b in present]
    return sorted(rows, key=lambda r: (-r["count"], -r["target"], r["key"]))


def topic_warnings(table: dict, tiers: dict) -> list:
    """Problems across all topic lists. The same id in two files is one shared topic, which is
    fine; what gets a warning is an id twice in one file, a shared topic whose files disagree on
    step2_system, different ids with the same topic text or the same 'canonical' diagnosis, and
    tier or step2_system names scenarios.json doesn't have."""
    by_id, by_text, by_canon, out = {}, {}, {}, []
    bad_tier, bad_step2, bad_pres = {}, {}, {}

    for system in all_systems():
        try:
            data = load_topics(system)
        except SystemExit as e:
            out.append(str(e.code))
            continue
        default = data.get("step2_system")
        if default and default not in table:
            bad_step2.setdefault(str(default), set()).add(system)
        for t in data["topics"]:
            entry = {"system": system, "id": t["id"], "topic": str(t["topic"]),
                     "step2": t.get("step2_system") or default,
                     "pres": frozenset(presentations_of(t)) if "presentations" in t else None}
            listed = t.get("presentations")
            for p in (listed if isinstance(listed, list) else [listed] if listed else []):
                if str(p).strip().lower() not in PRESENTATION_NAME:
                    bad_pres.setdefault(str(p), set()).add(system)
            by_id.setdefault(t["id"], []).append(entry)
            by_text.setdefault(" ".join(str(t["topic"]).lower().split()), []).append(entry)
            if t.get("canonical"):
                by_canon.setdefault(" ".join(str(t["canonical"]).lower().split()), []).append(entry)
            if t.get("tier") and t["tier"] not in tiers:
                bad_tier.setdefault(str(t["tier"]), set()).add(system)
            if t.get("step2_system") and t["step2_system"] not in table:
                bad_step2.setdefault(str(t["step2_system"]), set()).add(system)
    for tid, entries in by_id.items():
        systems = [e["system"] for e in entries]
        twice = sorted({x for x in systems if systems.count(x) > 1})
        if twice:
            out.append(f"The id '{tid}' is used more than once inside {', '.join(twice)}.")
        said = list(dict.fromkeys(e["step2"] for e in entries if e["step2"]))
        if len(said) > 1:
            out.append(f"The shared topic '{tid}' has different step2_system values ("
                       + ", ".join(f"{e['system']}: {e['step2']}" for e in entries if e["step2"])
                       + f"). Mixed practice uses the first, {said[0]}.")
        if len({e["pres"] for e in entries if e["pres"] is not None}) > 1:
            out.append(f"The shared topic '{tid}' has different presentations in "
                       + ", ".join(e["system"] for e in entries if e["pres"] is not None)
                       + ". Complaint mode uses all of them.")
    flagged = set()  # one warning per group of topics
    for label, groups in (("The same topic text is listed under different ids", by_text),
                          ("Different ids are marked as the same diagnosis (canonical '{key}')", by_canon)):
        for key, entries in groups.items():
            ids = frozenset(e["id"] for e in entries)
            if len(ids) > 1 and ids not in flagged:
                flagged.add(ids)
                out.append(f"{label.format(key=key)}: " + ", ".join(f"{e['system']} id '{e['id']}' ('{e['topic']}')" for e in entries))
    for name, systems in sorted(bad_tier.items()):
        out.append(f"Tier '{name}' ({', '.join(sorted(systems))}) is not in scenarios.json, so those topics get weight 1.")
    for name, systems in sorted(bad_pres.items()):
        out.append(f"Presentation '{name}' ({', '.join(sorted(systems))}) is not in the list complaint mode uses, "
                   "so it is ignored.")
    for name, systems in sorted(bad_step2.items()):
        out.append(f"Step 2 system '{name}' ({', '.join(sorted(systems))}) is not in scenarios.json, so those topics "
                   "count as untagged.")
    return out


def cmd_status(args, rng):
    progress = load_progress()
    built = progress.get("built", {})
    systems = [system_status(s, built, args.show_topics) for s in args.systems]
    single = len(systems) == 1
    if single:
        totals = {k: systems[0][k] for k in ("topics_total", "topics_covered", "built")}
    else:  # a topic two systems share counts once in the totals
        ids = {t["id"] for s in args.systems for t in load_topics(s)["topics"]}
        totals = {"topics_total": len(ids), "topics_covered": sum(1 for i in ids if built.get(i, 0) > 0),
                  "built": sum(built.get(i, 0) for i in ids)}
    hint = "  (add --show-topics to list them; this names any picked cases you haven't run yet)"
    for s in systems:
        print(f"{s['system']}: {s['topics_covered']} of {s['topics_total']} topics picked at least once, "
              f"{s['built']} built cases in total")
        if args.show_topics:
            for t in s["topics"]:
                print(f"  {t['count']}x  {t['topic']}")
        elif single:
            print(hint)
    if not single:
        print(f"All {len(systems)} systems: {totals['topics_covered']} of "
              f"{totals['topics_total']} topics picked at least once, "
              f"{totals['built']} built cases in total (a topic two systems share counts once)")
        if not args.show_topics:
            print(hint)
    print(f"Case reports used: {len(progress.get('reports', []))}")
    print(f"ECGs used: {len(progress.get('ecgs', []))}")
    enc = progress.get("encounters", {})
    ranked = sorted(enc.items(), key=lambda kv: -kv[1])
    if enc:
        total = sum(enc.values())
        print("Encounter mix so far: " + ", ".join(
            f"{encounter_label(k)} {v} ({100 * v / total:.0f}%)" for k, v in ranked))
    for s in systems:
        name = s["system"]
        if s["missing"]:
            print(f"\nGuideline PDFs missing from guidelines/{name}/:")
            for m in s["missing"]:
                print(f"  {m['file']:24} {m['guideline']}")
        else:
            print("\nAll guideline PDFs are in place." if single else f"\n{name}: all guideline PDFs are in place.")
        tag = "" if single else f"{name}: "
        if s["unconverted"]:
            print(f"{tag}Not yet converted to text (run Prepare guidelines): " + ", ".join(s["unconverted"]))
        if s["strays"]:
            print(f"{tag}PDFs with names the topic list doesn't use (rename them?): " + ", ".join(s["strays"]))
    index = progress.get("cases", {})
    log = read_log()
    scenarios = load_scenarios()
    mix = step2_mix(args.systems, progress, log, scenarios["step2_systems"], args.show_topics, scenarios["tiers"])
    counted = sum(r["count"] for r in mix)
    if not single and counted:
        print(f"\nStep 2 system mix so far ({'all built cases' if args.show_topics else 'finished cases only'}): "
              + ", ".join(f"{r['label']} {r['count']} ({100 * r['count'] / counted:.0f}%, target {100 * r['target']:.0f}%)"
                          for r in mix))
    warnings = topic_warnings(scenarios["step2_systems"], scenarios["tiers"])
    if warnings:
        print("\nCheck the topic lists:")
        for w in warnings:
            print(f"  {w}")
    return {
        "step2_mix": mix,
        "step2_mix_scope": "all" if args.show_topics else "finished",
        "step2_weighted": not single,
        "warnings": warnings,
        "systems": systems,
        **totals,
        "reports_used": len(progress.get("reports", [])),
        "ecgs_used": len(progress.get("ecgs", [])),
        "encounters": [{"key": k, "label": encounter_label(k), "count": v} for k, v in ranked],
        "cases_finished": len(log),
        "cases_waiting": sum(1 for c in index if c not in log),
    }


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, help="random seed, for repeatable picks")
    sub = ap.add_subparsers(dest="cmd", required=True)
    several = "; several separated by commas (cardio,gi,pulm) pool their topics"
    as_json = "print one JSON object instead of text (used by the Cases page in LearnHarness)"

    c = sub.add_parser("common", help="seed a typical case of a core topic")
    c.add_argument("--system", required=True, help="topic list in topics/, e.g. cardio" + several + ", or all")
    c.add_argument("--batch", type=int, default=1)
    c.add_argument("--mode", choices=["system", "complaint"], default="system",
                   help="complaint: draw a presenting complaint, then a topic that can present that way")
    c.add_argument("--complaint", help='with --mode complaint: the presentation to use, e.g. "chest pain" '
                                       "(default: a random one that has topics)")
    c.add_argument("--clip", action="store_true", help="copy the opening message to the clipboard")
    c.add_argument("--json", action="store_true", help=as_json)

    pz = sub.add_parser("presentations", help="the presenting complaints complaint mode can use")
    pz.add_argument("--system", default="all", help="one system, several separated by commas, or all (default)")
    pz.add_argument("--json", action="store_true", help=as_json)

    r = sub.add_parser("report", help="fetch a real case report from Europe PMC")
    r.add_argument("--system", help="use this system's complaint list, e.g. cardio; several separated by commas "
                                    "draw a system per case")
    r.add_argument("--complaint", nargs="+", default=[], help="keywords searched in the abstract")
    r.add_argument("--topic", nargs="+", default=[], help="keywords in the title (tells you the diagnosis)")
    r.add_argument("--ed", action="store_true", help="only reports mentioning the emergency department")
    r.add_argument("--journal", help='e.g. "Cureus"')
    r.add_argument("--population", choices=sorted(POPULATION), help="uses MeSH; drops journals without MeSH")
    r.add_argument("--years", default="2015-2025")
    r.add_argument("--min-words", type=int, default=200)
    r.add_argument("--batch", type=int, default=1)
    r.add_argument("--clip", action="store_true", help="copy the opening message to the clipboard")
    r.add_argument("--json", action="store_true", help=as_json)

    pr = sub.add_parser("prepare", help="convert guideline PDFs to searchable text (once)")
    pr.add_argument("--system", required=True, help="e.g. cardio; several separated by commas, or all")
    pr.add_argument("--force", action="store_true", help="reconvert even if already done")
    pr.add_argument("--json", action="store_true", help=as_json)

    rv = sub.add_parser("review", help="weak topics and weak spots from finished cases")
    rv.add_argument("--system", help="only these systems' cases (one, or several separated by commas); default all")
    rv.add_argument("--last", type=int, default=40, help="how many recent cases to list weak spots for")
    rv.add_argument("--json", action="store_true", help=as_json)

    s = sub.add_parser("status", help="coverage and missing guideline PDFs")
    s.add_argument("--system", default="all", help="one system, several separated by commas, or all (default)")
    s.add_argument("--show-topics", action="store_true", help="list covered topics (can spoil unrun cases)")
    s.add_argument("--json", action="store_true", help=as_json)

    args = ap.parse_args()
    rng = random.Random(args.seed)
    handler = {"common": cmd_common, "report": cmd_report, "status": cmd_status, "prepare": cmd_prepare,
               "review": cmd_review, "presentations": cmd_presentations}[args.cmd]

    if not args.json:
        args.systems = parse_systems(args.system, args.cmd != "prepare")
        handler(args, rng)
        return

    # --json: stdout carries exactly one JSON object. Whatever the command prints is returned in
    # "text"; a failure is {"ok": false, "error": ...} with exit code 1.
    import contextlib
    import io
    buf = io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf):
            args.systems = parse_systems(args.system, args.cmd != "prepare")
            out = {"ok": True, **(handler(args, rng) or {})}
    except SystemExit as e:
        if e.code in (None, 0):
            out = {"ok": True}
        else:
            out, code = {"ok": False, "error": str(e.code)}, 1
    except Exception as e:
        out, code = {"ok": False, "error": f"{type(e).__name__}: {e}"}, 1
    out["notes"] = NOTES
    out["text"] = buf.getvalue()
    print(json.dumps(out))
    sys.exit(code)


if __name__ == "__main__":
    main()
