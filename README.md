# LearnHarness cases

A rounds-style case picker for [LearnHarness](https://github.com/amosblomqvist/learnharness) Practice sessions, built for USMLE Step 2 study.

A Python script (`pick_case.py`) writes a case file that only the practice agent reads. You start a Practice session, paste the opening message, and work the case without knowing the diagnosis. A LearnHarness plugin ("Rounds tools") shows ECGs inline (with a full-screen view you can zoom and pan), lets the agent search a case's reference without showing you what it searched for, logs how each case went so weak topics come back for review, and adds a **Cases** page to the app that does everything the launchers do.

Nothing here shows a case's topic, diagnosis or guideline before you finish it. File names are neutral on purpose.

## The Cases page

After installing the plugin (see Setting up from scratch), open **Cases** from the sidebar in LearnHarness.

- **Systems**: tick one or several. Every file in `topics/` gets a checkbox. Several systems pool their topics, and the case never says which system it came from. With several ticked, cases are spread across the USMLE Step 2 systems (see Mixed practice).
- **New case**: makes a case and copies the opening message. Start a Practice session and paste. **Pick by** chooses how: by system (the default), or by presenting complaint. For a complaint, start typing and pick one from the list (only complaints that have topics in the ticked systems are offered), or press **Random complaint**. You aren't told the topic or its system.
- **Case report**: the same, from a real open-access case report. Optional complaint, journal, and emergency department only.
- **Progress**: coverage, encounter mix, Step 2 system mix, problems in the topic lists, and missing or unconverted guideline files. Per-system counts and topic names stay hidden unless you tick the switch, because they can give away a case you haven't run. For the same reason the Step 2 mix counts finished cases only until you tick it.
- **Review**: weakest topics and weak spots from finished cases.
- **Mix**: edits `scenarios.json` (encounter weights, extras, review settings, topic tier weights, Step 2 system weights).
- **Guidelines**: converts guideline PDFs to text. A book is split into one file per chapter.

The plugin's settings page (the gear on the Cases page) has the **Cases folder** and the **Python path**. Leave both empty to use `Documents\LearnHarness-cases` and the Python the launchers would find.

## During a case

- **ECGs and other images** appear inline. Click one to switch between fit-to-width and full size. The **Fullscreen** button, or a double-click, opens it on a black full-screen view: scroll to zoom in where the cursor is, drag to move, double-click to reset, Esc or Close to leave.
- **"Searched case reference · N matches"** means the agent looked something up in the case's guideline. You see only the count; the search words and the matching text stay hidden so they can't give the case away. Don't expand tool lines (the small arrow next to `READ` and similar) during a case: the app shows a tool's full input and output there, and no plugin can turn that off.

## Folder layout

```
pick_case.py            the case picker
scenarios.json          encounter weights, extras chances, review settings, tier and Step 2 system weights (edit freely)
topics/<system>.json    topic list for a system: topics, their references, ECG codes
doctrine/10-doctrine.md practice-agent instructions for rounds mode (paste into LearnHarness Settings)
skills/rounds-topic-file/SKILL.md   Claude skill that writes a topic list for a new system
plugin/case-images/     the "Rounds tools" plugin (source of truth; install from here)
*.bat                   Windows launchers

Not in git (see .gitignore):
guidelines/<system>/    guideline PDFs you save yourself, their converted .md text, and chapters.txt for split books
cases/                  generated case files, ECG images, per-case guideline links
data/ptbxl/             cached ECG recordings
progress.json           coverage tracker
case_log.jsonl          one line per finished case, written by the plugin
review.md               written by the review command
python_path.txt         optional: full path to python.exe for the launchers
```

## Setting up from scratch

This is for someone starting with nothing but this repository. Windows only.

### 1. What you need

- **LearnHarness 0.6.1 or newer** ([github.com/amosblomqvist/learnharness](https://github.com/amosblomqvist/learnharness)). The plugin needs at least 0.6.1.
- **Python 3.9 or newer.**
- **Packages** for ECGs and guideline conversion (the picker itself runs on the standard library):

  ```
  python -m pip install numpy matplotlib pymupdf pymupdf4llm
  ```

- **This repository** in `Documents\LearnHarness-cases`. That is the folder the plugin looks in by default; anywhere else works if you set the Cases folder in the plugin's settings.

  ```
  git clone <this repository's URL> "%USERPROFILE%\Documents\LearnHarness-cases"
  ```

If the launchers can't find Python, put the full path to `python.exe` in a file named `python_path.txt` in this folder. Get the path with:

```
python -c "import sys; print(sys.executable)"
```

### 2. Get the guideline files

The repository has no guideline or book files: they belong to their publishers, and `.gitignore` keeps them out. Download each one yourself and save it under **exactly** the file name below. The topic lists refer to these names. Search for the title; most of the guidelines are free on the publisher's or society's site.

**Cardiology** (`guidelines/cardio/`). Emergency medicine topics reuse most of these, so get them even if you only want EM.

| Save as | Guideline | Used by |
|---|---|---|
| `guidelines/cardio/acls.pdf` | Current AHA Guidelines for CPR and Emergency Cardiovascular Care (ACLS) | cardio, em |
| `guidelines/cardio/acs-2025.pdf` | 2025 ACC/AHA/ACEP/NAEMSP/SCAI Guideline for the Management of Patients With Acute Coronary Syndromes | cardio, em |
| `guidelines/cardio/af-2023.pdf` | 2023 ACC/AHA/ACCP/HRS Guideline for the Diagnosis and Management of Atrial Fibrillation | cardio, em |
| `guidelines/cardio/aortic-2022.pdf` | 2022 ACC/AHA Guideline for the Diagnosis and Management of Aortic Disease | cardio, em |
| `guidelines/cardio/brady-2018.pdf` | 2018 ACC/AHA/HRS Guideline on the Evaluation and Management of Patients With Bradycardia and Cardiac Conduction Delay | cardio, em |
| `guidelines/cardio/ccd-2023.pdf` | 2023 AHA/ACC Guideline for the Management of Patients With Chronic Coronary Disease (with the 2021 AHA/ACC Chest Pain Guideline) | cardio |
| `guidelines/cardio/endocarditis-2026.pdf` | 2026 AHA Scientific Statement: Infective Endocarditis: Diagnosis, Antibiotic Therapy, and Management (uses 2023 Duke-ISCVID criteria) | cardio |
| `guidelines/cardio/hcm-2024.pdf` | 2024 AHA/ACC Guideline for the Management of Hypertrophic Cardiomyopathy | cardio |
| `guidelines/cardio/hf-2022.pdf` | 2022 AHA/ACC/HFSA Guideline for the Management of Heart Failure | cardio, em |
| `guidelines/cardio/hfpef-ecdp-2026.pdf` | 2022 AHA/ACC/HFSA Heart Failure Guideline plus the 2026 ACC Expert Consensus Decision Pathway on HFpEF | cardio |
| `guidelines/cardio/htn-2025.pdf` | 2025 AHA/ACC Guideline for the Prevention, Detection, Evaluation, and Management of High Blood Pressure in Adults | cardio, em |
| `guidelines/cardio/lipids-2026.pdf` | 2026 ACC/AHA Guideline on the Management of Dyslipidemia | cardio |
| `guidelines/cardio/myoperi-esc-2025.pdf` | 2025 ESC Guidelines for the management of myocarditis and pericarditis (no current ACC/AHA guideline) | cardio, em |
| `guidelines/cardio/pad-2024.pdf` | 2024 ACC/AHA Guideline for the Management of Lower Extremity Peripheral Artery Disease | cardio, em |
| `guidelines/cardio/svt-2015.pdf` | 2015 ACC/AHA/HRS Guideline for the Management of Adult Patients With Supraventricular Tachycardia | cardio, em |
| `guidelines/cardio/syncope-2017.pdf` | 2017 ACC/AHA/HRS Guideline for the Evaluation and Management of Patients With Syncope | cardio, em |
| `guidelines/cardio/valve-2020.pdf` | 2020 ACC/AHA Guideline for the Management of Patients With Valvular Heart Disease | cardio |

**Emergency medicine** (`guidelines/em/`)

| Save as | Guideline | Used by |
|---|---|---|
| `guidelines/em/anaphylaxis-2023.pdf` | Anaphylaxis: A 2023 Practice Parameter Update (AAAAI/ACAAI JTFPP) | em |
| `guidelines/em/apap-2023.pdf` | Management of Acetaminophen Poisoning in the US and Canada: A Consensus Statement (JAMA Netw Open 2023) | em |
| `guidelines/em/dka-2024.pdf` | Hyperglycemic Crises in Adults With Diabetes: A Consensus Report (ADA/EASD/JBDS/AACE/DTS, Diabetes Care 2024;47:1257-1275) | em |
| `guidelines/em/mtbi-2023.pdf` | 2023 ACEP Clinical Policy: Adult Patients Presenting to the ED With Mild Traumatic Brain Injury | em |
| `guidelines/em/pe-2026.pdf` | 2026 AHA/ACC/ACCP/ACEP/CHEST/SCAI/SHM/SIR/SVM/SVN Guideline for the Evaluation and Management of Acute Pulmonary Embolism in Adults | em |
| `guidelines/em/sah-2023.pdf` | 2023 AHA/ASA Guideline for the Management of Patients With Aneurysmal Subarachnoid Hemorrhage | em |
| `guidelines/em/sepsis-2026.pdf` | Surviving Sepsis Campaign: International Guidelines for Management of Sepsis and Septic Shock 2026 (Crit Care Med 2026;54:725-812) | em |
| `guidelines/em/sepsis-peds-2026.pdf` | Surviving Sepsis Campaign International Guidelines for Sepsis and Septic Shock in Children 2026 (Pediatr Crit Care Med 2026) | em |
| `guidelines/em/stroke-2026.pdf` | 2026 AHA/ASA Guideline for the Early Management of Patients With Acute Ischemic Stroke | em |

**A main EM reference of your choice.** Most EM topics also point at chapter files of a general emergency medicine reference, called the "EM handbook" in `topics/em.json`. None is included, and none is named here: use a reference of your choice that you are entitled to use. Save it as a PDF with chapter bookmarks:

```
guidelines/em/em-handbook.pdf
```

Prepare (next step) splits a book into one text file per chapter using the PDF's bookmarks, and lists what it wrote in `guidelines/em/chapters.txt`. The EM topic list expects these 13 chapter files:

```
em-handbook-02-life-threatening-emergencies.md
em-handbook-03-medicine.md
em-handbook-04-toxicology.md
em-handbook-05-infectious-diseases.md
em-handbook-06-environmental-emergencies.md
em-handbook-08-major-trauma.md
em-handbook-09-wounds-fractures-and-orthopaedics.md
em-handbook-10-surgery.md
em-handbook-11-ophthalmology.md
em-handbook-12-ear-nose-and-throat.md
em-handbook-13-obstetrics-and-gynaecology.md
em-handbook-14-psychiatry.md
em-handbook-15-paediatric-emergencies.md
```

Your book's chapters will have their own names, so after Prepare, open `chapters.txt` and change each `"file"` in `topics/em.json` to the chapter of your book that covers that topic. Set `"region"` on those references to where your book is from: a non-US region tells the agent to use it for presentation and approach and to grade management against US practice. `python pick_case.py status --system em` shows which files a topic can't find. Never commit the book or its chapter files.

Without a main reference, EM topics that have a US guideline still work from that guideline; the rest fall back to "work from current US practice".

To see what is still missing at any point:

```
python pick_case.py status
```

### 3. Run Prepare

Prepare converts the PDFs to searchable text, so the agent reads only the sections a case needs and nothing is shown to you mid-case. Run it once, and again whenever you add a PDF.

```
python pick_case.py prepare --system all
```

`Prepare cardio guidelines.bat` does the same for cardiology alone, and the **Guidelines** tab on the Cases page does it from inside LearnHarness. It takes several minutes for a book.

### 4. Install the plugin

1. Close LearnHarness.
2. Run `Install plugin.bat`. It copies `plugin/case-images/dist` into `%APPDATA%\LearnHarness\data\plugins\case-images\dist` and leaves the plugin's own `data` folder alone.
3. Start LearnHarness and enable **Rounds tools** under Settings → Community plugins.

Run the launcher again after every update to this repository. The plugin is plain JavaScript with no build step; it runs `pick_case.py` with your Python and has the same access to your files as any LearnHarness plugin.

### 5. Paste the doctrine

In LearnHarness Settings, paste the whole contents of `doctrine/10-doctrine.md` as the prompt override for the practice agent. Paste it again whenever that file changes.

### 6. Start a case

1. Open **Cases** from the sidebar in LearnHarness.
2. Tick one or more systems, open **New case** and press **Make case**. The opening message is copied for you. It contains only a file path.
3. Start a Practice session and paste.

The launchers (`New cardio case.bat`, `New EM case.bat`) do steps 1 and 2 without opening the page.

### Adding topics with Claude

`skills/rounds-topic-file/SKILL.md` is a Claude skill that builds or extends a `topics/<system>.json` in the shape this picker expects, with verified US guideline references and a download table. Add it to Claude as a skill and ask for a topic file for a new system.

## Launchers

| Launcher | What it does |
|---|---|
| `New cardio case.bat` | Makes one case on a core topic and copies the opening message |
| `New EM case.bat` | The same for emergency medicine (needs `topics/em.json`) |
| `Cardio case report.bat` | Fetches a real open-access case report from Europe PMC |
| `Cardio review.bat` | Lists weak topics and weak spots from finished cases, writes `review.md` |
| `Prepare cardio guidelines.bat` | Converts guideline PDFs to text |
| `Install plugin.bat` | Copies the plugin from this folder into LearnHarness |

After making a case, start a Practice session and paste the opening message.

## Command line

```
python pick_case.py -h
python pick_case.py common --system cardio
python pick_case.py common --system cardio,gi,pulm     several systems, topics pooled
python pick_case.py common --system all --mode complaint                          a random presenting complaint
python pick_case.py common --system all --mode complaint --complaint "chest pain"
python pick_case.py presentations --system cardio,em   the complaints that have topics
python pick_case.py status                             all systems; add --system to narrow
python pick_case.py review --system cardio
```

- `--system` takes one system, several separated by commas, or `all`. A system is a file in `topics/`.
- `--json` on any command prints one JSON object instead of text. The Cases page uses it.
- `--seed N` (before the command) makes the random picks repeatable.

An older `progress.json` is converted on first use, and the original is kept next to it as a `.bak` file.

## Adding a system

1. Put the PDFs in `guidelines/<name>/`.
2. Run `python pick_case.py prepare --system <name>` (this works before the topic list exists).
3. Write `topics/<name>.json` in the shape of `topics/cardio.json`.
4. Run `python pick_case.py status`. It lists missing or unconverted files and warns about topics that appear twice.

**Books.** A PDF over 150 pages with top-level bookmarks is written as one text file per chapter, and `guidelines/<name>/chapters.txt` lists each file with its pages and title. Point topics at the chapter files. A PDF that a topic names as a whole file is never split.

**Topic fields.** Only `id` and `topic` are required.

| Field | Meaning |
|---|---|
| `id`, `topic` | Short id and the topic's name. The same id in two topic files is the same topic (see Shared topics). |
| `guideline`, `guideline_file` | One reference: its full name and its PDF's file name. |
| `references` | Several references instead of, or as well as, the pair above: a list of `{"file", "name", "region"}`. `file` is a PDF or a chapter file from `chapters.txt`. Add `"folder": "cardio"` when the file lives in `guidelines/cardio/` instead of this system's own folder. |
| `region` (in a reference) | `"UK"` or another non-US region tells the agent to use that reference for presentation and approach, grade management against US practice, and name the differences at the end. |
| `complaint` | The presenting complaint the case opens with. |
| `presentations` | The ways the topic can present, for complaint mode, including its classic atypical routes. Only these names: chest pain, dyspnea, palpitations, syncope/collapse, hypotension/shock, abdominal pain, GI bleeding, vomiting/diarrhea, headache, altered mental status, seizure, focal weakness, dizziness, fever, back pain, limb pain/swelling, joint pain, rash/skin, red eye/visual loss, sore throat/ENT, vaginal bleeding/pelvic pain, scrotal pain, urinary symptoms, overdose/poisoning, trauma, unwell child, behavioural disturbance. A shared topic should list the same ones in every file. |
| `tier` | `common`, `cant_miss` or `rare`. Weights are in `scenarios.json` (3, 2, 1); no tier means weight 1. |
| `step2_system` | The USMLE Step 2 system the topic belongs to, for mixed practice. A topic file can set a default at its top level. The names are the keys of `step2_systems` in `scenarios.json`. |
| `canonical` | A shared name for the same diagnosis listed in two files under different names. `status` warns about those. |
| `ecg_codes`, `ecg_rate` | PTB-XL codes for an attached ECG (`[]` for none), and an optional rate range. |

```json
{
  "id": "tca-overdose",
  "topic": "Tricyclic antidepressant overdose",
  "tier": "cant_miss",
  "step2_system": "multisystem",
  "complaint": "found drowsy at home",
  "references": [
    {"file": "em-handbook-04-toxicology.md", "name": "EM handbook, chapter 4", "region": "UK"}
  ],
  "ecg_codes": []
}
```

**Shared topics.** Give a topic the same `id` in two topic files (STEMI in `cardio.json` and `em.json`) and it is one topic with one history: a case made from either system counts as done in both, and its score decides when it comes back in either.

- The entries are merged for the case, whether you tick one system or both: all references from both (each file once), all ECG codes, and every other field from the first file that has it. A STEMI made with only cardio ticked still gets the EM handbook chapter and presenting complaint; one made with only EM ticked can still get a cardio ECG.
- The tier comes from the systems you ticked (the heavier one if both), so ticking one system weights its topics the way its own list says.
- `status` warns if the two entries name different Step 2 systems (the first is used), or if one diagnosis is listed under two different ids.

## How a topic is chosen

1. Topics you haven't seen, heavier tier first.
2. Weak topics that are due for review, weakest first. (The Mix tab can put these ahead of unseen topics.)
3. The least-covered topic, counting cases built divided by tier weight, so a weight-3 tier comes up three times as often as weight 1.

Ties are random.

**Mixed practice.** With several systems ticked, each case first draws a Step 2 system using the weights in `scenarios.json` (the midpoints of the USMLE Step 2 CK content ranges), only among the systems your ticked topic lists cover. The topic is then chosen inside that system by the rules above. Topics with no `step2_system` share an "untagged" group. With one system ticked there is no draw.

**Complaint mode.** Each case starts from a presenting complaint: the one you chose, or a random one drawn evenly among the complaints that have topics in the ticked systems. The topic is then chosen among those that can present that way, by the rules above. Step 2 system weights aren't used. The case opens with the complaint only, and at the end the agent asks you for the look-alikes and what told them apart.

**Atypical presentations.** Outside complaint mode, one case in five (`atypical_presentation` in the Mix tab) is built the way the diagnosis gets missed, such as an MI without chest pain, and the agent says at the end why it was atypical and which clue should have caught it.

## Sources and license

- ECGs come from [PTB-XL](https://physionet.org/content/ptb-xl/1.0.3/) (PhysioNet, CC BY 4.0), downloaded on demand.
- Case reports come from open-access articles on [Europe PMC](https://europepmc.org/); each case file records the article's own license.
- Guideline PDFs and reference books belong to their publishers and are not part of this repository. Each user supplies their own copies.

This repository is licensed under AGPL-3.0 (see `LICENSE`). `doctrine/10-doctrine.md` is derived from LearnHarness's AGPL-3.0 practice prompt.
