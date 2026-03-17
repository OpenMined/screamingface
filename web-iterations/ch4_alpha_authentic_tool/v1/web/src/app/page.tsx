const installCommand = `curl -fsSL https://screamingface.ai/install | sh`;

export default function Home() {
  return (
    <div style={{ maxWidth: 600, margin: "0 auto", padding: "40px 20px" }}>
      <div style={{ textAlign: "center", marginBottom: 40 }}>
        <div style={{ fontSize: 64, marginBottom: 16 }}>😱</div>
        <h1 style={{ fontSize: 36, fontWeight: "bold", marginBottom: 12 }}>
          SOTA on your laptop.
        </h1>
        <p>
          An ensemble of the CLI models you already run. Combines their outputs,
          picks the best answer. Open source. No new accounts.
        </p>
      </div>

      <div style={{ marginBottom: 40 }}>
        <h2 style={{ fontSize: 24, fontWeight: "bold", marginBottom: 8 }}>
          One command
        </h2>
        <p style={{ marginBottom: 16 }}>
          Detects models on your machine. Configures itself. Nothing sent to a
          server.
        </p>

        <pre
          style={{
            background: "#f0f0f0",
            border: "1px solid #000000",
            padding: "12px 16px",
            overflowX: "auto",
            marginBottom: 32,
          }}
        >
          <code>$ {installCommand}</code>
        </pre>

        <p style={{ marginBottom: 8 }}>
          <strong>01 — Install.</strong> One command. Configures locally. Nothing
          uploaded.
        </p>
        <p style={{ marginBottom: 8 }}>
          <strong>02 — Auto-detect.</strong> Finds Claude Code, Gemini CLI,
          Codex, and Ollama on your PATH.
        </p>
        <p style={{ marginBottom: 8 }}>
          <strong>03 — Route.</strong> Each prompt goes to whichever model scores
          best on the task.
        </p>
      </div>

      <p style={{ marginBottom: 40 }}>
        <a
          href="https://github.com/OpenMined/screamingface"
          target="_blank"
          rel="noopener noreferrer"
        >
          github.com/OpenMined/screamingface
        </a>
      </p>

      <hr style={{ border: "none", borderTop: "1px solid #000000", marginBottom: 16 }} />

      <footer style={{ fontSize: 14 }}>
        😱 screamingface, built by{" "}
        <a
          href="https://openmined.org"
          target="_blank"
          rel="noopener noreferrer"
        >
          OpenMined
        </a>
        {" — "}
        <a
          href="https://github.com/OpenMined/screamingface"
          target="_blank"
          rel="noopener noreferrer"
        >
          GitHub
        </a>
      </footer>
    </div>
  );
}
