/**
 * Browser Geolocation API wrapper -- Phase 10.
 *
 * Namjerno gesture-triggered (poziva se tek na klik dugmeta "Koristi moju
 * lokaciju"), NE automatski na page load -- permission prompt pokrenut
 * korisničkom gestom je pouzdaniji (posebno na iOS Safari) i manje
 * namećući nego prompt odmah pri otvaranju stranice (dogovoreno prije
 * implementacije, vidi docs/architecture-feasibility-review.md).
 *
 * Jednokratno očitavanje (`getCurrentPosition`), NE `watchPosition` --
 * dovoljno za scenario "stojim na vidikovcu i gledam" iz brifa (tačka 1).
 * Kontinuirano praćenje ide u Future ako se pokaže potreba -- isti princip
 * "ne over-engineer-uj" kao i ostatak projekta.
 *
 * NAPOMENA (korisnička odluka, 28.09.2026 -- vidi docs/architecture-feasibility-review.md
 * sekcija 38): manual klik na mapu za postavljanje observera je UKLONJEN.
 * Ovo je namjerno odstupanje od brief tačke 16/42 (koje su tražile manual
 * mode kao obavezan fallback kad geolocation ne radi) -- korisnik je
 * eksplicitno odlučio da prihvati rizik da aplikacija bude neupotrebljiva
 * ako je pristup lokaciji odbijen ili nedostupan, u zamjenu za to da se
 * observer NIKAD ne može slučajno postaviti pogrešnim klikom na mapu.
 * Ako se ovaj rizik u praksi pokaže kao problem (npr. tokom LinkedIn demo
 * snimanja), najjednostavniji povratak je ponovo dodati manual klik SAMO
 * kao fallback koji se aktivira tek kad `getCurrentPosition()` odbaci
 * (vidi git istoriju za uklonjen `observerInteraction.js:setupObserverInteraction`).
 *
 * NAPOMENA o secure context-u: Geolocation API zahtijeva HTTPS ili
 * localhost. Testiranje sa pravog telefona preko LAN IP-a (npr.
 * http://192.168.x.x:5500 ka desktop dev serveru) NEĆE raditi -- ovo je
 * poznato ograničenje riješeno tek u Phase 15 (HTTPS deployment).
 */

const GEOLOCATION_TIMEOUT_MS = 10000;

/**
 * @typedef {Object} GeolocationResult
 * @property {number} latitude
 * @property {number} longitude
 * @property {number|null} horizontalAccuracyM
 * @property {number|null} phoneAltitudeM
 * @property {number|null} phoneAltitudeAccuracyM
 */

/**
 * @returns {Promise<GeolocationResult>}
 * @throws {Error} sa čitljivom porukom (na srpskom, za direktan prikaz
 *   korisniku) ako geolocation nije dostupan, bude odbijen, ili istekne timeout.
 */
export function getCurrentPosition() {
  if (!("geolocation" in navigator)) {
    return Promise.reject(
      new Error(
        "Geolocation nije dostupan u ovom browseru/kontekstu (potrebno je HTTPS ili localhost)."
      )
    );
  }

  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { coords } = position;
        resolve({
          latitude: coords.latitude,
          longitude: coords.longitude,
          horizontalAccuracyM: coords.accuracy ?? null,
          phoneAltitudeM: coords.altitude ?? null,
          phoneAltitudeAccuracyM: coords.altitudeAccuracy ?? null,
        });
      },
      (error) => reject(new Error(describeGeolocationError(error))),
      {
        enableHighAccuracy: true,
        timeout: GEOLOCATION_TIMEOUT_MS,
        maximumAge: 0,
      }
    );
  });
}

/**
 * GeolocationPositionError kodovi (spec, isti u svim browserima):
 * 1 = PERMISSION_DENIED, 2 = POSITION_UNAVAILABLE, 3 = TIMEOUT.
 */
function describeGeolocationError(error) {
  switch (error.code) {
    case error.PERMISSION_DENIED:
      return "Pristup lokaciji je odbijen. Omogući pristup lokaciji u podešavanjima browsera/telefona i pokušaj ponovo.";
    case error.POSITION_UNAVAILABLE:
      return "Lokacija trenutno nije dostupna (GPS signal?). Pokušaj ponovo na otvorenom prostoru.";
    case error.TIMEOUT:
      return "Očitavanje lokacije je isteklo. Pokušaj ponovo.";
    default:
      return "Nepoznata greška pri očitavanju lokacije. Pokušaj ponovo.";
  }
}
