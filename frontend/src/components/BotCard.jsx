import React from "react";

/**
 * BotCard — selectable card for Bot 1 or Bot 2.
 *
 * Props:
 *   id        "bot1" | "bot2"
 *   title     display name
 *   subtitle  short description
 *   selected  boolean
 *   running   boolean (shows green pulse when running)
 *   onSelect  () => void
 */
export default function BotCard({ id, title, subtitle, selected, running, onSelect }) {
  return (
    <button
      id={`card-${id}`}
      onClick={onSelect}
      className={`
        relative w-full rounded-2xl p-6 text-left transition-all duration-300
        border-2
        ${
          selected
            ? "border-brand-500 bg-brand-500/10 shadow-lg shadow-brand-500/20"
            : "border-surface-700 bg-surface-900 hover:border-surface-500 hover:bg-surface-800"
        }
      `}
    >
      {/* Running indicator */}
      {running && (
        <span className="absolute top-4 right-4 flex h-3 w-3">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex h-3 w-3 rounded-full bg-emerald-500" />
        </span>
      )}

      <h3 className="text-lg font-bold text-surface-50">{title}</h3>
      <p className="mt-1 text-sm text-surface-400">{subtitle}</p>

      {/* Status badge */}
      <div className="mt-4">
        {running ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-semibold text-emerald-400">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse-slow" />
            RUNNING
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-700 px-3 py-1 text-xs font-semibold text-surface-400">
            <span className="h-1.5 w-1.5 rounded-full bg-surface-500" />
            STOPPED
          </span>
        )}
      </div>
    </button>
  );
}
