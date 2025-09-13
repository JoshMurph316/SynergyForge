// src/App.tsx
import { useEffect, useState } from "react";
import { ensureAppToken, getTraits, getCharacters } from "./lib/msf";
import type { Trait, CharacterList } from "./types/msf";

export default function App() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [traits, setTraits] = useState<Trait[]>([]);
  const [charCount, setCharCount] = useState<number>(0);
  const [status, setStatus] = useState<string>("Checking…");

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      setStatus("Refreshing token…");
      await ensureAppToken();
      setStatus("Fetching MSF data…");
      const [traitsResp, characters] = await Promise.all([
        getTraits(),
        getCharacters(),
      ]);
      setTraits(Array.isArray(traitsResp) ? traitsResp : traitsResp.items ?? []);
      const n = Array.isArray(characters)
        ? characters.length
        : ((characters as CharacterList).items?.length ?? 0);
      setCharCount(n);
      setStatus("Ready");
    })()
      .catch((err) => {
        setError(err?.message ?? String(err));
        setStatus("Error");
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ padding: 16, fontFamily: "system-ui, sans-serif" }}>
      <h1>SynergyForge</h1>
      <div style={{ fontSize: 12, color: "#666", marginBottom: 8 }}>MSF status: {status}</div>
      {loading && <p>Loading MSF data…</p>}
      {error && (
        <p style={{ color: "#c00" }}>
          Error: {error}
        </p>
      )}
      {!loading && !error && (
        <>
          <p>Characters loaded: {charCount}</p>
          <h3>Traits</h3>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {traits.slice(0, 12).map((t) => (
              <span
                key={t.id}
                style={{
                  padding: "4px 8px",
                  background: "#eef",
                  border: "1px solid #ccd",
                  borderRadius: 12,
                  fontSize: 12,
                }}
                title={t.description ?? t.name}
              >
                {t.name}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
