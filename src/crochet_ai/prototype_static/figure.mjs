// Figure editor: edits a FigureSpec, solves it live on the local server and
// shows a schematic stitch-point preview. All results are NOT_VERIFIED/UNTESTED.

const $ = id => document.getElementById(id);
const STORE_KEY = "crochet.figure.spec.v1";
let csrf = "";
let meta = { shapes: [], templates: [] };
let spec = null;
let result = null;
let selectedPart = null;
let solveTimer = 0;
let solveSeq = 0;

const END_LABEL = { closed: "geschlossen", open: "offen (zum Annähen)", flat: "flach geschlossen" };
const STUFF_LABEL = { "": "automatisch", full: "fest", light: "leicht", none: "keine" };

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== undefined && value !== null) node.setAttribute(key, value);
  }
  for (const child of children) if (child !== null && child !== undefined) node.append(child);
  return node;
}

async function api(path, body, binary = false) {
  const options = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: JSON.stringify(body),
  };
  const response = await fetch(path, { ...options, credentials: "same-origin", cache: "no-store" });
  if (binary && response.ok) return response.blob();
  const data = await response.json();
  if (!data.ok) throw Object.assign(new Error(data.error.message_de || data.error.reason), data.error);
  return data.data;
}

function saveLocal() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(spec)); } catch { /* optional */ }
}

function loadLocal() {
  try { const raw = localStorage.getItem(STORE_KEY); return raw ? JSON.parse(raw) : null; } catch { return null; }
}

// ------------------------------------------------------------- form editing

function field(label, input) { return el("label", {}, label, input); }

function numberInput(value, onChange, { min, max, step = 1 } = {}) {
  return el("input", { type: "number", value, min, max, step, oninput: e => {
    const v = parseFloat(e.target.value); if (Number.isFinite(v)) onChange(v);
  } });
}

function textInput(value, onChange, max = 40) {
  return el("input", { value, maxlength: max, oninput: e => onChange(e.target.value) });
}

function select(options, value, onChange) {
  const node = el("select", { onchange: e => onChange(e.target.value) });
  for (const [key, label] of options) node.append(el("option", { value: key, text: label }));
  node.value = value;
  return node;
}

function colorOptions() { return spec.colors.map(c => [c.id, c.label]); }

function uniqueId(base, taken) {
  let id = base; let i = 2;
  while (taken.has(id)) id = `${base}${i++}`;
  return id;
}

function renderForm() {
  $("name").value = spec.name;
  $("g-stitches").value = spec.gauge.stitches_per_100mm;
  $("g-rows").value = spec.gauge.rows_per_100mm;
  $("g-hook").value = spec.gauge.hook_mm ?? 3;
  $("g-yarn").value = spec.gauge.yarn ?? "";
  renderColors(); renderParts(); renderFeatures(); renderJson();
}

function renderColors() {
  const box = $("colors"); box.replaceChildren();
  spec.colors.forEach((color, index) => {
    box.append(el("div", { class: "color-line" },
      el("input", { type: "color", value: color.hex, "aria-label": `Farbe ${color.label}`,
        oninput: e => { color.hex = e.target.value.toUpperCase(); changed(false); } }),
      textInput(color.label, v => { color.label = v; changed(false); }),
      el("button", { type: "button", class: "icon-btn", text: "×", "aria-label": "Farbe entfernen",
        disabled: spec.colors.length < 2 ? "" : null,
        onclick: () => { spec.colors.splice(index, 1); changed(true); } })));
  });
}

function renderParts() {
  const box = $("parts"); box.replaceChildren();
  spec.parts.forEach((part, index) => {
    const shape = meta.shapes.find(s => s.id === part.shape) || meta.shapes[0];
    const ends = shape.ends.map(e => [e, END_LABEL[e]]);
    if (!shape.ends.includes(part.end ?? shape.ends[0])) part.end = shape.ends[0];
    const card = el("div", { class: "card" },
      el("div", { class: "card-head" }, el("strong", { text: `${index + 1}. ${part.label}` }),
        index === 0 ? el("span", { class: "small-note", text: "Grundkörper" }) :
          el("button", { type: "button", class: "icon-btn", text: "Entfernen", onclick: () => removePart(index) })),
      el("div", { class: "field-row" },
        field("Name", textInput(part.label, v => { part.label = v; changed(false); })),
        field("Form", select(meta.shapes.map(s => [s.id, s.label_de]), part.shape, v => {
          part.shape = v; const s = meta.shapes.find(x => x.id === v); part.end = s.ends[0]; changed(true);
        }))),
      el("div", { class: "field-row" },
        field(part.circumference_mm !== undefined ? "Umfang (mm)" : "Breite Ø (mm)",
          numberInput(part.circumference_mm ?? part.width_mm, v => {
            if (part.circumference_mm !== undefined) part.circumference_mm = v; else part.width_mm = v; changed(false);
          }, { min: 4, max: 950 })),
        field("Höhe (mm)", numberInput(part.height_mm, v => { part.height_mm = v; changed(false); }, { min: 3, max: 400 }))),
      el("div", { class: "field-row" },
        field("Ende", select(ends, part.end, v => { part.end = v; changed(false); })),
        field("Farbe", select(colorOptions(), part.color, v => { part.color = v; changed(false); })),
        field("Füllung", select(Object.entries(STUFF_LABEL), part.stuffing ?? "", v => {
          if (v) part.stuffing = v; else delete part.stuffing; changed(false);
        }))),
    );
    if (index > 0) {
      const attach = part.attach;
      const hosts = spec.parts.slice(0, index).filter(p => !p.attach || p.attach.angles.length === 1).map(p => [p.id, p.label]);
      card.append(el("div", { class: "field-row" },
        field("Annähen an", select(hosts, attach.to, v => { attach.to = v; changed(false); })),
        field(`Höhe auf Teil (${Math.round(attach.at * 100)} %)`, el("input", { type: "range", min: 0, max: 100, step: 1,
          value: Math.round(attach.at * 100), oninput: e => {
            attach.at = Number(e.target.value) / 100;
            e.target.parentElement.firstChild.textContent = `Höhe auf Teil (${e.target.value} %)`;
            changed(false);
          } }))),
        el("div", { class: "field-row" },
          field("Winkel (°, je Exemplar)", textInput(attach.angles.join(", "), v => {
            const values = v.split(/[,;\s]+/).filter(Boolean).map(Number);
            if (values.length && values.every(Number.isFinite)) { attach.angles = values; changed(false); }
          }, 60)),
          field("Neigung nach unten (°)", numberInput(attach.tilt ?? 0, v => { attach.tilt = v; changed(false); }, { min: -85, max: 85 }))),
        el("p", { class: "small-note", text: "Höhe: 0 % = Fadenring, 100 % = letzte Runde. Winkel: 0 = vorne, 90 = rechts, 180 = hinten, 270 = links. Mehrere Winkel = mehrere Exemplare (z. B. 80, 280 für zwei Arme)." }));
    }
    box.append(card);
  });
}

function renderFeatures() {
  const box = $("features"); box.replaceChildren();
  (spec.features ?? []).forEach((feature, index) => {
    const hosts = spec.parts.filter(p => !p.attach || p.attach.angles.length === 1).map(p => [p.id, p.label]);
    box.append(el("div", { class: "card" },
      el("div", { class: "card-head" }, el("strong", { text: feature.type === "eye" ? "Sicherheitsaugen" : "Nase (gestickt)" }),
        el("button", { type: "button", class: "icon-btn", text: "Entfernen", onclick: () => { spec.features.splice(index, 1); changed(true); } })),
      el("div", { class: "field-row" },
        field("Typ", select([["eye", "Augen"], ["nose", "Nase"]], feature.type, v => { feature.type = v; changed(true); })),
        field("auf Teil", select(hosts, feature.on, v => { feature.on = v; changed(false); })),
        field("Farbe", select(colorOptions(), feature.color, v => { feature.color = v; changed(false); }))),
      el("div", { class: "field-row" },
        field("Höhe (%)", numberInput(Math.round(feature.at * 100), v => { feature.at = Math.min(1, Math.max(0, v / 100)); changed(false); }, { min: 0, max: 100 })),
        field("Winkel (°)", textInput(feature.angles.join(", "), v => {
          const values = v.split(/[,;\s]+/).filter(Boolean).map(Number);
          if (values.length && values.every(Number.isFinite)) { feature.angles = values; changed(false); }
        }, 40)),
        field("Größe (mm)", numberInput(feature.size_mm, v => { feature.size_mm = v; changed(false); }, { min: 2, max: 40 })))));
  });
}

function renderJson() { $("json").value = JSON.stringify(spec, null, 2); }

function removePart(index) {
  const removed = spec.parts[index].id;
  const doomed = new Set([removed]);
  // Remove dependants transitively so the spec stays consistent.
  for (const part of spec.parts) if (part.attach && doomed.has(part.attach.to)) doomed.add(part.id);
  spec.parts = spec.parts.filter(p => !doomed.has(p.id));
  spec.features = (spec.features ?? []).filter(f => !doomed.has(f.on));
  changed(true);
}

function changed(rerenderForm) {
  if (rerenderForm) { renderParts(); renderFeatures(); renderColors(); }
  renderJson(); saveLocal(); scheduleSolve();
}

// ------------------------------------------------------------- solving

function scheduleSolve() {
  clearTimeout(solveTimer);
  solveTimer = setTimeout(solve, 350);
}

async function solve() {
  const seq = ++solveSeq;
  try {
    const data = await api("/api/figure/solve", { spec });
    if (seq !== solveSeq) return;
    result = data;
    $("error").hidden = true;
    renderResult();
  } catch (error) {
    if (seq !== solveSeq) return;
    $("error").hidden = false;
    $("error").textContent = error.message || String(error);
  }
}

function renderResult() {
  $("figure-title").textContent = result.name;
  const height = result.bounds_mm.max[1] - result.bounds_mm.min[1];
  $("summary").textContent = `${result.parts.length} Teile · ${result.total_stitches} Maschen · ca. ${Math.round(height)} mm hoch (Schema)`;
  const tabs = $("part-tabs"); tabs.replaceChildren();
  if (!result.parts.some(p => p.id === selectedPart)) selectedPart = result.parts[0].id;
  result.parts.forEach(part => {
    const color = result.colors.find(c => c.id === part.color);
    tabs.append(el("button", { type: "button", "aria-pressed": String(part.id === selectedPart),
      onclick: () => { selectedPart = part.id; renderResult(); },
      onmouseenter: () => viewer.highlight(result.parts.indexOf(part)),
      onmouseleave: () => viewer.highlight(-1) },
      el("span", { class: "swatch", style: `background:${color.hex}` }),
      `${part.label}${part.instances > 1 ? ` ×${part.instances}` : ""}`));
  });
  const part = result.parts.find(p => p.id === selectedPart);
  const colors = Object.fromEntries(result.colors.map(c => [c.id, c]));
  const list = el("ol", { class: "rounds" });
  for (const row of part.rows) {
    for (const note of row.notes) list.append(el("li", { class: "note", text: note }));
    list.append(el("li", {}, el("span", { class: "swatch", style: `background:${colors[row.color].hex}` }), row.text_de));
  }
  list.append(el("li", { text: part.finish_de }));
  $("part-detail").replaceChildren(...[
    el("p", { class: "part-meta", text: `${part.round_count} Runden · max. ${part.max_stitches} Maschen · Ø nach Maschenzahl ca. ${part.predicted_width_mm} mm · Ende: ${END_LABEL[part.end]}` }),
    part.note ? el("p", { class: "small-note", text: part.note }) : null,
    list].filter(Boolean));
  const steps = $("assembly"); steps.replaceChildren();
  for (const step of [...result.features, ...result.assembly]) steps.append(el("li", { text: step.text_de }));
  viewer.setResult(result);
}

// ------------------------------------------------------------- viewer

class FigureViewer {
  constructor(canvas) {
    this.canvas = canvas; this.ctx = canvas.getContext("2d");
    this.yaw = -0.5; this.pitch = 0.18; this.zoom = 1; this.focus = -1; this.result = null;
    new ResizeObserver(() => this.draw()).observe(canvas);
    canvas.addEventListener("pointerdown", e => { this.drag = { x: e.clientX, y: e.clientY }; canvas.setPointerCapture(e.pointerId); });
    canvas.addEventListener("pointermove", e => {
      if (!this.drag) return;
      this.yaw += (e.clientX - this.drag.x) * 0.01;
      this.pitch = Math.max(-1.3, Math.min(1.3, this.pitch + (e.clientY - this.drag.y) * 0.01));
      this.drag = { x: e.clientX, y: e.clientY }; this.draw();
    });
    canvas.addEventListener("pointerup", () => { this.drag = null; });
    canvas.addEventListener("dblclick", () => { this.yaw = -0.5; this.pitch = 0.18; this.zoom = 1; this.draw(); });
    canvas.addEventListener("wheel", e => { e.preventDefault(); this.zoom = Math.max(0.4, Math.min(4, this.zoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1))); this.draw(); }, { passive: false });
    canvas.addEventListener("keydown", e => {
      const step = { ArrowLeft: [-0.15, 0], ArrowRight: [0.15, 0], ArrowUp: [0, 0.1], ArrowDown: [0, -0.1] }[e.key];
      if (step) { this.yaw += step[0]; this.pitch += step[1]; this.draw(); e.preventDefault(); }
    });
  }
  setResult(result) { this.result = result; this.draw(); }
  highlight(index) { this.focus = index; this.draw(); }
  draw() {
    const { canvas, ctx } = this;
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth; const height = canvas.clientHeight;
    canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, width, height);
    if (!this.result) return;
    const { min, max } = this.result.bounds_mm;
    const center = [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2];
    const extent = Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2], 1);
    const scale = Math.min(width, height) / extent * 0.82 * this.zoom;
    const cy = Math.cos(this.yaw), sy = Math.sin(this.yaw), cp = Math.cos(this.pitch), sp = Math.sin(this.pitch);
    const palette = this.result.colors.map(c => [parseInt(c.hex.slice(1, 3), 16), parseInt(c.hex.slice(3, 5), 16), parseInt(c.hex.slice(5, 7), 16)]);
    const projected = this.result.preview.points.map(p => {
      const x = p[0] - center[0], y = p[1] - center[1], z = p[2] - center[2];
      const x1 = x * cy + z * sy, z1 = -x * sy + z * cy;
      const y2 = y * cp - z1 * sp, z2 = y * sp + z1 * cp;
      return [width / 2 + x1 * scale, height / 2 - y2 * scale, z2, p];
    }).sort((a, b) => a[2] - b[2]);
    for (const [sx, sy2, depth, p] of projected) {
      const shade = 0.62 + 0.38 * Math.max(0, Math.min(1, (depth / extent) + 0.5));
      const [r, g, b] = palette[p[3]];
      const dim = this.focus >= 0 && p[4] !== this.focus && p[4] !== -1;
      ctx.fillStyle = `rgba(${Math.round(r * shade)},${Math.round(g * shade)},${Math.round(b * shade)},${dim ? 0.18 : 1})`;
      ctx.beginPath(); ctx.arc(sx, sy2, Math.max(1.2, p[6] * scale * 1.15), 0, Math.PI * 2); ctx.fill();
    }
  }
}

const viewer = new FigureViewer($("figure-canvas"));

// ------------------------------------------------------------- downloads

async function download(path, filename, type) {
  try {
    const blob = await api(path, { spec }, true);
    if (!(blob instanceof Blob)) throw new Error("Download fehlgeschlagen.");
    const url = URL.createObjectURL(type ? new Blob([blob], { type }) : blob);
    const link = el("a", { href: url, download: filename }); document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  } catch (error) {
    $("error").hidden = false; $("error").textContent = error.message || String(error);
  }
}

async function verify() {
  const box = $("verify-result"); const button = $("verify");
  box.hidden = false; button.disabled = true;
  box.textContent = "Prüfe jedes Teil als CrochetIR mit dem unabhängigen Validator … (kann einige Sekunden dauern)";
  try {
    const data = await api("/api/figure/verify", { spec });
    const passed = data.parts.filter(p => p.status === "PASS").length;
    box.replaceChildren(
      el("strong", { text: `Strukturprüfung: ${passed} von ${data.parts.length} Teilen bestanden. ` }),
      "Jede Masche, Einstichstelle, jeder Farbwechsel und jede Öffnung wurde unabhängig nachgerechnet. Form und Größe sind damit noch nicht bestätigt.",
      ...data.parts.filter(p => p.status !== "PASS").map(p => el("div", { text: `✗ ${p.label}: ${p.reason}` })));
  } catch (error) {
    box.textContent = `Prüfung fehlgeschlagen: ${error.message}`;
  } finally { button.disabled = false; }
}

function slug() { return (spec.name || "figur").toLowerCase().replace(/[^a-z0-9äöüß]+/g, "-").replace(/^-|-$/g, "") || "figur"; }

// ------------------------------------------------------------- bootstrap

function loadTemplate(id) {
  const template = meta.templates.find(t => t.id === id);
  spec = structuredClone(template.spec);
  if (!spec.features) spec.features = [];
  renderForm(); saveLocal(); solve();
}

async function start() {
  const boot = await api("/api/bootstrap");
  csrf = boot.csrf_token;
  meta = await api("/api/figure/templates");
  const picker = $("template");
  for (const t of meta.templates) picker.append(el("option", { value: t.id, text: t.name }));
  picker.append(el("option", { value: "", text: "— eigene (gespeichert) —" }));
  picker.addEventListener("change", e => { if (e.target.value) loadTemplate(e.target.value); });
  $("name").addEventListener("input", e => { spec.name = e.target.value; changed(false); });
  const gauge = (id, key) => $(id).addEventListener("input", e => {
    const v = parseFloat(e.target.value); if (Number.isFinite(v)) { spec.gauge[key] = v; changed(false); }
  });
  gauge("g-stitches", "stitches_per_100mm"); gauge("g-rows", "rows_per_100mm"); gauge("g-hook", "hook_mm");
  $("g-yarn").addEventListener("input", e => { spec.gauge.yarn = e.target.value; changed(false); });
  $("add-color").addEventListener("click", () => {
    const id = uniqueId("farbe", new Set(spec.colors.map(c => c.id)));
    spec.colors.push({ id, label: "Neue Farbe", hex: "#7A8FA6" }); changed(true);
  });
  $("add-part").addEventListener("click", () => {
    const id = uniqueId("teil", new Set(spec.parts.map(p => p.id)));
    spec.parts.push({ id, label: "Neues Teil", shape: "sphere", width_mm: 20, height_mm: 20, color: spec.colors[0].id,
      attach: { to: spec.parts[0].id, at: 0.5, angles: [0] } });
    changed(true);
  });
  $("add-feature").addEventListener("click", () => {
    spec.features = spec.features ?? [];
    spec.features.push({ type: "eye", on: spec.parts[spec.parts.length > 1 ? 1 : 0].id, at: 0.5, angles: [25, 335], size_mm: 8,
      color: spec.colors[spec.colors.length - 1].id });
    changed(true);
  });
  $("apply-json").addEventListener("click", () => {
    try { spec = JSON.parse($("json").value); if (!spec.features) spec.features = []; renderForm(); saveLocal(); solve(); }
    catch (error) { $("error").hidden = false; $("error").textContent = `JSON ungültig: ${error.message}`; }
  });
  $("verify").addEventListener("click", verify);
  $("download-pdf").addEventListener("click", async () => {
    const button = $("download-pdf"); button.disabled = true; button.textContent = "PDF wird geprüft und erstellt …";
    try { await download("/api/figure/pdf", `${slug()}.pdf`); }
    finally { button.disabled = false; button.textContent = "Anleitung als PDF"; }
  });
  $("download-text").addEventListener("click", () => download("/api/figure/text", `${slug()}.txt`, "text/plain;charset=utf-8"));
  const saved = loadLocal();
  if (saved && saved.parts) { spec = saved; picker.value = ""; if (!spec.features) spec.features = []; renderForm(); solve(); }
  else loadTemplate(meta.templates[0].id);
}

start().catch(error => { $("error").hidden = false; $("error").textContent = `Start fehlgeschlagen: ${error.message}`; });
