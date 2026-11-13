# LearnHarness cases

A rounds-style case picker for USMLE Step 2 study in [LearnHarness](https://github.com/amosblomqvist/learnharness) (desktop app, Windows, v0.6.1). The learner works simulated clinical cases in Practice sessions without knowing the diagnosis in advance. `README.md` is the user-facing guide; this file is for whoever changes the code.

**Keep this file current.** When a change affects anything described here (flow, layout, rules, decisions, testing, install), update this file in the same commit.

## How the pieces connect

1. **`pick_case.py`** picks a topic and writes a case file into `cases/`. `common` writes a seed (topic, patient frame, encounter, extras, guideline reference, optional ECG) for the agent to build a patient from. `report` saves a real open-access case report from Europe PMC.
2. The learner pastes an **opening message** into a Practice session. It contains only the case file's absolute path.
3. The **practice agent** reads the case file and runs it under `10-doctrine.md`, section X "Rounds mode". The learner pastes that file into LearnHarness Settings as the practice prompt override. It is derived from LearnHarness's own AGPL-3.0 practice prompt. **Don't edit it unless the user asks.**
4. The **plugin** (`plugin/case-images`, id `case-images`, name "Rounds tools") gives the agent two tools:
   - `show_case_image(path, caption)` shows `cases/case_*.png|jpg` inline to the learner.
   - `log_case_result(case_file, diagnosis, decisions[], weak_spots[], exam_questions)` appends one line to `case_log.jsonl` in the folder that contains `cases/`. The score is correct = 1, partial = 0.5, wrong = 0, averaged over decisions.
5. **Scheduling.** The next `common` run reads `progress.json` and `case_log.jsonl`. `pick_topics()` ranks: never-built topics, then weak topics that are due (last score below `review.weak_below`, built at least `review.after_days` ago, weakest first), then least-built. `review.order` swaps the first two groups. Ties are random.
6. **The Cases page** is a plugin view opened from the sidebar. Its backend runs `pick_case.py <command> --json` as a child process (no shell, args as an array, cwd = cases folder) and the frontend renders the result. Tabs: New case, Case report, Progress, Review, Mix (edits `scenarios.json`), Guidelines (runs `prepare` as a background job). The plugin settings page holds the cases folder and the Python path.

A plugin cannot create a Practice session or type into its composer (`ctx.app.openSession` only navigates to an existing one). That is why the flow is "copy the message, the learner pastes it".

## File layout

```
pick_case.py            case picker; Python 3.9+, standard library, optional numpy/matplotlib (ECGs), pymupdf/pymupdf4llm (prepare)
scenarios.json          encounter weights, extras chances (0-1), review settings; user-edited, keep the _how_to_edit key
topics/<system>.json    topic list: id, topic, guideline, guideline_file, ecg_codes, optional ecg_rate; plus complaints for reports
10-doctrine.md          practice-agent instructions (see above)
plugin/case-images/dist/
  manifest.json         id, version, minAppVersion
  backend.cjs           Node CommonJS: the two tools, then registerCases() for the Cases page handlers
  main.js               browser ES module: the two tool renderers, then the Cases view and settings page
*.bat                   launchers: New cardio case, Cardio case report, Cardio review, Prepare cardio guidelines, Install plugin
README.md, LICENSE      user guide; AGPL-3.0
CLAUDE_CODE_BRIEF.md    the original brief for the Cases page work

Ignored by git:
cases/                  case_<stamp>_<hex>.md, _ecg.png, _ref.md (per-case guideline link)
guidelines/<system>/    guideline PDFs and their converted .md text
data/ptbxl/             cached PTB-XL files
progress.json(.bak)     built counts keyed system/id, case index, used reports and ECGs, encounter counts
case_log.jsonl          one line per finished case (written by the plugin)
review.md               written by `review`
python_path.txt         optional full path to python.exe
plugin/case-images/data/  the app's per-plugin data, if it ever lands here
```

The installed plugin lives at `%APPDATA%\LearnHarness\data\plugins\case-images\dist`. The repo copy is the source.

### `pick_case.py` commands

`common`, `report`, `status`, `review`, `prepare`. Run `python pick_case.py -h` and each subcommand's `-h`.

- `--system` takes one system, several separated by commas, or `all`. Several systems pool their topics.
- `--json` prints exactly one JSON object on stdout; a failure is `{"ok": false, "error": ...}` with exit code 1. Without it, output is plain text.
- `--seed N` goes before the command.
- Extras (rolled per case, written into the case file as ON/off): full history and exam, exam sign deep dive, ethics or communication, recall questions, exam-style questions. **Adding an extra touches four places:** `EXTRA_LABELS` and `DEFAULT_SCENARIOS` in `pick_case.py`, `DEFAULT_SCENARIOS` and `LABELS` in `backend.cjs` (the Mix tab then shows it by itself), `scenarios.json`, and a paragraph in `10-doctrine.md` telling the agent what the extra means (only when the user supplies or approves the text). Adding one changes which cases a given `--seed` produces.
- Progress keys are `system/id`. `load_progress()` re-keys bare ids from older files under `cardio` and saves the original as `progress.json.bak` once.

## Rules that must not break

The whole point is that the learner doesn't know the diagnosis until they work it out.

- **Neutral file names.** Case files, ECG images and per-case guideline copies are named `case_<stamp>_<hex>…`. Never put a topic, system, diagnosis or guideline name in any path. The learner sees tool-call headlines in chat, and a headline is the file path (or the grep pattern when no path is given).
- **Nothing about an unfinished case is shown.** No topic, diagnosis, guideline name or ECG label, in script output or in the GUI. A case is finished when it is in `case_log.jsonl`.
  - `status` hides topic names unless `--show-topics` is passed, because a topic counts as covered when its case is made.
  - With mixed systems, a per-system count going up reveals which system a new case came from. The backend's `status` handler therefore strips per-system counts and topic names unless `showTopics` is true, and the Progress switch is off every time the page opens (never persisted).
  - The case file must not name its system.
  - The GUI never shows case file contents.
- **Finished cases** may be shown with topic and diagnosis (Review).
- **The `.bat` launchers keep working.** Keep every existing flag and the single-system plain-text output unchanged.
- **Both plugin tools keep their names, parameters and behavior.** Add to the plugin; don't change them.
- **Never commit** `cases/`, `guidelines/`, `data/`, `progress.json`, `case_log.jsonl`, `review.md` or `python_path.txt`. Cases are spoilers, guideline files belong to their publishers, the rest is personal or machine-specific. Check `git status` before committing.
- **Ask the user before** changing anything outside the plugin and `pick_case.py`, creating a GitHub repository, or touching their installed app.
- **Frontend:** insert text with `textContent`, never `innerHTML` with data. Use the app's theme variables (`--foreground`, `--background`, `--border`, `--muted-foreground`, `--primary`).
- **Paths:** Windows paths everywhere, and the cases folder path may contain spaces.

## Why things are the way they are

- **Hard-linked per-case guideline copies** (`neutral_link()`): the agent must read the guideline during the case, but a path like `svt-2015.md` in a tool-call headline gives the diagnosis away. Each case gets `case_…_ref.md`, a hard link to the converted guideline, which costs no disk space. It falls back to a copy if the drive can't hard-link.
- **Guidelines are converted to text first** (`prepare`): results of the app's pdf tool are displayed to the learner in full, so the PDF can't be read mid-case. The text version has a contents list with line numbers so the agent reads only the sections a case needs.
- **Big references are split by chapter** (`chapter_plan()`): a PDF over 150 pages with at least two top-level bookmarks becomes one `.md` per bookmark (`<stem>-<nn>-<slug>.md`, each with its own contents list), plus `guidelines/<system>/chapters.txt` listing file, page range and title. Bookmarks under 3 pages get no file. A PDF that a topic names as a whole file (`guideline_file`, or a `.pdf` in `references`) is never split, which is what keeps the two cardio guidelines over 150 pages as single files. A big PDF with no bookmarks that no topic names is reported and not converted. `prepare` accepts a system that has a guidelines folder but no topic list yet, because the chapter names are needed to write the topic list.
- **No symlink or junction for the plugin's `dist`**: LearnHarness's plugin tooling refuses symlinked package roots, removing the plugin in the app could delete through a link into this repo, and the app the user studies with would load half-finished edits. `Install plugin.bat` copies `dist` instead (`robocopy /MIR`, leaving the sibling `data` folder alone).
- **`unseen_first` is the default review order**: every topic gets seen once before due reviews are scheduled. The user can flip it to `review_first` in the Mix tab. This is the user's chosen default; the reasoning beyond the note in `scenarios.json` isn't written down, so ask before changing it.
- **PTB-XL rate matching**: the script measures the ventricular rate of each candidate tracing (`heart_rate()`), honors a topic's optional `ecg_rate` range (AF with rapid response needs a fast tracing), and writes the rate into the seed so the vitals the agent releases match the ECG. The patient frame (age, sex) comes from the ECG's patient for the same reason.
- **The model gets no image tokens from `show_case_image`**: the tool returns a short text result to the model and puts the image in `details` for the frontend renderer only. The agent grades ECG interpretation against the cardiologist-coded PTB-XL statements in the seed, never against its own reading.
- **`--json` rather than scraping text**: the GUI needs structured data, and the text output has to stay stable for the launchers. In JSON mode everything the command prints is captured and returned under `text`, so stdout stays one object.
- **One script run at a time** in the backend (`exclusive()`): every run reads and rewrites `progress.json`.
- **`prepare` runs as a job** that emits a `prepare` notification when done, because it can take many minutes and a single backend call would hang the page.
- **Clipboard**: the frontend copies with `navigator.clipboard`; if the page has lost permission (the case took a while to make), it falls back to the backend's `copy` handler, which pipes UTF-16 to `clip.exe`.
- **Python detection** follows the launchers' order: `python_path.txt`, `py`, `python` on PATH (skipping the Microsoft Store stub in `WindowsApps`), conda folders, `%LOCALAPPDATA%\Programs\Python\Python3*`. A `.lnk` shortcut is rejected with a warning because it can't be run without a shell.
- **AGPL-3.0**: `10-doctrine.md` derives from LearnHarness's AGPL-3.0 practice prompt.

## Testing

There is no test suite. Never test against the real folder; it holds the user's study data.

**Script.** Copy `pick_case.py`, `scenarios.json`, `topics/`, `progress.json`, `data/` and the guideline `.md` files to a temp folder (add a `python_path.txt` with the real `python.exe` there if you run launchers). The script finds its data next to itself, so each copy is self-contained.
- For regressions, make two identical copies, put `git show HEAD:pick_case.py` in one and the new script in the other, run the same commands with the same `--seed`, and diff the output after replacing case names (`case_<stamp>_<hex>`) with a placeholder. Compare the case files and `progress.json` the same way.
- For Review and scheduling, write a synthetic `case_log.jsonl` for case ids in the copy's `progress.json`.
- For mixed systems, add a fake `topics/<name>.json` whose ids collide with cardio's.
- `--clip` overwrites the real clipboard. Test it by importing `pick_case` and replacing `copy_to_clipboard`.
- Run a launcher by its full path with stdin from `NUL` so `pause` returns.
- `common` may download ECG recordings from PhysioNet; `report` calls Europe PMC.

**Plugin backend.** `node --check` both files. Then `require` `backend.cjs` in a small Node script with a stand-in `ctx` (`dataDirectory`, `signal`, `handle`, `registerTools`, `registerInstructions`, `events.emit`), set the cases folder to the temp copy with `setConfig`, and call each handler.

**Plugin frontend.** Serve a page from localhost that imports `main.js`, calls `activate()` with a mock `ctx` (returning real handler output saved as JSON), and mounts the view and the settings page. A page opened from `file://` is not interactive in the browser tools.

**In the app.** The plugin has not been run in a source build of LearnHarness; the user tests in their installed app. Running the app from source (`npm ci`, `npm run dev` with `LH_DATA_DIR` and `LH_AUTH_FILE` pointing at scratch locations) needs the user's permission first. Don't modify the installed app's data to test.

## Installing the plugin

1. Close LearnHarness (code is not hot-reloaded).
2. Run `Install plugin.bat`. It mirrors `plugin/case-images/dist` into `%APPDATA%\LearnHarness\data\plugins\case-images\dist`.
3. Start LearnHarness. A newly discovered plugin starts disabled; enable it under Settings → Community plugins.

Bump `version` in `manifest.json` for every plugin change the user will install. `minAppVersion` must be a version that has every API used.

## Plugin authoring references

- The authoring skill is `skills/learnharness-plugins/SKILL.md` in the LearnHarness repository, and the app offers it under Settings → Community plugins → "Download authoring skill". No copy is kept in this repo.
- Docs, in the LearnHarness repository at the tag matching the installed app (`v0.6.1`): `docs/plugin-authoring.md`, `docs/plugin-api/plugins.md` (frontend and backend context types), `docs/plugin-api/plugin-ui.md`, `docs/plugin-architecture.md`. Template: `examples/plugins/teaching-extension` (no-build CommonJS backend plus ES module frontend, the shape this plugin uses).
- Clone at the matching tag into a temp folder to read them: `git clone --depth 1 --branch v0.6.1 https://github.com/amosblomqvist/learnharness`.

## Commits

Commit after each step that works, with a message that says what changed and why, so any single change can be rolled back. The first commit with the unmodified v1.1.0 plugin is `dede251`.
