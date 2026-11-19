import { describe, expect, it } from "vitest";
import type { Artist } from "./mapFile";
import { MatchTier, buildSearchIndex, normalize, search } from "./search";

function artist(id: number, name: string, nights: number, aliases: string[] = []): Artist {
  return { id, name, aliases, nights, cities: [], scene: null };
}

const roster: Artist[] = [
  artist(1, "Vela Moss", 10),
  artist(2, "Mossbank", 50),
  artist(3, "Kilo Vela", 90),
  artist(4, "Avelanne", 300),
  artist(5, "Orrin Tal", 5, ["Ćevrà Dœlmüth", "O.T."]),
  artist(6, "Vela", 1),
  artist(7, "Brix & Søn", 20),
];

describe("normalize", () => {
  it("lowercases, strips accents and collapses punctuation", () => {
    expect(normalize("  Ćevrà   Dœlmüth ")).toBe("cevra doelmuth");
    expect(normalize("D.J.  Kíló--Vela!")).toBe("d j kilo vela");
    expect(normalize("Brix & Søn")).toBe("brix son");
    expect(normalize("Straße")).toBe("strasse");
  });

  it("folds compatibility forms", () => {
    expect(normalize("ＶＥＬＡ")).toBe("vela");
    expect(normalize("ﬁre")).toBe("fire");
  });

  it("keeps letters from other scripts", () => {
    expect(normalize("Тихо Море")).toBe("тихо море");
    expect(normalize("夜 光")).toBe("夜 光");
  });

  it("gives an empty string for punctuation only", () => {
    expect(normalize(" -- ")).toBe("");
  });
});

describe("search", () => {
  const index = buildSearchIndex(roster);
  const names = (query: string) => search(index, query).map((hit) => roster[hit.index].name);

  it("puts an exact match first, then prefixes, then word prefixes, then substrings", () => {
    expect(names("vela")).toEqual(["Vela", "Vela Moss", "Kilo Vela", "Avelanne"]);
  });

  it("orders matches of the same kind by nights", () => {
    expect(names("ve")).toEqual(["Vela Moss", "Vela", "Kilo Vela", "Avelanne"]);
  });

  it("ranks a prefix above a busier substring", () => {
    expect(names("moss")).toEqual(["Mossbank", "Vela Moss"]);
    expect(names("vel")[0]).toBe("Vela Moss");
  });

  it("finds an artist by an alias, with or without accents", () => {
    const hits = search(index, "cevra doel");
    expect(hits).toHaveLength(1);
    expect(roster[hits[0].index].name).toBe("Orrin Tal");
    expect(hits[0].alias).toBe("Ćevrà Dœlmüth");
    expect(hits[0].tier).toBe(MatchTier.Prefix);
    expect(names("ĆEVRÀ")).toEqual(["Orrin Tal"]);
  });

  it("prefers the name over an alias when both match", () => {
    const hits = search(index, "orrin");
    expect(hits[0].alias).toBeNull();
  });

  it("ignores punctuation in the query", () => {
    expect(names("o.t.")).toEqual(["Orrin Tal"]);
    expect(names("brix son")).toEqual(["Brix & Søn"]);
  });

  it("returns nothing for an empty query and respects the limit", () => {
    expect(search(index, "   ")).toEqual([]);
    expect(search(index, "a", 2)).toHaveLength(2);
  });
});
