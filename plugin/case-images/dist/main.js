// Draws the image returned by show_case_image. Click the image to switch between
// fit-to-width and full size (scroll sideways at full size to follow a rhythm strip).

const text = (doc, tag, value, style) => {
  const el = doc.createElement(tag);
  el.textContent = value;
  if (style) el.setAttribute("style", style);
  return el;
};

export function activate(ctx) {
  ctx.registerToolRenderer({
    toolName: "show_case_image",
    mount(container, tool) {
      const doc = container.ownerDocument;
      const muted = "font-size:12px;opacity:0.7;margin:4px 0;";

      if (tool.state === "output-error") {
        container.append(text(doc, "p", `Couldn't show the image: ${tool.errorText || "unknown error"}`, muted));
        return () => container.replaceChildren();
      }
      const out = tool.output;
      if (tool.state !== "output-available" || !out || typeof out.dataUrl !== "string" || !out.dataUrl.startsWith("data:image/")) {
        container.append(text(doc, "p", "Loading image…", muted));
        return () => container.replaceChildren();
      }

      const frame = doc.createElement("div");
      frame.setAttribute("style", "max-width:100%;overflow-x:auto;border:1px solid rgba(127,127,127,0.3);border-radius:8px;background:#fff;");
      const img = doc.createElement("img");
      img.src = out.dataUrl;
      img.alt = out.caption || "Case image";
      let full = false;
      const fit = () => img.setAttribute("style", `display:block;cursor:${full ? "zoom-out" : "zoom-in"};${full ? "max-width:none;" : "width:100%;height:auto;"}`);
      fit();
      img.addEventListener("click", () => { full = !full; fit(); });
      frame.append(img);

      container.append(frame, text(doc, "p", `${out.caption ? out.caption + " · " : ""}click to zoom`, muted));
      return () => container.replaceChildren();
    },
  });

  ctx.registerToolRenderer({
    toolName: "log_case_result",
    mount(container, tool) {
      const doc = container.ownerDocument;
      const muted = "font-size:12px;opacity:0.7;margin:4px 0;";
      if (tool.state === "output-error") {
        container.append(text(doc, "p", `Couldn't log this case: ${tool.errorText || "unknown error"}`, muted));
        return () => container.replaceChildren();
      }
      const out = tool.output;
      if (tool.state !== "output-available" || !out || !Array.isArray(out.decisions)) {
        container.append(text(doc, "p", "Logging case…", muted));
        return () => container.replaceChildren();
      }
      const box = doc.createElement("div");
      box.setAttribute("style", "border:1px solid var(--border, rgba(127,127,127,0.3));border-radius:8px;padding:10px 12px;font-size:13px;");
      const right = out.decisions.filter(d => d.verdict === "correct").length;
      const part = out.decisions.filter(d => d.verdict === "partial").length;
      let head = `Case logged · ${out.diagnosis || ""} · ${right}/${out.decisions.length} right`;
      if (part) head += `, ${part} partial`;
      if (out.exam_questions) head += ` · questions ${out.exam_questions.correct}/${out.exam_questions.total}`;
      box.append(text(doc, "div", head, "font-weight:600;margin-bottom:6px;"));
      const mark = { correct: "✓", partial: "~", wrong: "✗" };
      const list = doc.createElement("div");
      for (const d of out.decisions) list.append(text(doc, "div", `${mark[d.verdict] || "·"} ${d.point}`, "margin:2px 0;"));
      box.append(list);
      if (Array.isArray(out.weak_spots) && out.weak_spots.length) {
        box.append(text(doc, "div", "Review:", "margin-top:8px;font-weight:600;"));
        for (const w of out.weak_spots) box.append(text(doc, "div", `• ${w}`, "margin:2px 0;"));
      }
      container.append(box);
      return () => container.replaceChildren();
    },
  });

  ctx.registerSettings((container) => {
    container.append(text(container.ownerDocument, "p",
      "Rounds tools for practice sessions. Shows case images (ECGs, films) inline, reading only image files named " +
      "case_*.png or .jpg inside a folder called 'cases'. Logs each finished case to case_log.jsonl in the folder that " +
      "contains 'cases', so the case picker can bring weak topics back. No model calls, no settings."));
    return () => container.replaceChildren();
  });
}
