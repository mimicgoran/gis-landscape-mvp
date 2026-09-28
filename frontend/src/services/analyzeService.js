/**
 * Poziva backend GIS pipeline (/api/v1/analyze/preview) i vraća parsiran
 * odgovor -- "Šta gledam?" dugme (originalni brief Phase 9, uveden tek
 * sada zajedno sa Phase 10, vidi napomenu u glavnoj arhitekturi o procjepu
 * u numeraciji faza).
 *
 * NAPOMENA o kompromisu: backend endpoint je i dalje GET sa query
 * parametrima, nazvan "/preview" (vidi backend/app/api/routes/analyze.py
 * modul docstring, koji najavljuje finalni `POST /api/v1/analyze` sa
 * observer objektom u body-ju). Odlučeno je da se ta REST-čistoća odloži
 * (jednostavnije rješenje za sada -- trenutni GET oblik već potpuno
 * pokriva frontend potrebe, a mijenjanje ugovora bi u ovom trenutku bilo
 * čisto kozmetičko). Prirodna prilika da se ipak uradi: Phase 13 (OpenAI
 * sloj), kad endpoint svakako mora da se promijeni da doda `ai_description`.
 */

import { BACKEND_BASE_URL } from "../config.js";

/**
 * @param {{
 *   latitude: number, longitude: number,
 *   headingDeg: number, fovDeg: number, radiusKm: number,
 *   horizontalAccuracyM?: number|null,
 *   phoneAltitudeM?: number|null,
 *   phoneAltitudeAccuracyM?: number|null,
 * }} params
 * @returns {Promise<object>} pun /api/v1/analyze/preview JSON odgovor
 * @throws {Error} sa čitljivom porukom na HTTP grešku, mrežni problem, ili
 *   backend-signalizovanu grešku (npr. DEM nedostupan za observer lokaciju).
 */
export async function fetchAnalysis(params) {
  const query = new URLSearchParams({
    lat: String(params.latitude),
    lon: String(params.longitude),
    heading_deg: String(params.headingDeg),
    fov_deg: String(params.fovDeg),
    radius_km: String(params.radiusKm),
  });

  if (params.horizontalAccuracyM != null) {
    query.set("horizontal_accuracy_m", String(params.horizontalAccuracyM));
  }
  if (params.phoneAltitudeM != null) {
    query.set("phone_altitude_m", String(params.phoneAltitudeM));
  }
  if (params.phoneAltitudeAccuracyM != null) {
    query.set("phone_altitude_accuracy_m", String(params.phoneAltitudeAccuracyM));
  }

  let response;
  try {
    response = await fetch(`${BACKEND_BASE_URL}/api/v1/analyze/preview?${query.toString()}`);
  } catch (networkError) {
    throw new Error("Backend nije dostupan -- provjeri da li je uvicorn pokrenut.");
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(`Analiza nije uspjela (${response.status}): ${body.detail ?? "nepoznata greška"}`);
  }

  const data = await response.json();

  if (data.debug?.error) {
    // Backend vraća HTTP 200 sa `debug.error` kad DEM nije dostupan za
    // observer lokaciju (vidi analyze.py) -- na frontendu ovo tretiramo
    // kao grešku umjesto da tiho prikažemo prazne rezultate.
    throw new Error(data.debug.error);
  }

  return data;
}
