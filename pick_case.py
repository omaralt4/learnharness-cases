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

  review   Weak topics and weak spots from finished cases (logged by the Rounds
           tools plugin). Also writes review.md.
             python pick_case.py review

  status   What you have covered so far, and which guideline PDFs are missing.
             python pick_case.py status --system cardio

Nothing about a case's content is printed, only file names.

Each case rolls an encounter type (ED, ward, handover, clinic...) and a set of
extras (full history and exam, exam sign, ethics, exam-style questions, ECG)
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
    "exam_style_questions": "Exam-style questions",
}
DEFAULT_SCENARIOS = {
    "encounters": {"ed_first_presentation": 35, "ward_called_by_nurse": 15, "ward_round_day_2": 15,
                   "handover": 10, "clinic_follow_up": 15, "clinic_new_referral": 10},
    "extras": {"full_history_and_exam": 0.25, "exam_sign_deep_dive": 0.30, "ethics_or_communication": 0.10,
               "exam_style_questions": 0.50, "ecg_when_topic_has_one": 0.80, "handover_contains_an_error": 0.50},
    "review": {"weak_below": 0.7, "after_days": 2, "order": "unseen_first"},
}


# ---------- shared ----------

def load_topics(system: str) -> dict:
    path = BASE / "topics" / f"{system}.json"
    if not path.exists():
        sys.exit(f"No topic list at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_progress() -> dict:
    if PROGRESS.exists():
        return json.loads(PROGRESS.read_text(encoding="utf-8"))
    return {"built": {}, "reports": []}


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


def finish(paths: list, clip: bool) -> None:
    if not clip or not paths:
        return
    msg = opening_message(paths)
    if copy_to_clipboard(msg):
        print("\nCopied the opening message. Start a Practice session in LearnHarness and paste it.")
    else:
        print("\nCouldn't reach the clipboard. Paste this into a Practice session:\n\n" + msg)


def guideline_path(system: str, topic: dict) -> Path:
    return BASE / "guidelines" / system / topic["guideline_file"]


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


def guideline_reference(gpath: Path, case_path: Path) -> tuple:
    """(seed text, state) where state is 'text', 'pdf' or 'missing'."""
    md = gpath.with_suffix(".md")
    if md.exists():
        ref = neutral_link(md, case_path.with_name(case_path.stem + "_ref.md"))
        return (
            f"Reference guideline text: {ref}\n"
            "The top of the file is a contents list giving each section's line number. Read the contents "
            "first, then read only the sections this case needs (read with offset and limit), and grep this "
            "file for specific thresholds or drugs as they come up, always giving this file as the path. "
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


def convert_guideline(pdf: Path, md_path: Path) -> dict:
    import pymupdf4llm
    chunks = pymupdf4llm.to_markdown(str(pdf), page_chunks=True, use_ocr=False)
    pages = [(c["metadata"].get("page_number") or i + 1, c["text"]) for i, c in enumerate(chunks)]

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
            m = re.match(r"^(#{1,3})\s+(.*\S)", line)
            if m:
                headings.append((len(body), num, len(m.group(1)), m.group(2).strip("* ")))
            body.append(line)
        body.append("")

    head = [
        f"# {pdf.stem} (text version of {pdf.name})",
        "",
        "Contents: line number, page, section. Read a section with read(offset=line, limit=...).",
        "",
    ]
    contents_len = len(head) + len(headings) + 2
    for idx, num, level, title in headings:
        head.append(f"L{contents_len + idx + 1}  p{num}  {'  ' * (level - 1)}{title}")
    head += ["", "=" * 40]
    assert len(head) == contents_len, "contents length mismatch"
    md_path.write_text("\n".join(head + body) + "\n", encoding="utf-8")
    words = sum(len(t.split()) for _, t in pages)
    return {"pages": len(pages), "headings": len(headings), "weak": weak, "words": words}


def cmd_prepare(args, rng):
    try:
        import pymupdf4llm  # noqa: F401
    except ImportError:
        sys.exit("Needs PyMuPDF. Run: python -m pip install pymupdf pymupdf4llm")
    folder = BASE / "guidelines" / args.system
    pdfs = sorted(folder.glob("*.pdf")) if folder.exists() else []
    if not pdfs:
        sys.exit(f"No PDFs in {folder}")
    done = 0
    for pdf in pdfs:
        md = pdf.with_suffix(".md")
        if md.exists() and md.stat().st_mtime >= pdf.stat().st_mtime and not args.force:
            print(f"  {pdf.name}: already converted")
            continue
        try:
            r = convert_guideline(pdf, md)
        except Exception as e:
            print(f"  {pdf.name}: FAILED ({type(e).__name__}: {e}). Cases will use the PDF instead.")
            continue
        done += 1
        msg = f"  {pdf.name}: {r['pages']} pages, {r['words']:,} words, {r['headings']} sections indexed"
        if r["headings"] < 5:
            msg += "  <- few headings found, the contents list will be thin"
        if r["weak"]:
            shown = ", ".join(map(str, r["weak"][:12])) + (" ..." if len(r["weak"]) > 12 else "")
            msg += f"\n      little or no text on pages {shown} (usually figures or algorithm charts; normal in small numbers)"
        print(msg)
    print(f"\nConverted {done} file(s). Spot-check one: open a .md in Notepad and skim a page or two.")


# ---------- scenario settings ----------

def load_scenarios() -> dict:
    if not SCENARIOS.exists():
        SCENARIOS.write_text(json.dumps(DEFAULT_SCENARIOS, indent=2), encoding="utf-8")
        print(f"Created {SCENARIOS.name} with default percentages; edit it to change the mix.")
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
    return {"encounters": enc, "extras": extras, "review": review}


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
        print("Note: ECGs skipped. Run 'python -m pip install numpy matplotlib' to enable them.")
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
        print(f"Note: ECG skipped for one case ({type(e).__name__}: {e}).")
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


def pick_topics(topics: list, built: dict, n: int, rng: random.Random, hist: dict = None, review: dict = None) -> list:
    """Never-seen topics and weak topics that are due again (weakest first), in the order the
    'review' settings choose; then the least-covered. Random among ties."""
    hist, review = hist or {}, review or DEFAULT_SCENARIOS["review"]
    now = datetime.now()
    pool = topics[:]
    rng.shuffle(pool)

    def key(t):
        h = hist.get(t["id"], {})
        score, last = h.get("last_score"), h.get("last_built")
        due = last is None or (now - last).total_seconds() >= review["after_days"] * 86400
        unseen_rank, weak_rank = (0, 1) if review.get("order", "unseen_first") == "unseen_first" else (1, 0)
        if built.get(t["id"], 0) == 0:
            return (unseen_rank, 0.0, 0)
        if score is not None and score < review["weak_below"] and due:
            return (weak_rank, score, 0)
        return (2, 0.0, built.get(t["id"], 0))

    pool.sort(key=key)
    return pool[:n]


def cmd_common(args, rng):
    data = load_topics(args.system)
    scenarios = load_scenarios()
    progress = load_progress()
    built = progress.setdefault("built", {})
    enc_counts = progress.setdefault("encounters", {})
    hist = topic_history(progress, read_log())
    chosen = pick_topics(data["topics"], built, args.batch, rng, hist, scenarios["review"])
    missing = unconverted = 0
    made = []
    for topic in chosen:
        gpath = guideline_path(args.system, topic)
        sc = roll_scenario(scenarios, rng)
        dest = new_case_path()
        ref, ref_state = guideline_reference(gpath, dest)
        missing += ref_state == "missing"
        unconverted += ref_state == "pdf"

        ecg_block, ecg_frame = (None, None)
        if sc["want_ecg"] and topic.get("ecg_codes"):
            ecg_block, ecg_frame = attach_ecg(topic, dest, rng, progress)
        frame = ecg_frame or f"{rng.choice(AGE_BANDS)}, {rng.choice(['male', 'female'])}"

        enc_line = encounter_label(sc["encounter"])
        if sc["encounter"] == "handover":
            enc_line += " (contains one planted error)" if sc["handover_error"] else " (accurate, no planted error)"
        extras = "\n".join(f"- {label}: {'ON' if sc['extras'][k] else 'off'}" for k, label in EXTRA_LABELS.items())

        dest.write_text(
            "# Case seed (for the agent only)\n\n"
            "This is a built case. Follow the 'Built cases' rules in rounds mode.\n\n"
            f"Topic: {topic['topic']}\n"
            f"Patient frame: {frame}\n"
            f"Encounter: {enc_line}\n"
            f"Extras:\n{extras}\n\n"
            f"Current guideline: {topic['guideline']}\n"
            f"{ref}\n\n"
            + (ecg_block + "\n" if ecg_block else "")
            + "Build a common, typical presentation of this topic as a Step 2 question or a real "
            "patient would show it. Grade all management against the current guideline.\n",
            encoding="utf-8",
        )
        built[topic["id"]] = built.get(topic["id"], 0) + 1
        progress.setdefault("cases", {})[dest.stem] = {
            "system": args.system, "topic": topic["id"], "encounter": sc["encounter"],
            "made": datetime.now().isoformat(timespec="seconds"),
        }
        enc_counts[sc["encounter"]] = enc_counts.get(sc["encounter"], 0) + 1
        save_progress(progress)
        print(f"Saved {dest.relative_to(BASE)}" + ("  (+ ECG)" if ecg_block else ""))
        made.append(dest)
        time.sleep(1.1)  # keeps timestamps in file names distinct and in order
    if missing:
        print(f"Note: {missing} of these cases have no guideline PDF saved yet. "
              f"Run 'status --system {args.system}' to see which files are missing.")
    if unconverted:
        print(f"Note: {unconverted} of these cases point at a PDF that hasn't been converted to text. "
              "Run 'Prepare guidelines' first to make them cheaper.")
    finish(made, args.clip)


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
    preset = load_topics(args.system)["complaints"] if args.system else []
    y0, y1 = (int(x) for x in args.years.split("-"))
    saved = 0
    made = []
    for _ in range(args.batch):
        # With a system preset and no --complaint, each case gets a fresh random complaint.
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
                    "system": args.system or "", "report": pmcid, "made": datetime.now().isoformat(timespec="seconds"),
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
            print("One case could not be found with these filters; skipped.")
    if not saved:
        sys.exit("No usable case found. Loosen the filters or widen --years.")
    finish(made, args.clip)


# ---------- status ----------

def cmd_review(args, rng):
    progress = load_progress()
    log = read_log()
    index = progress.get("cases", {})
    names = {}
    for sysname in {m.get("system") for m in index.values() if m.get("system")}:
        try:
            names.update({t["id"]: t["topic"] for t in load_topics(sysname)["topics"]})
        except SystemExit:
            pass
    rows = []
    for case_id, e in log.items():
        meta = index.get(case_id, {})
        if args.system and meta.get("system") and meta["system"] != args.system:
            continue
        label = names.get(meta.get("topic"), "Case report" if meta.get("report") else meta.get("topic", "Unknown"))
        rows.append((e.get("logged", ""), label, e))
    if not rows:
        print("No finished cases logged yet. Cases are logged at the end of each practice session.")
        return
    rows.sort(key=lambda r: r[0], reverse=True)

    by_topic = {}
    for _, label, e in rows:
        by_topic.setdefault(label, []).append(e.get("score", 0))
    lines = ["# Case review", "", f"{len(rows)} finished cases logged.", "", "## By topic (weakest first)", ""]
    for label, scores in sorted(by_topic.items(), key=lambda kv: sum(kv[1]) / len(kv[1])):
        lines.append(f"- {label}: {len(scores)} case(s), last {scores[0]:.0%}, average {sum(scores) / len(scores):.0%}")
    lines += ["", "## Weak spots, most recent first", ""]
    for when, label, e in rows[: args.last]:
        spots = e.get("weak_spots") or []
        if not spots:
            continue
        lines.append(f"### {when[:10]} · {label} · {e.get('diagnosis', '')} · {e.get('score', 0):.0%}")
        lines += [f"- {w}" for w in spots]
        lines.append("")
    out = BASE / "review.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[: 6 + len(by_topic)]))
    print(f"\nFull list of weak spots written to {out.name} (open it in Notepad).")


def cmd_status(args, rng):
    data = load_topics(args.system)
    progress = load_progress()
    built = progress.get("built", {})
    topics = data["topics"]
    done = [t for t in topics if built.get(t["id"], 0) > 0]
    print(f"{args.system}: {len(done)} of {len(topics)} topics picked at least once, "
          f"{sum(built.values())} built cases in total")
    if args.show_topics:
        # Counts a case as covered when it is picked, so this also names cases you haven't run yet.
        for t in sorted(done, key=lambda t: -built[t["id"]]):
            print(f"  {built[t['id']]}x  {t['topic']}")
    else:
        print("  (add --show-topics to list them; this names any picked cases you haven't run yet)")
    print(f"Case reports used: {len(progress.get('reports', []))}")
    print(f"ECGs used: {len(progress.get('ecgs', []))}")
    enc = progress.get("encounters", {})
    if enc:
        total = sum(enc.values())
        print("Encounter mix so far: " + ", ".join(
            f"{encounter_label(k)} {v} ({100 * v / total:.0f}%)" for k, v in sorted(enc.items(), key=lambda kv: -kv[1])))
    missing = {}
    for t in topics:
        if not guideline_path(args.system, t).exists():
            missing.setdefault(t["guideline_file"], t["guideline"])
    if missing:
        print(f"\nGuideline PDFs missing from guidelines/{args.system}/:")
        for fname, name in missing.items():
            print(f"  {fname:24} {name}")
    else:
        print("\nAll guideline PDFs are in place.")
    unconverted = sorted({t["guideline_file"] for t in topics
                          if guideline_path(args.system, t).exists()
                          and not guideline_path(args.system, t).with_suffix(".md").exists()})
    if unconverted:
        print("Not yet converted to text (run Prepare guidelines): " + ", ".join(unconverted))
    folder = BASE / "guidelines" / args.system
    expected = {t["guideline_file"].lower() for t in topics}
    strays = sorted(p.name for p in folder.glob("*.pdf") if p.name.lower() not in expected) if folder.exists() else []
    if strays:
        print("PDFs with names the topic list doesn't use (rename them?): " + ", ".join(strays))


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, help="random seed, for repeatable picks")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("common", help="seed a typical case of a core topic")
    c.add_argument("--system", required=True, help="topic list in topics/, e.g. cardio")
    c.add_argument("--batch", type=int, default=1)
    c.add_argument("--clip", action="store_true", help="copy the opening message to the clipboard")

    r = sub.add_parser("report", help="fetch a real case report from Europe PMC")
    r.add_argument("--system", help="use this system's complaint list, e.g. cardio")
    r.add_argument("--complaint", nargs="+", default=[], help="keywords searched in the abstract")
    r.add_argument("--topic", nargs="+", default=[], help="keywords in the title (tells you the diagnosis)")
    r.add_argument("--ed", action="store_true", help="only reports mentioning the emergency department")
    r.add_argument("--journal", help='e.g. "Cureus"')
    r.add_argument("--population", choices=sorted(POPULATION), help="uses MeSH; drops journals without MeSH")
    r.add_argument("--years", default="2015-2025")
    r.add_argument("--min-words", type=int, default=200)
    r.add_argument("--batch", type=int, default=1)
    r.add_argument("--clip", action="store_true", help="copy the opening message to the clipboard")

    pr = sub.add_parser("prepare", help="convert guideline PDFs to searchable text (once)")
    pr.add_argument("--system", required=True)
    pr.add_argument("--force", action="store_true", help="reconvert even if already done")

    rv = sub.add_parser("review", help="weak topics and weak spots from finished cases")
    rv.add_argument("--system", help="only this system's cases")
    rv.add_argument("--last", type=int, default=40, help="how many recent cases to list weak spots for")

    s = sub.add_parser("status", help="coverage and missing guideline PDFs")
    s.add_argument("--system", required=True)
    s.add_argument("--show-topics", action="store_true", help="list covered topics (can spoil unrun cases)")

    args = ap.parse_args()
    rng = random.Random(args.seed)
    {"common": cmd_common, "report": cmd_report, "status": cmd_status, "prepare": cmd_prepare, "review": cmd_review}[args.cmd](args, rng)


if __name__ == "__main__":
    main()
