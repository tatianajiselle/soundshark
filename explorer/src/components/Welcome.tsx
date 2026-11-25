import { useEffect, useRef } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  artists: number;
}

export function Welcome({ open, onClose, artists }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (open && !element.open) element.showModal();
    if (!open && element.open) element.close();
  }, [open]);

  return (
    <dialog
      ref={dialog}
      className="about welcome"
      onClose={onClose}
      aria-labelledby="welcome-title"
      data-testid="welcome"
    >
      <h2 id="welcome-title">Welcome to SoundShark</h2>
      <p>
        SoundShark is a map of {artists.toLocaleString("en-GB")} DJs, drawn from who plays with whom. Every point is a
        DJ, and two DJs sit close together when they keep sharing lineups, especially back-to-back sets and recent
        nights.
      </p>
      <p>
        Genre tags and recommendation feeds flatten a scene. The people a DJ plays alongside say more about their sound,
        so this map lets you follow those links and find artists you’d never be recommended.
      </p>
      <h3>Ways to explore</h3>
      <ul className="welcome-ways">
        <li>
          <strong>Start from someone you love.</strong> Search an artist to see who is one, two and three hops away.
        </li>
        <li>
          <strong>Wander.</strong> Click any point to jump to that DJ, then keep clicking through their related artists.
        </li>
        <li>
          <strong>Follow a scene.</strong> Pick a colour in the legend to light up a group of DJs who mostly play
          together, or choose a city to see its scene.
        </li>
        <li>
          <strong>Connect two artists.</strong> Use <em>Connect to…</em> to find the shortest chain between them, then{" "}
          <em>Fly the path</em> in 3D to travel it hop by hop.
        </li>
      </ul>
      <p className="welcome-note">
        The 3D map needs a GPU to render smoothly. If it feels slow, switch to 2D at the top.
      </p>
      <button type="button" className="button" onClick={onClose} data-testid="welcome-start">
        Start exploring
      </button>
    </dialog>
  );
}
