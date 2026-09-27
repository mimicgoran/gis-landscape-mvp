/**
 * Simbol definicije za graphics na mapi.
 *
 * Odvojeno od mapSetup.js/observerInteraction.js jer će se ovdje kasnije
 * dodati i visible/blocked simboli za vrhove (Phase 9) — svi vizuelni
 * stilovi na jednom mjestu, ne razbacani po fajlovima koji rade drugu logiku.
 */

/**
 * Simbol za observer marker (korisnikova pozicija na mapi).
 *
 * Jednostavan krug uočljive boje — observer je uvijek tačno jedan graphic
 * na observerLayer-u (Phase 2 ga postavlja/pomjera klikom; Phase 10 dodaje
 * browser geolocation kao alternativni izvor pozicije).
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
