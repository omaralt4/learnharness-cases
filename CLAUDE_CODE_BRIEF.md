# Brief: build a "Cases" GUI inside LearnHarness for my rounds-style case picker

## Who I am and what this is

I'm a medical student using LearnHarness (open-source desktop learning app, https://github.com/amosblomqvist/learnharness, I'm on v0.6.1, Windows) to study for USMLE Step 2 with simulated clinical cases in **Practice** sessions. A Python script makes the cases; a LearnHarness plugin shows ECGs inline and logs results. Right now I run the script through `.bat` launchers. I want all of that inside the app as a GUI.

Before you write code, read this whole brief, look at the files listed below, and show me a short plan. Ask me before changing anything outside the plugin and `pick_case.py`.

## Step 0: version control (before any other change)

1. Install Git if it's missing (`winget install Git.Git`).
2. `git init` the `LearnHarness-cases` folder.
3. Add a `.gitignore` that excludes: `cases/`, `guidelines/`, `data/`, `progress.json`, `case_log.jsonl`, `review.md`, `python_path.txt`, and Python caches. Reasons: cases are generated and full of spoilers, guideline PDFs/text belong to the publishers, `data/` is downloaded ECGs, and the rest is my personal study data or machine-specific. Check `git status` before the first commit so none of those get added.
4. Copy the installed plugin's `dist` folder (from the app's plugins folder, see Settings → Community plugins) into `plugin/case-images/dist/` in the repo. From now on the repo copy is the source.
5. Set up installing from the repo: either a small script that copies `plugin/case-images` into the app's plugins folder, or a directory junction (`mklink /J`, no admin needed) so the app loads the repo copy directly. Tell me which you chose and why.
6. Write a short `README.md`: what this is, folder layout, setup (Python, packages, guideline PDFs, Prepare, plugin install, pasting `10-doctrine.md` into Settings), and the launchers.
7. Add a `LICENSE` file with AGPL-3.0. `10-doctrine.md` is derived from LearnHarness's own AGPL-3.0 practice prompt, so the repo should carry the same license.
8. Make the first commit. After that, commit after each step that works, with clear messages, so I can roll back any single change.
9. Ask me before creating any GitHub repository, and whether it should be private or public.

## What exists (all in `C:\Users\Omar\Documents\LearnHarness-cases\`)

```
pick_case.py            the case picker (Python 3.9+, standard library + optional numpy/matplotlib/pymupdf)
scenarios.json          encounter weights, extras probabilities, review settings (user-edited)
topics\cardio.json      topic list: id, topic, guideline, guideline_file, ecg_codes, optional ecg_rate
guidelines\cardio\      guideline PDFs + converted .md text versions
cases\                  generated case files (case_<stamp>_<hex>.md), ECG PNGs, per-case guideline links (_ref.md)
data\ptbxl\             cached ECG recordings
progress.json           coverage counts, case index (case id -> system, topic, encounter, made)
case_log.jsonl          one line per finished case, written by the plugin
review.md               written by `pick_case.py review`
python_path.txt         optional: full path to python.exe (used by the .bat launchers)
*.bat                   launchers: New cardio case, Cardio case report, Cardio progress, Cardio review, Prepare cardio guidelines
10-doctrine.md          my practice-agent instructions (pasted into Settings as a prompt override). Don't edit unless I ask.
```

The installed plugin is in LearnHarness's plugins folder (Settings → Community plugins shows the path): `case-images\dist\` with `manifest.json` (id `case-images`, name "Rounds tools", v1.1.0), `backend.cjs`, `main.js`. It's a no-build plugin modeled on the repo's `examples/plugins/teaching-extension`. It registers two practice-agent tools with renderers:
- `show_case_image(path, caption)`: shows `cases\case_*.png|jpg` inline
- `log_case_result(case_file, diagnosis, decisions[], weak_spots[], exam_questions)`: appends to `case_log.jsonl` (the folder containing `cases`)

Keep both tools and their behavior exactly as they are.

### `pick_case.py` commands (run `python pick_case.py -h` and each subcommand's `-h`)

| Command | What it does | Prints |
|---|---|---|
| `common --system cardio [--batch N] [--clip]` | picks topic(s), rolls encounter/extras from scenarios.json, attaches a PTB-XL ECG when the topic has codes, writes case file(s) | `Saved cases\case_….md  (+ ECG)` per case, notes; with `--clip` copies an opening message |
| `report --system cardio [--complaint …] [--ed] [--journal …] [--batch N] [--clip]` | fetches an open-access case report from Europe PMC | `Saved …` |
| `status --system cardio [--show-topics]` | coverage, ECGs used, encounter mix, missing/unconverted/misnamed guideline PDFs | text |
| `review [--system cardio] [--last N]` | weak topics (weakest first) + weak spots, writes review.md | text |
| `prepare --system cardio [--force]` | converts guideline PDFs to searchable .md (PyMuPDF) | per-file report |
| global `--seed N` | repeatable randomness | |

The opening message `--clip` copies looks like: `Rounds. Run the case at <absolute path>. I haven't read it, so don't reveal anything from it until I ask for it.`

## What I want

### 1. A "Cases" page in the app (plugin view + sidebar button)
Extend the existing `case-images` plugin (same id, bump the version) so I install one plugin. Add a view opened from a sidebar action. On it:

- **New case**: system checkboxes (one per `topics\*.json` found; today only cardio) and a **Make case** button. After it succeeds: copy the opening message to the clipboard and show "Copied. Start a Practice session and paste." Optional batch size, default 1.
- **Case report**: same flow with the report options (complaint text, ED only, journal).
- **Progress**: the `status` output, presented nicely (coverage per system as counts, encounter mix, missing/unconverted/misnamed guideline files).
- **Review**: weakest topics table and the weak-spots list from `case_log.jsonl` (what `review` shows), most recent first.
- **Settings for the mix**: edit `scenarios.json` with sliders/number inputs: encounter weights, extras probabilities (0–1), review settings (`weak_below`, `after_days`, `order` = `unseen_first` | `review_first`). Validate the same way the script does and write the file back preserving the `_how_to_edit` key. Show the effective percentages for encounters.
- **Prepare guidelines** (lower priority, skip if it gets hairy): button that runs `prepare` for the selected systems and shows its report.
- Plugin settings page: **Cases folder** (default `C:\Users\Omar\Documents\LearnHarness-cases`) and **Python path** (auto-detect like the .bat files do: `python_path.txt`, `py`, `python` that isn't the Microsoft Store stub, `%USERPROFILE%\anaconda3`, `miniconda3`, `%LOCALAPPDATA%\Programs\Python\Python3*\python.exe`; let me override).

Implementation: the plugin backend runs `pick_case.py` as a child process (Node `child_process`, no shell; pass args as an array; cwd = cases folder; timeout; capture stdout/stderr; show stderr on failure). Plugins are trusted local code, so this is allowed (see docs below). Prefer adding a `--json` output flag to the script's `common`, `report`, `status` and `review` commands so the GUI parses structured data instead of scraping text. Keep the plain-text output and every existing flag working, because the `.bat` launchers must keep working.

### 2. Mixed-system practice
`--system` should accept several systems: `--system cardio,gi,pulm,renal`. Pool their topics; "least-covered / unseen-first / weak-review" ordering works across the pool. The case file must not name the system. Topic ids may collide between systems: key progress by `system/id` from now on, and migrate existing bare cardio keys in `progress.json` (`built` counts and the `cases` index) without losing data. `status` and `review` should work per system and for all. The GUI checkboxes drive this.

## Hard constraints: spoilers

The whole point is that I don't know the diagnosis until I work it out.
- Never display a topic, diagnosis, guideline name or ECG label for a case I haven't finished. `status` hides topic names by default for this reason (a case counts as covered when it's made). In the GUI, covered-topic names may only be shown behind an explicit "show topic names (may spoil cases you haven't run)" toggle, off by default.
- Finished cases (those in `case_log.jsonl`) can be shown with their diagnosis and topic in Review.
- File names stay neutral (`case_<stamp>_<hex>…`). Don't add topic or system to any path.
- Don't show the contents of case files anywhere in the GUI.

## Platform facts I already found (verify in the repo docs)

- Plugin docs: `docs/plugin-authoring.md`, `docs/plugin-api/plugins.md`, `docs/plugin-api/plugin-ui.md`, and the skill `skills/learnharness-plugins/SKILL.md`. Template: `examples/plugins/teaching-extension` (no-build CommonJS backend + ES module frontend).
- Plugins can register views, actions (sidebar placement), settings pages, tools and tool renderers. Backend ↔ frontend talk through the plugin's request/notification APIs.
- **Plugins cannot create a native Practice session or type into its composer.** `ctx.app.openSession(id)` only navigates to an existing one. That's why the flow is "copy message → I paste". If you find a supported way to do better, tell me before using it.
- Tool calls are visible to me in the chat with a headline (file path, or the grep pattern when no path is given). That's why case files and guideline copies have neutral names. Nothing in the GUI should undo that.
- Use the app's theme CSS variables (`--foreground`, `--background`, `--border`) and safe text insertion, no innerHTML with data.

## Testing and safety

- Clone the LearnHarness repo at the tag/commit matching v0.6.1 for docs and types. Don't modify my installed app; test in a disposable profile as the plugin docs describe, or tell me exactly what to do and what to look for.
- Test `pick_case.py` changes with `--seed` on a copy of my folder, not the real one, and make sure the old `.bat` launchers and the existing `progress.json` still work afterwards.
- Windows paths everywhere. The cases folder path may contain spaces.
- When done: give me install/update steps, what you tested, what you couldn't test, and anything you changed in `pick_case.py` (list the new flags).
