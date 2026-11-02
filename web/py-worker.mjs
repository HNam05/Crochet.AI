// Web Worker that hosts Python (Pyodide) and the crochet_ai package. All files
// are served from this site; there are no calls to other services.

import { loadPyodide } from "./pyodide/pyodide.mjs";

const status = (text, extra = {}) => postMessage({ status: text, ...extra });
const fetchBytes = async path => {
  const response = await fetch(new URL(path, import.meta.url));
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.arrayBuffer();
};

let py = null;
let handle = null;
let commit = "unknown";

const ready = (async () => {
  status("Rechenkern wird geladen …");
  const manifest = await (await fetch(new URL("./manifest.json", import.meta.url))).json();
  commit = manifest.commit;
  py = await loadPyodide({ indexURL: new URL("./pyodide/", import.meta.url).href });
  status("Python-Pakete werden geladen …");
  await py.loadPackage(manifest.pyodide_packages, { messageCallback: () => {} });
  for (const wheel of manifest.wheels) py.unpackArchive(await fetchBytes(`./wheels/${wheel}`), "wheel");
  py.unpackArchive(await fetchBytes("./crochet_ai.zip"), "zip", { extractDir: "/home/pyodide/app" });
  py.runPython("import sys; sys.path.insert(0, '/home/pyodide/app')");
  py.runPython(new TextDecoder().decode(await fetchBytes("./bridge.py")));
  handle = py.globals.get("handle");
  status("", { ready: true });
})().catch(error => status(`Der Rechenkern konnte nicht starten: ${error.message}`, { failed: true }));

onmessage = async ({ data: { id, path, body } }) => {
  try {
    await ready;
    if (!handle) throw new Error("Rechenkern nicht verfügbar.");
    const reply = JSON.parse(handle(path, body === undefined ? "" : JSON.stringify(body), commit));
    let bytes = null;
    if (reply.binary) {
      const proxy = py.globals.get("LAST_BYTES"); const buffer = proxy.getBuffer("u8");
      bytes = buffer.data.slice(); buffer.release(); proxy.destroy();
    }
    postMessage({ id, reply, bytes }, bytes ? [bytes.buffer] : []);
  } catch (error) {
    postMessage({ id, reply: { ok: false, error: { reason: String(error.message || error) } } });
  }
};
