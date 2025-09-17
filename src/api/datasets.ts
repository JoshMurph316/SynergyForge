import type { Trait, MsfList, Character } from "../types/msf";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path, { credentials: "include" });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

export const loadTraits = () => get<Trait[]>("/api/datasets/traits");
export const loadCharacters = () => get<MsfList<Character>>("/api/datasets/characters");

