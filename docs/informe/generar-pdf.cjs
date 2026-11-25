// Regenera el PDF del informe desde informe.html con el Chromium de Playwright.
// Uso (desde la raíz del repo, con las dependencias del frontend instaladas):
//   node docs/informe/generar-pdf.cjs
const path = require("node:path");
const { createRequire } = require("node:module");
const req = createRequire(path.join(__dirname, "..", "..", "frontend", "package.json"));
const { chromium } = req("@playwright/test");

(async () => {
  const html = path.join(__dirname, "informe.html");
  const pdf = path.join(__dirname, "Informe_Asistencia_Biometrica.pdf");
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto("file:///" + html.split(path.sep).join("/"), { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  await page.pdf({ path: pdf, printBackground: true, preferCSSPageSize: true });
  await browser.close();
  console.log("PDF generado:", pdf);
})();
