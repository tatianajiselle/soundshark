import { useEffect, useRef, useState } from "react";
import { placeLabels, type PlacedLabel } from "../graph/labels";

interface Tracker {
  getPointPositions(): ArrayLike<number> | undefined;
  spaceToScreenPosition(position: [number, number]): [number, number] | undefined;
}

interface Props {
  tracker: Tracker | null;
  path: readonly number[];
  names: readonly string[];
  everyMs: number;
}

export function PathLabels({ tracker, path, names, everyMs }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const [labels, setLabels] = useState<{ path: readonly number[]; placed: PlacedLabel[] }>({ path, placed: [] });

  useEffect(() => {
    if (!tracker || path.length === 0) return;
    let frame = 0;
    let last = 0;
    const tick = (now: number) => {
      frame = requestAnimationFrame(tick);
      if (now - last < everyMs) return;
      last = now;
      const positions = tracker.getPointPositions();
      if (!positions) return;
      const anchors = path.flatMap((index, step) => {
        const x = positions[index * 2];
        const y = positions[index * 2 + 1];
        const screen = Number.isFinite(x) && Number.isFinite(y) ? tracker.spaceToScreenPosition([x, y]) : undefined;
        return screen ? [{ index, x: screen[0], y: screen[1], text: names[step] ?? "" }] : [];
      });
      setLabels({ path, placed: placeLabels(anchors, box.current?.clientWidth ?? Infinity) });
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [tracker, path, names, everyMs]);

  return (
    <div className="path-labels" aria-hidden="true" data-testid="path-labels" ref={box}>
      {(labels.path === path ? labels.placed : []).map((label) => (
        <span
          key={label.index}
          className={label.index === path[0] || label.index === path[path.length - 1] ? "path-label end" : "path-label"}
          style={{ transform: `translate(${Math.round(label.left)}px, ${Math.round(label.top)}px)` }}
        >
          {label.text}
        </span>
      ))}
    </div>
  );
}
