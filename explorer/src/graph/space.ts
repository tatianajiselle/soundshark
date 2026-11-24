export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export interface Candidate {
  key: string;
  x: number;
  y: number;
  width: number;
  height: number;
  priority: number;
}

export interface Box {
  key: string;
  left: number;
  top: number;
  width: number;
  height: number;
}

const sub = (a: Vec3, b: Vec3): Vec3 => ({ x: a.x - b.x, y: a.y - b.y, z: a.z - b.z });
const length = (v: Vec3) => Math.hypot(v.x, v.y, v.z);

export function unit(v: Vec3): Vec3 {
  const n = length(v);
  return n === 0 ? { x: 0, y: 0, z: 1 } : { x: v.x / n, y: v.y / n, z: v.z / n };
}

export function depth(point: Vec3, eye: Vec3, forward: Vec3): number {
  const d = sub(point, eye);
  return d.x * forward.x + d.y * forward.y + d.z * forward.z;
}

export function fade(distance: number, full: number, gone: number): number {
  if (distance <= full) return 1;
  if (distance >= gone) return 0;
  return 1 - (distance - full) / (gone - full);
}

export function spread(positions: readonly Vec3[]): number {
  if (positions.length === 0) return 1;
  const radii = positions.map((p) => length(p)).sort((a, b) => a - b);
  return Math.max(1, radii[Math.floor((radii.length - 1) * 0.9)]);
}

export function pickBoxes(candidates: readonly Candidate[], max: number, width: number, height: number): Box[] {
  const chosen: Box[] = [];
  const order = [...candidates].sort((a, b) => b.priority - a.priority);
  for (const c of order) {
    if (chosen.length >= max) break;
    const box = { key: c.key, left: c.x - c.width / 2, top: c.y - c.height, width: c.width, height: c.height };
    if (box.left < 0 || box.top < 0 || box.left + box.width > width || box.top + box.height > height) continue;
    const clash = chosen.some(
      (o) =>
        box.left < o.left + o.width &&
        o.left < box.left + box.width &&
        box.top < o.top + o.height &&
        o.top < box.top + box.height,
    );
    if (!clash) chosen.push(box);
  }
  return chosen;
}

export function flightShot(prev: Vec3 | null, here: Vec3, next: Vec3 | null, distance: number): Vec3 {
  const heading = next !== null ? sub(next, here) : prev !== null ? sub(here, prev) : here;
  const back = unit(heading);
  const lift = distance * 0.35;
  return { x: here.x - back.x * distance, y: here.y - back.y * distance + lift, z: here.z - back.z * distance };
}

export interface RelatedLike {
  index: number;
}

export interface HopFacts {
  sharedCities: string[];
  rankFromA: number | null;
  rankFromB: number | null;
}

export function hopFacts(
  citiesA: readonly string[],
  citiesB: readonly string[],
  relatedA: readonly RelatedLike[],
  relatedB: readonly RelatedLike[],
  a: number,
  b: number,
): HopFacts {
  const inB = new Set(citiesB);
  const rank = (list: readonly RelatedLike[], other: number) => {
    const i = list.findIndex((r) => r.index === other);
    return i === -1 ? null : i + 1;
  };
  return {
    sharedCities: citiesA.filter((c) => inB.has(c)),
    rankFromA: rank(relatedA, b),
    rankFromB: rank(relatedB, a),
  };
}
