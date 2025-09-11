import { onRequest } from "firebase-functions/v2/https";
import { defineString } from "firebase-functions/params";

// === Existing ===
const MSF_CLIENT_ID     = defineString("MSF_CLIENT_ID");
const MSF_CLIENT_SECRET = defineString("MSF_CLIENT_SECRET");
const MSF_TOKEN_URL     = defineString("MSF_TOKEN_URL");
const MSF_API_BASE      = defineString("MSF_API_BASE");
const MSF_X_API_KEY     = defineString("MSF_X_API_KEY");

function isLocal(req: any) {
  const xfProto = (req.headers["x-forwarded-proto"] || "").toString();
  return xfProto !== "https";
}

function setSessionCookie(req: any, res: any, name: string, value: string, maxAgeSec: number) {
  const sameSite = "Lax";
  const secure   = isLocal(req) ? "" : " Secure;";
  res.setHeader(
    "Set-Cookie",
    `${name}=${value}; HttpOnly; Path=/; SameSite=${sameSite}; Max-Age=${maxAgeSec};${secure}`
  );
}

/** =========================
 * OPTIONAL: Client Credentials
 * Mint an app-only token (like your Postman flow) and set it in the cookie (msf_at).
 * This is perfect while you’re calling non-player endpoints under /game/v1/*.
 * ========================= */
export const oauthClientCreds = onRequest({ cors: true }, async (req, res) => {
  try {
    const form = new URLSearchParams({
      grant_type: "client_credentials",
      scope: "openid",
      client_id: MSF_CLIENT_ID.value(),
    });
    if (MSF_CLIENT_SECRET.value()) form.set("client_secret", MSF_CLIENT_SECRET.value());

    const r = await fetch(MSF_TOKEN_URL.value(), {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
    });
    const data: any = await r.json().catch(() => ({}));
    if (!r.ok) {
      res.status(r.status).json(data);
      return;
    }

    if (data.access_token) {
      setSessionCookie(req, res, "msf_at", data.access_token, Math.max(60, Number(data.expires_in || 1800)));
    }
    // client_credentials doesn’t usually return refresh_token; that’s fine.
    res.json({ ok: true, flow: "client_credentials", expires_in: data.expires_in ?? 0 });
  } catch (e) {
    res.status(500).json({ error: "oauth_client_credentials_failed" });
  }
});

// === Your existing oauthExchange / oauthRefresh remain unchanged ===

// Generic API proxy: forwards to MSF API with Bearer token in cookie
export const msfProxy = onRequest({ cors: true }, async (req, res) => {
  try {
    const cookies = String(req.headers.cookie || "");
    const at = cookies.split(";").map(s => s.trim()).find(s => s.startsWith("msf_at="))?.split("=")[1];
    if (!at) {
      res.status(401).json({ error: "no_access_token" });
      return;
    }

    const path = req.query.path ? String(req.query.path) : "";
    if (!path) {
      res.status(400).json({ error: "missing_path" });
      return;
    }

    const base = MSF_API_BASE.value().replace(/\/+$/, "");
    const dest = path.replace(/^\/+/, "");
    const url = new URL(`${base}/${dest}`);

    Object.entries(req.query).forEach(([k, v]) => {
      if (k !== "path") url.searchParams.set(k, String(v));
    });

    const isBodyMethod = ["POST", "PUT", "PATCH", "DELETE"].includes(req.method);
    const headers: Record<string, string> = {
      // === CRITICAL: add x-api-key ===
      "x-api-key": MSF_X_API_KEY.value(),
      "Authorization": `Bearer ${at}`,
      "Accept": "application/json",
      "User-Agent": "SynergyForge/1.0 (+https://synergyforge.web.app)"
    };
    if (isBodyMethod) {
      headers["Content-Type"] = (req.headers["content-type"] as string) || "application/json";
    }

    const r = await fetch(url.toString(), {
      method: req.method,
      headers,
      body: isBodyMethod ? JSON.stringify(req.body || {}) : undefined,
    });

    const text = await r.text();
    const ct = r.headers.get("content-type") || "application/json";
    res.setHeader("Content-Type", ct);
    res.status(r.status).send(text);
  } catch (e) {
    res.status(500).json({ error: "proxy_failed" });
  }
});
