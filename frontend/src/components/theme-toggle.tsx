"use client";

import { Moon, Sun } from "lucide-react";

export function ThemeToggle() {
  function toggleTheme() {
    const nextDark = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", nextDark);
    localStorage.setItem("screamingface-theme", nextDark ? "dark" : "light");
  }

  return (
    <button
      className="theme-button"
      type="button"
      aria-label="Toggle color theme"
      onClick={toggleTheme}
    >
      <Moon className="theme-icon theme-icon-moon" size={15} />
      <Sun className="theme-icon theme-icon-sun" size={15} />
    </button>
  );
}
