"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type SavedModel = {
  id: string;
  name: string;
  providerId: string;
  providerName: string;
};

export type SavedSlot = {
  model: SavedModel;
  systemPrompt: string;
  weight: number;
};

export type SavedEnsemble = {
  id: string;
  name: string;
  slots: SavedSlot[];
  strategy: "majority_vote" | "weighted_avg" | "best_of_n" | "merge";
  customReduce: boolean;
  loopMode: "parallel" | "custom";
  judgeId: string | null;
  runs: number;
  updatedAt: number;
};

type EnsembleState = {
  ensembles: SavedEnsemble[];
  activeEnsembleId: string | null;
  hasHydrated: boolean;
  upsertEnsemble: (ensemble: SavedEnsemble) => void;
  setActiveEnsemble: (id: string | null) => void;
  setHasHydrated: (hasHydrated: boolean) => void;
};

export const useEnsembleStore = create<EnsembleState>()(
  persist(
    (set) => ({
      ensembles: [],
      activeEnsembleId: null,
      hasHydrated: false,
      upsertEnsemble: (ensemble) =>
        set((state) => {
          const exists = state.ensembles.some((item) => item.id === ensemble.id);
          const ensembles = exists
            ? state.ensembles.map((item) =>
                item.id === ensemble.id ? ensemble : item,
              )
            : [ensemble, ...state.ensembles];
          return {
            ensembles: ensembles.sort((a, b) => b.updatedAt - a.updatedAt),
          };
        }),
      setActiveEnsemble: (activeEnsembleId) => set({ activeEnsembleId }),
      setHasHydrated: (hasHydrated) => set({ hasHydrated }),
    }),
    {
      name: "screamingface-ensembles",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ ensembles: state.ensembles }),
      onRehydrateStorage: () => (state) => state?.setHasHydrated(true),
    },
  ),
);
