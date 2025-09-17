export interface Trait { id: string; name: string; description?: string }
export interface Character {
  id: string;
  name: string;
  imageUrl?: string;
  traits: string[];
  faction?: string;
  role?: string;
  stats?: Record<string, number>;
}

export interface MsfMeta {
  perTotal?: number;
  perPage?: number;
  page?: number;
}

export interface MsfList<T> {
  meta?: MsfMeta;
  items: T[];
}

export type CharacterList = Character[] | MsfList<Character>
