"use client";

import { useEffect } from "react";
import { useTheme } from "next-themes";

type TauriGlobal = {
  core?: { invoke?: (command: string, args?: Record<string, unknown>) => Promise<unknown> };
};

export function NativeThemeSync() {
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    const tauri = (window as Window & { __TAURI__?: TauriGlobal }).__TAURI__;
    if (!resolvedTheme || typeof tauri?.core?.invoke !== "function") return;
    void tauri.core.invoke("update_theme", { isDark: resolvedTheme === "dark" });
  }, [resolvedTheme]);

  return null;
}
