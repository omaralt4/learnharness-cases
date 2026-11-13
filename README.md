# LearnHarness cases

A rounds-style case picker for [LearnHarness](https://github.com/amosblomqvist/learnharness) Practice sessions, built for USMLE Step 2 study.

A Python script (`pick_case.py`) writes a case file that only the practice agent reads. You start a Practice session, paste the opening message, and work the case without knowing the diagnosis. A LearnHarness plugin ("Rounds tools") shows ECGs inline, logs how each case went so weak topics come back for review, and adds a **Cases** page to the app that does everything the launchers do.

Nothing here shows a case's topic, diagnosis or guideline before you finish it. File names are neutral on purpose.

## The Cases page

After installing the plugin (see Setup), open **Cases** from the sidebar in LearnHarness.

- **Systems**: tick one or several. Several systems pool their topics, and the case never says which system it came from.
- **New case**: makes a case and copies the opening message. Start a Practice session and paste.
- **Case report**: the same, from a real open-access case report. Optional complaint, journal, and emergency department only.
- **Progress**: coverage, encounter mix, and missing or unconverted guideline files. Per-system counts and topic names stay hidden unless you tick the switch, because they can give away a case you haven't run.
- **Review**: weakest topics and weak spots from finished cases.
- **Mix**: edits `scenarios.json` (encounter weights, extras, review settings).
- **Guidelines**: converts guideline PDFs to text.

The plugin's settings page (the gear on the Cases page) has the **Cases folder** and the **Python path**. Leave both empty to use `Documents\LearnHarness-cases` and the Python the launchers would find.

## Folder layout

```
pick_case.py            the case picker
scenarios.json          encounter weights, extras chances, review settings (edit freely)
topics/cardio.json      topic list for a system: topic, guideline, ECG codes
10-doctrine.md          practice-agent instructions for rounds mode
plugin/case-images/     the "Rounds tools" plugin (source of truth; install from here)
*.bat                   Windows launchers

Not in git (see .gitignore):
guidelines/<system>/    guideline PDFs you save yourself, and their converted .md text
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

4. **Prepare.** Run `Prepare cardio guidelines.bat` once (and again after adding PDFs). It converts the PDFs to searchable text so the agent reads only the sections a case needs.

5. **Plugin.** Close LearnHarness, run `Install plugin.bat`, then start LearnHarness and enable "Rounds tools" under Settings → Community plugins. The launcher copies `plugin/case-images/dist` into `%APPDATA%\LearnHarness\data\plugins\case-images\dist` and leaves the plugin's own `data` folder alone. Run it again after every plugin update. The plugin is plain JavaScript with no build step; it runs `pick_case.py` with your Python and has the same access to your files as any LearnHarness plugin.

6. **Doctrine.** In LearnHarness Settings, paste the contents of `10-doctrine.md` as the prompt override for the practice agent.

## Launchers

| Launcher | What it does |
|---|---|
| `New cardio case.bat` | Makes one case on a core topic and copies the opening message |
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

To add a system, add `topics/<name>.json` in the same shape as `topics/cardio.json` and put its guideline PDFs in `guidelines/<name>/`. Topic ids only need to be unique within a system: `progress.json` keys them as `system/id`. An older `progress.json` is converted on first use, and the original is kept as `progress.json.bak`.

## Sources and license

- ECGs come from [PTB-XL](https://physionet.org/content/ptb-xl/1.0.3/) (PhysioNet, CC BY 4.0), downloaded on demand.
- Case reports come from open-access articles on [Europe PMC](https://europepmc.org/); each case file records the article's own license.
- Guideline PDFs belong to their publishers and are not part of this repository.

This repository is licensed under AGPL-3.0 (see `LICENSE`). `10-doctrine.md` is derived from LearnHarness's AGPL-3.0 practice prompt.
