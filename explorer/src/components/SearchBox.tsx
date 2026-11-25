import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type Ref } from "react";
import { clip, track } from "../analytics";
import type { Explorer } from "../graph/prepare";
import { search } from "../graph/search";
import { formatNights } from "../graph/text";
import { Swatch } from "./Swatch";

interface Props {
  explorer: Explorer;
  colors: Map<number, string>;
  label: string;
  placeholder: string;
  exclude?: number | null;
  onChoose: (index: number) => void;
  inputRef?: Ref<HTMLInputElement>;
  autoFocus?: boolean;
  testId: string;
}

export function SearchBox({
  explorer,
  colors,
  label,
  placeholder,
  exclude = null,
  onChoose,
  inputRef,
  autoFocus,
  testId,
}: Props) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const blurTimer = useRef<number | undefined>(undefined);

  const hits = useMemo(
    () =>
      search(explorer.search, query, 9)
        .filter((hit) => hit.index !== exclude)
        .slice(0, 8),
    [explorer.search, query, exclude],
  );
  const showList = open && query.trim() !== "";
  const missing = query.trim().length >= 2 && hits.length === 0;

  useEffect(() => {
    if (!missing) return;
    const wait = window.setTimeout(() => track("search-miss", { box: testId, query: clip(query, 60) }), 1200);
    return () => window.clearTimeout(wait);
  }, [missing, query, testId]);

  const choose = (index: number) => {
    const rank = hits.findIndex((hit) => hit.index === index);
    track("search-pick", {
      box: testId,
      query: clip(query, 60),
      name: explorer.map.artists[index].name,
      rank: rank + 1,
    });
    setQuery("");
    setOpen(false);
    setActive(0);
    onChoose(index);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActive((a) => (hits.length === 0 ? 0 : (a + 1) % hits.length));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      setActive((a) => (hits.length === 0 ? 0 : (a - 1 + hits.length) % hits.length));
    } else if (event.key === "Enter") {
      const hit = hits[Math.min(active, hits.length - 1)];
      if (showList && hit) {
        event.preventDefault();
        choose(hit.index);
      }
    } else if (event.key === "Escape") {
      if (query !== "" || open) {
        event.preventDefault();
        event.stopPropagation();
        setQuery("");
        setOpen(false);
      } else {
        event.currentTarget.blur();
      }
    }
  };

  const activeId = showList && hits[active] ? `${listId}-${active}` : undefined;

  return (
    <div className="search" data-testid={testId}>
      <label className="visually-hidden" htmlFor={`${listId}-input`}>
        {label}
      </label>
      <input
        id={`${listId}-input`}
        ref={inputRef}
        type="search"
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={activeId}
        aria-autocomplete="list"
        autoComplete="off"
        spellCheck={false}
        autoFocus={autoFocus}
        placeholder={placeholder}
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setActive(0);
          setOpen(true);
        }}
        onFocus={() => {
          window.clearTimeout(blurTimer.current);
          setOpen(true);
        }}
        onBlur={() => {
          blurTimer.current = window.setTimeout(() => setOpen(false), 120);
        }}
        onKeyDown={onKeyDown}
      />
      {showList && (
        <ul className="search-results" id={listId} role="listbox" aria-label={label}>
          {hits.length === 0 && <li className="search-empty">No artist matches “{query.trim()}”</li>}
          {hits.map((hit, i) => {
            const artist = explorer.map.artists[hit.index];
            const scene = artist.scene;
            return (
              <li
                key={hit.index}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                className={i === active ? "search-hit active" : "search-hit"}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setActive(i)}
                onClick={() => choose(hit.index)}
              >
                <Swatch color={scene === null ? undefined : colors.get(scene)} />
                <span className="search-hit-text">
                  <span className="search-hit-name">{artist.name}</span>
                  {hit.alias !== null && <span className="search-hit-alias">also listed as {hit.alias}</span>}
                </span>
                <span className="search-hit-nights">{formatNights(artist.nights)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
