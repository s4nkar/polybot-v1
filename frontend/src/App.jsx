import React from "react";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import Launcher from "./pages/Launcher";
import Analytics from "./pages/Analytics";
import Settings from "./pages/Settings";

export default function App() {
  const navLinkCls = ({ isActive }) =>
    `px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${isActive
      ? "bg-brand-500/15 text-brand-400"
      : "text-surface-400 hover:text-surface-200 hover:bg-surface-800"
    }`;

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-surface-950">
        {/* Top nav */}
        <nav className="sticky top-0 z-50 border-b border-surface-800 bg-surface-950/80 backdrop-blur-xl">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3">
            {/* Logo */}
            <div className="flex items-center gap-2">
              <span className="text-xl">🤖</span>
              <span className="text-lg font-extrabold tracking-tight">
                <span className="bg-gradient-to-r from-brand-400 to-brand-600 bg-clip-text text-transparent">Poly</span>
                <span className="text-surface-200">bot</span>
              </span>
            </div>

            {/* Links */}
            <div className="flex items-center gap-1">
              <NavLink to="/" className={navLinkCls} end>
                Dashboard
              </NavLink>
              <NavLink to="/analytics" className={navLinkCls}>
                Analytics
              </NavLink>
              <NavLink to="/settings" className={navLinkCls}>
                Settings
              </NavLink>
            </div>
          </div>
        </nav>

        {/* Main content */}
        <main className="mx-auto max-w-6xl px-6 py-8">
          <Routes>
            <Route path="/" element={<Launcher />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>

        {/* Footer */}
        <footer className="border-t border-surface-800 py-6 text-center text-xs text-surface-500">
          Polybot v1.0 — Automated Polymarket Trading
        </footer>
      </div>
    </BrowserRouter>
  );
}
