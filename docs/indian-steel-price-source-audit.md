# Indian steel-price source audit

Date assessed: 2026-10-22  
Scope: customer-facing, genuine Indian TMT/rebar, HRC and CRC price observations.

## Decision

No source currently meets both requirements for automatic customer-facing ingestion: technically accessible published observations **and** documented commercial storage/display/redistribution permission.

SteelBid must not ingest or display Ministry of Steel price observations until written permission confirms the proposed SaaS use. JPC price products require a subscription/licence. No suitable steel-price API or downloadable TMT/HRC/CRC price dataset was verified on data.gov.in.

## Sources assessed

| Publisher / source | Records evidenced | Product / geography / unit | Access | Reuse finding | Classification |
| --- | --- | --- | --- | --- | --- |
| Ministry of Steel, Monthly Economic Report | Monthly retail price observations and trend charts | Mumbai: TMT 10 mm, HR coils 2.50 mm, CR coils 0.63 mm; INR/tonne. Recent reports state prices are inclusive of GST. | Public PDF reports on the Ministry site; monthly report index and archive available. | Ministry copyright policy states website content may not be reproduced partly or fully without due permission. A source acknowledgement alone is insufficient. | `PERMISSION_REQUIRED` |
| Joint Plant Committee (JPC) | JPC states that it collects retail-market prices fortnightly from four metros and selected clusters. | Retail-market/landed-cost data; detailed product, location and basis require report access. | Official current domain verified as `jpcindiansteel.nic.in`. Retail Market Price–Fortnightly is listed as an annual or single-report subscription. | Price report is a paid publication; no commercial SaaS redistribution licence was evidenced. | `LICENSED_PAID` |
| Open Government Data Platform India | Steel production, consumption, import and export catalogues were found. | No verified free downloadable/API dataset containing TMT, HRC or CRC Indian retail price observations was found. | Catalog/API platform. | NDSAP can apply only to the specific dataset; no eligible steel-price dataset was identified. | `UNSUITABLE` |

## Evidence of real Ministry price observations

The Ministry’s Monthly Economic Report for May 2026 reports Mumbai retail prices as of 31 May 2026:

- TMT 10 mm: INR 62,140 per tonne
- HRC 2.50 mm: INR 68,990 per tonne
- CRC 0.63 mm: INR 78,120 per tonne

The report labels the series as **Trend in Retail Steel Prices in Mumbai (Rs/t incl. GST)**. These are genuine, published historical observations, but they are not approved for SteelBid ingestion or redistribution under the currently documented terms.

## Product and field coverage

| Product | Exact published specification | Region | Currency / unit | Price basis | Frequency / date treatment |
| --- | --- | --- | --- | --- | --- |
| TMT / rebar | TMT 10 mm | Mumbai | INR / tonne | Retail, inclusive of GST in current reports | Month-end published observation; monthly report |
| HRC | HR coils 2.50 mm | Mumbai | INR / tonne | Retail, inclusive of GST in current reports | Month-end published observation; monthly report |
| CRC | CR coils 0.63 mm | Mumbai | INR / tonne | Retail, inclusive of GST in current reports | Month-end published observation; monthly report |

Do not represent these observations as national averages, city prices outside Mumbai, ex-works prices, daily prices, or live prices.

## Exact official links

- [Ministry of Steel monthly reports](https://steel.gov.in/monthly-summary)
- [Ministry archived monthly reports](https://steel.gov.in/archived-monthly-summary)
- [May 2026 Monthly Economic Report](https://steel.gov.in/sites/default/files/2026-06/Monthly%20Economic%20Report%20for%20the%20month%20of%20May%2C%202026.pdf)
- [Ministry copyright policy](https://steel.gov.in/website-policies)
- [JPC profile and data coverage](https://jpcindiansteel.nic.in/pages/display/137-jpc-profile)
- [JPC Statistical Reports and subscription pricing](https://jpcindiansteel.nic.in/pages/display/149-jpc-statistical-reports)
- [data.gov.in steel catalogue](https://data.gov.in/catalogs/?filter=catalog_type%3Acatalog_type_raw_data%2Bagency%3A3731&sort=updated+desc)

## Minimum permission / onboarding checklist

Before a Ministry adapter can be enabled, obtain written confirmation covering:

1. Automated retrieval from the specified Monthly Economic Report URLs.
2. Storage of the source document/checksum and extraction of price observations.
3. Customer-facing display in SteelBid, including source attribution.
4. Commercial SaaS redistribution to tenant users.
5. Permitted historical retention and refresh frequency.
6. The exact product, city, unit, GST/freight treatment and reporting-period interpretation.

For JPC, obtain a subscription or data licence that expressly covers API/file access, storage, display and tenant redistribution; document credentials and permitted fields before activation.

## Integration feasibility

Technically, a Ministry adapter can parse monthly Mumbai historical observations and map them without ambiguity to separate TMT 10 mm, HRC 2.50 mm and CRC 0.63 mm series. The existing provider registry, document provenance model and scheduler are sufficient. It must remain disabled because reuse/display permission has not been verified.

### Answer: can SteelBid legally and technically obtain genuine TMT, HRC and CRC prices for free?

Technically yes: Ministry reports publish genuine historical observations. Legally for customer-facing commercial SaaS display, **not yet**: the published Ministry copyright policy requires prior permission. JPC has broader price coverage but is a paid subscription product. No eligible free authorised government API/feed was verified in this audit.
