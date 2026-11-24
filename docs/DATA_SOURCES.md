# Data sources

All data is public, free, and needs no credentials. `python/ingest.py` (`make ingest`) downloads each file to
`data/raw/<source>_<download-date>.csv`. It also writes `docs/source_manifest.json`, which records the exact URL, the
dataset version, the file size and a SHA-256 checksum for every file it downloaded.

The ingest script finds the **current** download link at run time:

- **Provider Data Catalog** datasets come from the CMS metastore API
  (`https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/<id>`).
- **Medicare Inpatient** comes from the data.cms.gov DCAT catalog (`https://data.cms.gov/data.json`), taking the most
  recent data year.

When CMS publishes a new version, a re-run picks it up. If the catalog lookup fails, the script falls back to the pinned
URLs below. If a download fails, it prints the dataset page and the filename to save the file under.

## Versions used for the committed results (downloaded 2026-11-24)

| # | Source (`data/raw/` prefix) | Publisher / catalog ID | Version | Period covered | Grain | Rows |
|---|---|---|---|---|---|---|
| 1 | Hospital General Information (`hospital_general_info_`) | CMS Provider Data Catalog `xubh-q36u` | modified 2026-10-26 | current facility list | 1 row per facility | 5,435 |
| 2 | Hospital Readmissions Reduction Program (`hrrp_`) | CMS Provider Data Catalog `9n3s-kdb3` | FY 2026 program year, modified 2026-01-26 | discharges 07/01/2021 – 06/30/2024 | facility × condition | 18,330 |
| 3 | Medicare Inpatient Hospitals – by Provider and Service (`inpatient_by_provider_service_`) | data.cms.gov (Medicare Provider Utilization & Payment), RY26 P03 V10 DY24 | data year 2024, catalog modified 2026-04-23 | CY 2024 Original Medicare (FFS) IPPS discharges | facility × MS-DRG | 145,879 |
| 4 | Medicare Spending Per Beneficiary – Hospital (`mspb_`) | CMS Provider Data Catalog `rrqw-56er` | modified 2026-10-19 | episodes in CY 2024 | 1 row per facility | 4,623 |
| 5 | Medicare Hospital Spending by Claim (`mspb_by_claim_`) *(added; see below)* | CMS Provider Data Catalog `nrth-mfg3` | modified 2026-01-26 | episodes in CY 2024 | facility × period × claim type | 63,646 |

### Exact download URLs

1. Hospital General Information
   - Page: https://data.cms.gov/provider-data/dataset/xubh-q36u
   - File: https://data.cms.gov/provider-data/sites/default/files/resources/d3bf87c5505155f549d603688414f3c6_1793059553/Hospital_General_Information_2.csv
2. Hospital Readmissions Reduction Program
   - Page: https://data.cms.gov/provider-data/dataset/9n3s-kdb3
   - File: https://data.cms.gov/provider-data/sites/default/files/resources/a171bc36c488d3e0dc33ec63abb469a6_1770163617/FY_2026_Hospital_Readmissions_Reduction_Program_Hospital.csv
3. Medicare Inpatient Hospitals – by Provider and Service (data year 2024)
   - Page: https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals/medicare-inpatient-hospitals-by-provider-and-service
   - File: https://data.cms.gov/sites/default/files/2026-04/828defb5-c9e6-4442-8c1b-f27bc0799daf/MUP_INP_RY26_P03_V10_DY24_PrvSvc.CSV
   - API: https://data.cms.gov/data-api/v1/dataset/690ddc6c-2767-4618-b277-420ffb2bf27c/data
4. Medicare Spending Per Beneficiary – Hospital
   - Page: https://data.cms.gov/provider-data/dataset/rrqw-56er
   - File: https://data.cms.gov/provider-data/sites/default/files/resources/69874ce604586980ac088283c1b35095_1792599862/Medicare_Hospital_Spending_Per_Patient-Hospital.csv
5. Medicare Hospital Spending by Claim
   - Page: https://data.cms.gov/provider-data/dataset/nrth-mfg3
   - File: https://data.cms.gov/provider-data/sites/default/files/resources/1f8cde9e222d5d49f88a894bcf7a8981_1770163638/Medicare_Hospital_Spending_by_Claim.csv

### Why a fifth dataset?

The brief asks which **cost components** drive MSPB. The MSPB file has only one number per hospital (the ratio), so it
can't answer that. *Medicare Hospital Spending by Claim* is the companion CMS file. It splits the same MSPB episode
dollars by period (before admission, the index stay, 30 days after discharge) and by claim type (inpatient, skilled
nursing, home health, physician/carrier, outpatient, hospice, equipment). It is small (10 MB) and uses the same facility ID.

## How the sources link

All five files identify a hospital by its **CMS Certification Number (CCN)**: 6 characters, called "Facility ID" in the
Provider Data Catalog and `Rndrng_Prvdr_CCN` in the inpatient file. Staging stores it as text padded to 6 characters, so
leading zeros are kept (`010001`, not `10001`). Join match rates are in `reports/data_quality.md`.

## Known source quirks (handled in `sql/staging/`)

| Quirk | Where | Handling |
|---|---|---|
| Missing values written as text: `Not Available`, `N/A`, `Too Few to Report` | all PDC files | `to_num()` macro returns NULL |
| HRRP discharges and readmissions suppressed when readmissions < 11, while the ratio and rates are still published | HRRP (3,683 rows) | kept and flagged `counts_suppressed`. Excluded from excess counts, with an upper-bound sensitivity calculated for them |
| HRRP counts cover 3 years | HRRP | divided by the period length (3.0 years) to annualise |
| Hospital × DRG cells with < 11 discharges are not published | Inpatient | hospital totals undercount small hospitals (noted as a limitation) |
| Percent strings (`0.09%`) | Spending by Claim | `%` stripped, divided by 100 |
| Maryland hospitals are paid under the state all-payer model and have no MSPB score | Inpatient, MSPB | kept. Regression re-run without Maryland as a robustness check |

## Re-downloading manually

If `make ingest` reports a failure, open the dataset page above, download the CSV, and save it as
`data/raw/<prefix><YYYY-MM-DD>.csv` (for example `data/raw/hrrp_2026-11-24.csv`). Then run `make transform`.
