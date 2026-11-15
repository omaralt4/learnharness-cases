# LearnHarness cases

A rounds-style case picker for USMLE Step 2 study in [LearnHarness](https://github.com/amosblomqvist/learnharness) (desktop app, Windows, v0.6.1). The learner works simulated clinical cases in Practice sessions without knowing the diagnosis in advance. `README.md` is the user-facing guide; this file is for whoever changes the code.

**Keep this file current.** When a change affects anything described here (flow, layout, rules, decisions, testing, install), update this file in the same commit.

## How the pieces connect

1. **`pick_case.py`** picks a topic and writes a case file into `cases/`. `common` writes a seed (topic, patient frame, encounter, extras, guideline reference, optional ECG) for the agent to build a patient from. `report` saves a real open-access case report from Europe PMC.
2. The learner pastes an **opening message** into a Practice session. It contains only the case file's absolute path.
3. The **practice agent** reads the case file and runs it under `doctrine/10-doctrine.md`, section X "Rounds mode". The learner pastes that file into LearnHarness Settings as the practice prompt override. It is derived from LearnHarness's own AGPL-3.0 practice prompt. **Don't edit it unless the user asks.**
4. The **plugin** (`plugin/case-images`, id `case-images`, name "Rounds tools") gives the agent three tools:
   - `show_case_image(path, caption)` shows `cases/case_*.png|jpg` inline to the learner. Its renderer keeps click-to-zoom and adds a Fullscreen button (double-click does the same): a black overlay with wheel zoom around the cursor, drag to pan, double-click to reset, Esc or Close to leave (`openImageViewer()`). The overlay sets `-webkit-app-region: no-drag` and Close sits 48px down, because the app's frameless window drags by the top strip of the page and draws the window buttons over its top right corner; both swallow clicks.
   - `search_case_ref(case_file, query, context, max_matches)` searches that case's own reference files (`<stem>_ref*.md` next to the case file, nothing else) for a case-insensitive regex and returns `ref2:L123: text` lines to the model, which then reads by offset and limit. The agent is told to use it instead of grep.
   - `log_case_result(case_file, diagnosis, decisions[], weak_spots[], exam_questions)` appends one line to `case_log.jsonl` in the folder that contains `cases/`. The score is correct = 1, partial = 0.5, wrong = 0, averaged over decisions.
5. **Scheduling.** The next `common` run reads `progress.json` and `case_log.jsonl`. `pick_topics()` ranks: never-built topics, then weak topics that are due (last score below `review.weak_below`, built at least `review.after_days` ago, weakest first), then least-built. `review.order` swaps the first two groups. Ties are random. Tier weights refine this without changing the order of the groups: among never-built topics the heavier tier goes first, and "least-built" means the lowest built count divided by weight. With every weight 1 (cardio has no tiers) the picks for a given `--seed` are the same as before tiers existed; re-prove that with the old-versus-new seed diff under Testing whenever `pick_topics()` changes.
   - **Several systems ticked** (`pick_mixed()`): each case first draws a Step 2 system from the `step2_systems` weights in `scenarios.json`, only among the systems that still have a topic in the pool, then runs `pick_topics()` inside that bucket. Topics with no (or an unknown) `step2_system` share the `untagged` bucket. One system never takes this path, so single-system picks don't change.
   - **Complaint mode** (`common --mode complaint`, `pick_by_complaint()`): each case takes a presentation from the fixed vocabulary in `PRESENTATIONS` (the one given with `--complaint`, else one drawn evenly among those that still have a topic in the pool), then runs `pick_topics()` among the topics whose `presentations` list has it. Step 2 system weights play no part, and it works the same for one system or several. The seed gets a `Presentation:` line in place of the topic's own `complaint` (which may not be the route this case takes) and the complaint-mode paragraph (`COMPLAINT_TEXT`). `--complaint` alone implies the mode. `presentations --system X` lists the presentations that have topics, for the Cases page.
6. **The Cases page** is a plugin view opened from the sidebar. Its backend runs `pick_case.py <command> --json` as a child process (no shell, args as an array, cwd = cases folder) and the frontend renders the result. Tabs: New case (pick by system, or by presenting complaint: a box that completes from the `presentations` handler's list, plus a Random complaint button), Case report, Progress (coverage, encounter mix, Step 2 system mix, topic-list warnings, guideline files), Review, Mix (edits `scenarios.json`: encounters, extras, review, tier weights, Step 2 system weights), Guidelines (runs `prepare` as a background job). The systems checkboxes come from the file names in `topics/`, so a new `topics/<name>.json` shows up when the page is reopened. The plugin settings page holds the cases folder and the Python path.

A plugin cannot create a Practice session or type into its composer (`ctx.app.openSession` only navigates to an existing one). That is why the flow is "copy the message, the learner pastes it".

## File layout

```
pick_case.py            case picker; Python 3.9+, standard library, optional numpy/matplotlib (ECGs), pymupdf/pymupdf4llm (prepare)
scenarios.json          encounter weights, extras chances (0-1), review settings, tier weights, Step 2 system weights; user-edited, keep the _how_to_edit key
topics/<system>.json    topic list (fields under "pick_case.py commands"); plus complaints for reports and an optional file-level step2_system
doctrine/10-doctrine.md practice-agent instructions (see above)
skills/rounds-topic-file/SKILL.md   the user's Claude skill for writing topic lists; it repeats the presentations vocabulary and the Step 2 system names
plugin/case-images/dist/
  manifest.json         id, version, minAppVersion
  backend.cjs           Node CommonJS: the three tools, then registerCases() for the Cases page handlers
  main.js               browser ES module: the three tool renderers, then the Cases view and settings page
*.bat                   launchers: New cardio case, New EM case, Cardio case report, Cardio review, Prepare cardio guidelines, Install plugin
README.md, LICENSE      user guide; AGPL-3.0
CLAUDE_CODE_BRIEF.md    the original brief for the Cases page work

Ignored by git:
cases/                  case_<stamp>_<hex>.md, _ecg.png, _ref.md (per-case guideline link)
guidelines/<system>/    guideline PDFs and their converted .md text
data/ptbxl/             cached PTB-XL files
progress.json(*.bak)    built counts keyed by topic id, case index, used reports and ECGs, encounter counts
case_log.jsonl          one line per finished case (written by the plugin)
review.md               written by `review`
python_path.txt         optional full path to python.exe
plugin/case-images/data/  the app's per-plugin data, if it ever lands here
```

The installed plugin lives at `%APPDATA%\LearnHarness\data\plugins\case-images\dist`. The repo copy is the source.

### `pick_case.py` commands

`common`, `report`, `status`, `review`, `prepare`, `presentations`. Run `python pick_case.py -h` and each subcommand's `-h`.

- `--system` takes one system, several separated by commas, or `all`. Several systems pool their topics.
- `--json` prints exactly one JSON object on stdout; a failure is `{"ok": false, "error": ...}` with exit code 1. Without it, output is plain text.
- `--seed N` goes before the command.
- Extras (rolled per case, written into the case file as ON/off): full history and exam, exam sign deep dive, ethics or communication, recall questions, exam-style questions. **A new section or key in `scenarios.json`** needs its default in `DEFAULT_SCENARIOS` in both `pick_case.py` and `backend.cjs` and a label in the backend's `LABELS`; `saveScenarios` only writes the sections it is sent, so an older frontend can't wipe newer ones. **Adding an extra touches four places:** `EXTRA_LABELS` and `DEFAULT_SCENARIOS` in `pick_case.py`, `DEFAULT_SCENARIOS` and `LABELS` in `backend.cjs` (the Mix tab then shows it by itself), `scenarios.json`, and a paragraph in `doctrine/10-doctrine.md` telling the agent what the extra means (only when the user supplies or approves the text). Adding one changes which cases a given `--seed` produces.
- **`atypical_presentation`** is in `extras` in `scenarios.json` (default 0.20) but is not one of the ON/off extras: when it rolls, `cmd_common` writes `ATYPICAL_TEXT` into the seed, changes the closing "build a common, typical presentation" sentence, and relabels the topic's `complaint` as the usual one. It is rolled from its own generator (`random.Random(f"atypical:{seed}")`), so every other roll of a given `--seed` is where it was; with the chance at 0 the output is byte-identical to the script before it (re-prove with the seed diff). It is not rolled in complaint mode. `progress.json` marks such a case `"atypical": true`, and a complaint-mode case `"mode": "complaint"` with its `"presentation"`; nothing shows these.
- **Seed instructions stay out of the doctrine.** The atypical and complaint-mode paragraphs (`ATYPICAL_TEXT`, `COMPLAINT_TEXT`) are the user's wording and live only in `pick_case.py`; `doctrine/10-doctrine.md` just says "Some cases carry extra instructions in their seed; follow them for that case." Don't copy them into the doctrine.
- **Topic fields** (only `id` and `topic` are required; `topics/cardio.json` uses the old pair and must keep working unchanged):
  - `guideline` + `guideline_file`: the original single reference. A topic without a `references` key gets exactly the old seed text.
  - `references`: a list of `{"file", "name", "region"}`. `file` is a PDF (read through its converted `.md`) or a chapter `.md` from `chapters.txt`; `"folder": "<system>"` on a reference puts its file in `guidelines/<system>/` instead of the topic file's own folder (`othersystem/file` as the file name means the same). Each reference gets its own neutral link (`case_…_ref.md`, `_ref2.md`, …). A non-US `region` (e.g. `"UK"`) labels it `Reference (UK)` and adds the "grade against US practice" sentence (`region_note()`); US or no region is labelled `Current guideline`. The Built cases paragraph of `doctrine/10-doctrine.md` carries the matching rule (non-US reference for presentation and approach, management from US practice).
  - `tier`: `common`, `cant_miss` or `rare`. The weights live once in `scenarios.json` under `tiers` (default 3, 2, 1); no tier means weight 1.
  - `step2_system`: the USMLE Step 2 CK system the topic belongs to, per topic or as a default at the top of the topic file (`cardio.json` sets `cardiovascular`). Names come from `step2_systems` in `scenarios.json`.
  - `canonical`: an optional shared name that marks topics with different ids as the same diagnosis; only `status` uses it, to warn.
  - `complaint`: written into the seed as the presenting complaint to open with.
  - `presentations`: the ways the topic can present, from the 27 names in `PRESENTATIONS` only (matched case-insensitively; anything else is ignored and `status` warns). Includes the classic atypical routes. Used by complaint mode; a topic with none is never picked there. The `rounds-topic-file` skill carries the same vocabulary, so change both together.
  - Topic files are read as `utf-8-sig`, because Notepad and PowerShell can add a BOM.
- **The same `id` in two topic files is the same topic** (e.g. `stemi` in `cardio.json` and `em.json`).
  - History is keyed by topic id alone: built counts, the case index's `topic`, scores, weak/due review and least-covered. A case of a shared topic made from one system counts in the other. `migrate_progress()` re-keys a `progress.json` that used `system/id`, adding the counts of the same id together, and saves the original once as `progress.json.system-keys.bak`. `case_log.jsonl` is keyed by case, so it needs no migration. Ids can't contain a slash.
  - `load_pool()` merges every entry with the same id (`merge_topics()`), before the Step 2 draw, **in single-system mode too and including entries from topic files that weren't chosen**: a STEMI made with only cardio ticked still gets the EM entry's references and complaint, and one made with only em ticked gets the cardio ECG codes. The user asked for this explicitly. References are unioned and deduped by resolved file path, `ecg_codes` and `presentations` are unioned, and every other field (including `ecg_rate` and `step2_system`) comes from the first file that has it, chosen systems first in `--system` order, then the other files alphabetically. A merged topic always gets the multi-reference seed format.
  - `tier` is the exception: it is the heaviest among the *chosen* systems' entries only. An unchosen file never changes the weighting, so which topic a single-system run picks for a given `--seed` is the same as before shared topics; the seed text of a shared topic, and the random rolls after it in a batch (an ECG may now be attached), are not. A topic that is in one file only is untouched.
  - Per-system counts in `status` count a shared topic in each system; the totals over several systems count it once.
  - `review --system X` shows the cases whose topic id is in X's list, whichever system the case was made from.

## Rules that must not break

The whole point is that the learner doesn't know the diagnosis until they work it out.

- **Neutral file names.** Case files, ECG images and per-case guideline copies are named `case_<stamp>_<hex>…`. Never put a topic, system, diagnosis or guideline name in any path. The learner sees tool-call headlines in chat, and a headline is the file path (or the grep pattern when no path is given).
- **Nothing about an unfinished case is shown.** No topic, diagnosis, guideline name or ECG label, in script output or in the GUI. A case is finished when it is in `case_log.jsonl`.
  - `status` hides topic names unless `--show-topics` is passed, because a topic counts as covered when its case is made.
  - With mixed systems, a per-system count going up reveals which system a new case came from. The backend's `status` handler therefore strips per-system counts and topic names unless `showTopics` is true, and the Progress switch is off every time the page opens (never persisted).
  - The Step 2 system mix (`step2_mix()`) counts finished cases only, for the same reason; `--show-topics` / the Progress switch counts every built case. The text `status` prints it only for several systems.
  - The case file must not name its system.
  - In complaint mode the script output and the Cases page don't say which presentation a random case drew. The learner sees it when the case opens; the page has no need to say it sooner.
  - The GUI never shows case file contents.
- **Finished cases** may be shown with topic and diagnosis (Review).
- **`status` warnings** (`topic_warnings()`, JSON key `warnings`) name topics from the topic lists, never from cases: an id used twice inside one file, a shared topic whose files disagree on `step2_system` (the first is used), different ids with the same topic text or the same `canonical`, tier or `step2_system` names missing from `scenarios.json`, a `presentations` value outside the vocabulary, and a shared topic whose files list different presentations. The same id in two files is a shared topic and is not a warning. They are printed only when there is something to report, so clean single-system output is unchanged.
- **The `.bat` launchers keep working.** Keep every existing flag and the single-system plain-text output unchanged.
- **The plugin tools keep their names, parameters and behavior** (`show_case_image`, `log_case_result`, `search_case_ref`). Add to the plugin; don't change them.
- **`search_case_ref` shows the learner nothing but a count.** Its renderer prints "Searched case reference · N matches" in every state and never reads `tool.input` (the query), `tool.result` (the matched text) or `tool.errorText`. The backend puts only `{kind, matches, files}` in `details`, and its error messages never repeat the query. Keep it that way: a search word or a matched line is the diagnosis.
- **No grep or find during a case.** The host prints `input.pattern` as the headline of those tools whether or not a path is given, so any search word shows. The seed text (`guideline_reference()`), `doctrine/10-doctrine.md` and the plugin's instruction all send the agent to `search_case_ref` instead; keep the three in step.
- **Never name a plugin tool parameter `pattern`,** for the same reason: if the plugin's renderer isn't running, the host's own card shows that value collapsed. That is why the search parameter is `query`.
- **Never commit** `cases/`, `guidelines/`, `data/`, `progress.json`, `case_log.jsonl`, `review.md` or `python_path.txt`. Never commit a `.pdf`, an `.epub`, or converted book or guideline text anywhere in the tree (converted text lives only under `guidelines/`), and never name a copyrighted book in a tracked file: the EM list's main reference is called "EM handbook" (`em-handbook-*.md`) on purpose, and each user supplies a reference of their own choice. Cases are spoilers, guideline files belong to their publishers, the rest is personal or machine-specific. Check `git status` before committing.
- **The README's guideline download tables** (Setting up from scratch) are built from the topic files' references. When a topic file gains or renames a reference file, update the tables in the same commit.
- **Ask the user before** changing anything outside the plugin and `pick_case.py`, creating a GitHub repository, or touching their installed app.
- **Frontend:** insert text with `textContent`, never `innerHTML` with data. Use the app's theme variables (`--foreground`, `--background`, `--border`, `--muted-foreground`, `--primary`).
- **Paths:** Windows paths everywhere, and the cases folder path may contain spaces.

## Why things are the way they are

- **Hard-linked per-case guideline copies** (`neutral_link()`): the agent must read the guideline during the case, but a path like `svt-2015.md` in a tool-call headline gives the diagnosis away. Each case gets `case_…_ref.md`, a hard link to the converted guideline, which costs no disk space. It falls back to a copy if the drive can't hard-link.
- **Guidelines are converted to text first** (`prepare`): results of the app's pdf tool are displayed to the learner in full, so the PDF can't be read mid-case. The text version has a contents list with line numbers so the agent reads only the sections a case needs.
- **Big references are split by chapter** (`chapter_plan()`): a PDF over 150 pages with at least two top-level bookmarks becomes one `.md` per bookmark (`<stem>-<nn>-<slug>.md`, each with its own contents list), plus `guidelines/<system>/chapters.txt` listing file, page range and title. Bookmarks under 3 pages get no file. A PDF that any topic list names as a whole file (`guideline_file`, or a `.pdf` in `references`, in whichever folder) is never split, which is what keeps the two cardio guidelines over 150 pages as single files. A big PDF with no bookmarks that no topic names is reported and not converted. `prepare` accepts a system that has a guidelines folder but no topic list yet, because the chapter names are needed to write the topic list. `prepare --system X` also converts the PDFs X's topics use from other systems' folders (`borrowed_pdfs()`), and `status` doesn't call a PDF a stray when another system's topics use it (`referenced_paths()`).
- **No symlink or junction for the plugin's `dist`**: LearnHarness's plugin tooling refuses symlinked package roots, removing the plugin in the app could delete through a link into this repo, and the app the user studies with would load half-finished edits. `Install plugin.bat` copies `dist` instead (`robocopy /MIR`, leaving the sibling `data` folder alone).
- **`unseen_first` is the default review order**: every topic gets seen once before due reviews are scheduled. The user can flip it to `review_first` in the Mix tab. This is the user's chosen default; the reasoning beyond the note in `scenarios.json` isn't written down, so ask before changing it.
- **PTB-XL rate matching**: the script measures the ventricular rate of each candidate tracing (`heart_rate()`), honors a topic's optional `ecg_rate` range (AF with rapid response needs a fast tracing), and writes the rate into the seed so the vitals the agent releases match the ECG. The patient frame (age, sex) comes from the ECG's patient for the same reason.
- **`search_case_ref` exists because grep leaks.** The host's own tool card shows `input.pattern` as the collapsed headline of any tool that has one (grep and find included, with or without a path), and when the learner expands it, the full input, then the error text or else `details` (LearnHarness v0.6.1 `components/artifacts/tool-call-card.tsx`, `toolFallbackPart()` in `components/plugin-renderers.tsx`). A plugin renderer replaces that card completely, so the search can be hidden. The host falls back to its own card if the renderer throws or the plugin's frontend isn't loaded, so the renderer must never throw; in that fallback the collapsed line is just the tool name (the parameter is `query`, and `details` holds only counts), and the query is visible only if the learner expands the card on purpose. That last step can't be closed from a plugin. The regex runs in a `vm` context with a 2 second limit so a pattern that backtracks forever can't hang the backend; a long line is searched whole (up to 20,000 characters) and returned as a 400-character window around the match, because converted guideline paragraphs are single long lines. Symbolic links are not followed (hard links, which is what the references are, are ordinary files).
- **The model gets no image tokens from `show_case_image`**: the tool returns a short text result to the model and puts the image in `details` for the frontend renderer only. The agent grades ECG interpretation against the cardiologist-coded PTB-XL statements in the seed, never against its own reading.
- **`--json` rather than scraping text**: the GUI needs structured data, and the text output has to stay stable for the launchers. In JSON mode everything the command prints is captured and returned under `text`, so stdout stays one object.
- **One script run at a time** in the backend (`exclusive()`): every run reads and rewrites `progress.json`.
- **`prepare` runs as a job** that emits a `prepare` notification when done, because it can take many minutes and a single backend call would hang the page.
- **Clipboard**: the frontend copies with `navigator.clipboard`; if the page has lost permission (the case took a while to make), it falls back to the backend's `copy` handler, which pipes UTF-16 to `clip.exe`.
- **Python detection** follows the launchers' order: `python_path.txt`, `py`, `python` on PATH (skipping the Microsoft Store stub in `WindowsApps`), conda folders, `%LOCALAPPDATA%\Programs\Python\Python3*`. A `.lnk` shortcut is rejected with a warning because it can't be run without a shell.
- **AGPL-3.0**: `doctrine/10-doctrine.md` derives from LearnHarness's AGPL-3.0 practice prompt.

## Testing

There is no test suite. Never test against the real folder; it holds the user's study data.

**Script.** Copy `pick_case.py`, `scenarios.json`, `topics/`, `progress.json`, `data/` and the guideline `.md` files to a temp folder (add a `python_path.txt` with the real `python.exe` there if you run launchers). The script finds its data next to itself, so each copy is self-contained.
- For regressions, make two identical copies, put `git show HEAD:pick_case.py` in one and the new script in the other, run the same commands with the same `--seed`, and diff the output after replacing case names (`case_<stamp>_<hex>`) with a placeholder. Compare the case files and `progress.json` the same way.
- For Review and scheduling, write a synthetic `case_log.jsonl` for case ids in the copy's `progress.json`.
- For mixed systems, add a fake `topics/<name>.json` whose ids collide with cardio's.
- `--clip` overwrites the real clipboard. Test it by importing `pick_case` and replacing `copy_to_clipboard`.
- Run a launcher by its full path with stdin from `NUL` so `pause` returns.
- `common` may download ECG recordings from PhysioNet; `report` calls Europe PMC.

**Plugin backend.** `node --check` both files. Then `require` `backend.cjs` in a small Node script with a stand-in `ctx` (`dataDirectory`, `signal`, `handle`, `registerTools`, `registerInstructions`, `events.emit`), set the cases folder to the temp copy with `setConfig`, and call each handler. For a tool, take it from `registerTools`' `create()` and call `execute(id, input, signal)`; for `search_case_ref` use a temp `cases` folder with hard links to real converted files plus decoy files it must not read.

**Plugin frontend.** Serve a page from localhost that imports `main.js`, calls `activate()` with a mock `ctx` (returning real handler output saved as JSON), and mounts the view and the settings page. Tool renderers are captured from `registerToolRenderer` and mounted with `{state, input, output, result, errorText}`; `output` is the tool's `details`. Scripted events can't grant real fullscreen, so `requestFullscreen()` itself is only exercised in the app. A page opened from `file://` is not interactive in the browser tools.

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

Commit after each step that works, with a message that says what changed and why, so any single change can be rolled back. History was rewritten once, on 2026-11-15 before the first push, to use a GitHub no-reply author address and a generic name for the EM reference; commit hashes quoted anywhere before that date no longer exist. Commit with the repo's configured no-reply address. The first commit with the unmodified v1.1.0 plugin is `9f8ce07`.
