import { describe, expect, it } from "vitest";
import { formatHash, parseHash, safeHref } from "./urlState";

describe("parseHash", () => {
  it("reads a focus and a path end", () => {
    expect(parseHash("#a=17")).toEqual({ a: 17, b: null, city: null });
    expect(parseHash("#a=17&b=42")).toEqual({ a: 17, b: 42, city: null });
    expect(parseHash("a=17&b=42")).toEqual({ a: 17, b: 42, city: null });
  });

  it("ignores junk", () => {
    expect(parseHash("")).toEqual({ a: null, b: null, city: null });
    expect(parseHash("#a=abc")).toEqual({ a: null, b: null, city: null });
    expect(parseHash("#a=1e3")).toEqual({ a: null, b: null, city: null });
    expect(parseHash("#b=42")).toEqual({ a: null, b: null, city: null });
    expect(parseHash("#a=17&b=17")).toEqual({ a: 17, b: null, city: null });
    expect(parseHash("#a=12345678901234567890")).toEqual({ a: null, b: null, city: null });
  });
});

describe("formatHash", () => {
  it("round-trips", () => {
    expect(formatHash({ a: 17, b: 42, city: null })).toBe("#a=17&b=42");
    expect(parseHash(formatHash({ a: 17, b: 42, city: null }))).toEqual({ a: 17, b: 42, city: null });
    expect(formatHash({ a: 17, b: null, city: null })).toBe("#a=17");
    expect(formatHash({ a: null, b: 42, city: null })).toBe("");
  });

  it("keeps the city with or without a focus", () => {
    expect(formatHash({ a: null, b: null, city: "Some City" })).toBe("#c=Some+City");
    expect(parseHash("#c=Some+City")).toEqual({ a: null, b: null, city: "Some City" });
    expect(parseHash(formatHash({ a: 17, b: 42, city: "Some City" }))).toEqual({ a: 17, b: 42, city: "Some City" });
    expect(parseHash("#c=")).toEqual({ a: null, b: null, city: null });
  });
});

describe("safeHref", () => {
  it("allows only http and https", () => {
    expect(safeHref("https://example.org/")).toBe("https://example.org/");
    expect(safeHref("http://example.org/x?y=1")).toBe("http://example.org/x?y=1");
    expect(safeHref("javascript:alert(1)")).toBeNull();
    expect(safeHref("JaVaScRiPt:alert(1)")).toBeNull();
    expect(safeHref("data:text/html,hi")).toBeNull();
    expect(safeHref("/relative")).toBeNull();
    expect(safeHref("not a url")).toBeNull();
  });
});
