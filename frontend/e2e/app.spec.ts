import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "e2e-clave-2026";
const SHOTS = "e2e/screenshots";

async function setTheme(page: Page, theme: "light" | "dark") {
  await page.addInitScript((t) => {
    try {
      localStorage.setItem("asistencia.theme", t);
    } catch {
      /* sin almacenamiento */
    }
  }, theme);
}

async function login(page: Page) {
  await page.goto("/admin");
  await page.getByLabel("Contraseña").fill(PASSWORD);
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await expect(page.getByRole("heading", { name: "Resumen del día" })).toBeVisible();
}

test("el kiosco carga y obtiene video de la cámara", async ({ page }) => {
  await setTheme(page, "dark");
  await page.goto("/");
  const video = page.getByTestId("kiosk-video");
  await expect(video).toBeVisible();
  await page.waitForFunction(() => {
    const v = document.querySelector<HTMLVideoElement>("[data-testid=kiosk-video]");
    return !!v && v.readyState >= 2 && v.videoWidth > 0;
  });
  // Con la cámara falsa no hay rostro: el kiosco queda esperando a la persona.
  await expect(page.getByText("Acércate para marcar")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("No conectada (opcional)")).toBeVisible();
  await expect(page.getByRole("button", { name: "Ingresar código" })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/kiosco-oscuro.png` });

  await page.getByRole("button", { name: "Ingresar código" }).click();
  await page.getByLabel("Código de estudiante").fill("NOEXISTE");
  await page.getByRole("button", { name: "Continuar" }).click();
  await expect(page.getByText("No hay una persona activa con ese código")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/kiosco-codigo.png` });
});

test("kiosco en tema claro", async ({ page }) => {
  await setTheme(page, "light");
  await page.goto("/");
  await expect(page.getByText("Acércate para marcar")).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: `${SHOTS}/kiosco-claro.png` });
});

test("panel: iniciar sesión, listar personas y exportar", async ({ page }) => {
  await setTheme(page, "light");
  await page.goto("/admin");
  await page.getByLabel("Contraseña").fill("incorrecta");
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await expect(page.getByText("Contraseña incorrecta")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/panel-login.png` });

  await login(page);
  await expect(page.getByText("Presentes ahora").first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/panel-resumen.png`, fullPage: true });

  await page.getByRole("link", { name: "Personas" }).click();
  await expect(page.getByRole("heading", { name: "Personas" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "DEMO001" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "U2026001" })).toBeVisible();
  await page.getByLabel("Buscar").fill("Valentina");
  await expect(page.getByRole("cell", { name: "DEMO001" })).toHaveCount(0);
  await page.getByLabel("Buscar").fill("");
  await expect(page.getByRole("cell", { name: "DEMO001" })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/panel-personas.png`, fullPage: true });

  await page.getByRole("link", { name: "Valentina Ejemplo" }).click();
  await expect(page.getByRole("heading", { name: "Valentina Ejemplo" })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/panel-ficha.png`, fullPage: true });

  await page.getByRole("link", { name: "Marcaciones" }).click();
  await expect(page.getByRole("heading", { name: "Marcaciones" })).toBeVisible();
  await expect(page.getByText(/marcaciones/).first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/panel-marcaciones.png` });

  await page.getByRole("link", { name: "Horas" }).click();
  await expect(page.getByRole("heading", { name: "Totales por persona" })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/panel-horas.png` });

  await page.getByRole("link", { name: "Exportar" }).click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByTestId("export-shifts-csv").click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^jornadas_.*\.csv$/);
  await expect(page.getByText(/Última exportación: jornadas_/)).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/panel-exportar.png` });

  await page.getByRole("link", { name: "Configuración" }).click();
  await expect(page.getByRole("heading", { name: "Motor facial" })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/panel-configuracion.png`, fullPage: true });

  await page.getByRole("link", { name: "Auditoría" }).click();
  await expect(page.getByRole("cell", { name: "Exportación" }).first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/panel-auditoria.png` });
});

test("panel en tema oscuro", async ({ page }) => {
  await setTheme(page, "dark");
  await login(page);
  await page.screenshot({ path: `${SHOTS}/panel-resumen-oscuro.png`, fullPage: true });
});

test("responsive: kiosco y panel a 390 px sin scroll horizontal", async ({ page }) => {
  await setTheme(page, "light");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByText("Acércate para marcar")).toBeVisible({ timeout: 15_000 });
  const kioskOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(kioskOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: `${SHOTS}/movil-kiosco.png`, fullPage: true });

  await login(page);
  await page.getByRole("button", { name: "Menú" }).click();
  await page.getByRole("link", { name: "Personas" }).click();
  await expect(page.getByRole("heading", { name: "Personas" })).toBeVisible();
  const adminOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(adminOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: `${SHOTS}/movil-personas.png` });
});
