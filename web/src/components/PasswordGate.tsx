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
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 16, padding: 24 }}>
      <div style={{ fontSize: 48 }}>😱</div>
      <p style={{ fontSize: 16 }}>
        <strong>screamingface</strong>
      </p>

      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8, width: "100%", maxWidth: 280 }}>
        <input
          ref={inputRef}
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="password"
          autoComplete="current-password"
          style={{
            width: "100%",
            border: error ? "1px solid #cc0000" : "1px solid #ccc",
            padding: "8px 12px",
            fontSize: 13,
            fontFamily: "var(--font-mono)",
          }}
        />
        {error && (
          <p style={{ fontSize: 11, color: "#cc0000" }}>Incorrect password.</p>
        )}
        <button
          type="submit"
          style={{
            width: "100%",
            border: "1px solid #ccc",
            padding: "8px 12px",
            fontSize: 13,
            background: "#f4f4f4",
            cursor: "pointer",
          }}
        >
          enter
        </button>
      </form>
    </div>
  );
}
