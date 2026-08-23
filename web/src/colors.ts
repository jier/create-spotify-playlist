/**
 * Deterministic genre -> color hashing for the DNA visualization. The same
 * genre set always hashes to the same color, so a viewer can visually
 * associate hue with genre across a run without a legend, and the same
 * artist/genre combination looks the same across different runs too.
 *
 * Genre-color mapping is deliberately a frontend concern, not the
 * backend's -- Spotify's genre vocabulary is open-ended (confirmed back in
 * the gospel-variant dry run: genres like "afrogospel" or "kompa gospel"
 * appear with no fixed enum behind them), so hashing whatever string the
 * backend happens to send avoids needing a maintained genre -> color
 * lookup table that would inevitably miss genres it hasn't seen yet.
 */

function hashString(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i++) {
    hash = (hash * 31 + value.charCodeAt(i)) | 0;
  }
  return hash;
}

const UNTAGGED_COLOR = "hsl(0, 0%, 55%)";

/**
 * Deterministic HSL color for a set of genres. Same genres, any order,
 * same color. Untagged (empty genre list — a real case, see the "urban
 * gospel" discography-fallback seed from the dry run) gets a neutral gray
 * rather than colliding with a real hash bucket.
 */
export function genreColor(genres: readonly string[]): string {
  if (genres.length === 0) return UNTAGGED_COLOR;
  const key = [...genres].sort().join("|");
  const hue = Math.abs(hashString(key)) % 360;
  return `hsl(${hue}, 70%, 55%)`;
}
