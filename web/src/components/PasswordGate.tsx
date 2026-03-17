"use client";

import { useState, useEffect, useRef } from "react";

const PASSWORD = "letmein";
const STORAGE_KEY = "sf_auth";

export default function PasswordGate({ children }: { children: React.ReactNode }) {
  const [unlocked, setUnlocked] = useState<boolean | null>(null);
  const [value, setValue] = useState("");
  const [error, setError] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setUnlocked(sessionStorage.getItem(STORAGE_KEY) === "1");
  }, []);

  useEffect(() => {
    if (unlocked === false) inputRef.current?.focus();
  }, [unlocked]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (value === PASSWORD) {
      sessionStorage.setItem(STORAGE_KEY, "1");
      setUnlocked(true);
    } else {
      setError(true);
      setValue("");
      setTimeout(() => setError(false), 1200);
    }
  }

  // Avoid flash — render nothing until we've checked storage
  if (unlocked === null) return null;

  if (unlocked) return <>{children}</>;

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-8 px-6">
      <div className="text-6xl select-none">😱</div>
      <p
        className="text-xl font-medium tracking-tight"
        style={{ fontFamily: "var(--font-rubik)" }}
      >
        screamingface
      </p>

      <form onSubmit={submit} className="flex flex-col items-center gap-3 w-full max-w-xs">
        <input
          ref={inputRef}
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Password"
          autoComplete="current-password"
          className={`w-full bg-card border rounded-lg px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:ring-1 focus:ring-ring transition-colors ${
            error ? "border-destructive focus:ring-destructive" : "border-border"
          }`}
          style={{ fontFamily: "var(--font-sometype-mono)" }}
        />
        {error && (
          <p className="text-xs text-destructive">Incorrect password.</p>
        )}
        <button
          type="submit"
          className="w-full gradient-gold text-[#1a1720] py-3 rounded-lg text-sm font-medium hover:opacity-90 transition-opacity"
        >
          Enter
        </button>
      </form>
    </div>
  );
}
