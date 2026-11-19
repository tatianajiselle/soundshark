import { useCallback, useEffect, useMemo, useRef } from "react";
import type { Explorer } from "../graph/prepare";
import { THEMES, pointSize, type Theme } from "../graph/styling";

interface Props {
  explorer: Explorer;
  colors: Map<number, string>;
  theme: Theme;
  focus: number | null;
  reducedMotion: boolean;
  onPick: (index: number) => void;
  onReady: () => void;
}

interface Node {
  id: number;
  x?: number;
  y?: number;
  z?: number;
}

type Instance = import("3d-force-graph").ForceGraph3DInstance;

const LINKS_PER_NODE = 4;
const FLY_MS = 1200;
const FLY_DISTANCE = 90;

export function ForceView({ explorer, colors, theme, focus, reducedMotion, onPick, onReady }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const graphRef = useRef<Instance | null>(null);
  const focusRef = useRef(focus);
  const pickRef = useRef(onPick);
  const readyRef = useRef(onReady);
  const t = THEMES[theme];
  const paintRef = useRef({ colorOf: (_: number) => t.neutral, background: t.background });

  const data = useMemo(() => {
    const { artists } = explorer.map;
    const nodes: Node[] = artists.map((_, id) => ({ id }));
    const seen = new Set<number>();
    const links: { source: number; target: number }[] = [];
    const n = artists.length;
    explorer.related.forEach((list, a) => {
      for (const { index: b } of list.slice(0, LINKS_PER_NODE)) {
        const key = a < b ? a * n + b : b * n + a;
        if (a === b || seen.has(key)) continue;
        seen.add(key);
        links.push({ source: a, target: b });
      }
    });
    return { nodes, links };
  }, [explorer]);

  const colorOf = useMemo(() => {
    const { sceneOf } = explorer;
    return (index: number) => {
      if (index === focus) return t.ring;
      const scene = sceneOf[index];
      return (scene === null ? undefined : colors.get(scene)) ?? t.neutral;
    };
  }, [explorer, colors, focus, t]);

  useEffect(() => {
    paintRef.current = { colorOf, background: t.background };
    pickRef.current = onPick;
    readyRef.current = onReady;
    focusRef.current = focus;
  }, [colorOf, t.background, onPick, onReady, focus]);

  const fly = useCallback(
    (node: Node | undefined) => {
      const graph = graphRef.current;
      if (!graph || !node || node.x === undefined) return;
      const x = node.x;
      const y = node.y ?? 0;
      const z = node.z ?? 0;
      const norm = Math.hypot(x, y, z) || 1;
      const k = 1 + FLY_DISTANCE / norm;
      graph.cameraPosition({ x: x * k, y: y * k, z: z * k }, { x, y, z }, reducedMotion ? 0 : FLY_MS);
    },
    [reducedMotion],
  );

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let alive = true;
    let observer: ResizeObserver | null = null;
    const { artists } = explorer.map;
    const maxNights = explorer.maxNights;
    import("3d-force-graph").then(({ default: ForceGraph3D }) => {
      if (!alive) return;
      const graph = new ForceGraph3D(el)
        .width(el.clientWidth)
        .height(el.clientHeight)
        .backgroundColor(paintRef.current.background)
        .nodeColor((node: object) => paintRef.current.colorOf((node as Node).id))
        .graphData(data)
        .nodeId("id")
        .nodeLabel((node: object) => artists[(node as Node).id]?.name ?? "")
        .nodeRelSize(1.5)
        .nodeVal((node: object) => {
          const size = pointSize(artists[(node as Node).id]?.nights ?? 0, maxNights);
          return 1 + (size - 2) / 5;
        })
        .nodeResolution(6)
        .nodeOpacity(0.9)
        .linkOpacity(0.12)
        .linkWidth(0)
        .linkColor(() => "#8a93a6")
        .warmupTicks(60)
        .cooldownTicks(120)
        .cooldownTime(8000)
        .enableNodeDrag(false)
        .showNavInfo(false)
        .onNodeClick((node: object) => pickRef.current((node as Node).id))
        .onEngineStop(() => {
          performance.mark("explorer:3d-settled");
          document.documentElement.dataset.layout3d = "settled";
          const current = focusRef.current;
          if (current !== null) fly(data.nodes[current]);
        });
      const controls = graph.controls() as { autoRotate: boolean; autoRotateSpeed: number };
      controls.autoRotate = !reducedMotion;
      controls.autoRotateSpeed = 0.4;
      graphRef.current = graph;
      observer = new ResizeObserver(() => graph.width(el.clientWidth).height(el.clientHeight));
      observer.observe(el);
      readyRef.current();
    });
    return () => {
      alive = false;
      observer?.disconnect();
      graphRef.current?._destructor();
      graphRef.current = null;
      delete document.documentElement.dataset.layout3d;
      el.replaceChildren();
    };
  }, [data, explorer, reducedMotion, fly]);

  useEffect(() => {
    graphRef.current?.backgroundColor(t.background).nodeColor((node: object) => colorOf((node as Node).id));
  }, [colorOf, t.background]);

  useEffect(() => {
    if (focus !== null) fly(data.nodes[focus]);
  }, [focus, data.nodes, fly]);

  return <div className="map map-3d" data-testid="map-3d" ref={host} />;
}
