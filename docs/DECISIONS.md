# Methodology decisions

This document explains each analytical choice in plain language: what was done, why, and what the alternative would
have been. The numbers come from `reports/analysis_results.md` (generated) and `reports/data_quality.md`.

---

## 1. Scope and unit of analysis

- **Population:** short-term acute-care hospitals paid under Medicare's Inpatient Prospective Payment System (IPPS).
  These are the 2,906 hospitals in the Medicare Inpatient by Provider and Service file. Critical-access, psychiatric,
  VA, children's and similar hospitals are not in that file, because they are paid differently or don't bill Medicare
  fee-for-service. They are kept in the hospital table but drop out of the payment analysis.
- **Grain:** `mart_hospital` has **one row per hospital (CCN)**. `mart_hospital_condition` has **one row per hospital
  per HRRP condition**. Duplicate-key checks enforce both grains, and the build fails if they are violated.
- **Payer:** Medicare fee-for-service only. "Cost" here means *what Medicare pays*. It is not the hospital's internal
  cost of delivering care.

## 2. Joins

- **Key:** all sources share the CMS Certification Number (CCN). It is standardised in staging as 6-character text with
  leading zeros (`to_ccn()` macro). This matters because a numeric cast would turn `010001` into `10001` and silently
  break joins.
- **Spine approach:** the hospital table starts from the *union* of CCNs across all sources, and `left join`s each
  source onto it. No hospital is silently dropped. `in_inpatient`, `in_hrrp` and `has_mspb` flags show coverage, and
  each analysis filters to the rows it needs.
- **Match rates** (base = 2,906 inpatient hospitals):

| Join | Match |
|---|---|
| Inpatient → General Information | 98.2% |
| Inpatient → HRRP (any row) | 99.2% |
| Inpatient → HRRP (≥1 scored readmission ratio) | 96.0% |
| Inpatient → MSPB (scored) | 95.9% |
| **Inpatient → all three other sources** | **93.0% (2,704 hospitals)** |
| HRRP condition rows → hospital's own DRG payment for that condition | 56.8% (the rest use state, then national, averages) |

  The 52 inpatient hospitals missing from General Information are mostly closed or merged facilities. Maryland
  hospitals have no MSPB score because Maryland is paid under its own all-payer model.

## 3. Cleaning (staging)

- CMS writes missing values as text (`Not Available`, `N/A`, `Too Few to Report`). One macro, `to_num()`, converts
  anything non-numeric to NULL. That way missing values are never mistaken for zeros, and a stray footnote never crashes
  a cast.
- HRRP rates are published as percentages (e.g. 14.5). They are divided by 100. A data quality check confirms that
  `ERR = predicted / expected` to within 0.001 on every row, which proves the fields were parsed correctly.
- Ownership: 12 CMS categories are collapsed into Non-profit, For-profit (including physician-owned) and Government
  (including VA, DoD and tribal). Several of the original categories are too small to estimate reliably.
- Region: states are mapped to the 4 US Census regions. This keeps the regression from needing about 50 state dummies.
  A state fixed-effects version is reported as a robustness check.
- Size band: fixed, readable cut-points on annual Medicare discharges, chosen after looking at the distribution
  (median ≈ 870): Small < 500, Medium 500–1,999, Large 2,000–4,999, Very large ≥ 5,000.

## 4. Cost components: case mix vs price

Payment per discharge is split into two parts:

```
payment per discharge = national average × case-mix index × price index
case-mix index = Σ(hospital discharges in DRG × national avg payment for DRG) / discharges / national avg
price index    = actual payments / that "expected" amount
```

- The **case-mix index** captures *what kind* of patients a hospital treats.
- The **price index** captures *how much Medicare pays it* for the same DRG: wage index, teaching (IME) and safety-net
  (DSH) add-ons, and outliers.

On the log scale the two add up, so their contribution to variance can be measured. Case mix accounts for 51% and price
for 49%. The case-mix index is built from the same data, so it is an approximation of CMS's official CMI, which uses
DRG weights.

**MSPB components:** the Spending by Claim file splits each hospital's average episode cost into 7 claim types × 3
periods. For each component, its share of *cross-hospital variation* is `cov(component, total) / var(total)`. These
shares add up to 100%, so they show which components make hospitals *differ*, as opposed to which are simply large.

## 5. Excess readmissions estimate

HRRP publishes, for each hospital and condition, the **predicted** readmission rate (this hospital's patients at this
hospital) and the **expected** rate (the same patients at an average hospital), both risk-adjusted by CMS.

```
excess readmissions (3 yrs) = (predicted rate − expected rate) × eligible discharges
annual excess               = that ÷ 3.0 years (Jul 2021 – Jun 2024)
annual excess cost          = max(annual excess, 0) × cost of one readmission
```

- **Why predicted − expected, not observed − expected:** this matches how CMS defines the ratio (ERR = P/E). The
  predicted rate is also stabilised by CMS's hierarchical model, so it is less noisy than the raw observed rate.
- **Why only positive excess:** a hospital doing *better* than expected doesn't create spending that someone could
  remove, and offsetting one hospital's success against another's failure would hide the opportunity. The net figure is
  also reported (321 readmissions a year, versus 4,082 positive), and it shows the national total is close to zero.
- **Cost of one readmission:** the user brief specifies the average payment for the condition's DRGs. The mapping is in
  `sql/staging/07_stg_hrrp_drg_map.sql`: AMI 280–282, HF 291–293, pneumonia 193–195 + 177–179, COPD 190–192,
  CABG 231–236, hip/knee 469–470.
  - **Base:** the hospital's own discharge-weighted average Medicare payment for those DRGs. If the hospital has no
    published DRG cells for the condition, the state average is used, then the national average.
  - **Low:** national average Medicare payment for the *non-MCC* DRGs only (on the view that avoidable readmissions are
    the less complex ones), capped at the base value.
  - **High:** the hospital's average *total* payment (Medicare + patient cost-sharing + other primary payer).
- **Suppressed counts:** 3,683 rows have a published ratio but suppressed counts (fewer than 11 readmissions over 3
  years). For rows with ERR > 1, an upper bound is `10 × (1 − 1/ERR)` excess readmissions over 3 years. Across all of
  them this adds at most **$4.3M/yr**, so the conclusion doesn't change.
- **Cross-check:** CMS's penalty formula is roughly (ERR − 1) × payments for index stays, which is excess readmissions ÷
  expected rate × payment. Our approximation of it is **$291M/yr**, the same order of magnitude as published HRRP penalty
  totals. This suggests the inputs are sensible, and it shows the penalty is about 6.6× the direct cost of the
  readmissions.

## 6. Regression (question a)

- **Model:** OLS (`statsmodels`). The outcomes are **log** Medicare payment per discharge and the MSPB ratio.
  - The log is used because payment is right-skewed and the drivers act multiplicatively (a wage index multiplies the
    price). Coefficients then read as % differences.
  - MSPB is already a ratio centred on 1, so it is modelled as is.
- **Predictors (as requested):** size band, ownership group, Census region, star rating (1–5, linear) and the
  hospital's mean excess readmission ratio. The ratio is rescaled so that 1 unit = +0.1 (e.g. 1.00 → 1.10).
  **Extended model:** adds the log case-mix index and urban/rural (from the RUCA code).
- **Reference groups:** Small, Non-profit, South (the largest region).
- **Sample:** acute-care hospitals with all predictors present. That is n = 2,594 for payment and n = 2,544 for MSPB.
  The main reason for exclusion is a missing star rating, which happens for hospitals with too few measures.
- **Assumptions checked** (all values in `reports/analysis_results.md`):

| Assumption | Check | Result | What was done |
|---|---|---|---|
| Constant error variance | Breusch–Pagan | rejected (p < 1e-9) | **HC3 robust standard errors** for all inference |
| Normal residuals | Jarque–Bera, skew/kurtosis | rejected (skew 1.2–1.9, heavy tails) | n > 2,500, so coefficient tests rely on the CLT. The log outcome reduces skew. Noted as a limitation |
| No multicollinearity | VIF | max VIF 1.8 | fine |
| Influential points | Cook's D > 4/n | 118–156 hospitals | refit without them: same signs, R² rises (0.64 → 0.75). Results are not driven by outliers |
| Linearity of star rating | star as categories | R² 0.642 → 0.643 | linear is adequate |
| Region too coarse | state fixed effects | R² 0.642 → 0.769 | states capture more of price (wage index). Conclusions unchanged |
| Maryland waiver | drop MD hospitals | R² 0.675, readmission ratio still n.s. | conclusions unchanged |

- **Importance:** besides coefficients, each block's **unique R²** is reported: how much R² falls if that block is
  removed. This answers "which driver matters most" better than comparing coefficients measured on different scales.
- **Interpretation:** these are associations from observational data, not causal effects.

## 7. Significance test (question c)

- **Groups:** top versus bottom **quartile** of hospitals by Medicare discharges (≥ 2,373 vs ≤ 292), among hospitals
  with a readmission ratio. Quartiles give clearly different groups of equal size (698 vs 702) without choosing an
  arbitrary cut-off.
- **Outcome:** each hospital's mean excess readmission ratio across its scored conditions.
- **Test: Mann–Whitney U** (two-sided).
  - The ratio distributions are skewed and heavy-tailed: Shapiro p = 1e-22 for the low group.
  - Their variances differ: Levene p = 0.001.
  - A rank test compares distributions without assuming normality, and isn't pulled by outliers.
  - **Welch's t-test** (which doesn't assume equal variances) is reported as a check, and agrees (p = 0.05).
- **Effect size:** **rank-biserial correlation** (r = 0.05). This pairs naturally with Mann–Whitney, and |r| < 0.1 is
  negligible. Also reported: Cohen's d (0.10), the Hodges–Lehmann shift (0.004) and a bootstrap 95% CI for the
  difference in medians (−0.002 to 0.011, which includes 0).
- **Per condition:** the same test is run for each condition, with **Holm correction** for the 5 comparisons. Only
  heart failure is significant (p_holm = 0.02), and high-volume hospitals are slightly *better* there (r = −0.09).
- **Caveat:** CMS shrinks low-volume hospitals' ratios toward 1.0 (hierarchical model). This makes low-volume hospitals
  look more "average" and reduces the power to detect a difference.

## 8. Savings scenario (question d)

```
annual saving = r × Σ (hospitals h in top N) Σ (conditions c) max(excess_hc per year, 0) × cost_per_readmission_hc
```

- **r = 10%** (as specified). The sensitivity table also shows 5%, 20% and 100%.
- **N = 402:** the smallest number of hospitals that together account for 50% of Medicare discharges (a running-share
  window function). The reasoning is Pareto-style: 14% of hospitals carry half the volume, so a program of realistic
  size reaches half the patients. N = 50, 100, 250 and all hospitals are shown for comparison.
- **Low / base / high** use the three readmission-cost assumptions in §5: **$1.33M / $1.92M / $2.39M per year**.
- **Assumptions:**
  1. The 10% reduction applies to *excess* readmissions only, not all readmissions.
  2. CY2024 payment levels.
  3. Average volumes from the 3-year HRRP window.
  4. No program cost is subtracted, so this is gross saving.
  5. A prevented readmission saves the full average payment.
  6. Only the 6 HRRP conditions are counted.

---

## 9. Ten likely interview questions (with answers)

**1. Why didn't you find readmissions to be the top cost driver, when they are usually described as a big problem?**
Readmissions in total *are* large. Post-discharge inpatient care is about 16% of MSPB episode spending. But the question
was about *excess* readmissions, the ones above what the patient mix predicts. Those come to about $44M/yr, or 0.06% of
the $75B. Most readmissions are expected given how sick the patients are. The policy weight of readmissions comes from
the HRRP penalty, which is about 6.6× the direct cost, not from the cost of the extra stays.

**2. How did you estimate excess readmissions, and why that formula?**
(Predicted rate − expected rate) × eligible discharges, divided by the 3-year period. CMS defines ERR as predicted ÷
expected, so this is the readmission count implied by CMS's own ratio. It uses CMS's risk adjustment rather than raw
rates that I would have to adjust myself.

**3. What does your regression R² of 0.26 vs 0.64 tell you?**
The requested predictors (size, ownership, region, stars, readmissions) explain 26% of the variation in payment per
discharge. Adding case mix raises that to 64%, and case mix alone has a unique R² of 0.37. Most "size effects" are really
case-mix effects: very large hospitals go from +43% to −4% once case mix is controlled.

**4. The readmission ratio was significant in the first model but not the second. Why?**
Confounding. Hospitals with higher readmission ratios tend to treat a less complex DRG mix, which is paid less per
discharge. Once case mix is in the model, the readmission coefficient drops to −0.9% (p = 0.34). This is a good example
of why I show both models rather than only the specified one.

**5. Which regression assumptions failed, and what did you do?**
Heteroskedasticity (Breusch–Pagan p < 1e-9), so I used HC3 robust standard errors. Residuals aren't normal, but with
more than 2,500 hospitals coefficient inference relies on the central limit theorem. I checked VIFs (max 1.8),
influential points (results hold without them), linearity of star rating, and state versus region fixed effects.

**6. Why Mann–Whitney instead of a t-test?**
The ratios are skewed with heavy tails and unequal variances, and the question is whether one group tends to have higher
values than the other. Mann–Whitney answers that without assuming normality. I also ran Welch's t-test as a sensitivity
check. Both say the difference is borderline at best (p = 0.09 / 0.05), and the effect size is negligible
(rank-biserial 0.05, d = 0.10). With n ≈ 700 per group, even tiny differences can reach significance, which is why I
lead with the effect size.

**7. How did you choose N for the savings scenario?**
N = 402, the fewest hospitals covering 50% of Medicare discharges, calculated with a running-share window function. It
reflects how a payer or health system would focus a program. I show N = 50, 100, 250 and all hospitals so the reader can
see that the answer depends very little on N: even 100% elimination nationally is only $44M.

**8. What are the biggest limitations?**
(a) Medicare fee-for-service only, so no commercial or Medicare Advantage patients. (b) Observational data, so these are
associations, not causes. (c) CMS suppresses small counts. Excess counts are only available for 44% of hospital-condition
rows, although an upper bound for the rest adds less than $4.3M. (d) The time windows differ: readmissions are Jul
2021–Jun 2024, while payments and MSPB are CY2024. (e) Readmission cost is approximated with the index condition's DRG
payment, but an actual readmission may fall in a different DRG.

**9. How do you know the joins are right?**
The CCN is standardised as 6-character text in every staging model. I report match rates for each join (93% of
inpatient hospitals match all three other sources) and enforce unique keys on every table. The ERR = P/E identity holds
on every HRRP row, and MSPB components add up to the episode total for every hospital. All of these checks are in
`sql/quality/` and run on every build.

**10. If you had more time or data, what would you add?**
Medicare Advantage or all-payer claims, to get beyond fee-for-service. CMS's official case-mix index and wage index from
the IPPS Impact File, to replace my approximations. Hospital Cost Reports, to measure what care *costs* the hospital
rather than what Medicare pays. Year-over-year HRRP files, to estimate change within hospitals, which gets closer to a
causal effect than a cross-section does.
