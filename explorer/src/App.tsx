import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { About, Footer } from "./components/About";
import { CityToggle } from "./components/CityToggle";
import { Legend } from "./components/Legend";
import { MapView, type Camera } from "./components/MapView";
import { Panel } from "./components/Panel";
import { SearchBox } from "./components/SearchBox";
import { ForceView } from "./components/ForceView";
import { loadExplorer, type Loaded, LoadError } from "./load";
import { edgesAlong, hopsFrom, shortestPath } from "./graph/graph";
import { basedIn, inCity } from "./graph/prepare";
import { MAX_HOPS, sceneColors, styleGraph, type View } from "./graph/styling";
import { formatHash, parseHash, type UrlState } from "./graph/urlState";
import { useMediaQuery } from "./useMediaQuery";

const VIEW_KEY = "soundshark:view";
type Mode = "2d" | "3d";

function savedMode(): Mode {
  try {
    return window.localStorage.getItem(VIEW_KEY) === "2d" ? "2d" : "3d";
  } catch {
    return "3d";
  }
}

function saveMode(mode: Mode): boolean {
  try {
    window.localStorage.setItem(VIEW_KEY, mode);
  } catch {
    return false;
  }
  return true;
}

type State = { status: "loading" } | { status: "error"; error: LoadError } | { status: "ready"; loaded: Loaded };

function useUrlState(): [UrlState, (next: UrlState) => void] {
  const [url, setUrl] = useState(() => parseHash(window.location.hash));
  useEffect(() => {
    const sync = () => setUrl(parseHash(window.location.hash));
    window.addEventListener("hashchange", sync);
    window.addEventListener("popstate", sync);
    return () => {
      window.removeEventListener("hashchange", sync);
      window.removeEventListener("popstate", sync);
    };
  }, []);
  const navigate = useCallback((next: UrlState) => {
    const hash = formatHash(next);
    if (hash !== window.location.hash) {
      window.history.pushState(null, "", hash === "" ? window.location.pathname + window.location.search : hash);
    }
    setUrl(next);
  }, []);
  return [url, navigate];
}

export function App() {
  const [state, setState] = useState<State>({ status: "loading" });
  const [rendered, setRendered] = useState(false);

  useEffect(() => {
    let alive = true;
    loadExplorer().then(
      (loaded) => alive && setState({ status: "ready", loaded }),
      (error: unknown) =>
        alive &&
        setState({
          status: "error",
          error: error instanceof LoadError ? error : new LoadError("Something went wrong.", String(error)),
        }),
    );
    return () => {
      alive = false;
    };
  }, []);

  const status = state.status === "ready" && !rendered ? "drawing" : state.status;
  useEffect(() => {
    document.documentElement.dataset.status = status;
  }, [status]);

  const onReady = useCallback(() => {
    performance.mark("explorer:rendered");
    performance.measure("explorer:first-render", "explorer:start", "explorer:rendered");
    setRendered(true);
  }, []);

  if (state.status === "error") {
    return (
      <main className="error-state" role="alert" data-testid="error">
        <h1>{state.error.message}</h1>
        <p>{state.error.detail}</p>
      </main>
    );
  }

  return (
    <>
      {state.status === "ready" && <Ready loaded={state.loaded} onReady={onReady} />}
      {!rendered && (
        <div className="loading" role="status" data-testid="loading">
          <span className="spinner" aria-hidden="true" />
          {state.status === "loading" ? "Loading the map…" : "Drawing the map…"}
        </div>
      )}
    </>
  );
}

function Ready({ loaded, onReady }: { loaded: Loaded; onReady: () => void }) {
  const { explorer, tables, connection } = loaded;
  const { graph, map } = explorer;
  const dark = useMediaQuery("(prefers-color-scheme: dark)", true);
  const theme = dark ? "dark" : "light";
  const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)", false);
  const [url, navigate] = useUrlState();
  const [highlight, setHighlight] = useState<number | null>(null);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [mode, setMode] = useState<Mode>(savedMode);
  const switchMode = useCallback(() => {
    const next = mode === "2d" ? "3d" : "2d";
    saveMode(next);
    setMode(next);
  }, [mode]);
  const searchInput = useRef<HTMLInputElement>(null);

  const colors = useMemo(() => sceneColors(map.scenes, theme), [map.scenes, theme]);
  const city = url.city !== null && explorer.cities.includes(url.city) ? url.city : null;
  const cityMask = useMemo(() => (city === null ? null : inCity(map, city)), [map, city]);
  const cityArea = useMemo(() => (city === null ? undefined : basedIn(map, city)), [map, city]);
  const focus = url.a === null ? null : (graph.indexById.get(url.a) ?? null);
  const target = focus === null || url.b === null ? null : (graph.indexById.get(url.b) ?? null);
  const missing = (url.a !== null && focus === null) || (url.b !== null && focus !== null && target === null);

  const path = useMemo(
    () => (focus === null || target === null ? null : shortestPath(graph, focus, target)),
    [graph, focus, target],
  );

  const view = useMemo<View>(() => {
    if (focus === null) return { kind: "map", scene: highlight, inCity: cityMask };
    const hops = hopsFrom(graph, focus, MAX_HOPS);
    if (path !== null && path.length > 1) {
      return { kind: "path", focus, hops, path, pathEdges: edgesAlong(graph, path) };
    }
    return { kind: "focus", focus, hops };
  }, [graph, focus, path, highlight, cityMask]);

  const styling = useMemo(
    () => styleGraph(graph, explorer.sceneOf, colors, view, theme),
    [graph, explorer.sceneOf, colors, view, theme],
  );

  const labelsFor = useMemo(() => {
    if (view.kind === "map") return undefined;
    const indices =
      view.kind === "path" ? view.path : [view.focus, ...explorer.related[view.focus].map((r) => r.index)];
    return indices.map((i) => String(graph.ids[i]));
  }, [view, explorer.related, graph.ids]);

  const camera = useMemo<Camera>(() => {
    if (focus === null) return { kind: "fit", indices: cityArea };
    if (path !== null && path.length > 1) return { kind: "indices", indices: path };
    return { kind: "point", index: focus };
  }, [focus, path, cityArea]);

  const focusOn = useCallback(
    (index: number) => {
      setHighlight(null);
      navigate({ a: graph.ids[index], b: null, city });
    },
    [graph.ids, navigate, city],
  );

  const connect = useCallback(
    (index: number | null) => {
      if (url.a === null) return;
      navigate({ a: url.a, b: index === null ? null : graph.ids[index], city });
    },
    [graph.ids, navigate, url.a, city],
  );

  const backToMap = useCallback(() => navigate({ a: null, b: null, city }), [navigate, city]);
  const chooseCity = useCallback(
    (next: string | null) => {
      setHighlight(null);
      navigate({ a: null, b: null, city: next });
    },
    [navigate],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || aboutOpen) return;
      const typing = event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement;
      if (event.key === "Escape") {
        if (focus !== null || url.a !== null) backToMap();
        else if (highlight !== null) setHighlight(null);
      } else if (event.key === "/" && !typing) {
        event.preventDefault();
        searchInput.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [aboutOpen, backToMap, focus, highlight, url.a]);

  useEffect(() => {
    const parts = [focus === null ? null : map.artists[focus].name, "SoundShark explorer"];
    if (target !== null && focus !== null) parts[0] = `${map.artists[focus].name} → ${map.artists[target].name}`;
    document.title = parts.filter(Boolean).join(" · ");
  }, [focus, target, map.artists]);

  return (
    <div className={focus === null ? "app" : "app has-panel"} data-theme-mode={theme}>
      {mode === "2d" ? (
        <MapView
          explorer={explorer}
          tables={tables}
          connection={connection}
          styling={styling}
          labelsFor={labelsFor}
          path={view.kind === "path" ? view.path : null}
          focus={focus}
          camera={camera}
          theme={theme}
          reducedMotion={reducedMotion}
          onPick={focusOn}
          onReady={onReady}
        />
      ) : (
        <ForceView
          explorer={explorer}
          styling={styling}
          camera={camera}
          theme={theme}
          reducedMotion={reducedMotion}
          onPick={focusOn}
          onReady={onReady}
        />
      )}

      <header className="topbar">
        <h1 className="brand">
          SoundShark <span>explorer</span>
        </h1>
        <SearchBox
          explorer={explorer}
          colors={colors}
          label="Search artists"
          placeholder={`Search ${map.artists.length.toLocaleString("en-GB")} artists`}
          onChoose={focusOn}
          inputRef={searchInput}
          testId="search"
        />
        <CityToggle cities={explorer.cities} city={city} onChoose={chooseCity} />
        <button
          type="button"
          className="mode-toggle"
          data-testid="mode-toggle"
          aria-label={mode === "3d" ? "Switch to the 2D map" : "Switch to the 3D map"}
          onClick={switchMode}
        >
          {mode === "3d" ? "2D" : "3D"}
        </button>
        {missing && (
          <p className="notice" role="status">
            That artist isn’t in this map.
          </p>
        )}
      </header>

      {focus !== null && (
        <Panel
          explorer={explorer}
          colors={colors}
          focus={focus}
          target={target}
          path={path}
          onFocus={focusOn}
          onConnect={connect}
          onClose={backToMap}
        />
      )}

      <Legend
        explorer={explorer}
        colors={colors}
        theme={theme}
        mode={view.kind}
        highlight={highlight}
        onHighlight={setHighlight}
      />

      <Footer credits={map.credits} generatedAt={map.generatedAt} onAbout={() => setAboutOpen(true)} />
      <About
        open={aboutOpen}
        onClose={() => setAboutOpen(false)}
        credits={map.credits}
        generatedAt={map.generatedAt}
        artists={map.artists.length}
      />
    </div>
  );
}
