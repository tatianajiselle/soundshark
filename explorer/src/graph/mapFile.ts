export interface Credit {
  name: string;
  url: string;
}

export interface Scene {
  id: number;
  label: string;
  size: number;
}

export interface Artist {
  id: number;
  name: string;
  aliases: string[];
  nights: number;
  cities: string[];
  scene: number | null;
  pos: Point3 | null;
}

export type Point3 = [x: number, y: number, z: number];

export type RelatedRow = [source: number, target: number, score: number];

export interface MapFile {
  version: 1;
  generatedAt: string;
  credits: Credit[];
  scenes: Scene[];
  artists: Artist[];
  related: RelatedRow[];
}

export class MapFileError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MapFileError";
  }
}

function fail(message: string): never {
  throw new MapFileError(message);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireArray(value: unknown, path: string): unknown[] {
  if (!Array.isArray(value)) fail(`${path} must be a list`);
  return value;
}

function requireRecord(value: unknown, path: string): Record<string, unknown> {
  if (!isRecord(value)) fail(`${path} must be an object`);
  return value;
}

function requireString(value: unknown, path: string): string {
  if (typeof value !== "string") fail(`${path} must be text`);
  return value;
}

function requireId(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value)) fail(`${path} must be a whole number`);
  return value;
}

function requireCount(value: unknown, path: string): number {
  const n = requireId(value, path);
  if (n < 0) fail(`${path} must not be negative`);
  return n;
}

function parseCredit(value: unknown, path: string): Credit {
  const record = requireRecord(value, path);
  return {
    name: requireString(record.name, `${path}.name`),
    url: requireString(record.url, `${path}.url`),
  };
}

function parseScene(value: unknown, path: string): Scene {
  const record = requireRecord(value, path);
  return {
    id: requireId(record.id, `${path}.id`),
    label: requireString(record.label, `${path}.label`),
    size: requireCount(record.size, `${path}.size`),
  };
}

function parsePoint(value: unknown, path: string): Point3 {
  const list = requireArray(value, path);
  if (list.length !== 3 || !list.every((v) => typeof v === "number" && Number.isFinite(v))) {
    fail(`${path} must be [x, y, z]`);
  }
  return [list[0], list[1], list[2]] as Point3;
}

function parseArtist(value: unknown, path: string): Artist {
  const record = requireRecord(value, path);
  const name = requireString(record.name, `${path}.name`);
  if (name.trim() === "") fail(`${path}.name must not be empty`);
  const aliases = requireArray(record.aliases, `${path}.aliases`).map((alias, i) =>
    requireString(alias, `${path}.aliases[${i}]`),
  );
  const scene = record.scene === null ? null : requireId(record.scene, `${path}.scene`);
  const cities =
    record.cities === undefined
      ? []
      : requireArray(record.cities, `${path}.cities`).map((city, i) => requireString(city, `${path}.cities[${i}]`));
  return {
    id: requireId(record.id, `${path}.id`),
    name,
    aliases,
    nights: requireCount(record.nights, `${path}.nights`),
    cities,
    scene,
    pos: record.pos === undefined || record.pos === null ? null : parsePoint(record.pos, `${path}.pos`),
  };
}

function parseRelated(value: unknown, path: string): RelatedRow {
  const row = requireArray(value, path);
  if (row.length !== 3) fail(`${path} must be [source, target, score]`);
  const score = row[2];
  if (typeof score !== "number" || !Number.isFinite(score)) fail(`${path} score must be a number`);
  return [requireId(row[0], `${path} source`), requireId(row[1], `${path} target`), score];
}

export function parseMapFile(raw: unknown): MapFile {
  const root = requireRecord(raw, "the map");
  if (root.version !== 1) fail(`unsupported map version ${JSON.stringify(root.version ?? null)} (expected 1)`);
  const generatedAt = requireString(root.generated_at, "generated_at");
  if (Number.isNaN(Date.parse(generatedAt))) fail("generated_at must be a date and time");

  const credits = requireArray(root.credits, "credits").map((c, i) => parseCredit(c, `credits[${i}]`));
  const scenes = requireArray(root.scenes, "scenes").map((s, i) => parseScene(s, `scenes[${i}]`));
  const artists = requireArray(root.artists, "artists").map((a, i) => parseArtist(a, `artists[${i}]`));
  const related = requireArray(root.related, "related").map((r, i) => parseRelated(r, `related[${i}]`));

  const sceneIds = new Set<number>();
  scenes.forEach((scene, i) => {
    if (sceneIds.has(scene.id)) fail(`scenes[${i}] repeats scene id ${scene.id}`);
    sceneIds.add(scene.id);
  });

  const artistIds = new Set<number>();
  artists.forEach((artist, i) => {
    if (artistIds.has(artist.id)) fail(`artists[${i}] repeats artist id ${artist.id}`);
    artistIds.add(artist.id);
    if (artist.scene !== null && !sceneIds.has(artist.scene)) {
      fail(`artists[${i}] is in scene ${artist.scene}, which is not in scenes`);
    }
  });

  related.forEach(([source, target], i) => {
    if (!artistIds.has(source)) fail(`related[${i}] starts at unknown artist ${source}`);
    if (!artistIds.has(target)) fail(`related[${i}] points at unknown artist ${target}`);
    if (source === target) fail(`related[${i}] links artist ${source} to itself`);
  });

  return { version: 1, generatedAt, credits, scenes, artists, related };
}
