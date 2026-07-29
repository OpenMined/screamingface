"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { SavedModel } from "@/lib/ensemble-store";

export type ProviderKind = "local" | "session" | "hub" | "api";

export type ModelProvider = {
  id: string;
  name: string;
  kind: ProviderKind;
  group: "Local & Sessions" | "Providers" | "Hubs";
  description: string;
  connected: boolean;
  apiKey: string;
  useOM: boolean;
  discovering: boolean;
  models: SavedModel[];
};

export const PROVIDER_COLORS: Record<string, string> = {
  ollama: "#52aec5",
  "claude-session": "#b8520a",
  "codex-session": "#256b24",
  "gemini-session": "#4392c5",
  anthropic: "#ca492c",
  openai: "#53bea9",
  deepmind: "#6976ae",
  perplexity: "#175c6d",
  openrouter: "#937098",
  hf: "#f79763",
  mistral: "#f79763",
  moonshot: "#563b59",
  xai: "#464158",
  meta: "#52aec5",
};

const providerModels: Record<string, SavedModel[]> = {
  ollama: [
    { id: "ol-1", name: "ollama/llama-3.3-70b", providerId: "ollama", providerName: "Ollama" },
    { id: "ol-2", name: "ollama/qwen-2.5-7b", providerId: "ollama", providerName: "Ollama" },
    { id: "ol-3", name: "ollama/phi-4", providerId: "ollama", providerName: "Ollama" },
    { id: "ol-4", name: "ollama/deepseek-r1-8b", providerId: "ollama", providerName: "Ollama" },
  ],
  "claude-session": [
    { id: "cs-1", name: "claude-session/claude-opus-4.8", providerId: "claude-session", providerName: "Claude Session" },
    { id: "cs-2", name: "claude-session/claude-sonnet-4.6", providerId: "claude-session", providerName: "Claude Session" },
    { id: "cs-3", name: "claude-session/claude-haiku-4.5", providerId: "claude-session", providerName: "Claude Session" },
  ],
  "codex-session": [
    { id: "cx-1", name: "codex-session/gpt-5-codex", providerId: "codex-session", providerName: "Codex Session" },
    { id: "cx-2", name: "codex-session/gpt-5", providerId: "codex-session", providerName: "Codex Session" },
  ],
  "gemini-session": [
    { id: "gs-1", name: "gemini-session/gemini-2.5-pro", providerId: "gemini-session", providerName: "Gemini CLI Session" },
    { id: "gs-2", name: "gemini-session/gemini-2.5-flash", providerId: "gemini-session", providerName: "Gemini CLI Session" },
  ],
  anthropic: [
    { id: "an-1", name: "anthropic/claude-opus-4.8", providerId: "anthropic", providerName: "Anthropic" },
    { id: "an-2", name: "anthropic/claude-sonnet-4.6", providerId: "anthropic", providerName: "Anthropic" },
    { id: "an-3", name: "anthropic/claude-haiku-4.5", providerId: "anthropic", providerName: "Anthropic" },
  ],
  openai: [
    { id: "oa-1", name: "openai/gpt-5", providerId: "openai", providerName: "OpenAI" },
    { id: "oa-2", name: "openai/gpt-4o", providerId: "openai", providerName: "OpenAI" },
    { id: "oa-3", name: "openai/o3", providerId: "openai", providerName: "OpenAI" },
    { id: "oa-4", name: "openai/gpt-4o-mini", providerId: "openai", providerName: "OpenAI" },
  ],
  deepmind: [
    { id: "dm-1", name: "deepmind/gemini-2.5-pro", providerId: "deepmind", providerName: "Google DeepMind" },
    { id: "dm-2", name: "deepmind/gemini-2.5-flash", providerId: "deepmind", providerName: "Google DeepMind" },
    { id: "dm-3", name: "deepmind/gemini-2.0-flash", providerId: "deepmind", providerName: "Google DeepMind" },
  ],
  perplexity: [
    { id: "px-1", name: "perplexity/sonar-pro", providerId: "perplexity", providerName: "Perplexity" },
    { id: "px-2", name: "perplexity/sonar-reasoning", providerId: "perplexity", providerName: "Perplexity" },
    { id: "px-3", name: "perplexity/sonar-large", providerId: "perplexity", providerName: "Perplexity" },
  ],
  openrouter: [
    { id: "or-1", name: "openrouter/claude-opus-4", providerId: "openrouter", providerName: "OpenRouter" },
    { id: "or-2", name: "openrouter/claude-sonnet-4.6", providerId: "openrouter", providerName: "OpenRouter" },
    { id: "or-3", name: "openrouter/gemini-2.5-pro", providerId: "openrouter", providerName: "OpenRouter" },
    { id: "or-4", name: "openrouter/gpt-4o", providerId: "openrouter", providerName: "OpenRouter" },
    { id: "or-5", name: "openrouter/llama-4-scout", providerId: "openrouter", providerName: "OpenRouter" },
    { id: "or-6", name: "openrouter/deepseek-r1", providerId: "openrouter", providerName: "OpenRouter" },
  ],
  hf: [
    { id: "hf-1", name: "hf/mistral-7b-instruct", providerId: "hf", providerName: "HuggingFace" },
    { id: "hf-2", name: "hf/zephyr-7b-beta", providerId: "hf", providerName: "HuggingFace" },
  ],
};

export const ALL_MODELS = Object.values(providerModels).flat();

const initialProviders: ModelProvider[] = [
  { id: "ollama", name: "Ollama", kind: "local", group: "Local & Sessions", description: "Local models on your machine — no API key", connected: false, apiKey: "", useOM: false, discovering: false, models: [] },
  { id: "claude-session", name: "Claude Session", kind: "session", group: "Local & Sessions", description: "Your signed-in Claude desktop / CLI session", connected: false, apiKey: "", useOM: false, discovering: false, models: [] },
  { id: "codex-session", name: "Codex Session", kind: "session", group: "Local & Sessions", description: "Your authenticated Codex CLI session", connected: false, apiKey: "", useOM: false, discovering: false, models: [] },
  { id: "gemini-session", name: "Gemini CLI Session", kind: "session", group: "Local & Sessions", description: "Your authenticated Gemini CLI session", connected: false, apiKey: "", useOM: false, discovering: false, models: [] },
  { id: "anthropic", name: "Anthropic", kind: "api", group: "Providers", description: "Claude models, direct from the API", connected: false, apiKey: "", useOM: false, discovering: false, models: [] },
  { id: "openai", name: "OpenAI", kind: "api", group: "Providers", description: "GPT & o-series models", connected: false, apiKey: "", useOM: false, discovering: false, models: [] },
  { id: "deepmind", name: "Google DeepMind", kind: "api", group: "Providers", description: "Gemini models, direct from the API", connected: false, apiKey: "", useOM: false, discovering: false, models: [] },
  { id: "perplexity", name: "Perplexity", kind: "api", group: "Providers", description: "Sonar online & reasoning models", connected: false, apiKey: "", useOM: false, discovering: false, models: [] },
  { id: "openrouter", name: "OpenRouter", kind: "hub", group: "Hubs", description: "300+ models behind one API key", connected: false, apiKey: "", useOM: false, discovering: false, models: [] },
  { id: "hf", name: "HuggingFace Inference", kind: "api", group: "Hubs", description: "Serverless open-source inference", connected: false, apiKey: "", useOM: false, discovering: false, models: [] },
];

type ModelState = {
  providers: ModelProvider[];
  library: SavedModel[];
  patchProvider: (id: string, patch: Partial<ModelProvider>) => void;
  discoverProvider: (id: string) => Promise<void>;
  toggleLibraryModel: (model: SavedModel) => void;
  addLibraryModels: (models: SavedModel[]) => void;
};

export const useModelStore = create<ModelState>()(
  persist(
    (set) => ({
      providers: initialProviders,
      library: [],
      patchProvider: (id, patch) =>
        set((state) => ({
          providers: state.providers.map((provider) =>
            provider.id === id ? { ...provider, ...patch } : provider,
          ),
        })),
      discoverProvider: async (id) => {
        set((state) => ({
          providers: state.providers.map((provider) =>
            provider.id === id ? { ...provider, discovering: true } : provider,
          ),
        }));
        await new Promise((resolve) => window.setTimeout(resolve, 900));
        set((state) => ({
          providers: state.providers.map((provider) =>
            provider.id === id
              ? {
                  ...provider,
                  discovering: false,
                  connected: true,
                  models: providerModels[id] ?? [],
                }
              : provider,
          ),
        }));
      },
      toggleLibraryModel: (model) =>
        set((state) => ({
          library: state.library.some((item) => item.id === model.id)
            ? state.library.filter((item) => item.id !== model.id)
            : [...state.library, model],
        })),
      addLibraryModels: (models) =>
        set((state) => {
          const ids = new Set(state.library.map((model) => model.id));
          return {
            library: [
              ...state.library,
              ...models.filter((model) => !ids.has(model.id)),
            ],
          };
        }),
    }),
    {
      name: "screamingface-models",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        library: state.library,
        providers: state.providers.map((provider) => ({
          ...provider,
          apiKey: "",
          discovering: false,
        })),
      }),
    },
  ),
);
