// src/App.jsx
import { useEffect, useState } from "react";
import { ensureAppToken, getTraits, getCharacters } from "./lib/msf";

export default function App() {
  const [charCount, setCharCount] = useState<number>(0);

  useEffect(() => {
    (async () => {
      await ensureAppToken();
      const traits = await getTraits();
      console.log("MSF traits:", traits);   // <-- verify in DevTools console

      const characters = await getCharacters();
      console.log("MSF characters:", characters);
      const n = Array.isArray(characters) ? characters.length : (characters.items?.length ?? 0);
      setCharCount(n);
    })().catch(err => console.error("Boot error:", err));
  }, []);

  return (
    <div style={{ padding: 16 }}>
      <h1>SynergyForge</h1>
      <p>Characters loaded: {charCount}</p>
    </div>
  );
}
