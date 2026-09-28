/**
 * Kontrole za heading/FOV/radius — Phase 3, prošireno Phase 12 (kompas).
 *
 * Opsezi i default vrijednosti dolaze iz config.js, koji MORA ostati
 * usklađen sa backend/app/core/config.py (vidi napomenu tamo). Namjerno bez
 * eksternog UI frameworka/biblioteke — tri range input-a i malo DOM koda su
 * dovoljni za MVP (brief, tačka 40: "Ne over-engineer-ovati").
 *
 * PHASE 12 (kompas, vidi services/deviceOrientationService.js za browser-
 * kompatibilnost i konverzije): heading slajder ima dodatno dugme "Koristi
 * kompas" u zaglavlju. Dok je kompas AKTIVAN, slajder je `disabled` -- ovo
 * je namjeran, jednostavan izbor umjesto suptilnijeg "prevuci slajder da
 * prekineš auto mod" ponašanja: eksplicitan klik na dugme je jedini način
 * da se kompas isključi, čime je MANUAL MODE (brief tačka 16, OBAVEZAN)
 * uvijek dostupan na jedan klik, bez rizika da korisnik slučajno završi u
 * "napola auto, napola manual" stanju. Live kompas ažuriranja se throttle-uju
 * preko `requestAnimationFrame` (najviše jednom po frejmu) -- ovo NIJE
 * smoothing/filtering senzorske vrijednosti (to je namjerno izostavljeno,
 * vidi deviceOrientationService.js), samo sprječava da se sektor na mapi
 * ponovo crta i po nekoliko desetina puta u sekundi ako uređaj šalje
 * orientation evente tom brzinom.
 */

import {
  DEFAULT_HEADING_DEG,
  FOV_DEFAULT_DEG,
  FOV_MAX_DEG,
  FOV_MIN_DEG,
  RADIUS_DEFAULT_KM,
  RADIUS_MAX_KM,
  RADIUS_MIN_KM,
} from "../config.js";
import {
  isCompassSupported,
  requestCompassPermission,
  startCompassHeading,
} from "../services/deviceOrientationService.js";

/**
 * Inicijalizuje kontrole unutar #controlsPanel i javlja svaku promjenu
 * pozivaocu preko `onChange`.
 *
 * @param {{
 *   onChange: (sector: { headingDeg: number, fovDeg: number, radiusKm: number }) => void,
 *   onCompassError?: (message: string) => void,
 * }} handlers
 * @returns {{ getSector: () => { headingDeg: number, fovDeg: number, radiusKm: number } }}
 */
export function initControlsPanel({ onChange, onCompassError }) {
  const panel = document.getElementById("controlsPanel");
  if (!panel) {
    throw new Error("initControlsPanel: element #controlsPanel ne postoji u DOM-u (provjeri index.html).");
  }

  const state = {
    headingDeg: DEFAULT_HEADING_DEG,
    fovDeg: FOV_DEFAULT_DEG,
    radiusKm: RADIUS_DEFAULT_KM,
  };

  panel.replaceChildren();

  const heading = createSliderRow({
    label: "Heading",
    min: 0,
    max: 360,
    step: 1,
    value: state.headingDeg,
    unit: "°",
    onInput: (value) => {
      state.headingDeg = value;
      onChange({ ...state });
    },
  });

  const fov = createSliderRow({
    label: "Field of View",
    min: FOV_MIN_DEG,
    max: FOV_MAX_DEG,
    step: 1,
    value: state.fovDeg,
    unit: "°",
    onInput: (value) => {
      state.fovDeg = value;
      onChange({ ...state });
    },
  });

  const radius = createSliderRow({
    label: "Radius",
    min: RADIUS_MIN_KM,
    max: RADIUS_MAX_KM,
    step: 1,
    value: state.radiusKm,
    unit: " km",
    onInput: (value) => {
      state.radiusKm = value;
      onChange({ ...state });
    },
  });

  const compassToggle = createCompassToggleButton({
    onEnabled: () => {
      heading.slider.disabled = true;
    },
    onDisabled: () => {
      heading.slider.disabled = false;
    },
    onHeadingUpdate: (headingDeg) => {
      state.headingDeg = headingDeg;
      heading.slider.value = String(headingDeg);
      heading.valueEl.textContent = `${Math.round(headingDeg)}°`;
      onChange({ ...state });
    },
    onError: (message) => {
      if (onCompassError) onCompassError(message);
    },
  });
  // Ispod slajdera (ne u headerRow-u) -- headerRow ima samo dva elementa
  // (label + value) raspoređena preko `justify-content: space-between`;
  // treći element bi tu izgledao neuredno na uskom (220px/mobilnom) panelu.
  heading.row.append(compassToggle);

  panel.append(heading.row, fov.row, radius.row);

  return {
    getSector: () => ({ ...state }),
  };
}

/**
 * Dugme "Koristi kompas" ugrađeno u heading red -- vidi modul docstring za
 * obrazloženje "disabled slider dok je auto mod aktivan" pristupa.
 */
function createCompassToggleButton({ onEnabled, onDisabled, onHeadingUpdate, onError }) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "compass-toggle";
  button.textContent = "Koristi kompas";

  let stopListening = null;
  let pendingHeadingDeg = null;
  let rafHandle = null;

  function scheduleHeadingUpdate(headingDeg) {
    pendingHeadingDeg = headingDeg;
    if (rafHandle !== null) return;
    rafHandle = requestAnimationFrame(() => {
      rafHandle = null;
      if (pendingHeadingDeg !== null) {
        onHeadingUpdate(pendingHeadingDeg);
      }
    });
  }

  function stop() {
    if (rafHandle !== null) {
      cancelAnimationFrame(rafHandle);
      rafHandle = null;
    }
    pendingHeadingDeg = null;
    if (stopListening) {
      stopListening();
      stopListening = null;
    }
    button.textContent = "Koristi kompas";
    button.classList.remove("compass-toggle-active");
    onDisabled();
  }

  button.addEventListener("click", async () => {
    if (stopListening) {
      stop();
      return;
    }

    if (!isCompassSupported()) {
      onError("Kompas nije podržan u ovom browseru. Koristi ručni mod (slajder).");
      return;
    }

    // `requestCompassPermission()` MORA biti prvi await u ovom handleru na
    // iOS Safari-ju -- permisija se traži unutar korisničke geste (klik), a
    // odlaganje poziva iza nekog drugog async koraka bi moglo poništiti tu
    // gestu (vidi deviceOrientationService.js docstring).
    const permission = await requestCompassPermission();
    if (permission !== "granted") {
      onError("Pristup senzoru orijentacije je odbijen. Koristi ručni mod (slajder).");
      return;
    }

    button.textContent = "Isključi kompas";
    button.classList.add("compass-toggle-active");
    onEnabled();

    stopListening = startCompassHeading(
      (headingDeg) => scheduleHeadingUpdate(headingDeg),
      (message) => {
        stop();
        onError(message);
      }
    );
  });

  return button;
}

function createSliderRow({ label, min, max, step, value, unit, onInput }) {
  const row = document.createElement("div");
  row.className = "control-row";

  const headerRow = document.createElement("div");
  headerRow.className = "control-row-header";

  const labelEl = document.createElement("label");
  labelEl.textContent = label;

  const valueEl = document.createElement("span");
  valueEl.className = "control-value";
  valueEl.textContent = `${value}${unit}`;

  headerRow.append(labelEl, valueEl);

  const slider = document.createElement("input");
  slider.type = "range";
  slider.min = String(min);
  slider.max = String(max);
  slider.step = String(step);
  slider.value = String(value);

  slider.addEventListener("input", () => {
    const numericValue = Number(slider.value);
    valueEl.textContent = `${numericValue}${unit}`;
    onInput(numericValue);
  });

  row.append(headerRow, slider);
  return { row, headerRow, slider, valueEl };
}
