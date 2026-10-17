import { chromium } from "@playwright/test";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
await p.goto("https://web-production-972cd.up.railway.app/login");
await p.fill("#email", "admin@apex.demo");
await p.fill("#password", "SteelBid#Demo2026");
await p.getByRole("button", { name: "Sign in" }).click();
await p.waitForURL(/\/$/, { timeout: 30000 });
await p.waitForTimeout(2500);
await p.getByRole("link", { name: "Inquiries" }).click();
await p.waitForTimeout(2500);
await p.getByRole("button", { name: /New inquiry/i }).click();
for (let i = 0; i < 8; i++) {
  await p.screenshot({ path: `frame-open-${i}.png` });
  await p.waitForTimeout(60);
}
await p.waitForTimeout(1200);
await p.keyboard.press("Escape");
for (let i = 0; i < 8; i++) {
  await p.screenshot({ path: `frame-close-${i}.png` });
  await p.waitForTimeout(60);
}
await b.close();
console.log("DONE");
