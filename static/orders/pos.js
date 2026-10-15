document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  const confirmation = form.dataset.confirm;
  if (confirmation && !window.confirm(confirmation)) {
    event.preventDefault();
    return;
  }
  const button = event.submitter;
  if (button instanceof HTMLButtonElement) {
    button.disabled = true;
    button.dataset.originalText = button.textContent;
    button.textContent = "Saving…";
  }
});

document.addEventListener("DOMContentLoaded", () => {
  const paper = document.querySelector("[data-receipt-paper]");
  const widthPickers = [...document.querySelectorAll("[data-receipt-width]")];
  const printButton = document.querySelector("[data-print-receipt]");
  if (!paper && !widthPickers.length) return;

  const supportedWidths = new Set(["80", "58"]);
  const preferenceKey = "tamil-kudil-receipt-width";
  let savedWidth = "80";
  try {
    const storedWidth = window.localStorage.getItem(preferenceKey);
    if (supportedWidths.has(storedWidth)) savedWidth = storedWidth;
  } catch (_) {
    // The selector still works when browser storage is disabled.
  }

  const applyWidth = (width) => {
    const safeWidth = supportedWidths.has(width) ? width : "80";
    if (paper) paper.dataset.paperWidth = safeWidth;
    widthPickers.forEach((picker) => { picker.value = safeWidth; });
    if (paper) document.documentElement.style.setProperty("--receipt-width", `${safeWidth}mm`);
    try {
      window.localStorage.setItem(preferenceKey, safeWidth);
    } catch (_) {
      // Keep the current choice for this page even if it cannot be saved.
    }
  };

  if (widthPickers.length) {
    applyWidth(savedWidth);
  } else if (paper) {
    paper.dataset.paperWidth = savedWidth;
    document.documentElement.style.setProperty("--receipt-width", `${savedWidth}mm`);
  }
  widthPickers.forEach((picker) => picker.addEventListener("change", () => applyWidth(picker.value)));
  printButton?.addEventListener("click", () => window.print());

  if (document.body.dataset.autoPrint === "true") {
    window.setTimeout(() => window.print(), 350);
  }
});
