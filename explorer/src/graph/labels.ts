export interface Anchor {
  index: number;
  x: number;
  y: number;
  text: string;
}

export interface PlacedLabel extends Anchor {
  left: number;
  top: number;
  width: number;
  height: number;
}

const CHAR_WIDTH = 7;
const PADDING = 14;
const HEIGHT = 20;
const GAP = 3;
const LIFT = 10;

function overlaps(a: PlacedLabel, b: PlacedLabel): boolean {
  return a.left < b.left + b.width && b.left < a.left + a.width && a.top < b.top + b.height && b.top < a.top + a.height;
}

export function placeLabels(anchors: readonly Anchor[], width = Infinity): PlacedLabel[] {
  const placed: PlacedLabel[] = [];
  const order = [...anchors].sort((a, b) => a.y - b.y || a.x - b.x);
  for (const anchor of order) {
    const labelWidth = anchor.text.length * CHAR_WIDTH + PADDING;
    const label: PlacedLabel = {
      ...anchor,
      width: labelWidth,
      height: HEIGHT,
      left: Math.max(4, Math.min(anchor.x - labelWidth / 2, width - labelWidth - 4)),
      top: anchor.y - LIFT - HEIGHT,
    };
    const tries = [0, 1, -1, 2, -2, 3, -3, 4, -4];
    for (const step of tries) {
      const candidate = { ...label, top: label.top + step * (HEIGHT + GAP) };
      if (!placed.some((other) => overlaps(candidate, other))) {
        label.top = candidate.top;
        break;
      }
    }
    placed.push(label);
  }
  return placed;
}
