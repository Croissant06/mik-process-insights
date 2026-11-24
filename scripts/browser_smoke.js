// Focused real-browser check (Playwright + Chromium). SYNTHETIC DATA ONLY - run against a demo/staging instance.
//
//   BASE_URL=http://127.0.0.1:8000 node scripts/browser_smoke.js
//   BASE_URL=https://reports.test.local CHROMIUM_ARGS="--host-resolver-rules=MAP reports.test.local 127.0.0.1" \
//     IGNORE_HTTPS_ERRORS=1 node scripts/browser_smoke.js
//
// Checks: six confirmed departments; date picker can reach years below 1000 (ISO value 4-digit padded, DD.MM.YYYY shown),
// the server accepts that date, future dates are refused by the server (422); 10 files accepted, an 11th is refused in the
// browser; a double submit (retry) with the same fill stores one report (same id returned).
const { chromium } = require("playwright");
const fs = require("fs");
const os = require("os");
const path = require("path");

const BASE = process.env.BASE_URL || "http://127.0.0.1:8000";
const DEPARTMENTS = ["Офис-администрация", "CAD/CAM", "Кроялен участък", "Шевен участък / Производство", "Довършителен участък", "Склад и опаковка"];
let failed = 0;
const check = (name, ok, extra = "") => { if (!ok) failed++; console.log(`${ok ? "PASS" : "FAIL"} ${name}${extra ? "  [" + extra + "]" : ""}`); };

(async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mik-smoke-"));
  const files = [...Array(11).keys()].map((i) => { const f = path.join(dir, `file-${i + 1}.dat`); fs.writeFileSync(f, Buffer.alloc(50000 + i, i + 1)); return f; });
  const args = (process.env.CHROMIUM_ARGS || "").split(" --").filter(Boolean).map((a, i) => (i ? "--" + a : a));
  const browser = await chromium.launch({ args });
  const ctx = await browser.newContext({ ignoreHTTPSErrors: !!process.env.IGNORE_HTTPS_ERRORS, viewport: { width: 390, height: 900 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error" && !/status of (4\d\d|5\d\d)/.test(m.text())) errors.push(m.text()); });

  await page.goto(BASE + "/");
  const options = await page.$$eval("select[name=department] option", (o) => o.map((x) => x.textContent.trim()).filter((t) => t && t !== "Изберете"));
  check("six confirmed department labels, exactly", JSON.stringify(options) === JSON.stringify(DEPARTMENTS), options.length + " labels");

  // --- date picker: years below 1000 -------------------------------------------------------------------------------
  await page.click(".datepicker__trigger");
  const year = await page.$(".datepicker__year");
  check("picker has a free year field (no earliest date)", !!year);
  for (const y of ["1995", "0950", "50", "1"]) {
    await year.fill(y); // no manual "change": typing alone must navigate
    const shown = Number(await year.inputValue());
    const first = await page.$eval(".datepicker__day", (e) => e.dataset.iso);
    check(`year ${y}: calendar shows ${String(Number(y)).padStart(4, "0")}`, shown === Number(y) && first.startsWith(String(Number(y)).padStart(4, "0") + "-"), first);
  }
  await year.fill("50");
  await page.click('.datepicker__day[data-iso$="-11-15"]');
  const iso = await page.$eval("input[name=work_date]", (e) => e.value);
  const label = await page.textContent(".datepicker__value");
  check("year 50 selected: ISO 0050-11-15 and display 15.11.0050", iso === "0050-11-15" && label.trim() === "15.11.0050", `${iso} / ${label.trim()}`);
  await page.click(".datepicker__trigger");
  const weekdayOk = await page.$eval(".datepicker__day[data-iso='0050-11-15']", (e) => e.getAttribute("aria-label"));
  check("calendar arithmetic stays in year 50 (no 1950 wrap)", /0050|50/.test(weekdayOk) && !/1950/.test(weekdayOk), weekdayOk);
  await page.keyboard.press("Escape");

  // --- submit that old date through the real form -----------------------------------------------------------------
  await page.fill("[name=respondent_name]", "Тест Браузър");
  await page.selectOption("select[name=department]", { label: "CAD/CAM" });
  const areas = await page.$$("textarea");
  await areas[0].fill("Синтетична задача");
  await areas[1].fill("Няма");
  await page.check("input[type=checkbox][value=none]");
  await page.setInputFiles("#attachments", files.slice(0, 10));
  const [res] = await Promise.all([page.waitForResponse((r) => r.url().includes("/api/submissions") && r.request().method() === "POST"), page.click("button[type=submit]")]);
  check("form with year-50 date and 10 files is accepted", [200, 201].includes(res.status()), String(res.status()));
  const firstId = (await res.json()).id;
  const body = JSON.parse(res.request().postData());

  // --- retry with the same key: one report -------------------------------------------------------------------------
  const retry = await page.evaluate(async ([payload, url]) => {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    return { status: r.status, body: await r.json() };
  }, [body, new URL(res.url()).pathname]);
  check("retry with the same key returns the same report (200)", retry.status === 200 && retry.body.id === firstId, `${retry.status}`);
  const conflict = await page.evaluate(async ([payload, url]) => {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...payload, respondent_name: "Друго" }) });
    return r.status;
  }, [body, new URL(res.url()).pathname]);
  check("same key, changed content -> 409", conflict === 409, String(conflict));

  // --- future date is refused by the server -----------------------------------------------------------------------
  const future = await page.evaluate(async (payload) => {
    const { attachments, idempotency_key, ...rest } = payload;
    const r = await fetch("/api/submissions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...rest, work_date: "2999-01-01" }) });
    return { status: r.status, body: await r.json() };
  }, body);
  check("future date refused by the server (422)", future.status === 422 && !!future.body.errors.work_date, String(future.status));

  // --- 11 files refused in the browser ------------------------------------------------------------------------------
  await page.goto(BASE + "/");
  await page.fill("[name=respondent_name]", "Тест Единадесет");
  await page.selectOption("select[name=department]", { label: "Склад и опаковка" });
  const areas2 = await page.$$("textarea");
  await areas2[0].fill("x");
  await areas2[1].fill("Няма");
  await page.check("input[type=checkbox][value=none]");
  await page.setInputFiles("#attachments", files);
  await page.click("button[type=submit]");
  await page.waitForTimeout(600);
  const msg = (await page.textContent("#err-attachments")).trim();
  check("11 files refused in the browser with the Bulgarian message", msg.includes("до 10 файла"), msg);

  check("no unexpected console/page errors", errors.length === 0, JSON.stringify(errors));
  await browser.close();
  fs.rmSync(dir, { recursive: true, force: true });
  console.log(failed ? `${failed} CHECK(S) FAILED` : "ALL PASS");
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error("ERROR", e.message); process.exit(1); });
