// Figure editor backend for the local prototype server. The static web build
// replaces this file with web/backend.mjs, which runs the same Python in the
// browser instead.

let csrf = null;

async function token() {
  if (csrf === null) csrf = (await call("/api/bootstrap")).csrf_token;
  return csrf;
}

async function call(path, body, binary = false) {
  const options = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": await token() },
    body: JSON.stringify(body),
  };
  const response = await fetch(path, { ...options, credentials: "same-origin", cache: "no-store" });
  if (binary && response.ok) return response.blob();
  const data = await response.json();
  if (!data.ok) throw Object.assign(new Error(data.error.message_de || data.error.reason), data.error);
  return data.data;
}

// 3D model upload: the file goes as raw bytes, the options as a header.
async function mesh(file, options) {
  const response = await fetch("/api/figure/mesh", {
    method: "POST", body: file, credentials: "same-origin", cache: "no-store",
    headers: { "Content-Type": "application/octet-stream", "X-CSRF-Token": await token(),
      "X-Mesh-Options": encodeURIComponent(JSON.stringify(options)) },
  });
  const data = await response.json();
  if (!data.ok) throw Object.assign(new Error(data.error.message_de || data.error.reason), data.error);
  return data.data;
}

export const backend = { name: "server", ready: Promise.resolve(), api: call, mesh };
