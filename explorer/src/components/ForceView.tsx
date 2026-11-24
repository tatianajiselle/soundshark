import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { emphasisedEdges, layoutEdges, mainMask, placedMask, rgbaCss } from "../graph/force";
import type { Explorer } from "../graph/prepare";
import { THEMES, pointSize, type Styling, type Theme } from "../graph/styling";
import type { Camera } from "./MapView";
import { ZoomButtons } from "./ZoomButtons";
import { FlightCard } from "./FlightCard";
import { flightShot, spread, type Vec3 } from "../graph/space";
import { SpaceLabels, type Projector } from "./SpaceLabels";

interface Props {
  explorer: Explorer;
  styling: Styling;
  camera: Camera;
  theme: Theme;
  reducedMotion: boolean;
  onPick: (index: number) => void;
  onReady: () => void;
  flight: readonly number[] | null;
  onFlightEnd: () => void;
}

interface Node {
  id: number;
  x?: number;
  y?: number;
  z?: number;
  fx?: number;
  fy?: number;
  fz?: number;
}

interface Link {
  e: number;
  source: number | Node;
  target: number | Node;
}

type Instance = import("3d-force-graph").ForceGraph3DInstance;

const LINKS_PER_ARTIST = 3;
const FLY_MS = 1200;
const FIT_MS = 900;
const FLY_DISTANCE = 260;
const LINK_OPACITY = 0.7;
const ZOOM_STEP = 0.6;
const ZOOM_MS = 300;
const FLIGHT_DISTANCE = 230;
const FLIGHT_MOVE_MS = 1600;
const FLIGHT_HOLD_MS = 1800;

export function ForceView({
  explorer,
  styling,
  camera,
  theme,
  reducedMotion,
  onPick,
  onReady,
  flight,
  onFlightEnd,
}: Props) {
  const host = useRef<HTMLDivElement>(null);
  const graphRef = useRef<Instance | null>(null);
  const [settled, setSettled] = useState(false);
  const pickRef = useRef(onPick);
  const readyRef = useRef(onReady);
  const flightEndRef = useRef(onFlightEnd);
  const [flightStep, setFlightStep] = useState<{ path: readonly number[]; step: number } | null>(null);
  const stylingRef = useRef(styling);
  const t = THEMES[theme];
  const { graph } = explorer;

  const placed = useMemo(() => placedMask(explorer.map.artists), [explorer.map.artists]);
  const shown = useMemo(() => placed ?? mainMask(graph), [placed, graph]);

  const base = useMemo(() => {
    const nodes: Node[] = [];
    const nodeAt = new Map<number, Node>();
    for (let i = 0; i < graph.size; i += 1) {
      if (shown[i] !== 1) continue;
      const pos = explorer.map.artists[i].pos;
      const node: Node =
        pos === null ? { id: i } : { id: i, x: pos[0], y: pos[1], z: pos[2], fx: pos[0], fy: pos[1], fz: pos[2] };
      nodes.push(node);
      nodeAt.set(i, node);
    }
    const edges = layoutEdges(graph, explorer.related, shown, LINKS_PER_ARTIST);
    const links: Link[] = edges.map((e) => ({ e, source: graph.edgeSource[e], target: graph.edgeTarget[e] }));
    return { nodes, nodeAt, links, drawn: new Set(edges) };
  }, [graph, explorer.related, explorer.map.artists, shown]);

  const extra = useMemo<Link[]>(
    () =>
      emphasisedEdges(graph, styling, shown, base.drawn).map((e) => ({
        e,
        source: graph.edgeSource[e],
        target: graph.edgeTarget[e],
      })),
    [graph, styling, shown, base.drawn],
  );

  useEffect(() => {
    pickRef.current = onPick;
    readyRef.current = onReady;
    flightEndRef.current = onFlightEnd;
    stylingRef.current = styling;
  }, [onPick, onReady, onFlightEnd, styling]);

  const paint = useCallback(
    (instance: Instance) => {
      const { artists } = explorer.map;
      const { maxNights } = explorer;
      instance
        .backgroundColor(t.background)
        .nodeColor((node: object) => rgbaCss(stylingRef.current.pointColors[(node as Node).id]))
        .nodeVal((node: object) => {
          const id = (node as Node).id;
          const size = 1 + (pointSize(artists[id]?.nights ?? 0, maxNights) - 2) / 4;
          return stylingRef.current.emphasis.has(id) ? size * 2.5 : size;
        })
        .linkColor((link: object) => rgbaCss(stylingRef.current.linkColors[(link as Link).e]))
        .linkWidth((link: object) => (stylingRef.current.linkWidths[(link as Link).e] > 1 ? 0.6 : 0));
    },
    [explorer, t.background],
  );

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let alive = true;
    let observer: ResizeObserver | null = null;
    const { artists } = explorer.map;
    setSettled(false);
    import("3d-force-graph").then(({ default: ForceGraph3D }) => {
      if (!alive) return;
      const instance = new ForceGraph3D(el)
        .width(el.clientWidth)
        .height(el.clientHeight)
        .nodeId("id")
        .nodeLabel((node: object) => artists[(node as Node).id]?.name ?? "")
        .nodeRelSize(3)
        .nodeResolution(6)
        .nodeOpacity(1)
        .linkOpacity(LINK_OPACITY)
        .warmupTicks(placed === null ? 60 : 0)
        .cooldownTicks(placed === null ? 120 : 1)
        .cooldownTime(8000)
        .enableNodeDrag(false)
        .showNavInfo(false)
        .onNodeClick((node: object) => pickRef.current((node as Node).id))
        .onEngineStop(() => {
          for (const node of base.nodes) {
            node.fx = node.x;
            node.fy = node.y;
            node.fz = node.z;
          }
          performance.mark("explorer:3d-settled");
          document.documentElement.dataset.layout3d = "settled";
          setSettled(true);
        });
      paint(instance);
      instance.graphData({ nodes: base.nodes, links: base.links });
      graphRef.current = instance;
      observer = new ResizeObserver(() => instance.width(el.clientWidth).height(el.clientHeight));
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
  }, [base, explorer, paint, placed]);

  useEffect(() => {
    const instance = graphRef.current;
    if (instance) paint(instance);
  }, [paint, styling]);

  useEffect(() => {
    const instance = graphRef.current;
    if (!instance || !settled) return;
    instance.graphData({ nodes: base.nodes, links: extra.length === 0 ? base.links : [...base.links, ...extra] });
  }, [base, extra, settled]);

  useEffect(() => {
    const instance = graphRef.current;
    if (!instance || !settled || flight !== null) return;
    const controls = instance.controls() as { autoRotate: boolean; autoRotateSpeed: number };
    controls.autoRotate = camera.kind === "fit" && camera.indices === undefined && !reducedMotion;
    controls.autoRotateSpeed = 0.4;
    const ms = reducedMotion ? 0 : FIT_MS;
    if (camera.kind === "point") {
      const node = base.nodeAt.get(camera.index);
      if (!node || node.x === undefined) return;
      const x = node.x;
      const y = node.y ?? 0;
      const z = node.z ?? 0;
      const k = 1 + FLY_DISTANCE / (Math.hypot(x, y, z) || 1);
      instance.cameraPosition({ x: x * k, y: y * k, z: z * k }, { x, y, z }, reducedMotion ? 0 : FLY_MS);
    } else if (camera.kind === "fit" || camera.kind === "indices") {
      const only = camera.indices === undefined ? null : new Set(camera.indices);
      instance.zoomToFit(ms, 40, (node: object) => only === null || only.has((node as Node).id));
    }
  }, [camera, settled, reducedMotion, base.nodeAt, flight]);

  useEffect(() => {
    const instance = graphRef.current;
    if (!instance || !settled || flight === null) return;
    (instance.controls() as { autoRotate: boolean }).autoRotate = false;
    const at = (index: number): Vec3 | null => {
      const node = base.nodeAt.get(index);
      return node && node.x !== undefined ? { x: node.x, y: node.y ?? 0, z: node.z ?? 0 } : null;
    };
    const move = reducedMotion ? 0 : FLIGHT_MOVE_MS;
    let step = 0;
    let timer = 0;
    const go = () => {
      if (step >= flight.length) {
        setFlightStep(null);
        flightEndRef.current();
        return;
      }
      const here = at(flight[step]);
      if (here !== null) {
        const prev = step > 0 ? at(flight[step - 1]) : null;
        const next = step + 1 < flight.length ? at(flight[step + 1]) : null;
        instance.cameraPosition(flightShot(prev, here, next, FLIGHT_DISTANCE), here, move);
      }
      setFlightStep({ path: flight, step });
      step += 1;
      timer = window.setTimeout(go, move + FLIGHT_HOLD_MS);
    };
    timer = window.setTimeout(go, 0);
    return () => {
      window.clearTimeout(timer);
      setFlightStep(null);
    };
  }, [flight, settled, reducedMotion, base.nodeAt]);

  const projector = useCallback(() => graphRef.current as unknown as Projector | null, []);
  const nameOf = useCallback((id: number) => explorer.map.artists[id]?.name ?? "", [explorer.map.artists]);
  const weightOf = useCallback(
    (id: number) => 1 + Math.log2(1 + (explorer.map.artists[id]?.nights ?? 0)),
    [explorer.map.artists],
  );
  const emphasis = useCallback(() => stylingRef.current.emphasis, []);
  const radius = useMemo(
    () => spread(base.nodes.flatMap((n) => (n.x === undefined ? [] : [{ x: n.x, y: n.y ?? 0, z: n.z ?? 0 }]))),
    [base.nodes],
  );

  const zoom = useCallback(
    (direction: 1 | -1) => {
      const instance = graphRef.current;
      if (!instance) return;
      const target = (instance.controls() as { target: { x: number; y: number; z: number } }).target;
      const from = instance.cameraPosition();
      const k = direction === 1 ? ZOOM_STEP : 1 / ZOOM_STEP;
      instance.cameraPosition(
        {
          x: target.x + (from.x - target.x) * k,
          y: target.y + (from.y - target.y) * k,
          z: target.z + (from.z - target.z) * k,
        },
        { x: target.x, y: target.y, z: target.z },
        reducedMotion ? 0 : ZOOM_MS,
      );
    },
    [reducedMotion],
  );

  return (
    <>
      <div className="map map-3d" data-testid="map-3d" ref={host} />
      {settled && (
        <SpaceLabels
          projector={projector}
          points={base.nodes}
          nameOf={nameOf}
          weightOf={weightOf}
          emphasis={emphasis}
          radius={radius}
        />
      )}
      {settled && <ZoomButtons onZoom={zoom} />}
      {flightStep !== null && flight === flightStep.path && (
        <FlightCard explorer={explorer} path={flightStep.path} step={flightStep.step} onStop={onFlightEnd} />
      )}
      {!settled && (
        <div className="scene-loading" role="status" data-testid="scene-loading">
          Loading the scene…
        </div>
      )}
    </>
  );
}
