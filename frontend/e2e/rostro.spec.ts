import { expect, test } from "@playwright/test";

const PASSWORD = "e2e-clave-2026";
const SHOTS = "e2e/screenshots";

// La cámara falsa reproduce un rostro estático enrolado como U2026001 (Valentina Ejemplo).
test("flujo completo con rostro: reto de vida, ENTRADA y ya registrado", async ({ page }) => {
  await page.addInitScript(() => {
    try {
      localStorage.setItem("asistencia.theme", "dark");
      localStorage.setItem("asistencia.sound", "off");
    } catch {
      /* sin almacenamiento */
    }
  });
  const login = await page.request.post("/api/admin/login", { data: { password: PASSWORD } });
  expect(login.ok()).toBeTruthy();
  await page.request.put("/api/admin/settings", { data: { changes: { liveness_enabled: true, liveness_timeout_seconds: 4 } } });

  await page.goto("/");
  // 1) Identifica el rostro y pide el giro de cabeza.
  await expect(page.getByText(/Gira la cabeza a tu (izquierda|derecha)/).first()).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: `${SHOTS}/kiosco-reto-vida.png` });
  // 2) Una foto no gira: la prueba de vida falla por tiempo.
  await expect(page.getByText("Prueba de vida no superada").first()).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: `${SHOTS}/kiosco-vida-fallida.png` });

  // 3) Sin prueba de vida: registra la ENTRADA y muestra la tarjeta.
  await page.request.put("/api/admin/settings", { data: { changes: { liveness_enabled: false } } });
  await expect(page.getByText("ENTRADA registrada").first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Valentina Ejemplo")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/kiosco-entrada.png` });

  // 4) Dentro del anti-rebote: "ya registrado".
  await expect(page.getByText(/Ya registraste tu entrada hace \d+ s/).first()).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: `${SHOTS}/kiosco-ya-registrado.png` });

  // La marcación queda en el panel con su foto.
  const events = await page.request.get("/api/admin/events");
  const body = await events.json();
  const mine = body.items.filter((e: { person_code: string }) => e.person_code === "U2026001");
  expect(mine.length).toBe(1);
  expect(mine[0].event_type).toBe("ENTRADA");
  expect(mine[0].photo_url).toContain("/api/admin/files/captures/");
  await page.request.put("/api/admin/settings", { data: { changes: { liveness_enabled: true, liveness_timeout_seconds: 7 } } });
});
