import { onRequest } from "firebase-functions/v2/https";
import { defineString } from "firebase-functions/params";
import * as logger from "firebase-functions/logger";

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

async function getAppAccessToken(): Promise<{ access_token: string; expires_in: number }> {
  const body = new URLSearchParams({
    grant_type: "client_credentials",
    scope: "openid",
    client_id: MSF_CLIENT_ID.value(),
    client_secret: MSF_CLIENT_SECRET.value(),
  });

  const r = await fetch(MSF_TOKEN_URL.value(), {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!r.ok) {
    const err = await r.text();
    throw new Error(`Hydra token error ${r.status}: ${err}`);
  }
  return r.json() as any;
}

// OAuth (Client Credentials) -> sets msf_at cookie
export const oauthClientCreds = onRequest(async (req, res) => {
  if (req.method !== "POST") { res.status(405).send("POST only"); return; }
  try {
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
        "Accept": "application/json"
      }
    });

    logger.info("msfProxy forward", {
      path, status: upstream.status,
      hasXApiKey: Boolean(MSF_X_API_KEY.value()),
      hasToken: Boolean(token),
    });

    const body = await upstream.text();
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

    const [traits, characters] = await Promise.all([
      fetchJSON("game/v1/traits", headers),
      fetchJSON("game/v1/characters", headers),
    ]);

    const bucket = getStorage().bucket();
    const db = getFirestore();

    await bucket.file("datasets/traits.json")
      .save(JSON.stringify(traits, null, 2), { contentType: "application/json" });
    await bucket.file("datasets/characters.json")
      .save(JSON.stringify(characters, null, 2), { contentType: "application/json" });

    const traitsCount = Array.isArray(traits) ? traits.length : (traits.items?.length ?? 0);
    const charsCount  = Array.isArray(characters) ? characters.length : (characters.items?.length ?? 0);

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
