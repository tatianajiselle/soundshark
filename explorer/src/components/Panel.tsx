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

export function Panel({ explorer, colors, focus, target, path, onFocus, onConnect, onClose, onFly }: Props) {
  const artist = explorer.map.artists[focus];
  const scene = artist.scene === null ? undefined : explorer.sceneById.get(artist.scene);
  const related = explorer.related[focus];
  const top = related[0]?.score ?? 0;

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
        <h3>Most related</h3>
        {related.length === 0 ? (
          <p className="muted">No related artists in this map.</p>
        ) : (
          <ol className="related" data-testid="related">
            {related.map((entry, rank) => {
              const other = explorer.map.artists[entry.index];
              return (
                <li key={entry.index}>
                  <span className="related-rank">{rank + 1}</span>
                  <button type="button" className="related-button" onClick={() => onFocus(entry.index)}>
                    <Swatch color={other.scene === null ? undefined : colors.get(other.scene)} />
                    <span className="related-name">{other.name}</span>
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
