import { Cosmograph, type CosmographProps } from "@cosmograph/react";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DuckDBConnection } from "../cosmograph/duckdb";
import type { GraphTables } from "../cosmograph/tables";
import type { Explorer } from "../graph/prepare";
import { boundsOf, closestStep, framingBox, insetsFrom } from "../graph/camera";
import { mainIndices } from "../graph/graph";
import { THEMES, pointSize, type Rgba, type Styling, type Theme } from "../graph/styling";
import { ZoomButtons } from "./ZoomButtons";
import { PathLabels } from "./PathLabels";

type CosmographInstance = Parameters<NonNullable<CosmographProps["onMount"]>>[0];

export type Camera =
  | { kind: "fit"; indices?: readonly number[] }
  | { kind: "point"; index: number }
  | { kind: "indices"; indices: readonly number[] }
  | { kind: "stay" };

interface Props {
  explorer: Explorer;
  tables: GraphTables;
  connection: DuckDBConnection;
  styling: Styling;
  labelsFor: string[] | undefined;
  path: readonly number[] | null;
  focus: number | null;
  camera: Camera;
  theme: Theme;
  reducedMotion: boolean;
  onPick: (index: number) => void;
  onReady: () => void;
}

const HIDDEN: Rgba = [0, 0, 0, 0];
const FOLLOW_EVERY_MS = 1500;
const FOLLOW_DURATION_MS = 500;
const ZOOM_FACTOR = 1.6;
const ZOOM_MS = 250;

const OVERLAYS = ".topbar, .legend, .panel, .footer";
const LABEL_ROOM = 30;

function frame(
  cosmograph: CosmographInstance,
  container: HTMLElement,
  indices: readonly number[],
  padding: number,
  duration: number,
  separate: boolean,
) {
  const positions = cosmograph.getPointPositions();
  const bounds = positions ? boundsOf(positions, indices) : null;
  const origin = cosmograph.spaceToScreenPosition([0, 0]);
  const up = cosmograph.spaceToScreenPosition([0, 1]);
  if (!bounds || !origin || !up) return;
  const rect = container.getBoundingClientRect();
  const overlays = Array.from(document.querySelectorAll<HTMLElement>(OVERLAYS), (el) => el.getBoundingClientRect());
  const covered = insetsFrom(rect, overlays);
  const insets = separate ? { ...covered, top: covered.top + LABEL_ROOM } : covered;
  const pair = separate && positions ? closestStep(positions, indices) : null;
  const separation = pair ? { pair, pixels: 70, maxBoost: 1.2 } : undefined;
  const box = framingBox(bounds, rect.width, rect.height, insets, padding, up[1] < origin[1], separation);
  cosmograph.setZoomTransformByPointPositions(new Float32Array(box), duration, undefined, 0);
}

function moveCamera(
  cosmograph: CosmographInstance,
  container: HTMLElement | null,
  main: readonly number[],
  camera: Camera,
  duration: number,
) {
  if (camera.kind === "point") cosmograph.zoomToPoint(camera.index, duration, 3, true);
  else if (container && camera.kind === "indices") frame(cosmograph, container, camera.indices, 0.3, duration, true);
  else if (container && camera.kind === "fit")
    frame(cosmograph, container, camera.indices ?? main, 0.04, duration, false);
}

function MapViewInner({
  explorer,
  tables,
  connection,
  styling,
  labelsFor,
  path,
  focus,
  camera,
  theme,
  reducedMotion,
  onPick,
  onReady,
}: Props) {
  const [tracker, setTracker] = useState<CosmographInstance | null>(null);
  const instance = useRef<CosmographInstance | null>(null);
  const container = useRef<HTMLDivElement>(null);
  const main = useMemo(() => mainIndices(explorer.graph), [explorer.graph]);
  const mainRef = useRef(main);
  const [ready, setReady] = useState(false);
  const [settled, setSettled] = useState(false);
  const onPickRef = useRef(onPick);
  const onReadyRef = useRef(onReady);
  const cameraRef = useRef<{ camera: Camera; reducedMotion: boolean; userMoved: boolean; lastFollow: number }>({
    camera,
    reducedMotion,
    userMoved: false,
    lastFollow: 0,
  });

  useEffect(() => {
    onPickRef.current = onPick;
    onReadyRef.current = onReady;
    mainRef.current = main;
  }, [onPick, onReady, main]);

  const handlers = useMemo(
    () => ({
      onMount: (cosmograph: CosmographInstance) => {
        instance.current = cosmograph;
        setTracker(cosmograph);
      },
      onZoomStart: (_event: unknown, userDriven: boolean) => {
        if (userDriven) cameraRef.current.userMoved = true;
      },
      onSimulationTick: () => {
        const state = cameraRef.current;
        const cosmograph = instance.current;
        const now = performance.now();
        if (!cosmograph || state.userMoved || state.reducedMotion || now - state.lastFollow < FOLLOW_EVERY_MS) return;
        state.lastFollow = now;
        moveCamera(cosmograph, container.current, mainRef.current, state.camera, FOLLOW_DURATION_MS);
      },
      onClick: (index: number | undefined) => {
        if (index !== undefined) onPickRef.current(index);
      },
      onGraphRebuilt: () => {
        setReady(true);
        onReadyRef.current();
      },
      onSimulationEnd: () => {
        performance.mark("explorer:settled");
        document.documentElement.dataset.layout = "settled";
        setSettled(true);
      },
    }),
    [],
  );

  const maxNights = explorer.maxNights;
  const big = explorer.graph.size > 20_000;
  const artists = explorer.map.artists;
  const sizeFn = useMemo(
    () => (index: number) => {
      const base = pointSize(artists[index]?.nights ?? 0, maxNights) * (big ? 0.7 : 1);
      return styling.emphasis.has(index) ? Math.max(base, 12) : base;
    },
    [artists, maxNights, big, styling],
  );
  const pointColorFn = useMemo(() => (value: number) => styling.pointColors[value] ?? HIDDEN, [styling]);
  const linkColorFn = useMemo(() => (value: number) => styling.linkColors[value] ?? HIDDEN, [styling]);
  const linkWidthFn = useMemo(() => (value: number) => styling.linkWidths[value] ?? 1, [styling]);

  const t = THEMES[theme];
  const focused = labelsFor !== undefined;
  const onPath = path !== null;
  const pathNames = useMemo(() => (path ? path.map((i) => artists[i]?.name ?? "") : []), [path, artists]);

  const config = useMemo<CosmographProps>(
    () => ({
      ...handlers,
      duckDBConnection: connection,
      points: tables.points,
      links: tables.links,
      pointIdBy: "id",
      pointIndexBy: "idx",
      pointLabelBy: "label",
      pointLabelWeightBy: "nights",
      pointSizeBy: "idx",
      pointSizeByFn: sizeFn,
      pointColorBy: "idx",
      pointColorByFn: pointColorFn,
      linkSourceBy: "source",
      linkSourceIndexBy: "sourceidx",
      linkTargetBy: "target",
      linkTargetIndexBy: "targetidx",
      linkColorBy: "edge",
      linkColorByFn: linkColorFn,
      linkWidthBy: "edge",
      linkWidthByFn: linkWidthFn,
      backgroundColor: t.background,
      focusedPointRingColor: t.ring,
      hoveredPointRingColor: t.ring,
      renderHoveredPointRing: true,
      hoveredPointCursor: "pointer",
      pointLabelColor: t.label,
      pointLabelClassName: "map-label",
      hoveredPointLabelClassName: "map-label map-label-hover",
      showHoveredPointLabel: true,
      showLabels: !onPath,
      showLabelsFor: labelsFor,
      showTopLabels: !focused,
      showTopLabelsLimit: 16,
      showDynamicLabels: !focused,
      showDynamicLabelsLimit: 12,
      showFocusedPointLabel: !onPath,
      selectPointOnClick: false,
      focusPointOnClick: false,
      resetSelectionOnEmptyCanvasClick: false,
      linkVisibilityMinTransparency: focused ? 1 : 0.4,
      scalePointsOnZoom: false,
      simulationDecay: big ? 3000 : 2000,
      simulationRepulsion: 1.2,
      simulationLinkSpring: 1,
      simulationLinkDistance: 10,
      simulationGravity: 0.1,
      simulationFriction: 0.85,
      spaceSize: big ? 8192 : 4096,
      fitViewOnInit: false,
      statusIndicatorMode: false,
      disableLogging: true,
      randomSeed: 7,
    }),
    [handlers, connection, tables, sizeFn, pointColorFn, linkColorFn, linkWidthFn, t, labelsFor, focused, onPath, big],
  );

  useEffect(() => {
    const state = cameraRef.current;
    state.reducedMotion = reducedMotion;
    if (state.camera !== camera) {
      state.camera = camera;
      state.userMoved = false;
    }
    const cosmograph = instance.current;
    if (!ready || !cosmograph || (settled && state.userMoved)) return;
    state.lastFollow = performance.now();
    moveCamera(cosmograph, container.current, main, camera, reducedMotion ? 0 : 700);
  }, [camera, ready, settled, reducedMotion, main]);

  useEffect(() => {
    if (ready) instance.current?.setFocusedPoint(focus ?? undefined);
  }, [focus, ready, settled]);

  const zoom = useCallback((direction: 1 | -1) => {
    const cosmograph = instance.current;
    const level = cosmograph?.getZoomLevel();
    if (!cosmograph || level === undefined) return;
    cameraRef.current.userMoved = true;
    cosmograph.setZoomLevel(
      direction === 1 ? level * ZOOM_FACTOR : level / ZOOM_FACTOR,
      cameraRef.current.reducedMotion ? 0 : ZOOM_MS,
    );
  }, []);

  return (
    <div className="map" data-testid="map" ref={container}>
      <Cosmograph className="map-canvas" {...config} />
      {ready && <ZoomButtons onZoom={zoom} />}
      {path && ready && <PathLabels tracker={tracker} path={path} names={pathNames} everyMs={big ? 50 : 0} />}
    </div>
  );
}

export const MapView = memo(MapViewInner);
