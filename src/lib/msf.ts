// src/lib/msf.ts
export async function ensureAppToken() {
  const r = await fetch("/api/oauth/client", { method: "POST", credentials: "include" });
  if (!r.ok) throw new Error(`/api/oauth/client -> ${r.status}`);
}

async function call(path: string) {
  const url = `/api/msf?path=${encodeURIComponent(path)}`;
  const r = await fetch(url, { credentials: "include" });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

export const getTraits = () => call("game/v1/traits");
export const getCharacters = () => call("game/v1/characters");
