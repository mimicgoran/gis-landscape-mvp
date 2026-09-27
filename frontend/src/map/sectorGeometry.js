/**
 * Frontend (približna) viewing sector geometrija — za live preview dok
 * korisnik pomjera slajdere, bez network round-trip-a na svaki pokret.
 *
 * VAŽNO: ovo NIJE izvor istine. Konačna sector/FOV/bearing logika za
 * filtriranje stvarnih kandidata (vrhova) živi na backendu
 * (app/services/geometry.py, geodesic preko pyproj/WGS84 elipsoida) — vidi
 * docs/architecture-feasibility-review.md, sekcija 8, korak 5: "ovo se
 * računa i na backendu... i duplira jednostavnom verzijom na frontendu za
 * live preview".
 *
 * Sferna aproksimacija (Earth radius ~6371 km, ne WGS84 elipsoid) je
 * dovoljno tačna za čisto vizuelni prikaz na ovim razmjerima (radius do
 * 30 km, vidi sekciju 0/8 o MVP scope-u ograničenom na Srbiju) — razlika
 * naspram elipsoida je vizuelno zanemarljiva, a implementacija bez
 * dodatnih zavisnosti (npr. turf.js) je namjerno jednostavnija.
 *
 * Wrap-around napomena: bearing vrijednosti ovdje NISU normalizovane na
 * [0, 360) prije korištenja u sin/cos — to je namjerno i ispravno, jer su
 * trigonometrijske funkcije periodične (cos/sin od 364° == cos/sin od 4°).
 * To znači da heading=359°, fov=10° (start=354°, end=364°) crta ispravan
 * luk bez ikakve posebne wrap-around logike ovdje.
 */

const EARTH_RADIUS_KM = 6371.0088;

function toRadians(degrees) {
  return (degrees * Math.PI) / 180;
}

function toDegrees(radians) {
  return (radians * 180) / Math.PI;
}

/**
 * Tačka na udaljenosti `distanceKm` i pravcu `bearingDeg` od (lat, lon).
 * Standardna sferna "destination point given bearing and distance" formula.
 */
function destinationPoint(latitude, longitude, bearingDeg, distanceKm) {
  const angularDistance = distanceKm / EARTH_RADIUS_KM;
  const bearingRad = toRadians(bearingDeg);
  const lat1 = toRadians(latitude);
  const lon1 = toRadians(longitude);

  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(angularDistance) + Math.cos(lat1) * Math.sin(angularDistance) * Math.cos(bearingRad)
  );
  const lon2 =
    lon1 +
    Math.atan2(
      Math.sin(bearingRad) * Math.sin(angularDistance) * Math.cos(lat1),
      Math.cos(angularDistance) - Math.sin(lat1) * Math.sin(lat2)
    );

  return { latitude: toDegrees(lat2), longitude: toDegrees(lon2) };
}

/**
 * Generiše zatvoren prsten [longitude, latitude] tačaka koje čine viewing
 * sector poligon: observer -> luk od (heading - fov/2) do (heading + fov/2)
 * na radius_km -> nazad na observer.
 *
 * @param {{ latitude: number, longitude: number }} observer
 * @param {number} headingDeg - 0-360, 0 = sjever, u smjeru kazaljke
 * @param {number} fovDeg
 * @param {number} radiusKm
 * @param {number} [arcStepDeg=3] - korak duž luka u stepenima (manji = glađi luk, sporije)
 * @returns {number[][]} niz [lon, lat] parova, zatvoren poligon (prva tačka == zadnja)
 */
export function buildSectorPolygonRing(observer, headingDeg, fovDeg, radiusKm, arcStepDeg = 3) {
  const startBearing = headingDeg - fovDeg / 2;
  const endBearing = headingDeg + fovDeg / 2;

  const ring = [[observer.longitude, observer.latitude]];

  const steps = Math.max(1, Math.ceil(fovDeg / arcStepDeg));
  for (let i = 0; i <= steps; i += 1) {
    const bearing = startBearing + (i / steps) * (endBearing - startBearing);
    const point = destinationPoint(observer.latitude, observer.longitude, bearing, radiusKm);
    ring.push([point.longitude, point.latitude]);
  }

  ring.push([observer.longitude, observer.latitude]);

  return ring;
}
