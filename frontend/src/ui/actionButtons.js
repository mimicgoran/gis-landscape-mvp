/**
 * Dva glavna akciona dugmeta: "Koristi moju lokaciju" (Phase 10, browser
 * geolocation) i "Šta gledam?" (originalni brief Phase 9, pokreće
 * /api/v1/analyze poziv). Odvojeno od controlsPanel.js jer su ovo AKCIJE
 * (jednokratni pozivi), ne kontinuirane kontrole (slajderi) -- brief
 * sekcija 34 layout ih i vizuelno razdvaja od CONTROLS bloka.
 */

/**
 * @param {{ onLocate: () => void, onAnalyze: () => void }} handlers
 * @returns {{ setLocateLoading: (isLoading: boolean) => void, setAnalyzeLoading: (isLoading: boolean) => void }}
 */
export function initActionButtons({ onLocate, onAnalyze }) {
  const locateButton = document.getElementById("locateButton");
  const analyzeButton = document.getElementById("analyzeButton");

  if (!locateButton || !analyzeButton) {
    throw new Error("initActionButtons: #locateButton ili #analyzeButton ne postoje u DOM-u (provjeri index.html).");
  }

  const locateDefaultText = locateButton.textContent;
  const analyzeDefaultText = analyzeButton.textContent;

  locateButton.addEventListener("click", onLocate);
  analyzeButton.addEventListener("click", onAnalyze);

  return {
    setLocateLoading(isLoading) {
      locateButton.disabled = isLoading;
      locateButton.textContent = isLoading ? "Tražim lokaciju…" : locateDefaultText;
    },
    setAnalyzeLoading(isLoading) {
      analyzeButton.disabled = isLoading;
      analyzeButton.textContent = isLoading ? "Analiziram…" : analyzeDefaultText;
    },
  };
}
