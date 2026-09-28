/**
 * Simbol definicije za graphics na mapi -- sve na jednom mjestu, ne
 * razbacano po fajlovima koji rade drugu logiku.
 */

/**
 * Simbol za observer marker (korisnikova pozicija na mapi).
 *
 * Jednostavan krug uočljive boje -- observer je uvijek tačno jedan graphic
 * na observerLayer-u (Phase 2: klik na mapu; Phase 10: browser geolocation).
 */
export function createObserverSymbol() {
  return {
    type: "simple-marker",
    style: "circle",
    color: [0, 120, 255, 0.9],
    size: 14,
    outline: {
      color: [255, 255, 255, 1],
      width: 2,
    },
  };
}

/**
 * Simbol za VIDLJIV tačkasti feature (vrh/naselje/vidikovac) -- brief
 * tačka 35: "Visible objekti treba da budu vizuelno važniji od blocked".
 * Veći, zasićeno zelen, jasan bijeli outline.
 */
export function createVisibleFeatureSymbol() {
  return {
    type: "simple-marker",
    style: "circle",
    color: [52, 168, 83, 0.95],
    size: 12,
    outline: {
      color: [255, 255, 255, 1],
      width: 1.5,
    },
  };
}

/**
 * Simbol za ZAKLONJEN tačkasti feature -- namjerno manji i prigušeniji
 * (sivo, niža neprozirnost) da vizuelno ne konkuriše visible feature-ima
 * (isto obrazloženje kao gore, brief tačka 35).
 */
export function createBlockedFeatureSymbol() {
  return {
    type: "simple-marker",
    style: "circle",
    color: [154, 160, 166, 0.65],
    size: 8,
    outline: {
      color: [255, 255, 255, 0.85],
      width: 1,
    },
  };
}
