// src/lib/msf.ts
import type { Trait, CharacterList } from "../types/msf";

type WhoAmI = { ok: boolean; msfTokenCookie?: boolean };

export async function ensureAppToken(): Promise<void> {
  // If already have cookie, skip
  try {
    const w = await fetch("/api/whoami", { credentials: "include" });
    if (w.ok) {
      const info = (await w.json()) as WhoAmI;
      if (info.msfTokenCookie) return;
    }
  } catch {}

  // Obtain/refresh token cookie
  const r = await fetch("/api/oauth/client", { method: "POST", credentials: "include" });
  if (!r.ok) throw new Error(`/api/oauth/client -> ${r.status}`);

  // Verify cookie present
  const w2 = await fetch("/api/whoami", { credentials: "include" });
  if (w2.ok) {
    const info2 = (await w2.json()) as WhoAmI;
    if (info2.msfTokenCookie) return;
  }
  throw new Error("MSF token cookie not set after oauth");
}

async function call<T>(path: string): Promise<T> {
  const url = `/api/msf?path=${encodeURIComponent(path)}`;
  let r = await fetch(url, { credentials: "include" });
  // If unauthorized, try to refresh token then retry once
  if (r.status === 401) {
    await ensureAppToken();
    r = await fetch(url, { credentials: "include" });
  }
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

export const getTraits = () => call<Trait[]>("game/v1/traits");
export const getCharacters = () => call<CharacterList>("game/v1/characters");
