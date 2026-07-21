"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export const OPENMINED_BUDGET_TOTAL = 20;

type OpenMinedState = {
  connected: boolean;
  key: string;
  budget: number;
  authOpen: boolean;
  authorizing: boolean;
  setKey: (key: string) => void;
  setAuthOpen: (authOpen: boolean) => void;
  authorize: () => Promise<void>;
};

export const useOpenMinedStore = create<OpenMinedState>()(
  persist(
    (set) => ({
      connected: false,
      key: "",
      budget: 0,
      authOpen: false,
      authorizing: false,
      setKey: (key) => set({ key }),
      setAuthOpen: (authOpen) => set({ authOpen }),
      authorize: async () => {
        set({ authorizing: true });
        await new Promise((resolve) => window.setTimeout(resolve, 1100));
        set({
          connected: true,
          budget: 12.4,
          authOpen: false,
          authorizing: false,
        });
      },
    }),
    {
      name: "screamingface-openmined",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        connected: state.connected,
        budget: state.budget,
      }),
    },
  ),
);
