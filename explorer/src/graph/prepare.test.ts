import { describe, expect, it } from "vitest";
import type { MapFile } from "./mapFile";
import { basedIn, inCity, prepare } from "./prepare";

const map: MapFile = {
  version: 1,
  generatedAt: "2026-11-17T04:31:00+00:00",
  credits: [],
  scenes: [],
  artists: [
    { id: 1, name: "Vela Moss", aliases: [], nights: 9, cities: ["Northvale", "Lakeport"], pos: null, scene: null },
    { id: 2, name: "Orrin Tal", aliases: [], nights: 4, cities: ["Northvale"], pos: null, scene: null },
    { id: 3, name: "Brix", aliases: [], nights: 2, cities: ["Lakeport"], pos: null, scene: null },
    { id: 4, name: "Tamsk", aliases: [], nights: 0, cities: [], pos: null, scene: null },
  ],
  related: [
    [1, 2, 0.5],
    [2, 3, 0.5],
    [3, 4, 0.5],
  ],
};

describe("cities", () => {
  it("lists cities by how many artists are based there", () => {
    expect(prepare(map).cities).toEqual(["Northvale", "Lakeport"]);
  });

  it("marks everyone who played a city and frames the artists based there", () => {
    expect([...inCity(map, "Lakeport")]).toEqual([1, 0, 1, 0]);
    expect(basedIn(map, "Lakeport")).toEqual([2]);
    expect(basedIn(map, "Northvale")).toEqual([0, 1]);
  });
});
