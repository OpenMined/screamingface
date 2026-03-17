const installCommand = `curl -fsSL https://screamingface.ai/install | sh`;

export default function Home() {
  return (
    <div
      style={{
        maxWidth: 700,
        margin: "0 auto",
        padding: "40px 20px 20px",
      }}
    >
      {/* Header */}
      <div style={{ textAlign: "center", marginBottom: 10 }}>
        <div style={{ fontSize: 64, marginBottom: 8 }}>😱</div>
        <h1
          style={{
            fontSize: 36,
            fontWeight: "bold",
            marginBottom: 8,
            fontFamily: '"Times New Roman", Times, serif',
          }}
        >
          screamingface
        </h1>
      </div>

      {/* Marquee — the one fancy 90s element */}
      {/* @ts-expect-error marquee is a deprecated HTML element not in JSX types */}
      <marquee
        scrollamount={4}
        style={{
          fontSize: 18,
          fontWeight: "bold",
          padding: "8px 0",
          marginBottom: 10,
          letterSpacing: 1,
        }}
      >
        *** SOTA ON YOUR LAPTOP *** SOTA ON YOUR LAPTOP *** SOTA ON YOUR
        LAPTOP ***
      {/* @ts-expect-error closing tag for marquee */}
      </marquee>

      <p style={{ textAlign: "center", marginBottom: 24 }}>
        An ensemble of the CLI models you already run.
        <br />
        Combines their outputs, picks the best answer.
        <br />
        Open source. No new accounts.
      </p>

      {/* Divider */}
      <div
        style={{
          textAlign: "center",
          margin: "16px 0",
          letterSpacing: 2,
          color: "#999",
        }}
      >
        ════════════════════════════════════
      </div>

      {/* Install section */}
      <h2
        style={{
          fontSize: 24,
          fontWeight: "bold",
          textAlign: "center",
          marginBottom: 8,
        }}
      >
        Install
      </h2>
      <p style={{ textAlign: "center", marginBottom: 16 }}>
        One command. Detects models on your machine. Configures itself.
        <br />
        Nothing sent to a server.
      </p>

      {/* Command block with dotted border */}
      <div
        style={{
          border: "2px dotted #000",
          padding: "12px 16px",
          marginBottom: 24,
          background: "#f5f5f5",
          fontFamily: '"Courier New", Courier, monospace',
          fontSize: 14,
          overflowX: "auto",
          whiteSpace: "nowrap",
        }}
      >
        <span style={{ userSelect: "none" }}>$ </span>
        {installCommand}
      </div>

      {/* Steps */}
      <h3
        style={{
          fontSize: 20,
          fontWeight: "bold",
          marginBottom: 12,
          textAlign: "center",
        }}
      >
        How it works:
      </h3>

      <ol
        style={{
          marginBottom: 24,
          paddingLeft: 24,
          lineHeight: 2,
        }}
      >
        <li>
          <b>Install</b> &mdash; One command. Configures locally. Nothing
          uploaded.
        </li>
        <li>
          <b>Auto-detect</b> &mdash; Finds Claude Code, Gemini CLI, Codex, and
          Ollama on your PATH.
        </li>
        <li>
          <b>Route</b> &mdash; Each prompt goes to whichever model scores best
          on the task.
        </li>
      </ol>

      {/* Divider */}
      <div
        style={{
          textAlign: "center",
          margin: "16px 0",
          letterSpacing: 2,
          color: "#999",
        }}
      >
        ════════════════════════════════════
      </div>

      {/* GitHub */}
      <p style={{ textAlign: "center", marginBottom: 24, fontSize: 18 }}>
        <a
          href="https://github.com/OpenMined/screamingface"
          target="_blank"
          rel="noopener noreferrer"
        >
          github.com/OpenMined/screamingface
        </a>
      </p>

      {/* Footer */}
      <footer
        style={{
          textAlign: "center",
          paddingTop: 16,
          paddingBottom: 8,
          fontSize: 14,
          borderTop: "1px solid #ccc",
        }}
      >
        <p style={{ marginBottom: 12 }}>
          😱 screamingface, built by{" "}
          <a
            href="https://openmined.org"
            target="_blank"
            rel="noopener noreferrer"
          >
            OpenMined
          </a>
        </p>

        {/* 88x31 badge */}
        <div
          style={{
            display: "inline-block",
            width: 88,
            height: 31,
            border: "1px solid #000",
            fontSize: 9,
            lineHeight: "31px",
            fontFamily: '"Courier New", Courier, monospace',
            fontWeight: "bold",
            background: "#000",
            color: "#0f0",
            letterSpacing: 0.5,
            textAlign: "center",
            marginBottom: 12,
          }}
        >
          😱 ENSEMBLE
        </div>

        <p style={{ color: "#888", fontSize: 12 }}>
          Last updated: March 2026
        </p>
      </footer>
    </div>
  );
}
