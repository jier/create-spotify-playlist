import assert from "node:assert/strict";
import { test } from "node:test";

import { genreColor } from "./colors";

test("genreColor returns the neutral untagged color for an empty genre list", () => {
  assert.equal(genreColor([]), "hsl(0, 0%, 55%)");
});

test("genreColor is deterministic: same genres, same color", () => {
  assert.equal(genreColor(["rock", "pop"]), genreColor(["rock", "pop"]));
});

test("genreColor is order-independent", () => {
  assert.equal(genreColor(["rock", "pop"]), genreColor(["pop", "rock"]));
});

test("genreColor differs for different genre sets (not a guarantee, but true for these)", () => {
  assert.notEqual(genreColor(["rock"]), genreColor(["gospel"]));
  assert.notEqual(genreColor(["rock", "pop"]), genreColor(["rock"]));
});

test("genreColor always returns a valid hsl() string with hue in [0, 360)", () => {
  for (const genres of [["rock"], ["gospel", "traditional gospel"], ["afrogospel"], ["a", "b", "c", "d"]]) {
    const color = genreColor(genres);
    const match = /^hsl\((\d+), 70%, 55%\)$/.exec(color);
    assert.ok(match, `expected an hsl(...) string, got ${color}`);
    const hue = Number(match![1]);
    assert.ok(hue >= 0 && hue < 360, `hue ${hue} out of range`);
  }
});
