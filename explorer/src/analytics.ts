export type EventData = Record<string, string | number | boolean>;

interface Umami {
  track: (event: string, data?: EventData) => void;
}

declare global {
  interface Window {
    umami?: Umami;
  }
}

const WAIT_MS = 250;
const MAX_TRIES = 40;
const pending: [string, EventData | undefined][] = [];
let tries = 0;
let timer: ReturnType<typeof setTimeout> | undefined;

function send(event: string, data: EventData | undefined): void {
  try {
    window.umami?.track(event, data);
  } catch {
    return;
  }
}

function flush(): void {
  timer = undefined;
  if (typeof window === "undefined") return;
  if (window.umami) {
    for (const [event, data] of pending.splice(0)) send(event, data);
    tries = 0;
    return;
  }
  tries += 1;
  if (tries >= MAX_TRIES) {
    pending.length = 0;
    tries = 0;
    return;
  }
  timer = setTimeout(flush, WAIT_MS);
}

export function track(event: string, data?: EventData): void {
  if (typeof window === "undefined") return;
  if (window.umami && pending.length === 0) {
    send(event, data);
    return;
  }
  pending.push([event, data]);
  timer ??= setTimeout(flush, 0);
}

export function clip(text: string, length = 80): string {
  return text.trim().slice(0, length);
}

export function trackOutboundLinks(): void {
  document.addEventListener("click", (event) => {
    const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
    if (!(link instanceof HTMLAnchorElement) || !/^https?:$/.test(link.protocol)) return;
    if (link.hostname === window.location.hostname) return;
    track("link", { to: link.hostname.replace(/^www\./, ""), url: clip(link.href, 200) });
  });
}
