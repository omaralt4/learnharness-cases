# LearnHarness cases

A rounds-style case picker for [LearnHarness](https://github.com/amosblomqvist/learnharness) Practice sessions, built for USMLE Step 2 study.

A Python script (`pick_case.py`) writes a case file that only the practice agent reads. You start a Practice session, paste the opening message, and work the case without knowing the diagnosis. A LearnHarness plugin ("Rounds tools") shows ECGs inline, logs how each case went so weak topics come back for review, and adds a **Cases** page to the app that does everything the launchers do.

Nothing here shows a case's topic, diagnosis or guideline before you finish it. File names are neutral on purpose.

## The Cases page

After installing the plugin (see Setup), open **Cases** from the sidebar in LearnHarness.

- **Systems**: tick one or several. Every file in `topics/` gets a checkbox. Several systems pool their topics, and the case never says which system it came from. With several ticked, cases are spread across the USMLE Step 2 systems (see Mixed practice).
- **New case**: makes a case and copies the opening message. Start a Practice session and paste.
- **Case report**: the same, from a real open-access case report. Optional complaint, journal, and emergency department only.
- **Progress**: coverage, encounter mix, Step 2 system mix, problems in the topic lists, and missing or unconverted guideline files. Per-system counts and topic names stay hidden unless you tick the switch, because they can give away a case you haven't run. For the same reason the Step 2 mix counts finished cases only until you tick it.
- **Review**: weakest topics and weak spots from finished cases.
- **Mix**: edits `scenarios.json` (encounter weights, extras, review settings, topic tier weights, Step 2 system weights).
- **Guidelines**: converts guideline PDFs to text. A book is split into one file per chapter.

The plugin's settings page (the gear on the Cases page) has the **Cases folder** and the **Python path**. Leave both empty to use `Documents\LearnHarness-cases` and the Python the launchers would find.

## Folder layout

```
pick_case.py            the case picker
scenarios.json          encounter weights, extras chances, review settings, tier and Step 2 system weights (edit freely)
topics/<system>.json    topic list for a system: topics, their references, ECG codes
10-doctrine.md          practice-agent instructions for rounds mode
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

## Setup

1. **Python 3.9 or newer.** If the launchers can't find it, put the full path to `python.exe` in a file named `python_path.txt` in this folder. Get the path with:

   ```
   python -c "import sys; print(sys.executable)"
   ```

2. **Packages.** The script runs on the standard library alone. ECGs and guideline conversion need extras:

   ```
   python -m pip install numpy matplotlib pymupdf pymupdf4llm
   ```

3. **Guideline PDFs.** Save each guideline as `guidelines/<system>/<guideline_file>`, using the file names in `topics/<system>.json`. To see which are missing:

   ```
   python pick_case.py status --system cardio
   ```

4. **Prepare.** Run `Prepare cardio guidelines.bat` once (and again after adding PDFs). It converts the PDFs to searchable text so the agent reads only the sections a case needs. For another system, use the Guidelines tab or `python pick_case.py prepare --system <name>`.

5. **Plugin.** Close LearnHarness, run `Install plugin.bat`, then start LearnHarness and enable "Rounds tools" under Settings → Community plugins. The launcher copies `plugin/case-images/dist` into `%APPDATA%\LearnHarness\data\plugins\case-images\dist` and leaves the plugin's own `data` folder alone. Run it again after every plugin update. The plugin is plain JavaScript with no build step; it runs `pick_case.py` with your Python and has the same access to your files as any LearnHarness plugin.

6. **Doctrine.** In LearnHarness Settings, paste the contents of `10-doctrine.md` as the prompt override for the practice agent.

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
python pick_case.py status                             all systems; add --system to narrow
python pick_case.py review --system cardio
```

- `--system` takes one system, several separated by commas, or `all`. A system is a file in `topics/`.
- `--json` on any command prints one JSON object instead of text. The Cases page uses it.
- `--seed N` (before the command) makes the random picks repeatable.

An older `progress.json` is converted on first use, and the original is kept as `progress.json.bak`.

## Adding a system

1. Put the PDFs in `guidelines/<name>/`.
2. Run `python pick_case.py prepare --system <name>` (this works before the topic list exists).
3. Write `topics/<name>.json` in the shape of `topics/cardio.json`.
4. Run `python pick_case.py status`. It lists missing or unconverted files and warns about topics that appear twice.

**Books.** A PDF over 150 pages with top-level bookmarks is written as one text file per chapter, and `guidelines/<name>/chapters.txt` lists each file with its pages and title. Point topics at the chapter files. A PDF that a topic names as a whole file is never split.

**Topic fields.** Only `id` and `topic` are required.

| Field | Meaning |
|---|---|
| `id`, `topic` | Short id and the topic's name. Ids only need to be unique within a system; `progress.json` keys them as `system/id`. |
| `guideline`, `guideline_file` | One reference: its full name and its PDF's file name. |
| `references` | Several references instead of, or as well as, the pair above: a list of `{"file", "name", "region"}`. `file` is a PDF or a chapter file from `chapters.txt`; `cardio/acs-2025.pdf` borrows a file from another system's folder. |
| `region` (in a reference) | `"UK"` or another non-US region tells the agent to use that reference for presentation and approach, grade management against US practice, and name the differences at the end. |
| `complaint` | The presenting complaint the case opens with. |
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

## How a topic is chosen

1. Topics you haven't seen, heavier tier first.
2. Weak topics that are due for review, weakest first. (The Mix tab can put these ahead of unseen topics.)
3. The least-covered topic, counting cases built divided by tier weight, so a weight-3 tier comes up three times as often as weight 1.

Ties are random.

**Mixed practice.** With several systems ticked, each case first draws a Step 2 system using the weights in `scenarios.json` (the midpoints of the USMLE Step 2 CK content ranges), only among the systems your ticked topic lists cover. The topic is then chosen inside that system by the rules above. Topics with no `step2_system` share an "untagged" group. With one system ticked there is no draw.

## Sources and license

- ECGs come from [PTB-XL](https://physionet.org/content/ptb-xl/1.0.3/) (PhysioNet, CC BY 4.0), downloaded on demand.
- Case reports come from open-access articles on [Europe PMC](https://europepmc.org/); each case file records the article's own license.
- Guideline PDFs belong to their publishers and are not part of this repository.

This repository is licensed under AGPL-3.0 (see `LICENSE`). `10-doctrine.md` is derived from LearnHarness's AGPL-3.0 practice prompt.
