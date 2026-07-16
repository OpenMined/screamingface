import {
  Boxes,
  FileCode,
  Flame,
  Key,
  Layers,
  Plug,
  Sparkles,
  Trophy,
  User,
} from "lucide-react";
import { ThemeToggle } from "./theme-toggle";

const navigation = [
  { label: "Ensembles", Icon: Boxes },
  { label: "Models", Icon: Layers },
  { label: "Leaderboard", Icon: Trophy },
  { label: "Scripts", Icon: FileCode, badge: "2" },
];

export default function Home() {
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <header className="brand-row">
          <button className="brand" type="button">
            <span className="brand-mark" aria-hidden="true">😱</span>
            <span className="brand-copy">
              <strong>ScreamingFace</strong>
              <small>the loudest ensemble hub</small>
            </span>
          </button>
          <ThemeToggle />
        </header>

        <nav className="primary-nav">
          {navigation.map(({ label, Icon, badge }) => (
            <button className="nav-item" type="button" key={label}>
              <Icon size={15} strokeWidth={2} />
              <span>{label}</span>
              {badge && <span className="nav-badge">{badge}</span>}
            </button>
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
            <button className="apply-button" type="button"><Sparkles size={11} /> Apply</button>
          </section>

          <div className="profile">
            <span className="avatar" aria-hidden="true"><User size={14} /></span>
            <span className="profile-copy"><strong>irina</strong><small>irina@openmined.org</small></span>
          </div>
        </footer>
      </aside>

      <main className="workspace" aria-label="Workspace" />
    </div>
  );
}
