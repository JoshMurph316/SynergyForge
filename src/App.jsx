import { useEffect, useState } from "react";

export default function App() {
  const [chars, setChars] = useState([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    fetch("/data/characters_min.json")
      .then(r => r.json())
      .then(setChars)
      .catch(e => setErr(String(e)));
  }, []);

  return (
    <div style={{ padding: 16 }}>
      <h1>SynergyForge</h1>
      {err && <pre>Load error: {err}</pre>}
      <ul>
        {chars.map(c => (
          <li key={c.path}>{c.name}</li>
        ))}
      </ul>
    </div>
  );
}