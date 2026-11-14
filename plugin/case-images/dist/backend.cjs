// Rounds tools for LearnHarness practice sessions.
//
// show_case_image  shows a case's image (an ECG, a film) inline. Reads only image files named
//                  case_*.png/.jpg/.jpeg inside a folder named "cases", up to 8 MB.
// log_case_result  appends one line per finished case to case_log.jsonl in the folder that
//                  contains "cases". It writes nothing else, anywhere.
// search_case_ref  searches a case's own reference files (<case>_ref*.md next to the case file)
//                  for a pattern. It reads nothing else, and its renderer never shows the pattern
//                  or the matches, so a search can't give the diagnosis away.
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const MAX_BYTES = 8 * 1024 * 1024;
const TYPES = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg" };
const IMAGE_NAME = /^case_[A-Za-z0-9_-]+\.(png|jpe?g)$/i;
const CASE_NAME = /^case_[A-Za-z0-9_-]+\.md$/i;
const VERDICTS = ["correct", "partial", "wrong"];
const MAX_REF_BYTES = 20 * 1024 * 1024;
const MAX_LINE = 400;          // characters of a line that are returned (a window around the match)
const MAX_SEARCHED = 20000;    // characters of a line that are searched; guideline paragraphs are one long line
const MAX_RESULT_CHARS = 24000;
const SEARCH_TIMEOUT_MS = 2000;

const wholeNumber = (v, lo, hi, fallback) => (Number.isInteger(v) ? Math.min(hi, Math.max(lo, v)) : fallback);

/** This case's reference files: case_<stamp>_<hex>_ref.md, _ref2.md, ... next to the case file.
 * Only regular files count (a hard link is one; a symbolic link is not followed). */
async function caseReferenceFiles(caseFile) {
  const dir = path.dirname(caseFile);
  const stem = path.basename(caseFile, path.extname(caseFile)).toLowerCase();
  let names;
  try { names = await fs.promises.readdir(dir); } catch { return []; }
  const found = [];
  for (const name of names) {
    const lower = name.toLowerCase();
    if (!lower.startsWith(stem + "_ref") || !/^_ref\d*\.md$/.test(lower.slice(stem.length))) continue;
    const file = path.join(dir, name);
    let stat;
    try { stat = await fs.promises.lstat(file); } catch { continue; }
    if (!stat.isFile() || stat.size > MAX_REF_BYTES) continue;
    found.push({ file, suffix: lower.slice(stem.length + 1, -3) }); // "ref", "ref2", ...
  }
  const order = f => Number(f.suffix.slice(3)) || 1;
  return found.sort((a, b) => order(a) - order(b));
}

/** [line number (0-based), position of the match in that line] for each matching line. Runs in
 * a vm with a time limit, so a pattern that backtracks forever is stopped instead of hanging
 * the plugin. */
function matchingLines(lines, pattern, limit) {
  try {
    return vm.runInNewContext(
      "const re = new RegExp(pattern, 'i'); const hits = [];" +
      "for (let i = 0; i < lines.length && hits.length < limit; i++) { const at = lines[i].search(re); if (at >= 0) hits.push([i, at]); } hits;",
      { lines, pattern, limit }, { timeout: SEARCH_TIMEOUT_MS });
  } catch (e) {
    if (e && e.code === "ERR_SCRIPT_EXECUTION_TIMEOUT") throw new Error("That query took too long to run. Use a simpler one.");
    // V8 says "Invalid regular expression: /<the query>/i: <reason>". Keep the reason only: an error
    // text can end up on screen, and the query must not.
    const reason = String(e && e.message ? e.message : e).split(": ").pop();
    throw new Error(`The query is not a valid regular expression (${reason.includes(pattern) ? "syntax error" : reason}).`);
  }
}

function checkPath(raw, nameRule, what) {
  if (typeof raw !== "string" || !raw.trim()) throw new Error(`Give the ${what}'s full file path.`);
  const cleaned = raw.trim().replace(/^[`"']+|[`"']+$/g, "");
  if (!path.isAbsolute(cleaned)) throw new Error("The path must be absolute, exactly as given at the start of the case.");
  const resolved = path.resolve(cleaned);
  const parent = path.basename(path.dirname(resolved)).toLowerCase();
  if (!nameRule.test(path.basename(resolved)) || parent !== "cases") {
    throw new Error(`Only ${what}s named case_… inside a 'cases' folder are allowed.`);
  }
  return resolved;
}

const clip = (s, n) => (typeof s === "string" ? s.replace(/\s+/g, " ").trim().slice(0, n) : "");

exports.activate = ctx => {
  ctx.registerInstructions({
    agents: ["practice"],
    text:
      "Three rounds tools are available. show_case_image: when a case file attaches an image (an ECG, a film) and the " +
      "learner orders that test, call it with the image's path exactly as the case file gives it; the learner sees the " +
      "image inline, so do not also print the path, describe it or interpret it. If it fails, give the path as inline code. " +
      "log_case_result: call it exactly once per case, as the very last step after the case has closed (after the " +
      "one-liner, any exam-style questions and retests), with the case file's path from the opening message. " +
      "search_case_ref: to find a threshold, drug or section in a case's reference files, use this instead of grep. " +
      "Never run grep or find on a case file or its references while the case is open: the learner sees the search " +
      "words of those tools, and the words give the diagnosis away. Give search_case_ref the case file's path and a " +
      "query; it searches every reference of that case and returns matching lines with the file (ref, ref2, ...) and " +
      "line number, and the learner sees only that a search happened. Then read the lines you need from that reference " +
      "file with offset and limit.",
  });

  ctx.registerTools({
    agents: ["practice"],
    create: () => [
      {
        name: "show_case_image",
        label: "Show case image",
        description:
          "Show the learner an image attached to the current case (for example a 12-lead ECG) inline in the chat. " +
          "Use the exact absolute path from the case file. Only case_*.png/.jpg files in a 'cases' folder are allowed.",
        parameters: {
          type: "object",
          properties: {
            path: { type: "string", minLength: 1, maxLength: 1000, description: "Absolute path from the case file." },
            caption: { type: "string", maxLength: 120, description: "Neutral caption, e.g. '12-lead ECG'. Never a finding or diagnosis." },
          },
          required: ["path"],
          additionalProperties: false,
        },
        execute: async (_id, input, signal) => {
          if (signal.aborted || ctx.signal.aborted) throw new Error("Cancelled");
          const file = checkPath(input.path, IMAGE_NAME, "case image");
          let stat;
          try {
            stat = await fs.promises.stat(file);
          } catch {
            throw new Error("Image file not found at that path.");
          }
          if (!stat.isFile()) throw new Error("That path is not a file.");
          if (stat.size > MAX_BYTES) throw new Error("Image is larger than 8 MB.");
          const bytes = await fs.promises.readFile(file);
          if (signal.aborted) throw new Error("Cancelled");
          const mime = TYPES[path.extname(file).toLowerCase()];
          return {
            content: [{ type: "text", text: "The image is now shown to the learner. Wait for their interpretation." }],
            details: { kind: "image", dataUrl: `data:${mime};base64,${bytes.toString("base64")}`, caption: clip(input.caption, 120) },
          };
        },
      },
      {
        name: "log_case_result",
        label: "Log case result",
        description:
          "Record how the learner did on the case that just closed, so weak topics come back for review. Call once, " +
          "as the last step, after the case has closed. Be honest: a verdict is what the learner actually committed to, " +
          "not what they reached after hints.",
        parameters: {
          type: "object",
          properties: {
            case_file: { type: "string", minLength: 1, maxLength: 1000, description: "Absolute path of this case's file (case_….md), as given in the opening message." },
            diagnosis: { type: "string", minLength: 1, maxLength: 120, description: "Final diagnosis, short, e.g. 'Inferior STEMI with RV involvement'." },
            decisions: {
              type: "array", minItems: 1, maxItems: 12,
              description: "Each decision point or mechanism demand posed during the case, in order.",
              items: {
                type: "object",
                properties: {
                  point: { type: "string", minLength: 1, maxLength: 120, description: "What was asked, short, e.g. 'Reperfusion strategy and timing'." },
                  verdict: { type: "string", enum: VERDICTS, description: "correct = right unaided; partial = right with hints or incomplete; wrong = wrong or abandoned." },
                },
                required: ["point", "verdict"],
                additionalProperties: false,
              },
            },
            weak_spots: {
              type: "array", maxItems: 4,
              description: "The specific gaps this case exposed, one line each, phrased as what to review, e.g. 'Why nitrates are dangerous in RV infarct (preload dependence)'. Empty if none.",
              items: { type: "string", minLength: 1, maxLength: 200 },
            },
            exam_questions: {
              type: "object",
              description: "Only if exam-style questions were posed.",
              properties: { correct: { type: "integer", minimum: 0, maximum: 5 }, total: { type: "integer", minimum: 1, maximum: 5 } },
              required: ["correct", "total"],
              additionalProperties: false,
            },
          },
          required: ["case_file", "diagnosis", "decisions"],
          additionalProperties: false,
        },
        execute: async (_id, input, signal) => {
          if (signal.aborted || ctx.signal.aborted) throw new Error("Cancelled");
          const caseFile = checkPath(input.case_file, CASE_NAME, "case file");
          const decisions = (Array.isArray(input.decisions) ? input.decisions : [])
            .slice(0, 12)
            .filter(d => d && VERDICTS.includes(d.verdict))
            .map(d => ({ point: clip(d.point, 120), verdict: d.verdict }));
          if (!decisions.length) throw new Error("Give at least one decision with a verdict of correct, partial or wrong.");
          const weak = (Array.isArray(input.weak_spots) ? input.weak_spots : []).slice(0, 4).map(s => clip(s, 200)).filter(Boolean);
          const eq = input.exam_questions && Number.isInteger(input.exam_questions.correct) && Number.isInteger(input.exam_questions.total)
            ? { correct: Math.min(input.exam_questions.correct, input.exam_questions.total), total: input.exam_questions.total }
            : null;
          const score = decisions.reduce((s, d) => s + (d.verdict === "correct" ? 1 : d.verdict === "partial" ? 0.5 : 0), 0) / decisions.length;
          const entry = {
            logged: new Date().toISOString(),
            case: path.basename(caseFile, path.extname(caseFile)),
            diagnosis: clip(input.diagnosis, 120),
            score: Math.round(score * 100) / 100,
            decisions,
            weak_spots: weak,
            ...(eq ? { exam_questions: eq } : {}),
          };
          const logFile = path.join(path.dirname(path.dirname(caseFile)), "case_log.jsonl");
          if (signal.aborted) throw new Error("Cancelled");
          await fs.promises.appendFile(logFile, JSON.stringify(entry) + "\n", "utf8");
          return {
            content: [{ type: "text", text: "Logged. The case is complete." }],
            details: { kind: "log", ...entry },
          };
        },
      },
      {
        name: "search_case_ref",
        label: "Search case reference",
        description:
          "Search the current case's reference files (the guideline or chapter text the case file points at) for a " +
          "regular expression, case-insensitive. Use it instead of grep or find, which show the learner what you searched " +
          "for: here the learner sees only that a search was made, never the query or the matches. Returns matching lines as '<ref>:L<line>: text', where <ref> is the ending " +
          "of the reference file's name (ref = case_..._ref.md, ref2 = case_..._ref2.md). Follow up by reading that file " +
          "at that line with offset and limit.",
        parameters: {
          type: "object",
          properties: {
            case_file: { type: "string", minLength: 1, maxLength: 1000, description: "Absolute path of this case's file (case_….md), as given in the opening message." },
            // Named "query", not "pattern": the host's own tool card prints input.pattern as its headline,
            // and that card is what shows if this plugin's renderer is ever not running.
            query: { type: "string", minLength: 1, maxLength: 200, description: "Regular expression, matched per line, case-insensitive. Plain words work too." },
            context: { type: "integer", minimum: 0, maximum: 5, description: "Lines of context before and after each match. Default 2." },
            max_matches: { type: "integer", minimum: 1, maximum: 100, description: "Stop after this many matches. Default 30." },
          },
          required: ["case_file", "query"],
          additionalProperties: false,
        },
        execute: async (_id, input, signal) => {
          if (signal.aborted || ctx.signal.aborted) throw new Error("Cancelled");
          const caseFile = checkPath(input.case_file, CASE_NAME, "case file");
          const pattern = typeof input.query === "string" ? input.query : "";
          if (!pattern.trim()) throw new Error("Give a query to search for.");
          if (pattern.length > 200) throw new Error("The query can be at most 200 characters.");
          const context = wholeNumber(input.context, 0, 5, 2);
          const maxMatches = wholeNumber(input.max_matches, 1, 100, 30);
          const refs = await caseReferenceFiles(caseFile);
          if (!refs.length) {
            return {
              content: [{ type: "text", text: "This case has no reference text files to search. Work from the guideline the case file names." }],
              details: { kind: "search", matches: 0, files: 0 },
            };
          }
          const out = [];
          let total = 0, size = 0, cut = false;
          for (const ref of refs) {
            if (signal.aborted) throw new Error("Cancelled");
            if (total >= maxMatches) { cut = true; break; }
            const lines = (await fs.promises.readFile(ref.file, "utf8")).split(/\r?\n/).map(l => (l.length > MAX_SEARCHED ? l.slice(0, MAX_SEARCHED) : l));
            const hits = matchingLines(lines, pattern, maxMatches - total + 1);
            if (hits.length > maxMatches - total) { cut = true; hits.length = maxMatches - total; }
            total += hits.length;
            const matchAt = new Map(hits);
            // A long line is returned as a window around its match, so the match is always in view.
            const shown = i => {
              const full = lines[i];
              if (full.length <= MAX_LINE) return full;
              const start = Math.max(0, Math.min((matchAt.get(i) || 0) - 120, full.length - MAX_LINE));
              return (start ? "…" : "") + full.slice(start, start + MAX_LINE) + (start + MAX_LINE < full.length ? "…" : "");
            };
            let last = -1;
            for (const [hit] of hits) {
              const from = Math.max(hit - context, last + 1, 0), to = Math.min(hit + context, lines.length - 1);
              if (last >= 0 && from > last + 1) out.push("--");
              for (let i = from; i <= to; i++) {
                const line = `${ref.suffix}:L${i + 1}${matchAt.has(i) ? ":" : "-"} ${shown(i)}`;
                size += line.length + 1;
                if (size > MAX_RESULT_CHARS) { cut = true; break; }
                out.push(line);
              }
              last = Math.max(last, to);
              if (size > MAX_RESULT_CHARS) break;
            }
            if (hits.length && size <= MAX_RESULT_CHARS) out.push("--");
            if (size > MAX_RESULT_CHARS) break;
          }
          const head = total
            ? `${total} matching line${total === 1 ? "" : "s"} in ${refs.length} reference file${refs.length === 1 ? "" : "s"}` +
              (cut ? " (more exist; narrow the pattern to see the rest)" : "") + ". Lines marked ':' match, '-' are context."
            : `No matches in ${refs.length} reference file${refs.length === 1 ? "" : "s"}. Try another word or a broader pattern.`;
          return {
            content: [{ type: "text", text: [head, ...out].join("\n") }],
            // Only counts go to the renderer: the learner must not see the pattern or the matched text.
            details: { kind: "search", matches: total, files: refs.length },
          };
        },
      },
    ],
  });

  registerCases(ctx);
};

// ---------------------------------------------------------------------------------------------
// Cases page backend. Runs pick_case.py (in the cases folder) as a child process, with no shell,
// and returns its --json output to the plugin's own view. It never reads a case file, and it
// passes on a topic name only for finished cases (Review) or when the learner ticks the
// "may spoil" switch (Progress).
//
// Reads:  <cases folder>/topics/*.json (file names only), scenarios.json, python_path.txt
// Writes: <cases folder>/scenarios.json (the Mix tab), and this plugin's own data/settings.json.
// Everything else in the cases folder is written by pick_case.py itself.
// ---------------------------------------------------------------------------------------------
const os = require("os");
const { execFile, spawn } = require("child_process");

const WIN = process.platform === "win32";
const SYSTEM_NAME = /^[A-Za-z0-9_-]+$/;
const SETTING_KEY = /^[A-Za-z0-9][A-Za-z0-9_]*$/;
const ORDERS = ["unseen_first", "review_first"];

// Same defaults and labels as pick_case.py.
const DEFAULT_SCENARIOS = {
  encounters: { ed_first_presentation: 35, ward_called_by_nurse: 15, ward_round_day_2: 15, handover: 10, clinic_follow_up: 15, clinic_new_referral: 10 },
  extras: { full_history_and_exam: 0.25, exam_sign_deep_dive: 0.3, ethics_or_communication: 0.1, recall_questions: 0.2, exam_style_questions: 0.5, ecg_when_topic_has_one: 0.8, handover_contains_an_error: 0.5 },
  review: { weak_below: 0.7, after_days: 2, order: "unseen_first" },
  tiers: { common: 3, cant_miss: 2, rare: 1 },
  step2_systems: {
    renal_reproductive: 10, cardiovascular: 9, musculoskeletal_skin: 9, behavioral: 7.5, blood_immune: 7.5,
    gastrointestinal: 7.5, nervous: 7.5, respiratory: 7.5, multisystem: 6, endocrine: 5, pregnancy: 5,
    human_development: 3, untagged: 5,
  },
};
const LABELS = {
  ed_first_presentation: "Emergency department, first presentation",
  ward_called_by_nurse: "Ward, called by the nurse",
  ward_round_day_2: "Ward round, day 2",
  handover: "Handover",
  clinic_follow_up: "Clinic follow-up",
  clinic_new_referral: "Clinic new referral",
  full_history_and_exam: "Full history and exam",
  exam_sign_deep_dive: "Exam sign deep dive",
  ethics_or_communication: "Ethics or communication",
  recall_questions: "Recall questions",
  exam_style_questions: "Exam-style questions",
  ecg_when_topic_has_one: "ECG, when the topic has one",
  handover_contains_an_error: "Handover contains a planted error",
  common: "Common",
  cant_miss: "Can't miss",
  rare: "Rare",
  renal_reproductive: "Renal, urinary and reproductive",
  cardiovascular: "Cardiovascular",
  musculoskeletal_skin: "Musculoskeletal and skin",
  behavioral: "Behavioral health",
  blood_immune: "Blood and immune",
  gastrointestinal: "Gastrointestinal",
  nervous: "Nervous system and special senses",
  respiratory: "Respiratory",
  multisystem: "Multisystem processes",
  endocrine: "Endocrine",
  pregnancy: "Pregnancy, childbirth and puerperium",
  human_development: "Human development",
  untagged: "Untagged (topics with no Step 2 system)",
};
const labelOf = key => LABELS[key] || (key.charAt(0).toUpperCase() + key.slice(1)).replace(/_/g, " ");

const asObject = v => (v && typeof v === "object" && !Array.isArray(v) ? v : {});
const isNumber = v => typeof v === "number" && Number.isFinite(v);
const isFile = p => { try { return fs.statSync(p).isFile(); } catch { return false; } };
const isDir = p => { try { return fs.statSync(p).isDirectory(); } catch { return false; } };
const publicKeys = o => Object.keys(asObject(o)).filter(k => !k.startsWith("_"));

function writeFileAtomic(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, text, "utf8");
  fs.renameSync(tmp, file);
}

/** First match on PATH, skipping the Microsoft Store stubs in WindowsApps. */
function onPath(names) {
  const dirs = (process.env.PATH || process.env.Path || "").split(path.delimiter).filter(Boolean);
  for (const dir of dirs) {
    if (/[\\/]Microsoft[\\/]WindowsApps[\\/]?$/i.test(dir)) continue;
    for (const name of names) {
      const full = path.join(dir, name);
      if (isFile(full)) return full;
    }
  }
  return null;
}

/** Same search order as the .bat launchers: python_path.txt, py, python, conda, python.org installs. */
function findPython(folder, override) {
  const warnings = [];
  const usable = (file, what) => {
    if (!isFile(file)) { warnings.push(`${what} points to "${file}", which doesn't exist.`); return false; }
    if (WIN && path.extname(file).toLowerCase() !== ".exe") {
      warnings.push(`${what} points to "${file}", which is not python.exe (a shortcut can't be run from here).`);
      return false;
    }
    return true;
  };
  const found = (command, pre, source) => ({ command, pre, source, warnings });

  if (override && usable(override, "The Python path in this plugin's settings")) return found(override, [], "plugin settings");
  let listed = "";
  try {
    listed = fs.readFileSync(path.join(folder, "python_path.txt"), "utf8").replace(/^\uFEFF/, "").split(/\r?\n/)[0].trim().replace(/^"+|"+$/g, "");
  } catch { /* no python_path.txt */ }
  if (listed && usable(listed, "python_path.txt")) return found(listed, [], "python_path.txt");

  if (WIN) {
    const launcher = onPath(["py.exe"]);
    if (launcher) return found(launcher, ["-3"], "py launcher");
  }
  const python = onPath(WIN ? ["python.exe"] : ["python3", "python"]);
  if (python) return found(python, [], "PATH");
  if (WIN) {
    const home = os.homedir(), local = process.env.LOCALAPPDATA || "", common = process.env.ProgramData || "";
    const fixed = [
      [home, "anaconda3"], [home, "miniconda3"], [local, "anaconda3"], [local, "miniconda3"], [common, "anaconda3"],
    ].filter(([root]) => root).map(parts => path.join(...parts, "python.exe"));
    for (const file of fixed) if (isFile(file)) return found(file, [], "conda");
    const programs = path.join(local, "Programs", "Python");
    let installs = [];
    try { installs = fs.readdirSync(programs).filter(n => /^Python3/i.test(n)); } catch { /* none */ }
    installs.sort((a, b) => (parseInt(b.replace(/\D/g, ""), 10) || 0) - (parseInt(a.replace(/\D/g, ""), 10) || 0));
    for (const name of installs) {
      const file = path.join(programs, name, "python.exe");
      if (isFile(file)) return found(file, [], "python.org install");
    }
  }
  return found(null, [], null);
}

function registerCases(ctx) {
  const settingsFile = path.join(ctx.dataDirectory, "settings.json");
  const defaultFolder = path.join(os.homedir(), "Documents", "LearnHarness-cases");

  const readSettings = () => {
    try { return asObject(JSON.parse(fs.readFileSync(settingsFile, "utf8"))); } catch { return {}; }
  };
  const setting = key => { const v = readSettings()[key]; return typeof v === "string" ? v.trim() : ""; };
  const casesFolder = () => setting("casesFolder") || defaultFolder;
  const listSystems = () => {
    try {
      return fs.readdirSync(path.join(casesFolder(), "topics"))
        .filter(f => /\.json$/i.test(f)).map(f => f.slice(0, -5)).filter(s => SYSTEM_NAME.test(s)).sort();
    } catch { return []; }
  };
  const pickSystems = (input, required) => {
    const known = listSystems();
    const picked = Array.isArray(input) ? [...new Set(input.filter(s => typeof s === "string" && known.includes(s)))] : [];
    if (required && !picked.length) throw new Error(known.length ? "Tick at least one system." : `No topic lists found in ${path.join(casesFolder(), "topics")}.`);
    return picked;
  };
  const intBetween = (v, lo, hi, fallback) => (Number.isInteger(v) && v >= lo && v <= hi ? v : fallback);

  // One script run at a time: every run reads and rewrites progress.json.
  let queue = Promise.resolve();
  const exclusive = task => {
    const run = queue.then(task, task);
    queue = run.catch(() => {});
    return run;
  };

  const execPython = (py, args, options) => new Promise(resolve => {
    execFile(py.command, [...py.pre, ...args], {
      windowsHide: true, encoding: "utf8", maxBuffer: 32 * 1024 * 1024, signal: ctx.signal,
      env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" }, ...options,
    }, (error, stdout, stderr) => resolve({ error, stdout: stdout || "", stderr: stderr || "" }));
  });

  /** Runs pick_case.py with --json and returns the parsed object, or throws with the script's own message. */
  const runScript = (args, timeoutMs) => exclusive(async () => {
    const folder = casesFolder();
    const script = path.join(folder, "pick_case.py");
    if (!isFile(script)) throw new Error(`pick_case.py is not in "${folder}". Set the Cases folder in this plugin's settings.`);
    const py = findPython(folder, setting("pythonPath"));
    if (!py.command) {
      throw new Error(["Couldn't find Python.", ...py.warnings, "Set the Python path in this plugin's settings (full path to python.exe)."].join(" "));
    }
    const { error, stdout, stderr } = await execPython(py, [script, ...args, "--json"], { cwd: folder, timeout: timeoutMs });
    let parsed = null;
    const body = stdout.trim();
    for (const candidate of [body, body.split(/\r?\n/).pop() || ""]) {
      try { parsed = asObject(JSON.parse(candidate)); break; } catch { /* try the last line */ }
    }
    if (parsed && parsed.ok === true) return parsed;
    if (parsed && typeof parsed.error === "string") throw new Error(parsed.error);
    if (error && error.killed) throw new Error(`pick_case.py was stopped after ${Math.round(timeoutMs / 1000)} seconds without finishing.`);
    const detail = stderr.trim().slice(-1500) || (error ? error.message : "It printed nothing.");
    throw new Error(`pick_case.py failed.\n${detail}`);
  });

  // ----- configuration -----

  const describeConfig = async () => {
    const folder = casesFolder();
    const py = findPython(folder, setting("pythonPath"));
    let version = "";
    const warnings = [...py.warnings];
    if (py.command) {
      const { error, stdout, stderr } = await execPython(py, ["--version"], { timeout: 15000 });
      version = (stdout || stderr).trim().split(/\r?\n/)[0] || "";
      if (error || !/^Python 3/i.test(version)) {
        warnings.push(`"${py.command}" did not answer as Python 3${version ? ` (it said: ${version.slice(0, 120)})` : ""}.`);
      }
    }
    return {
      casesFolder: folder,
      casesFolderSetting: setting("casesFolder"),
      defaultFolder,
      folderOk: isFile(path.join(folder, "pick_case.py")),
      pythonSetting: setting("pythonPath"),
      python: py.command ? { path: py.command, source: py.source, version } : null,
      warnings,
      systems: listSystems(),
    };
  };

  ctx.handle("getConfig", () => describeConfig());

  ctx.handle("setConfig", input => {
    const next = { ...readSettings() };
    const given = asObject(input);
    if (typeof given.casesFolder === "string") {
      const folder = given.casesFolder.trim().replace(/^"+|"+$/g, "");
      if (folder) {
        if (!path.isAbsolute(folder)) throw new Error("Give the full path of the folder, starting with the drive letter.");
        if (!isDir(folder)) throw new Error("That folder doesn't exist.");
        if (!isFile(path.join(folder, "pick_case.py"))) throw new Error("pick_case.py is not in that folder.");
        next.casesFolder = path.resolve(folder);
      } else delete next.casesFolder;
    }
    if (typeof given.pythonPath === "string") {
      const file = given.pythonPath.trim().replace(/^"+|"+$/g, "");
      if (file) {
        if (!path.isAbsolute(file)) throw new Error("Give the full path to python.exe.");
        if (!isFile(file)) throw new Error("That file doesn't exist.");
        if (WIN && path.extname(file).toLowerCase() !== ".exe") throw new Error("That is not python.exe. A shortcut (.lnk) can't be used.");
        next.pythonPath = path.resolve(file);
      } else delete next.pythonPath;
    }
    writeFileAtomic(settingsFile, JSON.stringify(next, null, 2) + "\n");
    return describeConfig();
  });

  // ----- making cases -----

  const madeCases = result => ({
    cases: Array.isArray(result.cases) ? result.cases.filter(c => typeof c === "string") : [],
    message: typeof result.message === "string" ? result.message : "",
    notes: Array.isArray(result.notes) ? result.notes.filter(n => typeof n === "string") : [],
  });

  ctx.handle("newCase", async input => {
    const given = asObject(input);
    const systems = pickSystems(given.systems, true);
    const batch = intBetween(given.batch, 1, 10, 1);
    return madeCases(await runScript(["common", "--system", systems.join(","), "--batch", String(batch)], 120000 + 60000 * batch));
  });

  ctx.handle("caseReport", async input => {
    const given = asObject(input);
    const systems = pickSystems(given.systems, false);
    const batch = intBetween(given.batch, 1, 10, 1);
    const word = s => s.replace(/["\r\n]/g, " ").trim().replace(/^-+/, "").trim().slice(0, 80);
    const complaints = (typeof given.complaint === "string" ? given.complaint.split(",") : []).map(word).filter(Boolean).slice(0, 8);
    const journal = typeof given.journal === "string" ? word(given.journal) : "";
    if (!systems.length && !complaints.length) throw new Error("Tick at least one system or type a complaint.");
    const args = ["report", "--batch", String(batch)];
    if (systems.length) args.push("--system", systems.join(","));
    if (given.ed === true) args.push("--ed");
    if (journal) args.push(`--journal=${journal}`);
    if (complaints.length) args.push("--complaint", ...complaints);
    return madeCases(await runScript(args, 180000 + 120000 * batch));
  });

  // The frontend copies the opening message itself; this is the fallback for when the page has
  // lost clipboard permission (the case took a while to make).
  ctx.handle("copy", input => new Promise((resolve, reject) => {
    const text = asObject(input).text;
    if (typeof text !== "string" || !text || text.length > 20000) return reject(new Error("Nothing to copy."));
    if (!WIN) return reject(new Error("Clipboard fallback is only available on Windows."));
    const child = spawn(path.join(process.env.SystemRoot || "C:\\Windows", "System32", "clip.exe"), [], { windowsHide: true, stdio: ["pipe", "ignore", "ignore"] });
    child.on("error", reject);
    child.on("close", code => (code === 0 ? resolve({ copied: true }) : reject(new Error("The clipboard couldn't be reached."))));
    child.stdin.end(Buffer.from("\ufeff" + text, "utf16le"));
  }));

  // ----- progress and review -----

  ctx.handle("status", async input => {
    const given = asObject(input);
    const systems = pickSystems(given.systems, true);
    const showTopics = given.showTopics === true;
    const r = await runScript(["status", "--system", systems.join(","), ...(showTopics ? ["--show-topics"] : [])], 60000);
    return {
      topicsTotal: r.topics_total, topicsCovered: r.topics_covered, built: r.built,
      reportsUsed: r.reports_used, ecgsUsed: r.ecgs_used,
      casesFinished: r.cases_finished, casesWaiting: r.cases_waiting,
      encounters: Array.isArray(r.encounters) ? r.encounters : [],
      // The script counts finished cases only unless topic names were asked for, so this mix
      // can't show which system a case that hasn't been run came from.
      step2Mix: Array.isArray(r.step2_mix) ? r.step2_mix : [],
      step2Scope: r.step2_mix_scope === "all" ? "all" : "finished",
      step2Weighted: r.step2_weighted === true,
      // About the topic lists themselves (duplicate ids, names), never about a case.
      warnings: Array.isArray(r.warnings) ? r.warnings.filter(w => typeof w === "string") : [],
      // Per-system counts and topic names can give away a case that hasn't been run yet, so they
      // leave the backend only when asked for.
      systems: (Array.isArray(r.systems) ? r.systems : []).map(s => ({
        system: s.system, missing: s.missing || [], unconverted: s.unconverted || [], strays: s.strays || [],
        ...(showTopics ? { topicsTotal: s.topics_total, topicsCovered: s.topics_covered, built: s.built, topics: s.topics || [] } : {}),
      })),
    };
  });

  ctx.handle("review", async input => {
    const given = asObject(input);
    const systems = pickSystems(given.systems, false);
    const all = listSystems();
    const args = ["review", "--last", String(intBetween(given.last, 1, 500, 40))];
    if (systems.length && systems.length < all.length) args.push("--system", systems.join(","));
    const r = await runScript(args, 60000);
    return { finished: r.finished || 0, topics: r.topics || [], weakSpots: r.weak_spots || [], recent: r.recent || [] };
  });

  // ----- guideline conversion (slow, so it runs as a job and reports when done) -----

  let prepare = { running: false };
  const prepareState = () => ({ ...prepare });

  ctx.handle("prepareState", () => prepareState());
  ctx.handle("prepareStart", input => {
    if (prepare.running) return prepareState();
    const given = asObject(input);
    const systems = pickSystems(given.systems, true);
    prepare = { running: true, systems, started: new Date().toISOString() };
    runScript(["prepare", "--system", systems.join(","), ...(given.force === true ? ["--force"] : [])], 45 * 60000)
      .then(
        r => { prepare = { running: false, systems, converted: r.converted || 0, files: r.files || [], notes: r.notes || [] }; },
        e => { prepare = { running: false, systems, error: e instanceof Error ? e.message : String(e) }; },
      )
      .then(() => { if (!ctx.signal.aborted) ctx.events.emit("prepare", prepareState()); });
    return prepareState();
  });

  // ----- the mix: scenarios.json -----

  const scenariosFile = () => path.join(casesFolder(), "scenarios.json");
  const readScenariosFile = () => {
    const file = scenariosFile();
    if (!isFile(file)) return null;
    let parsed;
    try { parsed = JSON.parse(fs.readFileSync(file, "utf8").replace(/^\uFEFF/, "")); } catch (e) {
      throw new Error(`scenarios.json is not valid JSON (${e.message}). A missing comma or quote is the usual cause. Fix it in Notepad, then reload.`);
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("scenarios.json should contain one object with 'encounters', 'extras' and 'review'.");
    return parsed;
  };
  const section = (source, defaults) => {
    const out = { ...defaults };
    for (const k of publicKeys(source)) out[k] = source[k];
    return out;
  };

  ctx.handle("getScenarios", () => {
    const file = readScenariosFile();
    const encounters = file && publicKeys(file.encounters).length ? section(file.encounters, {}) : { ...DEFAULT_SCENARIOS.encounters };
    const extras = section(file && file.extras, DEFAULT_SCENARIOS.extras);
    const review = section(file && file.review, DEFAULT_SCENARIOS.review);
    const tiers = section(file && file.tiers, DEFAULT_SCENARIOS.tiers);
    const step2 = section(file && file.step2_systems, DEFAULT_SCENARIOS.step2_systems);
    const rows = o => Object.keys(o).map(key => ({ key, label: labelOf(key), value: o[key] }));
    return {
      exists: !!file,
      encounters: rows(encounters),
      extras: rows(extras),
      review: { weak_below: review.weak_below, after_days: review.after_days, order: review.order },
      tiers: rows(tiers),
      step2_systems: rows(step2),
    };
  });

  // Same rules as load_scenarios() in pick_case.py. Keys starting with "_" (the _how_to_edit note)
  // and anything else already in the file are kept as they are.
  ctx.handle("saveScenarios", input => {
    const given = asObject(input);
    const numbers = (source, what, check, rule) => {
      const out = {};
      for (const [key, value] of Object.entries(asObject(source))) {
        if (!SETTING_KEY.test(key)) throw new Error(`'${key}' is not a valid ${what} name.`);
        if (!isNumber(value) || !check(value)) throw new Error(`${labelOf(key)}: ${rule}`);
        out[key] = value;
      }
      return out;
    };
    const encounters = numbers(given.encounters, "encounter", v => v >= 0, "the weight must be 0 or more.");
    if (!Object.values(encounters).some(v => v > 0)) throw new Error("At least one encounter needs a weight above 0.");
    const extras = numbers(given.extras, "extra", v => v >= 0 && v <= 1, "the chance must be between 0 and 1.");
    const review = asObject(given.review);
    if (!isNumber(review.weak_below) || review.weak_below < 0 || review.weak_below > 1) throw new Error("'Weak below' must be between 0 and 1.");
    if (!isNumber(review.after_days) || review.after_days < 0) throw new Error("'Review after days' must be 0 or more.");
    if (!ORDERS.includes(review.order)) throw new Error("The order must be unseen_first or review_first.");
    const tiers = numbers(given.tiers, "tier", v => v > 0, "the weight must be above 0.");
    const step2 = numbers(given.step2_systems, "Step 2 system", v => v >= 0, "the weight must be 0 or more.");

    const next = readScenariosFile() || {};
    next.encounters = { ...asObject(next.encounters), ...encounters };
    next.extras = { ...asObject(next.extras), ...extras };
    next.review = { ...asObject(next.review), weak_below: review.weak_below, after_days: review.after_days, order: review.order };
    if (Object.keys(tiers).length) next.tiers = { ...asObject(next.tiers), ...tiers };
    if (Object.keys(step2).length) next.step2_systems = { ...asObject(next.step2_systems), ...step2 };
    writeFileAtomic(scenariosFile(), JSON.stringify(next, null, 2) + "\n");
    return { saved: true };
  });
}
