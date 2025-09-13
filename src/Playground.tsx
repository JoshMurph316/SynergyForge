import { useState } from "react";
import { collection, addDoc, getDocs, serverTimestamp } from "firebase/firestore";
import { db } from "./services/firebase";

export default function Playground() {
  const [log, setLog] = useState<string[]>([]);

  const write = async () => {
    const ref = await addDoc(collection(db, "smoke_test"), {
      createdAt: serverTimestamp(),
      note: "Hello from SynergyForge",
    });
    setLog((l) => [`Wrote doc ${ref.id}`, ...l]);
  };

  const read = async () => {
    const snap = await getDocs(collection(db, "smoke_test"));
    setLog((l) => [
      `Read ${snap.size} docs: ${snap.docs.map((d) => d.id).join(", ")}`,
      ...l,
    ]);
  };

  return (
    <div style={{ padding: 16 }}>
      <h2>Firestore Smoke Test</h2>
      <button onClick={write}>Write test doc</button>{" "}
      <button onClick={read}>Read test docs</button>
      <pre style={{ marginTop: 12, background: "#111", color: "#eee", padding: 12 }}>
        {log.join("\n")}
      </pre>
    </div>
  );
}

