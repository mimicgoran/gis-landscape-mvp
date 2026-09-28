/**
 * Device orientation (kompas heading) wrapper -- Phase 12.
 *
 * ISTRAŽENO PRIJE IMPLEMENTACIJE (brief tačka 16 traži da se istraži prije
 * pisanja koda):
 *
 * PERMISSION FLOW -- iOS Safari NASUPROT svemu ostalom:
 * - iOS Safari 13+ zahtijeva eksplicitan poziv
 *   `DeviceOrientationEvent.requestPermission()` (Promise koji vraća
 *   "granted"/"denied"), i taj poziv MORA se desiti direktno unutar
 *   korisničke geste (klik) -- isti razlog kao browser Geolocation (iOS
 *   blokira "tihe" senzorske pristupe), ali ovo je ODVOJENA permisija od
 *   geolocation-a, sa sopstvenim promptom.
 * - Android Chrome (i praktično svi ne-iOS browseri) NEMAJU ovu permisiju/
 *   API uopšte -- `deviceorientation`/`deviceorientationabsolute` eventi
 *   rade čim je stranica učitana preko HTTPS-a (secure context), bez
 *   ikakvog permission prompta. Detekcija: `typeof
 *   DeviceOrientationEvent.requestPermission === "function"` postoji SAMO
 *   na iOS Safari-ju.
 *
 * KOMPAS HEADING EKSTRAKCIJA (poznat cross-browser haos, glavni razlog zašto
 * je ovo istraženo posebno prije koda):
 * - iOS Safari: `event.webkitCompassHeading` je VEĆ gotov kompas heading
 *   (stepeni u smjeru kazaljke na satu od MAGNETNOG sjevera) -- koristi se
 *   DIREKTNO. `event.alpha` na iOS-u za apsolutnu orijentaciju NIJE
 *   pouzdan izvor kompasa (drugačija konvencija/nepouzdano), zato se ne
 *   koristi kad je webkitCompassHeading dostupan.
 * - Android Chrome i ostali: `deviceorientationabsolute` event (kad ga
 *   browser podržava) sa `event.absolute === true` i brojčanim
 *   `event.alpha` -- konverzija u kompas heading je
 *   `(360 - event.alpha) % 360`. Ovo je standardna, široko dokumentovana
 *   konverzija (alpha raste kontra-kazaljke na satu gledano odozgo na
 *   uređaj, kompas heading raste u smjeru kazaljke) -- vidi
 *   docs/architecture-feasibility-review.md sekcija 39 za izvore.
 * - Ako ni jedno ni drugo nije dostupno (stariji/nepodržani browseri, ili
 *   apsolutna orijentacija nije dostupna pa je alpha samo proizvoljan broj
 *   bez ikakve veze sa sjeverom, ili -- čest slučaj na desktop računarima
 *   bez senzora -- event se NIKAD ne desi) -- nema pouzdanog kompasa,
 *   pozivalac dobija grešku i mora ostati u manual modu (brief tačka 16:
 *   "Mora postojati fallback", tačka 42).
 *
 * NAMJERNO IZOSTAVLJENO U OVOJ VERZIJI (brief tačka 17: "Ne praviti
 * sofisticiran sensor-fusion sistem... tek ako testiranje pokaže da je
 * potrebno"):
 * - Nikakav smoothing/filtering sirovog heading-a (moving average/
 *   exponential smoothing) -- šalje se sirova vrijednost iz senzora.
 *   Ako se na pravom telefonu pokaže da je heading previše "skakutav",
 *   dodaje se kao sljedeći mali, izolovan korak.
 * - Magnetna deklinacija (razlika magnetni/geografski sjever) se
 *   zanemaruje -- na Balkanu je red veličine par stepeni, zanemarivo
 *   naspram FOV opsega (20-90°, brief tačka 19) i konzistentno sa ostalim
 *   namjernim pojednostavljenjima projekta (npr. Earth curvature, sekcija
 *   30).
 * - Kompenzacija za screen orientation (landscape/portrait) NIJE
 *   implementirana -- konverzija gore pretpostavlja portrait mod. Ako
 *   testiranje na telefonu u landscape modu pokaže pogrešan heading,
 *   dodaje se `screen.orientation.angle` korekcija kao poznat, izolovan
 *   fix (zabilježeno u Future, brief sekcija 53 "improved compass
 *   filtering").
 */

const ABSOLUTE_ORIENTATION_EVENT = "deviceorientationabsolute";
const FALLBACK_ORIENTATION_EVENT = "deviceorientation";

// Ako ni jedan event ne stigne u ovom roku nakon start-a, tretiramo kompas
// kao nedostupan (npr. desktop browser bez senzora, gdje `DeviceOrientationEvent`
// POSTOJI kao API ali se event nikad ne okine) -- bez ovoga bi UI ostao
// "zaglavljen" u auto modu bez ikakve povratne informacije.
const NO_EVENT_TIMEOUT_MS = 3000;

/**
 * @returns {boolean} da li browser uopšte izlaže DeviceOrientationEvent API.
 *   NE garantuje da će eventi stvarno stići (vidi NO_EVENT_TIMEOUT_MS gore).
 */
export function isCompassSupported() {
  return typeof window !== "undefined" && "DeviceOrientationEvent" in window;
}

function isIOSPermissionRequestNeeded() {
  return (
    typeof DeviceOrientationEvent !== "undefined" &&
    typeof DeviceOrientationEvent.requestPermission === "function"
  );
}

/**
 * MORA se pozvati direktno iz korisničke geste (klik) na iOS Safari-ju --
 * vidi modul docstring. Na browserima bez ove permisije (Android Chrome i
 * ostali) odmah se razrješava kao "granted" (nema šta da se traži).
 *
 * @returns {Promise<"granted"|"denied">}
 */
export async function requestCompassPermission() {
  if (!isIOSPermissionRequestNeeded()) {
    return "granted";
  }
  try {
    return await DeviceOrientationEvent.requestPermission();
  } catch (error) {
    console.warn("[deviceOrientationService] requestPermission nije uspio:", error);
    return "denied";
  }
}

/**
 * @param {DeviceOrientationEvent} event
 * @returns {number|null} kompas heading u stepenima [0, 360), ili `null`
 *   ako event ne nosi upotrebljivo polje (vidi modul docstring).
 */
function extractCompassHeadingDeg(event) {
  if (typeof event.webkitCompassHeading === "number" && !Number.isNaN(event.webkitCompassHeading)) {
    return event.webkitCompassHeading;
  }
  if (event.absolute === true && typeof event.alpha === "number") {
    return (360 - event.alpha) % 360;
  }
  return null;
}

/**
 * Pokreće slušanje kompas heading-a. `onHeading` se zove na SVAKI
 * upotrebljiv event (bez throttle-a/smoothing-a ovdje -- pozivalac je
 * odgovoran za throttle rendera ako treba, npr. preko
 * `requestAnimationFrame`, jer se eventi mogu dešavati vrlo često).
 *
 * @param {(headingDeg: number) => void} onHeading
 * @param {(message: string) => void} onError poziva se NAJVIŠE JEDNOM --
 *   ili čim prvi event stigne bez upotrebljivog heading polja, ili ako
 *   NIJEDAN event ne stigne u `NO_EVENT_TIMEOUT_MS`. Pozivalac tad treba
 *   da prekine auto mod (pozvati vraćenu stop funkciju) i vrati se na
 *   manual.
 * @returns {() => void} stop funkcija -- uklanja listener i timeout.
 */
export function startCompassHeading(onHeading, onError) {
  let reportedError = false;
  let receivedAnyEvent = false;

  const usingAbsolute = "ondeviceorientationabsolute" in window;
  const eventName = usingAbsolute ? ABSOLUTE_ORIENTATION_EVENT : FALLBACK_ORIENTATION_EVENT;

  function reportError(message) {
    if (reportedError) return;
    reportedError = true;
    clearTimeout(noEventTimer);
    onError(message);
  }

  function handleEvent(event) {
    receivedAnyEvent = true;
    const heading = extractCompassHeadingDeg(event);
    if (heading === null) {
      reportError(
        "Kompas nije dostupan na ovom uređaju/browseru (nema apsolutne orijentacije). Koristi ručni mod."
      );
      return;
    }
    onHeading(heading);
  }

  const noEventTimer = setTimeout(() => {
    if (!receivedAnyEvent) {
      reportError("Kompas se ne javlja na ovom uređaju/browseru. Koristi ručni mod.");
    }
  }, NO_EVENT_TIMEOUT_MS);

  window.addEventListener(eventName, handleEvent);

  return () => {
    clearTimeout(noEventTimer);
    window.removeEventListener(eventName, handleEvent);
  };
}
