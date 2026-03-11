"use client";

import { useState } from "react";

// Replace with your actual form endpoint (Formspree, custom API, etc.)
const FORM_ENDPOINT = "https://formspree.io/f/REPLACE_ME";

export default function EmailCapture() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email || status === "submitting") return;

    setStatus("submitting");

    try {
      const res = await fetch(FORM_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ email }),
      });

      if (res.ok) {
        setStatus("success");
        setEmail("");
      } else {
        setStatus("error");
      }
    } catch {
      setStatus("error");
    }
  }

  return (
    <section id="updates" className="px-6 py-20 border-t border-border">
      <div className="max-w-xl mx-auto text-center">
        <div className="text-4xl mb-4 select-none">😱</div>
        <h2
          className="text-2xl font-semibold mb-3"
          style={{ fontFamily: "var(--font-rubik)" }}
        >
          Stay in the loop.
        </h2>
        <p className="text-muted-foreground text-sm mb-8">
          Early access, benchmark drops, and open beta updates — when they happen. No noise.
        </p>

        {status === "success" ? (
          <p
            className="text-primary text-sm"
            style={{ fontFamily: "var(--font-sometype-mono)" }}
          >
            You&apos;re on the list.
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-3 justify-center">
            <input
              type="email"
              required
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="bg-card border border-border rounded-lg px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring w-full sm:w-72"
              style={{ fontFamily: "var(--font-sometype-mono)" }}
              disabled={status === "submitting"}
            />
            <button
              type="submit"
              disabled={status === "submitting"}
              className="gradient-gold text-[#1a1720] px-5 py-3 rounded-lg font-medium text-sm hover:opacity-90 transition-opacity disabled:opacity-50 shrink-0"
            >
              {status === "submitting" ? "Submitting…" : "Notify me"}
            </button>
          </form>
        )}

        {status === "error" && (
          <p className="text-destructive text-xs mt-3">
            Something went wrong. Try again or email us directly.
          </p>
        )}
      </div>
    </section>
  );
}
