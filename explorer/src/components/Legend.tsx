import { useState } from "react";
import type { Explorer } from "../graph/prepare";
import { THEMES, type Theme } from "../graph/styling";
import { formatCount } from "../graph/text";
import { Swatch } from "./Swatch";

interface Props {
  explorer: Explorer;
  colors: Map<number, string>;
  theme: Theme;
  mode: "map" | "focus" | "path";
  highlight: number | null;
  onHighlight: (scene: number | null) => void;
}

const HOP_LABELS = ["Chosen artist", "1 hop away", "2 hops away", "3 hops away"];

export function Legend({ explorer, colors, theme, mode, highlight, onHighlight }: Props) {
  const [open, setOpen] = useState(() => !window.matchMedia("(max-width: 700px)").matches);
  const scenes = [...explorer.map.scenes].sort((a, b) => b.size - a.size || a.id - b.id);
  const t = THEMES[theme];

  return (
    <details
      className="legend"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
      data-testid="legend"
    >
      <summary>{mode === "map" ? `Scenes (${scenes.length})` : mode === "focus" ? "Hops" : "Path"}</summary>
      {mode === "map" && (
        <>
          <ul className="legend-scenes">
            {scenes.map((scene) => {
              const active = highlight === scene.id;
              return (
                <li key={scene.id}>
                  <button
                    type="button"
                    className={active ? "legend-scene active" : "legend-scene"}
                    aria-pressed={active}
                    onClick={() => onHighlight(active ? null : scene.id)}
                  >
                    <Swatch color={colors.get(scene.id)} />
                    <span className="legend-label">{scene.label}</span>
                    <span className="legend-size">{scene.size.toLocaleString("en-GB")}</span>
                  </button>
                </li>
              );
            })}
          </ul>
          {explorer.withoutScene > 0 && (
            <p className="legend-note">
              <Swatch color={t.neutral} /> {formatCount(explorer.withoutScene, "artist", "artists")} without a scene
            </p>
          )}
          {highlight !== null && (
            <button type="button" className="text-button" onClick={() => onHighlight(null)}>
              Show all scenes
            </button>
          )}
        </>
      )}
      {mode === "focus" && (
        <ul className="legend-hops">
          {HOP_LABELS.map((label, hop) => (
            <li key={label}>
              <Swatch color={t.hops[hop]} /> {label}
            </li>
          ))}
        </ul>
      )}
      {mode === "path" && (
        <ul className="legend-hops">
          <li>
            <Swatch color={t.hops[0]} /> The two artists
          </li>
          <li>
            <Swatch color={t.path} /> In between
          </li>
        </ul>
      )}
    </details>
  );
}
