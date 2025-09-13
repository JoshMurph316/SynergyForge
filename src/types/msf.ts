export interface Trait { id: string; name: string; description?: string }
export interface Character {
  id: string | number;
  name: string;
  traits?: string[];
  // extend as we learn the API shape
}

export type CharacterList = Character[] | { items: Character[] }
