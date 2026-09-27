/**
 * Kontrole za heading/FOV/radius — Phase 3.
 *
 * Opsezi i default vrijednosti dolaze iz config.js, koji MORA ostati
 * usklađen sa backend/app/core/config.py (vidi napomenu tamo). Namjerno bez
 * eksternog UI frameworka/biblioteke — tri range input-a i malo DOM koda su
 * dovoljni za MVP (brief, tačka 40: "Ne over-engineer-ovati").
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

/**
 * Inicijalizuje kontrole unutar #controlsPanel i javlja svaku promjenu
 * pozivaocu preko `onChange`.
 *
 * @param {(sector: { headingDeg: number, fovDeg: number, radiusKm: number }) => void} onChange
 * @returns {{ getSector: () => { headingDeg: number, fovDeg: number, radiusKm: number } }}
 */
export function initControlsPanel(onChange) {
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

  const headingRow = createSliderRow({
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

  const fovRow = createSliderRow({
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

  const radiusRow = createSliderRow({
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

  panel.append(headingRow, fovRow, radiusRow);

  return {
    getSector: () => ({ ...state }),
  };
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
  return row;
}
