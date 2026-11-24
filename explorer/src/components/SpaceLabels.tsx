import { useEffect, useRef, useState } from "react";
import { depth, fade, pickBoxes, unit, type Candidate, type Vec3 } from "../graph/space";

export interface Projector {
  graph2ScreenCoords(x: number, y: number, z: number): { x: number; y: number };
  camera(): { position: Vec3 };
  controls(): unknown;
}

export interface SpacePoint {
  id: number;
  x?: number;
  y?: number;
  z?: number;
}

interface Props {
  projector: () => Projector | null;
  points: readonly SpacePoint[];
  nameOf: (id: number) => string;
  weightOf: (id: number) => number;
  emphasis: () => ReadonlySet<number>;
  radius: number;
}

interface Shown {
  key: string;
  text: string;
  at: Vec3;
  width: number;
  height: number;
  opacity: number;
  start: string;
}

const MAX_LABELS = 28;
const SHORTLIST = 200;
const PICK_EVERY_MS = 150;
const CHAR = 7;
const PAD = 14;
const HEIGHT = 20;
const LIFT = 8;
const ARTIST_ZOOM = 1.3;

export function SpaceLabels({ projector, points, nameOf, weightOf, emphasis, radius }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const els = useRef(new Map<string, HTMLSpanElement>());
  const [shown, setShown] = useState<Shown[]>([]);
  const shownRef = useRef<Shown[]>([]);

  useEffect(() => {
    let frame = 0;
    let last = 0;
    const tick = (now: number) => {
      frame = requestAnimationFrame(tick);
      const p = projector();
      const host = box.current;
      if (!p || !host) return;
      const width = host.clientWidth;
      const height = host.clientHeight;

      if (now - last >= PICK_EVERY_MS) {
        last = now;
        const eye = p.camera().position;
        const target = (p.controls() as { target?: Vec3 }).target ?? { x: 0, y: 0, z: 0 };
        const forward = unit({ x: target.x - eye.x, y: target.y - eye.y, z: target.z - eye.z });
        const boosted = emphasis();
        const focusMode = boosted.size > 0;
        const zoom = Math.hypot(target.x - eye.x, target.y - eye.y, target.z - eye.z);
        const on = focusMode || zoom < radius * ARTIST_ZOOM;
        const near: { id: number; at: Vec3; screen: { x: number; y: number }; priority: number; opacity: number }[] =
          [];
        for (const point of on ? points : []) {
          if (point.x === undefined || point.y === undefined || point.z === undefined) continue;
          const at = { x: point.x, y: point.y, z: point.z };
          if (depth(at, eye, forward) <= 1) continue;
          const isBoosted = boosted.has(point.id);
          if (focusMode && !isBoosted) continue;
          const distance = Math.hypot(at.x - eye.x, at.y - eye.y, at.z - eye.z);
          const opacity = isBoosted ? 1 : fade(distance, zoom + radius * 0.5, zoom + radius * 1.2);
          if (opacity < 0.05) continue;
          const screen = p.graph2ScreenCoords(at.x, at.y, at.z);
          if (screen.x < 0 || screen.y < 0 || screen.x > width || screen.y > height) continue;
          near.push({
            id: point.id,
            at,
            screen,
            opacity,
            priority: (weightOf(point.id) * opacity) / Math.max(distance, 1),
          });
        }
        near.sort((a, b) => b.priority - a.priority);
        const candidates: (Candidate & { label: Omit<Shown, "start"> })[] = near.slice(0, SHORTLIST).map((n) => {
          const text = nameOf(n.id);
          const w = text.length * CHAR + PAD;
          const key = `a${n.id}`;
          return {
            key,
            x: n.screen.x,
            y: n.screen.y - LIFT,
            width: w,
            height: HEIGHT,
            priority: n.priority,
            label: { key, text, at: n.at, width: w, height: HEIGHT, opacity: n.opacity },
          };
        });
        const byKey = new Map(candidates.map((c) => [c.key, c.label]));
        const next = pickBoxes(candidates, MAX_LABELS, width, height).map((b) => ({
          ...(byKey.get(b.key) as Omit<Shown, "start">),
          start: `translate(${Math.round(b.left)}px, ${Math.round(b.top)}px)`,
        }));
        shownRef.current = next;
        setShown(next);
      }

      for (const label of shownRef.current) {
        const el = els.current.get(label.key);
        if (!el) continue;
        const s = p.graph2ScreenCoords(label.at.x, label.at.y, label.at.z);
        el.style.transform = `translate(${Math.round(s.x - label.width / 2)}px, ${Math.round(s.y - LIFT - label.height)}px)`;
      }
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [projector, points, nameOf, weightOf, emphasis, radius]);

  return (
    <div className="space-labels" aria-hidden="true" data-testid="space-labels" ref={box}>
      {shown.map((label) => (
        <span
          key={label.key}
          ref={(el) => {
            if (el) els.current.set(label.key, el);
            else els.current.delete(label.key);
          }}
          className="space-label"
          style={{ opacity: label.opacity, transform: label.start }}
        >
          {label.text}
        </span>
      ))}
    </div>
  );
}
