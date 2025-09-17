import { onRequest } from "firebase-functions/v2/https";
import { defineString } from "firebase-functions/params";
import * as logger from "firebase-functions/logger";
import { Buffer } from "node:buffer";

import { initializeApp } from "firebase-admin/app";
import { getFirestore, Timestamp } from "firebase-admin/firestore";
import { getStorage } from "firebase-admin/storage";

initializeApp();

// Params
const MSF_CLIENT_ID = defineString("MSF_CLIENT_ID");
const MSF_CLIENT_SECRET = defineString("MSF_CLIENT_SECRET");
const MSF_TOKEN_URL = defineString("MSF_TOKEN_URL");
const MSF_API_BASE = defineString("MSF_API_BASE");
const MSF_X_API_KEY = defineString("MSF_X_API_KEY");

// Helpers
function getCookie(req: any, name: string): string | null {
  const raw = req.headers?.cookie ?? "";
  for (const part of raw.split(/;\s*/)) {
    const [k, v] = part.split("=");
    if (k === name) return decodeURIComponent(v ?? "");
  }
  return null;
}

function secureCookie(): string {
  return process.env.FUNCTIONS_EMULATOR ? "" : " Secure;";
}

async function fetchJSON(path: string, headers: Record<string, string>) {
  const url = `${MSF_API_BASE.value().replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
  const r = await fetch(url, { headers });
  if (!r.ok) throw new Error(`${path} -> ${r.status} ${r.statusText}`);
  return r.json();
}

let cachedToken: { access_token: string; expiresAt: number } | null = null;
async function getAppAccessToken(): Promise<{ access_token: string; expires_in: number }> {
  // Serve cached token if still valid (with 60s safety window)
  if (cachedToken && Date.now() < cachedToken.expiresAt - 60_000) {
    return { access_token: cachedToken.access_token, expires_in: Math.max(60, Math.floor((cachedToken.expiresAt - Date.now()) / 1000)) };
  }

  const useBasic = Boolean(MSF_CLIENT_ID.value() && MSF_CLIENT_SECRET.value());
  const form = new URLSearchParams({ grant_type: "client_credentials", scope: "openid" });
  const headers: Record<string, string> = { "Content-Type": "application/x-www-form-urlencoded" };
  if (useBasic) {
    const basic = Buffer.from(`${MSF_CLIENT_ID.value()}:${MSF_CLIENT_SECRET.value()}`).toString("base64");
    headers["Authorization"] = `Basic ${basic}`;
  } else {
    // Fallback if Basic is not available; some providers allow this
    form.set("client_id", MSF_CLIENT_ID.value());
    form.set("client_secret", MSF_CLIENT_SECRET.value());
  }

  logger.info("Hydra token request", { url: MSF_TOKEN_URL.value().replace(/https?:\/\//, ""), auth: useBasic ? "basic" : "body" });
  const r = await fetch(MSF_TOKEN_URL.value(), { method: "POST", headers, body: form });
  const text = await r.text();
  if (!r.ok) {
    logger.error("Hydra token error", { status: r.status, statusText: r.statusText, bodyStartsWith: text.slice(0, 80) });
    throw new Error(`Hydra token error ${r.status}`);
  }
  let json: any;
  try { json = JSON.parse(text); } catch {
    logger.error("Hydra token parse error", { textStart: text.slice(0, 120) });
    throw new Error("Hydra token parse error");
  }
  if (!json?.access_token || !json?.expires_in) {
    logger.error("Hydra token missing fields", { hasAccess: Boolean(json?.access_token), hasExpires: Boolean(json?.expires_in) });
    throw new Error("Hydra token missing fields");
  }
  cachedToken = { access_token: json.access_token, expiresAt: Date.now() + Number(json.expires_in) * 1000 };
  logger.info("Hydra token success", { expires_in: json.expires_in });
  return json as { access_token: string; expires_in: number };
}

// OAuth (Client Credentials) -> sets msf_at cookie
export const oauthClientCreds = onRequest(async (req, res) => {
  if (req.method !== "POST") { res.status(405).send("POST only"); return; }
  try {
    // Validate required params early for clearer errors in dev
    const missing: string[] = [];
    if (!MSF_CLIENT_ID.value()) missing.push("MSF_CLIENT_ID");
    if (!MSF_CLIENT_SECRET.value()) missing.push("MSF_CLIENT_SECRET");
    if (!MSF_TOKEN_URL.value()) missing.push("MSF_TOKEN_URL");
    if (missing.length) {
      res.status(400).json({ ok: false, error: `Missing env: ${missing.join(", ")}` });
      return;
    }
    const token = await getAppAccessToken();
    const maxAge = Math.max(60, Math.min(token.expires_in ?? 3300, 3600));
    res.setHeader(
      "Set-Cookie",
      `msf_at=${encodeURIComponent(token.access_token)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAge};${secureCookie()}`
    );
    res.status(200).json({ ok: true, expires_in: token.expires_in ?? 0 });
  } catch (e: any) {
    logger.error("oauthClientCreds error", e);
    res.status(500).json({ ok: false, error: e.message ?? String(e) });
  }
});

// Proxy to MSF API (requires msf_at cookie)
export const msfProxy = onRequest(async (req, res) => {
  try {
    const path = String(req.query.path ?? "");
    if (!/^game\/v1\//.test(path)) {
      res.status(400).json({ ok: false, error: "path must start with game/v1/..." });
      return;
    }

    const token = getCookie(req, "msf_at");
    if (!token) { res.status(401).json({ ok: false, error: "missing msf_at cookie" }); return; }

    const url = `${MSF_API_BASE.value().replace(/\/$/, "")}/${path}`;
    const upstream = await fetch(url, {
      headers: {
        "x-api-key": MSF_X_API_KEY.value(),
        "Authorization": `Bearer ${token}`,
        "User-Agent": "SynergyForge/1.0",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.8"
      }
    });

    logger.info("msfProxy forward", {
      path,
      status: upstream.status,
      statusText: upstream.statusText,
      hasXApiKey: Boolean(MSF_X_API_KEY.value()),
      hasToken: Boolean(token),
      base: MSF_API_BASE.value().replace(/https?:\/\//, ""),
    });

    const body = await upstream.text();
    if (!upstream.ok) {
      logger.error("msfProxy upstream error", {
        path,
        status: upstream.status,
        statusText: upstream.statusText,
        bodyStart: body.slice(0, 200),
      });
    }
    res.status(upstream.status);
    const ct = upstream.headers.get("content-type");
    if (ct) res.setHeader("Content-Type", ct);
    res.send(body);
  } catch (e: any) {
    logger.error("msfProxy error", e);
    res.status(500).json({ ok: false, error: e.message ?? String(e) });
  }
});

// Debug
export const whoami = onRequest((req, res) => {
  const hasToken = Boolean(getCookie(req, "msf_at"));
  res.json({ ok: true, env: "functions", msfTokenCookie: hasToken });
});

// ETL: traits + characters -> GCS + Firestore meta
export const syncGameRef = onRequest({ timeoutSeconds: 180 }, async (_req, res) => {
  try {
    const { access_token } = await getAppAccessToken();
    const headers = {
      "x-api-key": MSF_X_API_KEY.value(),
      "Authorization": `Bearer ${access_token}`,
      "User-Agent": "SynergyForge/1.0",
      "Accept": "application/json"
    };

    // Traits are small; request with lang=none to minimize size
    const traits = await fetchJSON("game/v1/traits?lang=none", headers);

    // Characters require paging; use lang=none & traitFormat=id to minimize size
    const perPage = 200;
    let page = 1;
    let allChars: any[] = [];
    let perTotal = Infinity;
    while (allChars.length < perTotal) {
      const path = `game/v1/characters?lang=none&traitFormat=id&perPage=${perPage}&page=${page}`;
      const resp: any = await fetchJSON(path, headers);
      const items: any[] = Array.isArray(resp) ? resp : (resp.items ?? []);
      // Normalize here to keep frontend lean and consistent
      const normalized = items.map((c: any) => {
        const out: any = {};
        out.id = String(c.id ?? "");
        out.name = c.name ?? "";
        if (c.imageUrl) out.imageUrl = String(c.imageUrl);
        out.traits = Array.isArray(c.traits) ? c.traits.map((t: any) => String(t)) : [];
        if (c.faction) out.faction = String(c.faction);
        if (c.role) out.role = String(c.role);
        if (c.stats && typeof c.stats === "object") out.stats = c.stats;
        return out;
      });
      allChars = allChars.concat(normalized);
      const meta = resp?.meta ?? {};
      perTotal = meta.perTotal ?? (items.length < perPage ? allChars.length : allChars.length + perPage);
      if (items.length < perPage) break;
      page += 1;
      if (page > 200) break; // safety
    }

    const bucket = getStorage().bucket();
    const db = getFirestore();

    await bucket.file("datasets/traits.json")
      .save(JSON.stringify(traits, null, 2), { contentType: "application/json" });
    await bucket.file("datasets/characters.json")
      .save(JSON.stringify({ items: allChars, meta: { perTotal: allChars.length, perPage, page } }, null, 2), { contentType: "application/json" });

    const traitsCount = Array.isArray(traits) ? traits.length : (traits.items?.length ?? 0);
    const charsCount  = allChars.length;

    await db.collection("meta").doc("datasets").set({
      updatedAt: Timestamp.now(),
      counts: { traits: traitsCount, characters: charsCount }
    }, { merge: true });

    res.json({
      ok: true,
      written: { traits: "datasets/traits.json", characters: "datasets/characters.json" },
      counts: { traits: traitsCount, characters: charsCount }
    });
  } catch (e: any) {
    logger.error("syncGameRef error", e);
    res.status(500).json({ ok: false, error: e.message ?? String(e) });
  }
});

// Local-only debug endpoint to test token retrieval without setting cookies
export const tokenDebug = onRequest(async (_req, res) => {
  if (!process.env.FUNCTIONS_EMULATOR) { res.status(404).send("Not found"); return; }
  try {
    const missing: string[] = [];
    if (!MSF_CLIENT_ID.value()) missing.push("MSF_CLIENT_ID");
    if (!MSF_CLIENT_SECRET.value()) missing.push("MSF_CLIENT_SECRET");
    if (!MSF_TOKEN_URL.value()) missing.push("MSF_TOKEN_URL");
    if (missing.length) { res.status(400).json({ ok: false, error: `Missing env: ${missing.join(", ")}` }); return; }
    const tok = await getAppAccessToken();
    res.json({ ok: true, expires_in: tok.expires_in, token_len: tok.access_token.length });
  } catch (e: any) {
    res.status(500).json({ ok: false, error: e.message ?? String(e) });
  }
});

// Stream normalized datasets from Storage
export const datasets = onRequest(async (req, res) => {
  try {
    // Accept either /datasets/:name or /datasets?name=...
    const url = new URL(req.url, "http://localhost");
    const pathname = url.pathname || "";
    const m = pathname.match(/\/datasets\/([^/]+)/);
    const raw = (m?.[1] || String(req.query.name || "")).toLowerCase();
    const name = raw.replace(/\.(json)?$/, "");
    logger.info("datasets request", { pathname, name });
    if (!name || !(name === "traits" || name === "characters")) {
      res.status(400).json({ ok: false, error: "name must be traits or characters" });
      return;
    }
    const filePath = `datasets/${name}.json`;
    const bucket = getStorage().bucket();
    const bucketName = (bucket as any).name || "<unknown>";
    const file = bucket.file(filePath);
    const [exists] = await file.exists();
    logger.info("datasets locate", { bucket: bucketName, filePath, exists });
    if (!exists) {
      res.status(404).json({ ok: false, error: `Not found: gs://${bucketName}/${filePath}` });
      return;
    }
    const [buf] = await file.download();
    res.setHeader("Content-Type", "application/json");
    res.setHeader("Cache-Control", "public, max-age=300");
    res.status(200).send(buf);
  } catch (e: any) {
    logger.error("datasets error", e);
    res.status(500).json({ ok: false, error: e.message ?? String(e) });
  }
});
