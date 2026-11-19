import type { Graph } from "./graph";
import type { Scene } from "./mapFile";

export type Theme = "dark" | "light";
export type Rgba = [number, number, number, number];

export interface ThemeColors {
  background: string;
  scenes: readonly string[];
  neutral: string;
  hops: readonly [string, string, string, string];
  path: string;
  ring: string;
  label: string;
  dimPointAlpha: number;
  dimLinkAlpha: number;
  mapLinkAlpha: number;
  crossLinkAlpha: number;
}

export const THEMES: Record<Theme, ThemeColors> = {
  dark: {
    background: "#0f1115",
    scenes: [
      "#3987e5",
      "#d95926",
      "#199e70",
      "#c98500",
      "#d55181",
      "#0ca30c",
      "#9085e9",
      "#e66767",
      "#1b98bb",
      "#78a10f",
      "#b86ad0",
      "#b4743a",
    ],
    neutral: "#6b7280",
    hops: ["#ffffff", "#ffc94d", "#4fc3f7", "#b39dff"],
    path: "#ff5c8a",
    ring: "#ffffff",
    label: "#e8eaef",
    dimPointAlpha: 0.14,
    dimLinkAlpha: 0.025,
    mapLinkAlpha: 0.16,
    crossLinkAlpha: 0.07,
  },
  light: {
    background: "#f6f7f9",
    scenes: [
      "#2a78d6",
      "#eb6834",
      "#1baf7a",
      "#eda100",
      "#e87ba4",
      "#008300",
      "#6250d6",
      "#e34948",
      "#1689a8",
      "#6b8f00",
      "#a24fc0",
      "#9a5f2a",
    ],
    neutral: "#9aa1ad",
    hops: ["#111418", "#c26a00", "#0b72b5", "#7c4dcc"],
    path: "#c2185b",
    ring: "#111418",
    label: "#1b1f27",
    dimPointAlpha: 0.2,
    dimLinkAlpha: 0.04,
    mapLinkAlpha: 0.22,
    crossLinkAlpha: 0.1,
  },
};

export const MAX_HOPS = 3;
export const HOP_POINT_ALPHA = [1, 1, 0.8, 0.4] as const;

export function hexToRgba(hex: string, alpha = 1): Rgba {
  const match = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!match) throw new Error(`not a #rrggbb colour: ${hex}`);
  const value = Number.parseInt(match[1], 16);
  return [((value >> 16) & 255) / 255, ((value >> 8) & 255) / 255, (value & 255) / 255, alpha];
}

export function sceneColors(scenes: readonly Scene[], theme: Theme): Map<number, string> {
  const palette = THEMES[theme].scenes;
  const ranked = [...scenes].sort((a, b) => b.size - a.size || a.id - b.id);
  const colors = new Map<number, string>();
  ranked.forEach((scene, rank) => {
    colors.set(scene.id, rank < palette.length ? palette[rank] : THEMES[theme].neutral);
  });
  return colors;
}

export function pointSize(nights: number, maxNights: number): number {
  const min = 2;
  const max = 12;
  if (maxNights <= 0) return min;
  return min + (max - min) * Math.sqrt(Math.max(0, nights) / maxNights);
}

export type View =
  | { kind: "map"; scene: number | null; inCity: Uint8Array | null }
  | { kind: "focus"; focus: number; hops: Int8Array }
  | { kind: "path"; focus: number; hops: Int8Array; path: readonly number[]; pathEdges: readonly number[] };

export interface Styling {
  emphasis: Set<number>;
  pointColors: Rgba[];
  linkColors: Rgba[];
  linkWidths: Float32Array;
}

export function styleGraph(
  graph: Graph,
  sceneOf: readonly (number | null)[],
  colors: Map<number, string>,
  view: View,
  theme: Theme,
): Styling {
  const t = THEMES[theme];
  const neutral = hexToRgba(t.neutral);
  const sceneRgba = new Map<number, Rgba>();
  for (const [id, hex] of colors) sceneRgba.set(id, hexToRgba(hex));
  const colorOf = (index: number): Rgba => {
    const scene = sceneOf[index];
    return (scene === null ? undefined : sceneRgba.get(scene)) ?? neutral;
  };
  const withAlpha = (c: Rgba, alpha: number): Rgba => [c[0], c[1], c[2], alpha];
  const dimPoint = withAlpha(neutral, t.dimPointAlpha);
  const dimLink = withAlpha(neutral, t.dimLinkAlpha);

  const pointColors: Rgba[] = new Array<Rgba>(graph.size);
  const linkColors: Rgba[] = new Array<Rgba>(graph.edgeCount);
  const linkWidths = new Float32Array(graph.edgeCount).fill(1);

  if (view.kind === "map") {
    const highlight = view.scene;
    const city = view.inCity;
    const shown = (i: number) => city === null || city[i] === 1;
    for (let i = 0; i < graph.size; i += 1) {
      pointColors[i] = shown(i) && (highlight === null || sceneOf[i] === highlight) ? colorOf(i) : dimPoint;
    }
    for (let e = 0; e < graph.edgeCount; e += 1) {
      const a = graph.edgeSource[e];
      const b = graph.edgeTarget[e];
      const same = sceneOf[a] !== null && sceneOf[a] === sceneOf[b];
      if (!shown(a) || !shown(b)) {
        linkColors[e] = dimLink;
      } else if (highlight === null) {
        linkColors[e] = same ? withAlpha(colorOf(a), t.mapLinkAlpha) : withAlpha(neutral, t.crossLinkAlpha);
      } else if (same && sceneOf[a] === highlight) {
        linkColors[e] = withAlpha(colorOf(a), Math.min(1, t.mapLinkAlpha * 2.5));
      } else {
        linkColors[e] = dimLink;
      }
    }
    return { emphasis: new Set(), pointColors, linkColors, linkWidths };
  }

  const hopRgba = t.hops.map((hex, hop) => hexToRgba(hex, HOP_POINT_ALPHA[hop]));
  const hopLinkAlpha = [1, 0.9, 0.18, 0.05];
  const { hops } = view;
  const onPath = view.kind === "path";

  for (let i = 0; i < graph.size; i += 1) {
    const h = hops[i];
    pointColors[i] = h >= 0 && !onPath ? hopRgba[h] : dimPoint;
  }
  for (let e = 0; e < graph.edgeCount; e += 1) {
    const ha = hops[graph.edgeSource[e]];
    const hb = hops[graph.edgeTarget[e]];
    if (onPath || ha < 0 || hb < 0) {
      linkColors[e] = dimLink;
      continue;
    }
    const h = Math.max(ha, hb, 1);
    linkColors[e] = withAlpha(hopRgba[h], hopLinkAlpha[h]);
    if (h === 1) linkWidths[e] = 2;
  }

  if (view.kind === "path") {
    const pathRgba = hexToRgba(t.path);
    const endRgba = hexToRgba(t.hops[0]);
    view.path.forEach((index, step) => {
      pointColors[index] = step === 0 || step === view.path.length - 1 ? endRgba : pathRgba;
    });
    for (const e of view.pathEdges) {
      linkColors[e] = pathRgba;
      linkWidths[e] = 4;
    }
  }

  const emphasis = new Set(view.kind === "path" ? view.path : [view.focus]);
  return { emphasis, pointColors, linkColors, linkWidths };
}
