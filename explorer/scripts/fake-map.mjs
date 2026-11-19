import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

const here = dirname(fileURLToPath(import.meta.url));

const { values } = parseArgs({
  options: {
    artists: { type: "string", default: "6000" },
    seed: { type: "string", default: "17" },
    out: { type: "string", default: resolve(here, "..", "public", "map.json") },
    "if-missing": { type: "boolean", default: false },
  },
});

const ARTIST_COUNT = Number.parseInt(values.artists, 10);
if (!Number.isInteger(ARTIST_COUNT) || ARTIST_COUNT < 50) {
  throw new Error("--artists must be an integer of at least 50");
}
const OUT = resolve(values.out);

if (values["if-missing"] && existsSync(OUT)) {
  process.exit(0);
}

function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const random = mulberry32(Number.parseInt(values.seed, 10));
const pick = (items) => items[Math.floor(random() * items.length)];

const ONSETS = [
  "b",
  "d",
  "f",
  "g",
  "k",
  "l",
  "m",
  "n",
  "p",
  "r",
  "s",
  "t",
  "v",
  "z",
  "br",
  "dr",
  "kr",
  "st",
  "sh",
  "th",
];
const VOWELS = ["a", "e", "i", "o", "u", "a", "e", "o", "ae", "io", "y"];
const CODAS = ["", "", "", "", "", "n", "r", "l", "x", "m", "s"];

function syllable() {
  return pick(ONSETS) + pick(VOWELS) + pick(CODAS);
}

function word(min, max) {
  const count = min + Math.floor(random() * (max - min + 1));
  let text = "";
  for (let i = 0; i < count; i += 1) text += syllable();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function inventName() {
  const shape = random();
  if (shape < 0.55) return `${word(1, 2)} ${word(2, 3)}`;
  if (shape < 0.8) return word(2, 3);
  if (shape < 0.9) return `${word(1, 2)} ${word(1, 2)} ${word(1, 2)}`;
  return `${word(1, 2)}-${word(1, 2)}`;
}

const ACCENTS = { a: "á", e: "é", i: "í", o: "ö", u: "ü", n: "ñ", c: "ç", s: "š", z: "ž" };

function accented(text) {
  let changed = false;
  const out = [...text].map((ch) => {
    const swap = ACCENTS[ch];
    if (swap && random() < 0.5) {
      changed = true;
      return swap;
    }
    return ch;
  });
  if (!changed) {
    const index = out.findIndex((ch) => ACCENTS[ch]);
    if (index >= 0) out[index] = ACCENTS[out[index]];
  }
  return out.join("");
}

const usedNames = new Set();
function uniqueName() {
  for (;;) {
    const name = inventName();
    const key = name.toLowerCase();
    if (!usedNames.has(key)) {
      usedNames.add(key);
      return name;
    }
  }
}

const sceneCount = Math.max(15, Math.min(40, Math.round(ARTIST_COUNT / 250)));
const sceneWeights = Array.from({ length: sceneCount }, (_, i) => 1 / Math.pow(i + 1, 0.85));
const sceneWeightTotal = sceneWeights.reduce((sum, w) => sum + w, 0);

function pickScene() {
  if (random() < 0.08) return null;
  let roll = random() * sceneWeightTotal;
  for (let i = 0; i < sceneCount; i += 1) {
    roll -= sceneWeights[i];
    if (roll <= 0) return i;
  }
  return sceneCount - 1;
}

function pickNights() {
  const pareto = 1 / Math.pow(1 - random(), 1 / 1.6);
  return Math.max(1, Math.min(640, Math.round(pareto * 1.8)));
}

const CITIES = ["Lakeport", "Northvale"];

function citiesOf(artist) {
  const home = (artist.sceneIndex ?? artist.id) % CITIES.length;
  return artist.id % 9 === 0 ? [CITIES[home], CITIES[1 - home]] : [CITIES[home]];
}

const ISLAND_SIZE = 3;
const artists = [];
let nextId = 101;
for (let i = 0; i < ARTIST_COUNT; i += 1) {
  nextId += 1 + Math.floor(random() * 4);
  const island = i >= ARTIST_COUNT - ISLAND_SIZE;
  artists.push({
    id: nextId,
    name: uniqueName(),
    aliases: [],
    nights: island ? 2 + Math.floor(random() * 3) : pickNights(),
    sceneIndex: island ? null : pickScene(),
    island,
  });
}

for (const artist of artists) {
  const roll = random();
  if (roll < 0.03) {
    artist.aliases.push(accented(artist.name.toLowerCase()).replace(/^./, (c) => c.toUpperCase()));
  } else if (roll < 0.05) {
    artist.aliases.push(accented(uniqueName()));
  } else if (roll < 0.06) {
    artist.aliases.push(`${artist.name} & ${word(1, 2)}`, accented(uniqueName()));
  }
}

const accentedAliasArtist = artists.find((a) => !a.island && a.aliases.length === 0 && a.nights >= 10);
accentedAliasArtist.aliases.push("Ćevrà Dœlmüth");

const members = Array.from({ length: sceneCount }, () => []);
const mainland = [];
for (let i = 0; i < artists.length; i += 1) {
  const artist = artists[i];
  if (artist.island) continue;
  mainland.push(i);
  if (artist.sceneIndex !== null) members[artist.sceneIndex].push(i);
}

function sampler(indices) {
  const cumulative = new Float64Array(indices.length);
  let total = 0;
  for (let k = 0; k < indices.length; k += 1) {
    total += Math.pow(artists[indices[k]].nights, 0.9);
    cumulative[k] = total;
  }
  return () => {
    const roll = random() * total;
    let lo = 0;
    let hi = indices.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (cumulative[mid] < roll) lo = mid + 1;
      else hi = mid;
    }
    return indices[lo];
  };
}

const sceneSamplers = members.map((list) => (list.length > 0 ? sampler(list) : null));
const anySampler = sampler(mainland);
const neighbours = Array.from({ length: sceneCount }, (_, i) => [
  (i + 1) % sceneCount,
  (i + sceneCount - 1) % sceneCount,
  (i * 7 + 3) % sceneCount,
]);

const related = [];
for (let i = 0; i < artists.length; i += 1) {
  const artist = artists[i];
  if (artist.island) continue;
  const wanted = artist.nights <= 1 && random() < 0.4 ? 3 + Math.floor(random() * 6) : 10;
  const chosen = new Set();
  let attempts = 0;
  while (chosen.size < wanted && attempts < 200) {
    attempts += 1;
    const roll = random();
    let target;
    if (artist.sceneIndex !== null && roll < 0.8) {
      target = sceneSamplers[artist.sceneIndex]();
    } else if (artist.sceneIndex !== null && roll < 0.95) {
      const other = sceneSamplers[pick(neighbours[artist.sceneIndex])];
      target = other ? other() : anySampler();
    } else {
      target = anySampler();
    }
    if (target !== i) chosen.add(target);
  }
  const top = random() * 0.05 + 0.01;
  const ordered = [...chosen]
    .map((target) => ({ target, weight: artists[target].nights * (0.5 + random()) }))
    .sort((a, b) => b.weight - a.weight);
  ordered.forEach(({ target }, rank) => {
    const score = top * Math.pow(0.86, rank) * (0.97 + random() * 0.03);
    related.push([artist.id, artists[target].id, Number(score.toFixed(6))]);
  });
}

const island = artists.filter((a) => a.island);
for (const source of island) {
  island
    .filter((target) => target !== source)
    .forEach((target, rank) => {
      related.push([source.id, target.id, Number((0.02 * Math.pow(0.9, rank)).toFixed(6))]);
    });
}
related.sort((a, b) => a[0] - b[0]);

const sceneIdByIndex = Array.from({ length: sceneCount }, (_, i) => i + 1);
const scenes = members
  .map((list, i) => {
    const top = [...list].sort((a, b) => artists[b].nights - artists[a].nights).slice(0, 3);
    return {
      id: sceneIdByIndex[i],
      label: top.map((k) => artists[k].name).join(" / "),
      size: list.length,
    };
  })
  .filter((scene) => scene.size > 0)
  .sort((a, b) => b.size - a.size || a.id - b.id);

const map = {
  version: 1,
  generated_at: "2026-11-17T04:31:00+00:00",
  credits: [
    { name: "Invented Lineup Archive", url: "https://example.org/" },
    { name: "Made-up Listings", url: "https://example.com/listings" },
  ],
  scenes,
  artists: artists.map((a) => ({
    id: a.id,
    name: a.name,
    aliases: a.aliases,
    nights: a.nights,
    cities: citiesOf(a),
    scene: a.sceneIndex === null ? null : sceneIdByIndex[a.sceneIndex],
  })),
  related,
};

mkdirSync(dirname(OUT), { recursive: true });
writeFileSync(OUT, JSON.stringify(map));
console.log(`fake map: ${artists.length} artists, ${scenes.length} scenes, ${related.length} related rows -> ${OUT}`);
