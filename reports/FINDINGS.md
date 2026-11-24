# Findings: what drives Medicare hospital costs?

**For:** Operations Director  **Data:** public CMS data for 2,906 US acute-care hospitals. Medicare fee-for-service
inpatient payments are for CY2024 ($75.1B, 4.95M discharges). Readmissions data is for July 2021–June 2024.
**Bottom line:** readmissions are **not** a major cost driver. **Which patients a hospital treats (case mix)** and
**where it is (regional price levels)** explain most of the cost differences. Excess readmissions cost less than 0.1% of
inpatient spend.

---

### 1. Excess readmissions cost about $44M a year, or 0.06% of Medicare inpatient spend

- **Number:** $44.3M per year (range $30.5M–$53.7M) for the six conditions Medicare tracks. That is about 4,100
  readmissions a year above what each hospital's patient mix predicts. Heart failure ($15.9M) and pneumonia ($15.8M)
  make up 72% of it. Across all hospitals the net excess is close to zero, because hospitals that do better than expected
  almost cancel out those that do worse.
- **What it means:** readmissions matter for quality and for Medicare's penalty program. A penalty-style calculation
  ((ratio − 1) × payments for the original stays) comes to about $291M, roughly 6.6× the direct cost. Most of a
  hospital's financial exposure is the penalty, not the cost of the extra stays. Readmissions are too small to anchor a
  cost-reduction program.
- **Action:** frame readmission work as quality improvement and penalty avoidance. Focus it on heart failure and
  pneumonia. Don't count it as a major source of cost savings.

### 2. The top cost driver is case mix, and sepsis leads it

- **Number:** one diagnosis group, sepsis with major complications (DRG 871), accounts for **$8.96B (11.9%)** of all
  Medicare inpatient payments. 25 of 540 DRGs account for half of all spending. Case mix accounts for about **half (51%)**
  of the hospital-to-hospital variation in payment per discharge. Adding it to the regression raises the share of
  variation explained from 26% to 64%.
- **What it means:** hospitals that look "expensive" usually treat sicker, more complex patients. In the raw comparison,
  very large hospitals cost 43% more per discharge than small ones. After adjusting for case mix, they cost about 4% *less*.
- **Action:** benchmark hospitals only on **case-mix-adjusted** cost. Put cost-reduction effort into the highest-spend
  service lines, starting with sepsis (early recognition, length of stay, ICU use).

### 3. Location is the second driver: the same patients cost 18–25% more in the Northeast and West

- **Number:** for the same case mix, payment per discharge is **25% higher in the West** and **18% higher in the
  Northeast** than in the South. Government-owned hospitals are 11% higher than non-profits, and for-profit hospitals are
  5% lower. Case-mix-adjusted payment ranges from about $10.3K (Vermont) to $20.2K (California) and $23.7K (Maryland,
  which uses a different all-payer payment system).
- **What it means:** much of the cost gap is driven by Medicare's price formula (local wage index, teaching and
  safety-net add-ons), which hospitals can't control.
- **Action:** compare hospitals with peers in the same region or state, not against a national average.

### 4. For whole episodes (MSPB), the index stay and post-discharge care drive costs, and low-star hospitals are the outliers

- **Number:** in a Medicare episode (3 days before admission to 30 days after discharge), the hospital stay is 45% of
  spending. **Inpatient care after discharge (all readmissions, expected or not) is 16% of spending but 22% of the
  difference between hospitals.** Skilled nursing is another 15% of spending. Each additional quality star is linked to
  1.5 points lower MSPB. 1-star hospitals have **~5× the excess readmission cost per 1,000 discharges** of 5-star
  hospitals ($126K vs $26K).
- **What it means:** the post-discharge period matters for cost through *all* readmissions and post-acute care, not
  just the "excess" ones. Low-rated hospitals are where improvement pays off most.
- **Action:** select hospitals for transition-of-care and post-acute partnership programs based on **star rating and
  readmission ratio**, not size.

### 5. A 10% cut in excess readmissions at the 402 largest hospitals saves about $1.9M a year, and size doesn't predict readmissions

- **Number:** the 402 highest-volume hospitals (14% of hospitals, 50% of discharges) would avoid about 168 readmissions
  a year, saving **$1.9M per year (range $1.3M–$2.4M)**. Even if every hospital eliminated *all* excess readmissions, the
  saving would be only $44M. High- and low-volume hospitals have nearly identical readmission ratios (median 0.998 vs
  0.994, p = 0.09, negligible effect size).
- **What it means:** targeting by size alone has low return, because size isn't linked to worse readmission performance.
- **Action:** if a readmission program goes ahead, enrol hospitals with ratios above 1.0 and low star ratings, and
  measure its value mainly through penalty avoidance and quality.

---
*Caveats:* the data covers Medicare fee-for-service only. The results are associations, not proof of cause and effect.
CMS suppresses small counts, which leaves out many low-volume hospital/condition cells (an upper-bound check adds less
than $4.3M). Full method: `docs/DECISIONS.md`. Full tables: `reports/analysis_results.md`.
