import type { Explorer } from "../graph/prepare";
import { hopFacts } from "../graph/space";

interface Props {
  explorer: Explorer;
  path: readonly number[];
  step: number;
  onStop: () => void;
}

const ordinal = (n: number) => `#${n}`;

export function FlightCard({ explorer, path, step, onStop }: Props) {
  const { artists } = explorer.map;
  const here = path[step];
  const sceneName = (index: number) => {
    const scene = explorer.sceneOf[index];
    return scene === null ? null : (explorer.sceneById.get(scene)?.label ?? null);
  };
  const prev = step > 0 ? path[step - 1] : null;
  const facts =
    prev === null
      ? null
      : hopFacts(
          artists[prev].cities,
          artists[here].cities,
          explorer.related[prev],
          explorer.related[here],
          prev,
          here,
        );
  const scene = sceneName(here);

  return (
    <div className="flight-card" role="status" aria-live="polite" data-testid="flight-card">
      <div className="flight-head">
        <span className="flight-step">
          {step + 1} / {path.length}
        </span>
        <button type="button" className="text-button" onClick={onStop} data-testid="flight-stop">
          Stop
        </button>
      </div>
      {prev === null ? (
        <p className="flight-title">
          Starting at <strong>{artists[here].name}</strong>
        </p>
      ) : (
        <p className="flight-title">
          {artists[prev].name} <span aria-hidden="true">→</span> <strong>{artists[here].name}</strong>
        </p>
      )}
      <ul className="flight-facts">
        {scene !== null && <li>Scene: {scene}</li>}
        {facts !== null && facts.rankFromA !== null && (
          <li>
            {ordinal(facts.rankFromA)} most related to {artists[prev as number].name}
          </li>
        )}
        {facts !== null && facts.rankFromB !== null && (
          <li>
            {artists[prev as number].name} is their {ordinal(facts.rankFromB)}
          </li>
        )}
        {facts !== null && facts.sharedCities.length > 0 && <li>Both play {facts.sharedCities.join(", ")}</li>}
      </ul>
    </div>
  );
}
