# LearnHarness cases

A rounds-style case picker for [LearnHarness](https://github.com/amosblomqvist/learnharness) Practice sessions, built for USMLE Step 2 study.

A Python script (`pick_case.py`) writes a case file that only the practice agent reads. You start a Practice session, paste the opening message, and work the case without knowing the diagnosis. A small LearnHarness plugin ("Rounds tools") shows ECGs inline and logs how each case went, so weak topics come back for review.

Nothing here prints a case's topic, diagnosis or guideline. File names are neutral on purpose.

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

5. **Plugin.** Close LearnHarness, run `Install plugin.bat`, then start LearnHarness and enable "Rounds tools" under Settings → Community plugins. The launcher copies `plugin/case-images/dist` into `%APPDATA%\LearnHarness\data\plugins\case-images\dist`. Run it again after every plugin update.

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

For everything else, including coverage so far:

```
python pick_case.py -h
python pick_case.py status --system cardio
```

## Sources and license

- ECGs come from [PTB-XL](https://physionet.org/content/ptb-xl/1.0.3/) (PhysioNet, CC BY 4.0), downloaded on demand.
- Case reports come from open-access articles on [Europe PMC](https://europepmc.org/); each case file records the article's own license.
- Guideline PDFs belong to their publishers and are not part of this repository.

This repository is licensed under AGPL-3.0 (see `LICENSE`). `10-doctrine.md` is derived from LearnHarness's AGPL-3.0 practice prompt.
