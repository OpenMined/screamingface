import {
  ArrowRight,
  Boxes,
  ChevronRight,
  FileCode,
  Flame,
  Key,
  Layers,
  Lock,
  Plug,
  Sparkles,
  Trophy,
  User,
} from "lucide-react";
import Link from "next/link";
import { ThemeToggle } from "./theme-toggle";

const navigation = [
  { label: "Ensembles", href: "/ensembles/", Icon: Boxes },
  { label: "Models", href: "/models/", Icon: Layers },
  { label: "Leaderboard", href: "/leaderboard/", Icon: Trophy },
  { label: "Scripts", href: "/scripts/", Icon: FileCode, badge: "2" },
];

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

function HomeView() {
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

export default function Home() {
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <header className="brand-row">
          <Link className="brand" href="/">
            <span className="brand-mark" aria-hidden="true">😱</span>
            <span className="brand-copy">
              <strong>ScreamingFace</strong>
              <small>the loudest ensemble hub</small>
            </span>
          </Link>
          <ThemeToggle />
        </header>

        <nav className="primary-nav">
          {navigation.map(({ label, href, Icon, badge }) => (
            <Link className="nav-item" href={href} key={label}>
              <Icon size={15} strokeWidth={2} />
              <span>{label}</span>
              {badge && <span className="nav-badge">{badge}</span>}
            </Link>
          ))}
        </nav>

        <div className="sidebar-spacer" />

        <footer className="sidebar-footer">
          <section className="program-card">
            <div className="program-title"><Flame size={11} /><span>Monster Fusion Program</span></div>
            <p>Connect your key to use subsidized OpenMined compute.</p>
            <label className="key-field">
              <Key size={10} />
              <input type="password" placeholder="om-…" aria-label="OpenMined key" />
            </label>
            <button className="connect-button" type="button"><Plug size={11} /> Connect OpenMined</button>
            <a className="apply-button" href="https://openmined.org" target="_blank" rel="noreferrer"><Sparkles size={11} /> Apply</a>
          </section>

          <div className="profile">
            <span className="avatar" aria-hidden="true"><User size={14} /></span>
            <span className="profile-copy"><strong>irina</strong><small>irina@openmined.org</small></span>
          </div>
        </footer>
      </aside>

      <main className="workspace" aria-label="Workspace">
        <HomeView />
      </main>
    </div>
  );
}
