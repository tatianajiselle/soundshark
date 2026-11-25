import { useMemo, useState } from "react";
import { relatedAtDegree, type DegreeEntry } from "../graph/degrees";
import type { Explorer } from "../graph/prepare";
import { formatNights } from "../graph/text";
import { SearchBox } from "./SearchBox";
import { Swatch } from "./Swatch";

interface Props {
  explorer: Explorer;
  colors: Map<number, string>;
  focus: number;
  target: number | null;
  path: readonly number[] | null;
  onFocus: (index: number) => void;
  onConnect: (index: number | null) => void;
  onClose: () => void;
  onFly?: () => void;
}

function ArtistButton({
  explorer,
  index,
  onFocus,
}: {
  explorer: Explorer;
  index: number;
  onFocus: (i: number) => void;
}) {
  return (
    <button type="button" className="link-button" onClick={() => onFocus(index)}>
      {explorer.map.artists[index].name}
    </button>
  );
}

type Degree = 1 | 2 | 3;
const DEGREES: { value: Degree; label: string; words: string }[] = [
  { value: 1, label: "1st", words: "one step" },
  { value: 2, label: "2nd", words: "two steps" },
  { value: 3, label: "3rd", words: "three steps" },
];
const LIST_SIZE = 10;

export function Panel({ explorer, colors, focus, target, path, onFocus, onConnect, onClose, onFly }: Props) {
  const artist = explorer.map.artists[focus];
  const scene = artist.scene === null ? undefined : explorer.sceneById.get(artist.scene);
  const [degree, setDegree] = useState<Degree>(1);
  const list = useMemo<{ entries: DegreeEntry[]; total: number }>(() => {
    if (degree === 1) {
      const direct = explorer.related[focus];
      return { entries: direct.map((e) => ({ index: e.index, score: e.score, via: null })), total: direct.length };
    }
    return relatedAtDegree(explorer.related, focus, degree, LIST_SIZE);
  }, [explorer.related, focus, degree]);
  const top = list.entries[0]?.score ?? 0;
  const words = DEGREES[degree - 1].words;

  return (
    <aside className="panel" aria-label={`About ${artist.name}`} data-testid="panel">
      <header className="panel-header">
        <div>
          <h2 className="panel-name">{artist.name}</h2>
          {artist.aliases.length > 0 && <p className="panel-aliases">Also listed as {artist.aliases.join(", ")}</p>}
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Back to the whole map">
          ×
        </button>
      </header>

      <dl className="panel-facts">
        <div>
          <dt>Nights</dt>
          <dd>{formatNights(artist.nights)}</dd>
        </div>
        <div>
          <dt>Scene</dt>
          <dd>
            {scene ? (
              <>
                <Swatch color={colors.get(scene.id)} /> {scene.label}
              </>
            ) : (
              "No scene"
            )}
          </dd>
        </div>
      </dl>

      <section className="panel-section" aria-label="Connect to another artist">
        <h3>Connect to…</h3>
        {target === null ? (
          <SearchBox
            explorer={explorer}
            colors={colors}
            label="Connect to another artist"
            placeholder="Another artist"
            exclude={focus}
            onChoose={(index) => onConnect(index)}
            testId="connect-search"
          />
        ) : (
          <div className="path" data-testid="path">
            {path === null ? (
              <p className="path-none">
                No path within the map between {artist.name} and {explorer.map.artists[target].name}.
              </p>
            ) : (
              <>
                <p className="path-summary">
                  {path.length - 1 === 1 ? "Directly related" : `${path.length - 1} steps apart`}
                </p>
                <ol className="path-steps">
                  {path.map((index, step) => (
                    <li key={index}>
                      {step > 0 && (
                        <span className="path-arrow" aria-hidden="true">
                          →{" "}
                        </span>
                      )}
                      <ArtistButton explorer={explorer} index={index} onFocus={onFocus} />
                    </li>
                  ))}
                </ol>
              </>
            )}
            {path !== null && path.length > 1 && onFly && (
              <button type="button" className="fly-button" onClick={onFly} data-testid="fly-path">
                Fly the path
              </button>
            )}
            <button type="button" className="text-button" onClick={() => onConnect(null)}>
              Clear the path
            </button>
          </div>
        )}
      </section>

      <section className="panel-section" aria-label="Most related">
        <div className="related-head">
          <h3>Most related</h3>
          <div className="degree-filter" role="group" aria-label="How far out">
            {DEGREES.map((d) => (
              <button
                key={d.value}
                type="button"
                aria-pressed={degree === d.value}
                aria-label={`${d.words} away`}
                onClick={() => setDegree(d.value)}
                data-testid={`degree-${d.value}`}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>
        {degree > 1 && list.total > 0 && (
          <p className="muted related-count" data-testid="related-count">
            {list.total > LIST_SIZE
              ? `Top ${LIST_SIZE} of ${list.total.toLocaleString("en-GB")} artists ${words} away`
              : `${list.total} ${list.total === 1 ? "artist" : "artists"} ${words} away`}
          </p>
        )}
        {list.entries.length === 0 ? (
          <p className="muted">
            {degree === 1 ? "No related artists in this map." : `No artists ${words} away in this map.`}
          </p>
        ) : (
          <ol className="related" data-testid="related">
            {list.entries.map((entry, rank) => {
              const other = explorer.map.artists[entry.index];
              return (
                <li key={entry.index}>
                  <span className="related-rank">{rank + 1}</span>
                  <button type="button" className="related-button" onClick={() => onFocus(entry.index)}>
                    <Swatch color={other.scene === null ? undefined : colors.get(other.scene)} />
                    <span className="related-name">
                      <span className="related-label">{other.name}</span>
                      {entry.via !== null && (
                        <span className="related-via"> via {explorer.map.artists[entry.via].name}</span>
                      )}
                    </span>
                    <span className="related-bar" aria-hidden="true">
                      <span style={{ width: `${top > 0 ? Math.max(4, (entry.score / top) * 100) : 0}%` }} />
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        )}
      </section>
    </aside>
  );
}
