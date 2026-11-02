// Figure editor backend for the static web build: the same Python package runs
// in the visitor's browser (Pyodide in a Web Worker). Nothing leaves the device.

const worker = new Worker(new URL("./py-worker.mjs", import.meta.url), { type: "module" });
const pending = new Map();
let seq = 0;
let lastStatus = "";
let onStatus = null;
let markReady, markFailed;
const ready = new Promise((resolve, reject) => { markReady = resolve; markFailed = reject; });

worker.onmessage = ({ data }) => {
  if ("status" in data) {
    lastStatus = data.status; onStatus?.(data.status);
    if (data.ready) markReady();
    if (data.failed) markFailed(new Error(data.status));
    return;
  }
  const { resolve, reject } = pending.get(data.id); pending.delete(data.id);
  const reply = data.reply;
  if (!reply.ok) reject(Object.assign(new Error(reply.error.message_de || reply.error.reason), reply.error));
  else resolve(data.bytes ? new Blob([data.bytes], { type: reply.content_type }) : reply.data);
};

function api(path, body, _binary, bytes = null) {
  return new Promise((resolve, reject) => {
    const id = ++seq; pending.set(id, { resolve, reject });
    worker.postMessage({ id, path, body, bytes }, bytes ? [bytes] : []);
  });
}

// 3D model upload: the file bytes are handed to the worker, never sent anywhere.
async function mesh(file, options) {
  return api("/api/figure/mesh", options, false, await file.arrayBuffer());
}

export const backend = {
  name: "browser", ready, api, mesh,
  onStatus(callback) { onStatus = callback; if (lastStatus) callback(lastStatus); },
};
