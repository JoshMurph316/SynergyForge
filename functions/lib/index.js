"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.datasets = exports.tokenDebug = exports.syncGameRef = exports.whoami = exports.msfProxy = exports.oauthClientCreds = void 0;
const https_1 = require("firebase-functions/v2/https");
const params_1 = require("firebase-functions/params");
const logger = __importStar(require("firebase-functions/logger"));
const node_buffer_1 = require("node:buffer");
const app_1 = require("firebase-admin/app");
const firestore_1 = require("firebase-admin/firestore");
const storage_1 = require("firebase-admin/storage");
(0, app_1.initializeApp)();
// Params
const MSF_CLIENT_ID = (0, params_1.defineString)("MSF_CLIENT_ID");
const MSF_CLIENT_SECRET = (0, params_1.defineString)("MSF_CLIENT_SECRET");
const MSF_TOKEN_URL = (0, params_1.defineString)("MSF_TOKEN_URL");
const MSF_API_BASE = (0, params_1.defineString)("MSF_API_BASE");
const MSF_X_API_KEY = (0, params_1.defineString)("MSF_X_API_KEY");
// Helpers
function getCookie(req, name) {
    var _a, _b;
    const raw = (_b = (_a = req.headers) === null || _a === void 0 ? void 0 : _a.cookie) !== null && _b !== void 0 ? _b : "";
    for (const part of raw.split(/;\s*/)) {
        const [k, v] = part.split("=");
        if (k === name)
            return decodeURIComponent(v !== null && v !== void 0 ? v : "");
    }
    return null;
}
function secureCookie() {
    return process.env.FUNCTIONS_EMULATOR ? "" : " Secure;";
}
async function fetchJSON(path, headers) {
    const url = `${MSF_API_BASE.value().replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
    const r = await fetch(url, { headers });
    if (!r.ok)
        throw new Error(`${path} -> ${r.status} ${r.statusText}`);
    return r.json();
}
let cachedToken = null;
async function getAppAccessToken() {
    // Serve cached token if still valid (with 60s safety window)
    if (cachedToken && Date.now() < cachedToken.expiresAt - 60000) {
        return { access_token: cachedToken.access_token, expires_in: Math.max(60, Math.floor((cachedToken.expiresAt - Date.now()) / 1000)) };
    }
    const useBasic = Boolean(MSF_CLIENT_ID.value() && MSF_CLIENT_SECRET.value());
    const form = new URLSearchParams({ grant_type: "client_credentials", scope: "openid" });
    const headers = { "Content-Type": "application/x-www-form-urlencoded" };
    if (useBasic) {
        const basic = node_buffer_1.Buffer.from(`${MSF_CLIENT_ID.value()}:${MSF_CLIENT_SECRET.value()}`).toString("base64");
        headers["Authorization"] = `Basic ${basic}`;
    }
    else {
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
    let json;
    try {
        json = JSON.parse(text);
    }
    catch (_a) {
        logger.error("Hydra token parse error", { textStart: text.slice(0, 120) });
        throw new Error("Hydra token parse error");
    }
    if (!(json === null || json === void 0 ? void 0 : json.access_token) || !(json === null || json === void 0 ? void 0 : json.expires_in)) {
        logger.error("Hydra token missing fields", { hasAccess: Boolean(json === null || json === void 0 ? void 0 : json.access_token), hasExpires: Boolean(json === null || json === void 0 ? void 0 : json.expires_in) });
        throw new Error("Hydra token missing fields");
    }
    cachedToken = { access_token: json.access_token, expiresAt: Date.now() + Number(json.expires_in) * 1000 };
    logger.info("Hydra token success", { expires_in: json.expires_in });
    return json;
}
// OAuth (Client Credentials) -> sets msf_at cookie
exports.oauthClientCreds = (0, https_1.onRequest)(async (req, res) => {
    var _a, _b, _c;
    if (req.method !== "POST") {
        res.status(405).send("POST only");
        return;
    }
    try {
        // Validate required params early for clearer errors in dev
        const missing = [];
        if (!MSF_CLIENT_ID.value())
            missing.push("MSF_CLIENT_ID");
        if (!MSF_CLIENT_SECRET.value())
            missing.push("MSF_CLIENT_SECRET");
        if (!MSF_TOKEN_URL.value())
            missing.push("MSF_TOKEN_URL");
        if (missing.length) {
            res.status(400).json({ ok: false, error: `Missing env: ${missing.join(", ")}` });
            return;
        }
        const token = await getAppAccessToken();
        const maxAge = Math.max(60, Math.min((_a = token.expires_in) !== null && _a !== void 0 ? _a : 3300, 3600));
        res.setHeader("Set-Cookie", `msf_at=${encodeURIComponent(token.access_token)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAge};${secureCookie()}`);
        res.status(200).json({ ok: true, expires_in: (_b = token.expires_in) !== null && _b !== void 0 ? _b : 0 });
    }
    catch (e) {
        logger.error("oauthClientCreds error", e);
        res.status(500).json({ ok: false, error: (_c = e.message) !== null && _c !== void 0 ? _c : String(e) });
    }
});
// Proxy to MSF API (requires msf_at cookie)
exports.msfProxy = (0, https_1.onRequest)(async (req, res) => {
    var _a, _b;
    try {
        const path = String((_a = req.query.path) !== null && _a !== void 0 ? _a : "");
        if (!/^game\/v1\//.test(path)) {
            res.status(400).json({ ok: false, error: "path must start with game/v1/..." });
            return;
        }
        const token = getCookie(req, "msf_at");
        if (!token) {
            res.status(401).json({ ok: false, error: "missing msf_at cookie" });
            return;
        }
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
        if (ct)
            res.setHeader("Content-Type", ct);
        res.send(body);
    }
    catch (e) {
        logger.error("msfProxy error", e);
        res.status(500).json({ ok: false, error: (_b = e.message) !== null && _b !== void 0 ? _b : String(e) });
    }
});
// Debug
exports.whoami = (0, https_1.onRequest)((req, res) => {
    const hasToken = Boolean(getCookie(req, "msf_at"));
    res.json({ ok: true, env: "functions", msfTokenCookie: hasToken });
});
// ETL: traits + characters -> GCS + Firestore meta
exports.syncGameRef = (0, https_1.onRequest)({ timeoutSeconds: 180 }, async (_req, res) => {
    var _a, _b, _c, _d, _e, _f;
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
        let allChars = [];
        let perTotal = Infinity;
        while (allChars.length < perTotal) {
            const path = `game/v1/characters?lang=none&traitFormat=id&perPage=${perPage}&page=${page}`;
            const resp = await fetchJSON(path, headers);
            const items = Array.isArray(resp) ? resp : ((_a = resp.items) !== null && _a !== void 0 ? _a : []);
            // Normalize here to keep frontend lean and consistent
            const normalized = items.map((c) => {
                var _a, _b;
                const out = {};
                out.id = String((_a = c.id) !== null && _a !== void 0 ? _a : "");
                out.name = (_b = c.name) !== null && _b !== void 0 ? _b : "";
                if (c.imageUrl)
                    out.imageUrl = String(c.imageUrl);
                out.traits = Array.isArray(c.traits) ? c.traits.map((t) => String(t)) : [];
                if (c.faction)
                    out.faction = String(c.faction);
                if (c.role)
                    out.role = String(c.role);
                if (c.stats && typeof c.stats === "object")
                    out.stats = c.stats;
                return out;
            });
            allChars = allChars.concat(normalized);
            const meta = (_b = resp === null || resp === void 0 ? void 0 : resp.meta) !== null && _b !== void 0 ? _b : {};
            perTotal = (_c = meta.perTotal) !== null && _c !== void 0 ? _c : (items.length < perPage ? allChars.length : allChars.length + perPage);
            if (items.length < perPage)
                break;
            page += 1;
            if (page > 200)
                break; // safety
        }
        const bucket = (0, storage_1.getStorage)().bucket();
        const db = (0, firestore_1.getFirestore)();
        await bucket.file("datasets/traits.json")
            .save(JSON.stringify(traits, null, 2), { contentType: "application/json" });
        await bucket.file("datasets/characters.json")
            .save(JSON.stringify({ items: allChars, meta: { perTotal: allChars.length, perPage, page } }, null, 2), { contentType: "application/json" });
        const traitsCount = Array.isArray(traits) ? traits.length : ((_e = (_d = traits.items) === null || _d === void 0 ? void 0 : _d.length) !== null && _e !== void 0 ? _e : 0);
        const charsCount = allChars.length;
        await db.collection("meta").doc("datasets").set({
            updatedAt: firestore_1.Timestamp.now(),
            counts: { traits: traitsCount, characters: charsCount }
        }, { merge: true });
        res.json({
            ok: true,
            written: { traits: "datasets/traits.json", characters: "datasets/characters.json" },
            counts: { traits: traitsCount, characters: charsCount }
        });
    }
    catch (e) {
        logger.error("syncGameRef error", e);
        res.status(500).json({ ok: false, error: (_f = e.message) !== null && _f !== void 0 ? _f : String(e) });
    }
});
// Local-only debug endpoint to test token retrieval without setting cookies
exports.tokenDebug = (0, https_1.onRequest)(async (_req, res) => {
    var _a;
    if (!process.env.FUNCTIONS_EMULATOR) {
        res.status(404).send("Not found");
        return;
    }
    try {
        const missing = [];
        if (!MSF_CLIENT_ID.value())
            missing.push("MSF_CLIENT_ID");
        if (!MSF_CLIENT_SECRET.value())
            missing.push("MSF_CLIENT_SECRET");
        if (!MSF_TOKEN_URL.value())
            missing.push("MSF_TOKEN_URL");
        if (missing.length) {
            res.status(400).json({ ok: false, error: `Missing env: ${missing.join(", ")}` });
            return;
        }
        const tok = await getAppAccessToken();
        res.json({ ok: true, expires_in: tok.expires_in, token_len: tok.access_token.length });
    }
    catch (e) {
        res.status(500).json({ ok: false, error: (_a = e.message) !== null && _a !== void 0 ? _a : String(e) });
    }
});
// Stream normalized datasets from Storage
exports.datasets = (0, https_1.onRequest)(async (req, res) => {
    var _a;
    try {
        // Accept either /datasets/:name or /datasets?name=...
        const url = new URL(req.url, "http://localhost");
        const pathname = url.pathname || "";
        const m = pathname.match(/\/datasets\/([^/]+)/);
        const raw = ((m === null || m === void 0 ? void 0 : m[1]) || String(req.query.name || "")).toLowerCase();
        const name = raw.replace(/\.(json)?$/, "");
        logger.info("datasets request", { pathname, name });
        if (!name || !(name === "traits" || name === "characters")) {
            res.status(400).json({ ok: false, error: "name must be traits or characters" });
            return;
        }
        const filePath = `datasets/${name}.json`;
        const bucket = (0, storage_1.getStorage)().bucket();
        const bucketName = bucket.name || "<unknown>";
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
    }
    catch (e) {
        logger.error("datasets error", e);
        res.status(500).json({ ok: false, error: (_a = e.message) !== null && _a !== void 0 ? _a : String(e) });
    }
});
//# sourceMappingURL=index.js.map