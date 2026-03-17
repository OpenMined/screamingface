const installCommand = `curl -fsSL https://screamingface.ai/install | sh`;

export default function Home() {
  return (
    <div style={{ maxWidth: 540, margin: "0 auto", padding: "48px 20px" }}>
      {/* Header */}
      <header style={{ marginBottom: 40 }}>
        <h1 style={{ fontSize: 20, fontWeight: "normal", marginBottom: 4 }}>
          screamingface
        </h1>
        <p style={{ color: "#666" }}>
          AI model ensemble for your terminal
        </p>
      </header>

      {/* What it does */}
      <section style={{ marginBottom: 32 }}>
        <p style={{ marginBottom: 12 }}>
          Routes prompts across Claude Code, Gemini CLI, Codex, and Ollama.
          Picks the best response. Runs locally.
        </p>
        <p>
          No accounts. No API keys you don&apos;t already have. Open source.
        </p>
      </section>

      {/* Install */}
      <section style={{ marginBottom: 32 }}>
        <div style={{ marginBottom: 8 }}>Install:</div>
        <pre
          style={{
            background: "#f6f6f6",
            border: "1px solid #ddd",
            padding: "10px 14px",
            overflowX: "auto",
          }}
        >
          <code>$ {installCommand}</code>
        </pre>
      </section>

      {/* How it works */}
      <section style={{ marginBottom: 32 }}>
        <div style={{ marginBottom: 8 }}>How it works:</div>
        <ol
          style={{
            paddingLeft: 20,
            listStyleType: "decimal",
          }}
        >
          <li style={{ marginBottom: 4 }}>
            Detects models on your PATH
          </li>
          <li style={{ marginBottom: 4 }}>
            Sends each prompt to the best-scoring model for that task type
          </li>
          <li style={{ marginBottom: 4 }}>
            Ensemble mode: runs multiple models, picks the best output
          </li>
          <li>
            Everything stays on your machine
          </li>
        </ol>
      </section>

      {/* Why */}
      <section style={{ marginBottom: 32 }}>
        <div style={{ marginBottom: 8 }}>Why:</div>
        <p>
          No single model wins every benchmark. Ensembles beat individual models
          on SWE-bench, HumanEval, and MMLU — but deploying them is a pain.
          This makes it one command.
        </p>
      </section>

      {/* Links */}
      <section style={{ marginBottom: 40 }}>
        <div style={{ display: "flex", gap: 20 }}>
          <a
            href="https://github.com/OpenMined/screamingface"
            target="_blank"
            rel="noopener noreferrer"
          >
            github
          </a>
          <a
            href="https://github.com/OpenMined/screamingface/issues"
            target="_blank"
            rel="noopener noreferrer"
          >
            issues
          </a>
          <a
            href="https://openmined.org"
            target="_blank"
            rel="noopener noreferrer"
          >
            openmined
          </a>
        </div>
      </section>

      {/* Footer */}
      <footer
        style={{
          borderTop: "1px solid #ddd",
          paddingTop: 16,
          color: "#999",
          fontSize: 12,
        }}
      >
        built by OpenMined · open source · alpha
      </footer>
    </div>
  );
}
