"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type ScriptKind = "reduce" | "loop";

export type SavedScript = {
  id: string;
  name: string;
  kind: ScriptKind;
  code: string;
  createdAt: string;
};

export const SCRIPT_TEMPLATES: Record<ScriptKind, string> = {
  reduce: `def reduce(responses: list[str], weights: list[float]) -> str:
    """Combine each model's answer into one final answer."""
    from collections import Counter
    # weighted majority vote
    tally: Counter = Counter()
    for answer, weight in zip(responses, weights):
        tally[answer] += weight
    return tally.most_common(1)[0][0]
`,
  loop: `def respond(question: str, models: list) -> str:
    """Iterative response loop across the ensemble."""
    draft = models[0].ask(question)
    for model in models[1:]:
        draft = model.ask(f"Critique and improve this answer:\n{draft}")
    return draft
`,
};

const initialScripts: SavedScript[] = [
  {
    id: "scr-1",
    name: "weighted_majority.py",
    kind: "reduce",
    code: SCRIPT_TEMPLATES.reduce,
    createdAt: "Jun 24",
  },
  {
    id: "scr-2",
    name: "debate_loop.py",
    kind: "loop",
    code: SCRIPT_TEMPLATES.loop,
    createdAt: "Jun 25",
  },
];

type ScriptState = {
  scripts: SavedScript[];
  saveScript: (script: SavedScript) => void;
  removeScript: (id: string) => void;
};

export const useScriptStore = create<ScriptState>()(
  persist(
    (set) => ({
      scripts: initialScripts,
      saveScript: (script) =>
        set((state) => ({
          scripts: state.scripts.some((item) => item.id === script.id)
            ? state.scripts.map((item) =>
                item.id === script.id ? script : item,
              )
            : [...state.scripts, script],
        })),
      removeScript: (id) =>
        set((state) => ({
          scripts: state.scripts.filter((script) => script.id !== id),
        })),
    }),
    {
      name: "screamingface-scripts",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
