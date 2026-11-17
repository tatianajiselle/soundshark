export interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export interface Insets {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export function boundsOf(positions: ArrayLike<number>, indices: readonly number[]): Bounds | null {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const i of indices) {
    const x = positions[i * 2];
    const y = positions[i * 2 + 1];
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  }
  return Number.isFinite(minX) ? { minX, minY, maxX, maxY } : null;
}

export interface ClosePair {
  distance: number;
}

export function closestStep(positions: ArrayLike<number>, path: readonly number[]): ClosePair | null {
  let best: ClosePair | null = null;
  for (let i = 0; i + 1 < path.length; i += 1) {
    const ax = positions[path[i] * 2];
    const ay = positions[path[i] * 2 + 1];
    const bx = positions[path[i + 1] * 2];
    const by = positions[path[i + 1] * 2 + 1];
    if (![ax, ay, bx, by].every(Number.isFinite)) continue;
    const distance = Math.hypot(bx - ax, by - ay);
    if (best === null || distance < best.distance) best = { distance };
  }
  return best;
}

export interface Separation {
  pair: ClosePair;
  pixels: number;
  maxBoost: number;
}

export function framingBox(
  bounds: Bounds,
  width: number,
  height: number,
  insets: Insets,
  padding: number,
  yUp: boolean,
  separation?: Separation,
): [number, number, number, number] {
  const visibleWidth = Math.max(1, width - insets.left - insets.right);
  const visibleHeight = Math.max(1, height - insets.top - insets.bottom);
  const spanX = Math.max(bounds.maxX - bounds.minX, 1e-6);
  const spanY = Math.max(bounds.maxY - bounds.minY, 1e-6);
  const fitScale = Math.min(visibleWidth / spanX, visibleHeight / spanY) * (1 - padding);
  let scale = fitScale;
  const focusX = (bounds.minX + bounds.maxX) / 2;
  const focusY = (bounds.minY + bounds.maxY) / 2;
  if (separation && separation.pair.distance > 0) {
    scale = Math.max(fitScale, Math.min(separation.pixels / separation.pair.distance, fitScale * separation.maxBoost));
  }
  const shiftX = insets.left + visibleWidth / 2 - width / 2;
  const shiftY = insets.top + visibleHeight / 2 - height / 2;
  const centreX = focusX - shiftX / scale;
  const centreY = focusY + (yUp ? shiftY : -shiftY) / scale;
  const halfX = width / 2 / scale;
  const halfY = height / 2 / scale;
  return [centreX - halfX, centreY - halfY, centreX + halfX, centreY + halfY];
}

export function insetsFrom(container: Rect, overlays: readonly Rect[], gap = 8): Insets {
  const insets: Insets = { left: 0, top: 0, right: 0, bottom: 0 };
  const width = container.right - container.left;
  const height = container.bottom - container.top;
  for (const o of overlays) {
    if (
      o.right <= container.left ||
      o.left >= container.right ||
      o.bottom <= container.top ||
      o.top >= container.bottom
    ) {
      continue;
    }
    const wide = o.right - o.left > width * 0.6;
    if (wide) {
      if ((o.top + o.bottom) / 2 < container.top + height / 2) {
        insets.top = Math.max(insets.top, o.bottom - container.top + gap);
      } else {
        insets.bottom = Math.max(insets.bottom, container.bottom - o.top + gap);
      }
    } else if ((o.left + o.right) / 2 < container.left + width / 2) {
      insets.left = Math.max(insets.left, o.right - container.left + gap);
    } else {
      insets.right = Math.max(insets.right, container.right - o.left + gap);
    }
  }
  const limitX = width * 0.45;
  const limitY = height * 0.6;
  return {
    left: Math.min(insets.left, limitX),
    right: Math.min(insets.right, limitX),
    top: Math.min(insets.top, limitY),
    bottom: Math.min(insets.bottom, limitY),
  };
}
