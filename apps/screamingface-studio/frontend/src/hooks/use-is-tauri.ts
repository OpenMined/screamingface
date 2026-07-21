"use client";

import { useEffect, useState } from "react";

export function useIsTauri() {
  const [isTauri, setIsTauri] = useState<boolean>();

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setIsTauri("__TAURI__" in window || "__TAURI_INTERNALS__" in window);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  return isTauri;
}
