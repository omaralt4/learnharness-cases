// Rounds tools for LearnHarness practice sessions.
//
// show_case_image  shows a case's image (an ECG, a film) inline. Reads only image files named
//                  case_*.png/.jpg/.jpeg inside a folder named "cases", up to 8 MB.
// log_case_result  appends one line per finished case to case_log.jsonl in the folder that
//                  contains "cases". It writes nothing else, anywhere.
const fs = require("fs");
const path = require("path");

const MAX_BYTES = 8 * 1024 * 1024;
const TYPES = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg" };
const IMAGE_NAME = /^case_[A-Za-z0-9_-]+\.(png|jpe?g)$/i;
const CASE_NAME = /^case_[A-Za-z0-9_-]+\.md$/i;
const VERDICTS = ["correct", "partial", "wrong"];

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
      "Two rounds tools are available. show_case_image: when a case file attaches an image (an ECG, a film) and the " +
      "learner orders that test, call it with the image's path exactly as the case file gives it; the learner sees the " +
      "image inline, so do not also print the path, describe it or interpret it. If it fails, give the path as inline code. " +
      "log_case_result: call it exactly once per case, as the very last step after the case has closed (after the " +
      "one-liner, any exam-style questions and retests), with the case file's path from the opening message.",
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
    ],
  });
};
