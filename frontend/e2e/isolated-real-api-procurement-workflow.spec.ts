import { expect, request, test } from "@playwright/test";

const password = "SteelBid#Demo2026";
async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill("admin@apex.demo");
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("[DEMO] Apex Steel Traders Pvt Ltd").first()).toBeVisible();
}

test("isolated real API: tender shortage progresses through RFQ, compatible offer, and persisted selection", async ({ page }) => {
  await login(page);
  const material = (await (await page.request.get("/api/v1/materials?search=ISMB%20200")).json()).items[0] as { id:string; name:string };
  const supplier = (await (await page.request.get("/api/v1/suppliers?page_size=1")).json()).items[0] as { id:string; name:string };
  const tenderResponse = await page.request.post("/api/v1/tenders", { data: { number: `E2E-PROC-${Date.now()}`, title: "[SYNTHETIC E2E] Tender procurement workspace", project_type: "FABRICATION" } });
  expect(tenderResponse.ok()).toBeTruthy(); const tender=await tenderResponse.json() as {id:string};
  expect((await page.request.post(`/api/v1/tenders/${tender.id}/boq`, { data: { line_no:"1",raw_description:"ISMB 200 E250",form:"BEAM",grade:"E250",quantity:"100",unit:"MT",material_id:material.id } })).ok()).toBeTruthy();
  expect((await page.request.post(`/api/v1/tenders/${tender.id}/requirement-snapshots`)).ok()).toBeTruthy();
  expect((await page.request.post(`/api/v1/tenders/${tender.id}/workflow/bom`)).ok()).toBeTruthy();
  const snapshot=(await (await page.request.get(`/api/v1/tenders/${tender.id}/requirement-snapshots`)).json())[0] as {id:string};
  const valid=await page.request.post("/api/v1/procurement/supplier-quotes", { data: { supplier_id:supplier.id,material_id:material.id,quantity:"100",unit:"MT",unit_price:"50000",freight_per_unit:"500",currency:"INR",valid_until:"2027-01-01" } });
  expect(valid.ok()).toBeTruthy();
  expect((await page.request.post("/api/v1/procurement/supplier-quotes", { data: { supplier_id:supplier.id,material_id:material.id,quantity:"100",unit:"MT",unit_price:"49000",currency:"INR",valid_until:"2020-01-01" } })).ok()).toBeTruthy();

  await page.goto(`/tenders/${tender.id}?section=procurement`);
  const workspace=page.getByLabel("Tender procurement and supplier offers");
  await expect(workspace.getByText(material.name).first()).toBeVisible();
  await expect(workspace.getByText("SHORTAGE", { exact:true })).toBeVisible();
  await workspace.getByRole("button", { name:"Create requirements" }).click();
  await expect(page.getByText("Tender procurement requirements saved.")).toBeVisible();
  await page.screenshot({path:"e2e/isolated-real-procurement-summary.png",fullPage:true});

  await workspace.getByLabel("RFQ supplier").selectOption(supplier.id);
  await workspace.getByRole("button", {name:"Generate draft RFQ"}).click();
  await expect(page.getByText("Draft RFQ created. It has not been issued or sent.")).toBeVisible();
  await expect(workspace.locator("tbody").getByText(supplier.name, {exact:true}).last()).toBeVisible();
  await expect(workspace.getByText("EXPIRED", {exact:true}).first()).toBeVisible();
  const expiredRow=workspace.locator("tr").filter({hasText:"EXPIRED"});
  await expect(expiredRow.first().getByRole("button", {name:"Select"})).toBeDisabled();
  const selectableOffer=workspace.locator("button:not([disabled])", {hasText:"Select"}).first();
  await expect(selectableOffer).toBeEnabled();
  await selectableOffer.click();
  await expect(page.getByText("Compatible supplier selection saved.")).toBeVisible();
  await page.reload();
  await expect(workspace.getByText("SELECTED", {exact:true})).toBeVisible();
  await page.screenshot({path:"e2e/isolated-real-procurement-selection.png",fullPage:true});
  const selection=(await (await page.request.get(`/api/v1/tenders/${tender.id}/supplier-selections`)).json())[0] as {id:string};
  await workspace.getByLabel(`Cancellation reason for ${selection.id}`).fill("Supplier revised delivery");
  await workspace.getByRole("button", {name:"Cancel selection"}).click();
  await expect(page.getByText("Supplier selection cancelled with its recorded reason.")).toBeVisible();
  const history=(await (await page.request.get(`/api/v1/tenders/${tender.id}/supplier-selections/history`)).json()) as {id:string;status:string;reason:string}[];
  expect(history.some((row)=>row.id===selection.id&&row.status==="CANCELLED"&&row.reason==="Supplier revised delivery")).toBeTruthy();

  const viewer=await request.newContext({baseURL:process.env.PLAYWRIGHT_BASE_URL||"http://127.0.0.1:3100"});
  expect((await viewer.post("/api/v1/auth/login",{data:{email:"viewer@apex.demo",password}})).ok()).toBeTruthy();
  expect((await viewer.post(`/api/v1/tenders/${tender.id}/workflow/procurement-requirements`)).status()).toBe(403);
  await viewer.dispose();
  const offers=await page.request.get(`/api/v1/tenders/${tender.id}/requirement-snapshots/${snapshot.id}/supplier-offers`);
  expect(offers.ok()).toBeTruthy();
  expect((await offers.json()).items.some((offer:{comparison_status:string})=>offer.comparison_status==="EXPIRED")).toBeTruthy();
});
