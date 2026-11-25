import { track } from "../analytics";

interface Props {
  onZoom: (direction: 1 | -1) => void;
}

export function ZoomButtons({ onZoom }: Props) {
  return (
    <div className="zoom-buttons" role="group" aria-label="Zoom">
      <button
        type="button"
        aria-label="Zoom in"
        data-testid="zoom-in"
        onClick={() => {
          track("zoom", { direction: "in" });
          onZoom(1);
        }}
      >
        +
      </button>
      <button
        type="button"
        aria-label="Zoom out"
        data-testid="zoom-out"
        onClick={() => {
          track("zoom", { direction: "out" });
          onZoom(-1);
        }}
      >
        −
      </button>
    </div>
  );
}
