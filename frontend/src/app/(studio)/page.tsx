import { ArrowRight, ChevronRight, Lock } from "lucide-react";
import Link from "next/link";

const providerColors: Record<string, string> = {
  anthropic: "#ca492c",
  deepmind: "#6976ae",
  openai: "#53bea9",
  ollama: "#52aec5",
  mistral: "#f79763",
};

const topEnsembles = [
  { recipe: "private-data-bridge-v1", author: "siddhant_r", models: ["anthropic", "deepmind", "openai"], benchmark: "GPQA Diamond", uplift: "25.6", private: true },
  { recipe: "5-model-heavy", author: "fusion_hunter", models: ["anthropic", "deepmind", "openai", "ollama", "mistral"], benchmark: "GPQA Diamond", uplift: "22.1" },
  { recipe: "llama-boost-v2", author: "tauquir_m", models: ["ollama", "openai"], benchmark: "GPQA Diamond", uplift: "21.9" },
  { recipe: "claude-gemini-fusion", author: "mwatson", models: ["anthropic", "deepmind"], benchmark: "GPQA Diamond", uplift: "19.9" },
  { recipe: "opus-gemini-v3", author: "elena_k", models: ["anthropic", "deepmind"], benchmark: "GPQA Diamond", uplift: "15.0" },
  { recipe: "code-triad", author: "dmitry_b", models: ["anthropic", "openai", "deepmind"], benchmark: "HumanEval+", uplift: "3.6" },
];

export default function HomePage() {
  return (
    <div className="home-view">
      <section className="home-hero">
        <div className="home-kicker">
          <span className="home-kicker-emoji" aria-hidden="true">😱</span>
          <span className="home-kicker-brand">ScreamingFace</span>
          <span className="home-kicker-tagline">· the loudest ensemble hub</span>
        </div>

        <h1>Ensembles that beat any single model.</h1>

        <div className="home-actions">
          <Link className="home-primary-action" href="/ensembles/new/">Compose an ensemble <ArrowRight size={14} /></Link>
          <Link className="home-secondary-action" href="/leaderboard/">View leaderboard</Link>
        </div>
        <div className="home-stats">9,431 ensembles · 184k evals run · 0 of them calm</div>
      </section>

      <section className="top-section">
        <header className="top-heading">
          <div>
            <h2>Top ensembles</h2>
            <p>Ranked by gain over the best single model.</p>
          </div>
          <Link className="all-results" href="/leaderboard/">All results <ChevronRight size={15} /></Link>
        </header>

        <div className="ensemble-list">
          {topEnsembles.map((ensemble, index) => (
            <Link className="ensemble-row" href={`/leaderboard/?ensemble=${encodeURIComponent(ensemble.recipe)}`} key={ensemble.recipe}>
              <span className="ensemble-rank">{index + 1}</span>
              <span className="ensemble-details">
                <span className="ensemble-name-line">
                  <span className="ensemble-name">{ensemble.recipe}</span>
                  {ensemble.private && <Lock className="private-icon" size={11} />}
                </span>
                <span className="ensemble-meta">
                  <span className="provider-dots" aria-hidden="true">
                    {ensemble.models.map((provider, dotIndex) => (
                      <span className="provider-dot" key={`${provider}-${dotIndex}`} style={{ background: providerColors[provider] }} />
                    ))}
                  </span>
                  <span className="model-count">{ensemble.models.length} models</span>
                  <span className="meta-divider">·</span>
                  <span className="ensemble-author">by {ensemble.author}</span>
                </span>
              </span>
              <span className="ensemble-benchmark">{ensemble.benchmark}</span>
              <span className="ensemble-uplift">+{ensemble.uplift}</span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
