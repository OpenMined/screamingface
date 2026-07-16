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
import Link from "next/link";
import { ThemeToggle } from "./theme-toggle";

const navigation = [
  { label: "Ensembles", href: "/ensembles/", Icon: Boxes },
  { label: "Models", href: "/models/", Icon: Layers },
  { label: "Leaderboard", href: "/leaderboard/", Icon: Trophy },
  { label: "Scripts", href: "/scripts/", Icon: FileCode, badge: "2" },
];

export function AppSidebar() {
  return (
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
  );
}
