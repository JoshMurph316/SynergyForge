// src/lib/msf.ts
import type { Trait, CharacterList, MsfList } from "../types/msf";

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

export const getTraits = () => call<Trait[]>("game/v1/traits?lang=none");

type CharOpts = { page?: number; perPage?: number; lang?: string; traitFormat?: "object" | "id" };
export async function getCharacters(opts: CharOpts = {}): Promise<CharacterList> {
  const page = opts.page ?? 1;
  const perPage = opts.perPage ?? 50;
  const lang = opts.lang ?? "none"; // reduce payload size
  const traitFormat = opts.traitFormat ?? "id"; // reduce payload size
  const qs = new URLSearchParams({ page: String(page), perPage: String(perPage), lang, traitFormat });
  const path = `game/v1/characters?${qs.toString()}`;
  return call<CharacterList>(path);
}

export async function getAllCharacters(perPage = 200): Promise<MsfList<any>> {
  const all: any[] = [];
  let page = 1;
  let total = Infinity;
  while (all.length < total) {
    const qs = new URLSearchParams({ page: String(page), perPage: String(perPage), lang: "none", traitFormat: "id" });
    const resp = await call<MsfList<any>>(`game/v1/characters?${qs.toString()}`);
    const items = Array.isArray(resp) ? (resp as any) : (resp.items ?? []);
    all.push(...items);
    const meta = (resp as MsfList<any>).meta;
    total = meta?.perTotal ?? (all.length < perPage ? all.length : all.length + perPage); // fallback
    if (items.length < perPage) break;
    page += 1;
    if (page > 200) break; // safety
  }
  return { items: all, meta: { perTotal: all.length, perPage, page } };
}
