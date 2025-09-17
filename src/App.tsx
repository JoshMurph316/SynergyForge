// src/App.tsx
import { useEffect, useState } from "react";
import { ensureAppToken, getTraits, getCharacters } from "./lib/msf";
import { loadTraits, loadCharacters } from "./api/datasets";
import type { Trait, Character, MsfList } from "./types/msf";

export default function App() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [traits, setTraits] = useState<Trait[]>([]);
  const traitMap = Object.fromEntries(traits.map(t => [t.id, t.name]));
  const [charCount, setCharCount] = useState<number>(0);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [page, setPage] = useState(1);
  const perPage = 50;
  const [status, setStatus] = useState<string>("Checking…");

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      setStatus("Refreshing token…");
      await ensureAppToken();
      setStatus("Fetching MSF data…");
      // Prefer prebuilt datasets if available; fallback to live API
      try {
        const traitsData = await loadTraits();
        setTraits(traitsData);
      } catch {
        const traitsResp = await getTraits();
        setTraits(Array.isArray(traitsResp) ? traitsResp : traitsResp.items ?? []);
      }
      try {
        const ds = await loadCharacters();
        setCharCount(ds.meta?.perTotal ?? ds.items.length);
        setCharacters(ds.items.slice(0, perPage));
      } catch {
        await loadPage(1);
      }
      setStatus("Ready");
    })()
      .catch((err) => {
        setError(err?.message ?? String(err));
        setStatus("Error");
      })
      .finally(() => setLoading(false));
  }, []);

  async function loadPage(nextPage: number) {
    try {
      setStatus(`Loading characters (page ${nextPage})…`);
      const resp = await getCharacters({ page: nextPage, perPage, lang: "none", traitFormat: "id" });
      const items = Array.isArray(resp) ? (resp as any) : ((resp as MsfList<Character>).items ?? []);
      const total = Array.isArray(resp) ? items.length : ((resp as MsfList<Character>).meta?.perTotal ?? items.length);
      setCharacters(items);
      setCharCount(total);
      setPage(nextPage);
      setStatus("Ready");
    } catch (e: any) {
      console.warn("Characters fetch failed:", e?.message ?? String(e));
      setStatus("Error");
    }
  }

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
          <h3 style={{ marginTop: 16 }}>Characters (page {page})</h3>
          <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
            <button onClick={() => loadPage(Math.max(1, page - 1))} disabled={page <= 1}>
              Prev
            </button>
            <button onClick={() => loadPage(page + 1)} disabled={characters.length < perPage}>
              Next
            </button>
          </div>
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
            gap: 12,
          }}>
            {characters.map((c) => (
              <div key={String((c as any).id ?? (c as any).name)} style={{
                border: "1px solid #ddd",
                borderRadius: 8,
                padding: 12,
                background: "#fff",
              }}>
                <div style={{ fontWeight: 600, marginBottom: 6 }}>{(c as any).name ?? "(unnamed)"}</div>
                {Array.isArray((c as any).traits) && (c as any).traits.length > 0 && (
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {(c as any).traits.slice(0, 6).map((t: string) => (
                      <span key={t} style={{ fontSize: 11, padding: "2px 6px", border: "1px solid #ccd", borderRadius: 10, background: "#f6f7ff" }}>
                        {traitMap[t] ?? t}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
