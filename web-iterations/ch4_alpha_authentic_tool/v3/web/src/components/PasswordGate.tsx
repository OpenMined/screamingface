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

  if (unlocked === null) return null;
  if (unlocked) return <>{children}</>;

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 32,
        padding: "0 24px",
      }}
    >
      <div style={{ fontSize: 64, userSelect: "none" }}>😱</div>
      <p style={{ fontSize: 20, fontWeight: 500 }}>screamingface</p>

      <form
        onSubmit={submit}
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 12,
          width: "100%",
          maxWidth: 280,
        }}
      >
        <input
          ref={inputRef}
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Password"
          autoComplete="current-password"
          style={{
            width: "100%",
            border: `1px solid ${error ? "#dc2626" : "#ccc"}`,
            borderRadius: 6,
            padding: "10px 14px",
            fontSize: 14,
            outline: "none",
          }}
        />
        {error && (
          <p style={{ fontSize: 12, color: "#dc2626" }}>Incorrect password.</p>
        )}
        <button
          type="submit"
          style={{
            width: "100%",
            background: "#1a1a1a",
            color: "#fff",
            padding: "10px 0",
            borderRadius: 6,
            fontSize: 14,
            fontWeight: 500,
            border: "none",
            cursor: "pointer",
          }}
        >
          Enter
        </button>
      </form>
    </div>
  );
}
