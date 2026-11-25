import { useEffect, useRef } from "react";
import type { Credit } from "../graph/mapFile";
import { formatGenerated } from "../graph/text";
import { safeHref } from "../graph/urlState";

export function Credits({ credits }: { credits: readonly Credit[] }) {
  if (credits.length === 0) return null;
  return (
    <span className="credits" data-testid="credits">
      {credits.map((credit, i) => {
        const href = safeHref(credit.url);
        return (
          <span key={`${i}-${credit.name}`}>
            {i > 0 && ", "}
            {href ? (
              <a href={href} target="_blank" rel="noopener noreferrer">
                {credit.name}
              </a>
            ) : (
              credit.name
            )}
          </span>
        );
      })}
    </span>
  );
}

interface FooterProps {
  credits: readonly Credit[];
  generatedAt: string;
  onAbout: () => void;
  onWelcome: () => void;
}

export function Footer({ credits, generatedAt, onAbout, onWelcome }: FooterProps) {
  return (
    <footer className="footer" data-testid="footer">
      <span>Connections are derived from public lineups.</span>
      {credits.length > 0 && (
        <span className="footer-credits">
          Data: <Credits credits={credits} />.
        </span>
      )}
      <span className="footer-generated">Map from {formatGenerated(generatedAt)}.</span>
      <button type="button" className="text-button" onClick={onWelcome} data-testid="open-welcome">
        How to explore
      </button>
      <button type="button" className="text-button" onClick={onAbout}>
        About
      </button>
    </footer>
  );
}

interface AboutProps extends FooterProps {
  open: boolean;
  onClose: () => void;
  artists: number;
}

export function About({ open, onClose, credits, generatedAt, artists }: Omit<AboutProps, "onAbout" | "onWelcome">) {
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (open && !element.open) element.showModal();
    if (!open && element.open) element.close();
  }, [open]);

  return (
    <dialog ref={dialog} className="about" onClose={onClose} aria-labelledby="about-title" data-testid="about">
      <h2 id="about-title">About this map</h2>
      <p>
        Every point is a DJ. Two DJs are joined when one of them is among the other’s ten most related artists. A bigger
        point has played more nights, and a colour is a scene: a group of DJs who mostly play with each other.
      </p>
      <p>
        Search for an artist to see who is one, two and three hops away, then use <em>Connect to…</em> to find the
        shortest chain between two artists. The address bar keeps the view, so a link opens the same artist.
      </p>
      <p>
        Connections are derived from public lineups: the map holds names, counts and scores, never copies of listings.
        {credits.length > 0 && (
          <>
            {" "}
            Lineup data: <Credits credits={credits} />.
          </>
        )}{" "}
        This map has {artists.toLocaleString("en-GB")} artists and was made {formatGenerated(generatedAt)}.
      </p>
      <p>
        Drawn with{" "}
        <a href="https://cosmograph.app/" target="_blank" rel="noopener noreferrer">
          Cosmograph
        </a>
        , used under its{" "}
        <a href="https://creativecommons.org/licenses/by-nc/4.0/" target="_blank" rel="noopener noreferrer">
          CC BY-NC 4.0
        </a>{" "}
        licence (non-commercial use). SoundShark itself is MIT licensed.
      </p>
      <button type="button" className="button" onClick={onClose}>
        Close
      </button>
    </dialog>
  );
}
