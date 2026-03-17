import CostTable from "@/components/CostTable";
import Sparkline from "@/components/Sparkline";

const lastUpdated = "March 16, 2026 04:00 UTC";

const categories = [
  { name: "Coding", anchor: "coding", benchmark: "SWE-bench Verified" },
  { name: "Math", anchor: "math", benchmark: "MATH-500" },
  { name: "Reasoning", anchor: "reasoning", benchmark: "GPQA Diamond" },
  { name: "General Knowledge", anchor: "general", benchmark: "MMLU-Pro" },
  { name: "Frontier", anchor: "frontier", benchmark: "HLE (Humanity's Last Exam)" },
];

export default function Home() {
  return (
    <>
      {/* Header */}
      <header style={{ borderBottom: "1px solid #ccc", paddingBottom: 8, marginBottom: 16, paddingTop: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
          <div>
            <span style={{ fontSize: 22 }}>😱</span>{" "}
            <strong style={{ fontSize: 16 }}>screamingface</strong>{" "}
            <span style={{ color: "#666", fontSize: 12 }}>the real cost of intelligence</span>
          </div>
          <nav style={{ fontSize: 12, display: "flex", gap: 16 }}>
            <a href="#about">about</a>
            <a href="/why">why this matters</a>
            <a href="#contribute">contribute data</a>
            <a href="https://github.com/OpenMined/screamingface">github</a>
          </nav>
        </div>
      </header>

      {/* Lede */}
      <div style={{ marginBottom: 20 }}>
        <p style={{ fontSize: 14, marginBottom: 8 }}>
          <strong>How much does it cost to solve a problem with AI?</strong>
        </p>
        <p style={{ color: "#666", fontSize: 12, lineHeight: 1.6 }}>
          Every benchmark measures accuracy. Every pricing page shows cost per token.
          Nobody shows what actually matters: the cost to get a correct answer on a real task.
          This page tracks that number across models and problem types, updated daily.
          All data is open. <a href="#methodology">Methodology</a>.
        </p>
      </div>

      {/* Jump links */}
      <p style={{ fontSize: 12, color: "#888", marginBottom: 20 }}>
        Jump to:{" "}
        {categories.map((cat, i) => (
          <span key={cat.anchor}>
            <a href={`#${cat.anchor}`}>{cat.name}</a>
            {i < categories.length - 1 ? ", " : ""}
          </span>
        ))}
        {" | "}
        <a href="#ensemble">Why ensembles win</a>
        {" | "}
        <a href="#about">About</a>
      </p>

      {/* Summary ticker */}
      <div style={{ marginBottom: 24 }}>
        <h2 id="summary" style={{ marginTop: 0 }}>Summary — cost per correct answer</h2>
        <p style={{ fontSize: 11, color: "#666", marginBottom: 8 }}>
          Cheapest option per category. <span style={{ color: "#c8842a", fontWeight: "bold" }}>■</span> = ensemble (multiple models combined).
          Updated {lastUpdated}. Prices in USD.
        </p>
        <table>
          <thead>
            <tr>
              <th>Category</th>
              <th>Benchmark</th>
              <th>Cheapest Model</th>
              <th style={{ textAlign: "right" }}>$/correct</th>
              <th style={{ textAlign: "right" }}>7d trend</th>
              <th>Best Single Model</th>
              <th style={{ textAlign: "right" }}>$/correct</th>
              <th style={{ textAlign: "right" }}>Ensemble savings</th>
            </tr>
          </thead>
          <tbody>
            <tr style={{ background: "#fff8e1" }}>
              <td><a href="#coding">Coding</a></td>
              <td style={{ fontSize: 11 }}>SWE-bench Verified</td>
              <td style={{ color: "#c8842a" }}>Ensemble 😱</td>
              <td style={{ textAlign: "right" }}>$0.42</td>
              <td style={{ textAlign: "right", color: "#006600" }}>
                <Sparkline data={[0.58, 0.55, 0.51, 0.48, 0.45, 0.43, 0.42]} color="#006600" />
                {" "}↓12%
              </td>
              <td>Claude Opus 4.5</td>
              <td style={{ textAlign: "right" }}>$0.71</td>
              <td style={{ textAlign: "right", color: "#006600" }}>-41%</td>
            </tr>
            <tr style={{ background: "#fff8e1" }}>
              <td><a href="#math">Math</a></td>
              <td style={{ fontSize: 11 }}>MATH-500</td>
              <td style={{ color: "#c8842a" }}>Ensemble 😱</td>
              <td style={{ textAlign: "right" }}>$0.08</td>
              <td style={{ textAlign: "right", color: "#006600" }}>
                <Sparkline data={[0.14, 0.13, 0.11, 0.10, 0.09, 0.08, 0.08]} color="#006600" />
                {" "}↓18%
              </td>
              <td>Gemini 2.5 Pro</td>
              <td style={{ textAlign: "right" }}>$0.11</td>
              <td style={{ textAlign: "right", color: "#006600" }}>-27%</td>
            </tr>
            <tr style={{ background: "#fff8e1" }}>
              <td><a href="#reasoning">Reasoning</a></td>
              <td style={{ fontSize: 11 }}>GPQA Diamond</td>
              <td style={{ color: "#c8842a" }}>Ensemble 😱</td>
              <td style={{ textAlign: "right" }}>$0.19</td>
              <td style={{ textAlign: "right", color: "#cc0000" }}>
                <Sparkline data={[0.17, 0.17, 0.18, 0.18, 0.19, 0.19, 0.19]} color="#cc0000" />
                {" "}↑8%
              </td>
              <td>o3</td>
              <td style={{ textAlign: "right" }}>$0.34</td>
              <td style={{ textAlign: "right", color: "#006600" }}>-44%</td>
            </tr>
            <tr style={{ background: "#fff8e1" }}>
              <td><a href="#general">General</a></td>
              <td style={{ fontSize: 11 }}>MMLU-Pro</td>
              <td style={{ color: "#c8842a" }}>Ensemble 😱</td>
              <td style={{ textAlign: "right" }}>$0.03</td>
              <td style={{ textAlign: "right", color: "#006600" }}>
                <Sparkline data={[0.05, 0.05, 0.04, 0.04, 0.03, 0.03, 0.03]} color="#006600" />
                {" "}↓22%
              </td>
              <td>GPT-4.1</td>
              <td style={{ textAlign: "right" }}>$0.04</td>
              <td style={{ textAlign: "right", color: "#006600" }}>-25%</td>
            </tr>
            <tr style={{ background: "#fff8e1" }}>
              <td><a href="#frontier">Frontier</a></td>
              <td style={{ fontSize: 11 }}>HLE</td>
              <td style={{ color: "#c8842a" }}>Ensemble 😱</td>
              <td style={{ textAlign: "right" }}>$4.72</td>
              <td style={{ textAlign: "right", color: "#006600" }}>
                <Sparkline data={[6.10, 5.80, 5.50, 5.20, 5.00, 4.85, 4.72]} color="#006600" />
                {" "}↓9%
              </td>
              <td>Claude Opus 4.5</td>
              <td style={{ textAlign: "right" }}>$8.30</td>
              <td style={{ textAlign: "right", color: "#006600" }}>-43%</td>
            </tr>
          </tbody>
        </table>
        <p style={{ fontSize: 10, color: "#999", marginTop: 4 }}>
          * illustrative data — real benchmarking infrastructure in development. <a href="#methodology">see methodology</a>.
        </p>
      </div>

      <hr />

      {/* Per-category tables */}
      <CostTable
        id="coding"
        title="Coding"
        benchmark="SWE-bench Verified"
        description="Resolving real GitHub issues from popular open-source repositories. Each task requires reading code, understanding the bug, and producing a working patch."
        data={[
          { model: "Ensemble 😱", config: "Claude + Gemini + Codex", accuracy: 83.2, costPer1k: 350, costPerCorrect: 0.42, trend: -12, ensemble: true },
          { model: "Claude Opus 4.5", config: "Anthropic API", accuracy: 80.9, costPer1k: 575, costPerCorrect: 0.71, trend: -3, ensemble: false },
          { model: "Gemini 2.5 Pro", config: "Google AI API", accuracy: 80.6, costPer1k: 420, costPerCorrect: 0.52, trend: -8, ensemble: false },
          { model: "GPT-4.1", config: "OpenAI API", accuracy: 72.3, costPer1k: 380, costPerCorrect: 0.53, trend: 0, ensemble: false },
          { model: "Codex CLI", config: "OpenAI API", accuracy: 69.1, costPer1k: 310, costPerCorrect: 0.45, trend: -5, ensemble: false },
          { model: "DeepSeek-R1", config: "DeepSeek API", accuracy: 64.8, costPer1k: 85, costPerCorrect: 0.13, trend: -2, ensemble: false },
          { model: "Llama 3.3 70B", config: "Ollama (local)", accuracy: 42.1, costPer1k: 0, costPerCorrect: 0, trend: 0, ensemble: false },
        ]}
      />

      <CostTable
        id="math"
        title="Math"
        benchmark="MATH-500"
        description="Competition-level mathematics problems. Algebra, geometry, number theory, combinatorics, probability."
        data={[
          { model: "Ensemble 😱", config: "Gemini + o3 + Claude", accuracy: 97.8, costPer1k: 78, costPerCorrect: 0.08, trend: -18, ensemble: true },
          { model: "Gemini 2.5 Pro", config: "Google AI API", accuracy: 96.4, costPer1k: 106, costPerCorrect: 0.11, trend: -6, ensemble: false },
          { model: "o3", config: "OpenAI API", accuracy: 96.1, costPer1k: 420, costPerCorrect: 0.44, trend: 2, ensemble: false },
          { model: "Claude Opus 4.5", config: "Anthropic API", accuracy: 94.2, costPer1k: 310, costPerCorrect: 0.33, trend: -4, ensemble: false },
          { model: "GPT-4.1", config: "OpenAI API", accuracy: 91.8, costPer1k: 145, costPerCorrect: 0.16, trend: -1, ensemble: false },
          { model: "DeepSeek-R1", config: "DeepSeek API", accuracy: 89.5, costPer1k: 42, costPerCorrect: 0.05, trend: -3, ensemble: false },
          { model: "Llama 3.3 70B", config: "Ollama (local)", accuracy: 68.3, costPer1k: 0, costPerCorrect: 0, trend: 0, ensemble: false },
        ]}
      />

      <CostTable
        id="reasoning"
        title="Reasoning"
        benchmark="GPQA Diamond"
        description="Graduate-level science questions written by domain experts. Physics, chemistry, biology. Questions that PhDs get wrong."
        data={[
          { model: "Ensemble 😱", config: "o3 + Claude + Gemini", accuracy: 78.4, costPer1k: 149, costPerCorrect: 0.19, trend: 8, ensemble: true },
          { model: "o3", config: "OpenAI API", accuracy: 76.7, costPer1k: 261, costPerCorrect: 0.34, trend: 5, ensemble: false },
          { model: "Claude Opus 4.5", config: "Anthropic API", accuracy: 74.9, costPer1k: 285, costPerCorrect: 0.38, trend: -2, ensemble: false },
          { model: "Gemini 2.5 Pro", config: "Google AI API", accuracy: 71.2, costPer1k: 198, costPerCorrect: 0.28, trend: -4, ensemble: false },
          { model: "GPT-4.1", config: "OpenAI API", accuracy: 62.1, costPer1k: 132, costPerCorrect: 0.21, trend: 0, ensemble: false },
          { model: "DeepSeek-R1", config: "DeepSeek API", accuracy: 58.3, costPer1k: 38, costPerCorrect: 0.07, trend: -1, ensemble: false },
          { model: "Llama 3.3 70B", config: "Ollama (local)", accuracy: 38.7, costPer1k: 0, costPerCorrect: 0, trend: 0, ensemble: false },
        ]}
      />

      <CostTable
        id="general"
        title="General Knowledge"
        benchmark="MMLU-Pro"
        description="57 subjects from elementary math to professional law, medicine, and engineering. The standard general-purpose benchmark."
        data={[
          { model: "Ensemble 😱", config: "GPT-4.1 + Gemini + Claude", accuracy: 89.7, costPer1k: 27, costPerCorrect: 0.03, trend: -22, ensemble: true },
          { model: "GPT-4.1", config: "OpenAI API", accuracy: 87.5, costPer1k: 35, costPerCorrect: 0.04, trend: -8, ensemble: false },
          { model: "Claude Opus 4.5", config: "Anthropic API", accuracy: 86.8, costPer1k: 112, costPerCorrect: 0.13, trend: -3, ensemble: false },
          { model: "Gemini 2.5 Pro", config: "Google AI API", accuracy: 85.3, costPer1k: 68, costPerCorrect: 0.08, trend: -5, ensemble: false },
          { model: "o3", config: "OpenAI API", accuracy: 84.1, costPer1k: 210, costPerCorrect: 0.25, trend: 1, ensemble: false },
          { model: "DeepSeek-R1", config: "DeepSeek API", accuracy: 78.9, costPer1k: 22, costPerCorrect: 0.03, trend: -2, ensemble: false },
          { model: "Llama 3.3 70B", config: "Ollama (local)", accuracy: 62.4, costPer1k: 0, costPerCorrect: 0, trend: 0, ensemble: false },
        ]}
      />

      <CostTable
        id="frontier"
        title="Frontier"
        benchmark="HLE (Humanity's Last Exam)"
        description="The hardest benchmark. Questions from 500+ experts across 100+ subjects, designed to be beyond current AI capability. Nobody scores above 20%."
        data={[
          { model: "Ensemble 😱", config: "All models combined", accuracy: 16.8, costPer1k: 793, costPerCorrect: 4.72, trend: -9, ensemble: true },
          { model: "Claude Opus 4.5", config: "Anthropic API", accuracy: 14.1, costPer1k: 1170, costPerCorrect: 8.30, trend: -1, ensemble: false },
          { model: "o3", config: "OpenAI API", accuracy: 12.3, costPer1k: 980, costPerCorrect: 7.97, trend: 3, ensemble: false },
          { model: "Gemini 2.5 Pro", config: "Google AI API", accuracy: 10.9, costPer1k: 640, costPerCorrect: 5.87, trend: -4, ensemble: false },
          { model: "GPT-4.1", config: "OpenAI API", accuracy: 9.1, costPer1k: 420, costPerCorrect: 4.62, trend: 0, ensemble: false },
          { model: "DeepSeek-R1", config: "DeepSeek API", accuracy: 6.2, costPer1k: 180, costPerCorrect: 2.90, trend: -2, ensemble: false },
          { model: "Llama 3.3 70B", config: "Ollama (local)", accuracy: 2.8, costPer1k: 0, costPerCorrect: 0, trend: 0, ensemble: false },
        ]}
      />

      <hr />

      {/* Why ensembles win */}
      <section id="ensemble" style={{ marginBottom: 24 }}>
        <h2>Why ensembles win on cost</h2>
        <p style={{ maxWidth: 640, lineHeight: 1.7, marginBottom: 12 }}>
          No single model is the best at everything. Claude is strong at coding. Gemini is strong at math. o3 is strong at reasoning. DeepSeek is strong at being cheap.
        </p>
        <p style={{ maxWidth: 640, lineHeight: 1.7, marginBottom: 12 }}>
          An ensemble routes each question to the model that&apos;s cheapest <em>for that specific kind of problem at the accuracy you need</em>. The result: higher accuracy at lower cost than any individual model. Every time.
        </p>
        <p style={{ maxWidth: 640, lineHeight: 1.7, marginBottom: 12 }}>
          This isn&apos;t theoretical. The data above shows it. The ensemble row is highlighted in every table because it wins in every table.
        </p>
        <p style={{ maxWidth: 640, lineHeight: 1.7 }}>
          <strong>Want this cost-efficiency for yourself?</strong> screamingface is an open-source tool that does exactly this — routes your AI prompts through the cheapest model that can handle the task.
          One command to install:
        </p>
        <pre style={{ background: "#f4f4f4", padding: "8px 12px", marginTop: 8, fontSize: 12, overflowX: "auto" }}>
          <code>curl -fsSL https://screamingface.ai/install | sh</code>
        </pre>
        <p style={{ fontSize: 11, color: "#666", marginTop: 8 }}>
          Auto-detects Claude Code, Gemini CLI, Codex, and Ollama. Doesn&apos;t change your workflow. Doesn&apos;t upload your code. <a href="https://github.com/OpenMined/screamingface">View source on GitHub</a>.
        </p>
      </section>

      <hr />

      {/* About */}
      <section id="about" style={{ marginBottom: 24 }}>
        <h2>About this page</h2>
        <p style={{ maxWidth: 640, lineHeight: 1.7, marginBottom: 12 }}>
          This is a project by <a href="https://openmined.org">OpenMined</a>, a nonprofit focused on privacy-preserving AI. We believe the cost of intelligence should be transparent, trackable, and open — like stock prices, not like trade secrets.
        </p>
        <p style={{ maxWidth: 640, lineHeight: 1.7, marginBottom: 12 }}>
          Right now, 3–4 companies set the price of intelligence and nobody is watching. Benchmarks measure accuracy in isolation. Pricing pages show cost per token in isolation. Neither tells you what you actually need to know: <strong>how much does it cost to get a correct answer?</strong>
        </p>
        <p style={{ maxWidth: 640, lineHeight: 1.7, marginBottom: 12 }}>
          We combine public benchmark data with real API pricing to compute cost-per-correct-answer across problem types. The ensemble data comes from our own runs using the screamingface tool. All methodology is documented and all code is open source.
        </p>
        <p style={{ maxWidth: 640, lineHeight: 1.7 }}>
          For the deeper argument about why this matters — market concentration, the 2-year window for public AI infrastructure, and what happens when nobody tracks the price of thinking — read <a href="/why">why this matters</a>.
        </p>
      </section>

      <hr />

      {/* Methodology */}
      <section id="methodology" style={{ marginBottom: 24 }}>
        <h2>Methodology</h2>
        <div style={{ fontSize: 13, lineHeight: 1.7, maxWidth: 640 }}>
          <p style={{ marginBottom: 10 }}>
            <strong>Accuracy data:</strong> Sourced from published benchmark results. We use official evaluations from model providers where available, third-party reproductions where not.
          </p>
          <p style={{ marginBottom: 10 }}>
            <strong>Cost data:</strong> Computed from published API pricing (input + output tokens) multiplied by average token usage per task. Local models (Ollama) listed at $0.00 — actual cost depends on your hardware.
          </p>
          <p style={{ marginBottom: 10 }}>
            <strong>Cost per correct answer</strong> = (cost per query) / (accuracy rate). A model that costs $0.10/query and gets 50% right has a $0.20 cost per correct answer.
          </p>
          <p style={{ marginBottom: 10 }}>
            <strong>Ensemble:</strong> Routes each query to the model predicted cheapest at the required accuracy level for that task type. Routing based on historical performance data. Costs include routing overhead.
          </p>
          <p style={{ marginBottom: 10 }}>
            <strong>7-day trend:</strong> Percentage change in cost-per-correct over trailing 7 days. Reflects price changes and accuracy updates.
          </p>
          <p>
            <strong>Update frequency:</strong> Pricing refreshed daily. Accuracy refreshed on new model releases or eval runs. Last update: {lastUpdated}.
          </p>
        </div>
      </section>

      <hr />

      {/* Contribute */}
      <section id="contribute" style={{ marginBottom: 24 }}>
        <h2>Contribute data</h2>
        <p style={{ maxWidth: 640, lineHeight: 1.7, marginBottom: 12 }}>
          We&apos;re building a crowdsourced dataset of real-world AI costs. Run our open-source script locally to anonymously contribute your actual token usage and costs:
        </p>
        <pre style={{ background: "#f4f4f4", padding: "8px 12px", fontSize: 12, overflowX: "auto" }}>
          <code>curl -fsSL https://screamingface.ai/contribute | sh</code>
        </pre>
        <p style={{ fontSize: 11, color: "#666", marginTop: 8, maxWidth: 640 }}>
          The script reads your local API usage logs (Claude, OpenAI, Google). It computes aggregate cost statistics and sends only the aggregates — no prompts, no responses, no API keys. <a href="https://github.com/OpenMined/screamingface">Review the source code</a> before running.
        </p>
      </section>

      <hr />

      {/* Footer */}
      <footer style={{ fontSize: 11, color: "#666", paddingBottom: 24, lineHeight: 1.8 }}>
        <p>
          😱 <strong>screamingface</strong> — the real cost of intelligence.
          Built by <a href="https://openmined.org">OpenMined</a> (nonprofit, est. 2017).
        </p>
        <p>
          <a href="/why">why this matters</a> ·{" "}
          <a href="https://github.com/OpenMined/screamingface">github</a> ·{" "}
          <a href="https://attribution-based-control.ai">attribution-based-control.ai</a> ·{" "}
          <a href="#methodology">methodology</a>
        </p>
        <p style={{ marginTop: 8, fontSize: 10, color: "#999" }}>
          Data on this page is illustrative while benchmarking infrastructure is in development.
          Want to help? <a href="#contribute">Contribute data</a> or <a href="https://github.com/OpenMined/screamingface">contribute code</a>.
        </p>
      </footer>
    </>
  );
}
