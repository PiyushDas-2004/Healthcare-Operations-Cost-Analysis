"""
Step 3 - Statistical analysis of the DuckDB analytical tables.

Answers four questions with real numbers from the CMS data:
  0) Context: where does Medicare inpatient money go? (DRG concentration,
     case-mix vs price decomposition, MSPB episode cost components)
  a) What drives Medicare payment per discharge and MSPB? (OLS, statsmodels)
  b) How much do excess readmissions cost, by condition and hospital segment?
  c) Do high-volume hospitals differ from low-volume ones on readmissions?
     (Mann-Whitney U + rank-biserial effect size, Welch t-test as a check)
  d) Savings scenario: top-N highest-volume hospitals cut excess readmissions 10%

Every function returns plain pandas objects / dicts so the notebook
(notebooks/analysis.ipynb) can call them and show the same numbers.

Outputs (python python/analysis.py):
  reports/results.json             every headline number, machine readable
  reports/analysis_results.md      all result tables (auto-generated)
  reports/figures/*.png, *.html    charts
  reports/powerbi/*.csv            clean tables for Power BI
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import statsmodels.formula.api as smf  # noqa: E402
from scipy import stats  # noqa: E402
from statsmodels.stats.diagnostic import het_breuschpagan  # noqa: E402
from statsmodels.stats.multitest import multipletests  # noqa: E402
from statsmodels.stats.outliers_influence import variance_inflation_factor  # noqa: E402
from statsmodels.stats.stattools import jarque_bera  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "healthcare.duckdb"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
POWERBI = REPORTS / "powerbi"

# Savings scenario parameters (see docs/DECISIONS.md)
REDUCTION = 0.10            # 10% cut in excess readmissions
TOP_N_DISCHARGE_SHARE = 0.50  # N = fewest hospitals covering 50% of Medicare discharges
RNG_SEED = 42

CONDITION_LABELS = {
    "HF": "Heart failure", "PN": "Pneumonia", "AMI": "Heart attack (AMI)",
    "COPD": "COPD", "CABG": "CABG surgery", "HIP-KNEE": "Hip/knee replacement",
}

# ---- chart styling (reference palette from the dataviz method, light mode) ----
C_SERIES1 = "#2a78d6"   # blue - single-series default
C_SERIES2 = "#eb6834"   # orange - emphasis / second series
C_MUTED = "#b9b8b2"     # de-emphasised marks
C_TEXT = "#0b0b0b"
C_TEXT2 = "#52514e"
C_GRID = "#e6e5e0"
C_SURFACE = "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": C_SURFACE, "axes.facecolor": C_SURFACE, "savefig.facecolor": C_SURFACE,
    "axes.edgecolor": C_GRID, "axes.labelcolor": C_TEXT2, "axes.titlecolor": C_TEXT,
    "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.axisbelow": True, "grid.color": C_GRID, "grid.linewidth": 0.6,
    "xtick.color": C_TEXT2, "ytick.color": C_TEXT2, "font.size": 10,
    "font.family": "DejaVu Sans",
})


# --------------------------------------------------------------------------- #
# Data access
# --------------------------------------------------------------------------- #
def load_tables(db_path: Path = DB_PATH) -> dict[str, pd.DataFrame]:
    """Read the analytical tables out of DuckDB."""
    con = duckdb.connect(str(db_path), read_only=True)
    names = ["mart_hospital", "mart_hospital_condition", "mart_state_summary",
             "int_drg_national", "mart_cost_drivers", "stg_mspb_by_claim"]
    out = {n: _numpy_dtypes(con.execute(f"select * from {n}").df()) for n in names}
    con.close()
    return out


def _numpy_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """DuckDB returns pandas nullable dtypes (Int32, boolean, string); patsy and
    scipy want plain numpy ones. Integers -> float (NaN for NULL), flags -> bool."""
    for c in df.columns:
        dt = df[c].dtype
        if pd.api.types.is_bool_dtype(dt):
            df[c] = df[c].fillna(False).astype(bool)
        elif pd.api.types.is_numeric_dtype(dt) and isinstance(dt, pd.api.extensions.ExtensionDtype):
            df[c] = df[c].astype("float64")
        elif pd.api.types.is_string_dtype(dt):
            df[c] = df[c].astype(object).where(df[c].notna(), None)
    return df


def money(x: float, digits: int = 1) -> str:
    """$1.2B / $3.4M / $5.6K formatting for prose."""
    a = abs(x)
    if a >= 1e9:
        return f"${x / 1e9:,.{digits}f}B"
    if a >= 1e6:
        return f"${x / 1e6:,.{digits}f}M"
    if a >= 1e3:
        return f"${x / 1e3:,.{digits}f}K"
    return f"${x:,.0f}"


# --------------------------------------------------------------------------- #
# 0) Context: where the money goes
# --------------------------------------------------------------------------- #
def cost_context(t: dict) -> dict:
    h = t["mart_hospital"].query("in_inpatient").copy()
    drg = t["int_drg_national"].sort_values("medicare_payment", ascending=False)
    total = drg["medicare_payment"].sum()

    # log(ppd) = log(national ppd) + log(case-mix index) + log(price index)
    lp, lc, lpr = (np.log(h["medicare_payment_per_discharge"]), np.log(h["case_mix_index"]),
                   np.log(h["price_index"]))
    var_total = lp.var()
    decomposition = {
        "share_case_mix": lc.var() / var_total,
        "share_price": lpr.var() / var_total,
        "share_covariance": 2 * np.cov(lc, lpr)[0, 1] / var_total,
        # additive "contribution to variance" (sums to 1): cov(component, total) / var(total)
        "contribution_case_mix": np.cov(lc, lp)[0, 1] / var_total,
        "contribution_price": np.cov(lpr, lp)[0, 1] / var_total,
    }

    # MSPB episode cost components (CY2024): national average shares, and which
    # component's cross-hospital variation drives variation in total episode spend
    claim = t["stg_mspb_by_claim"]
    comp = claim[claim["episode_period"] != "Complete episode"]
    wide = comp.pivot_table(index="ccn", columns="component", values="spend_hospital", aggfunc="first")
    total_ep = wide.sum(axis=1)
    nat = comp.groupby("component")["spend_national"].first()
    mspb_components = pd.DataFrame({
        "national_avg_spend_per_episode": nat,
        "share_of_national_episode_spend": nat / nat.sum(),
        "share_of_cross_hospital_variation": wide.apply(lambda c: np.cov(c, total_ep)[0, 1]) / total_ep.var(),
    }).sort_values("national_avg_spend_per_episode", ascending=False)

    cum = drg["medicare_payment"].cumsum() / total
    return {
        "total_medicare_inpatient_payment": float(total),
        "total_discharges": int(drg["discharges"].sum()),
        "national_payment_per_discharge": float(total / drg["discharges"].sum()),
        "hospitals_in_inpatient_file": int(len(h)),
        "drg_count": int(len(drg)),
        "top_drg": {
            "code": drg.iloc[0]["drg_code"], "desc": drg.iloc[0]["drg_desc"],
            "medicare_payment": float(drg.iloc[0]["medicare_payment"]),
            "share": float(drg.iloc[0]["medicare_payment"] / total),
            "discharges": int(drg.iloc[0]["discharges"]),
        },
        "top10_drg_share": float(drg.head(10)["medicare_payment"].sum() / total),
        "drgs_for_50pct_of_spend": int((cum < 0.5).sum() + 1),
        "payment_per_discharge_p10_p90": [float(h["medicare_payment_per_discharge"].quantile(q)) for q in (0.1, 0.9)],
        "variance_decomposition": {k: float(v) for k, v in decomposition.items()},
        "mspb_components": mspb_components,
        "top_drgs": drg.head(15)[["drg_code", "drg_desc", "discharges", "medicare_payment",
                                  "avg_medicare_payment", "share_of_medicare_payment", "cumulative_share"]],
    }


# --------------------------------------------------------------------------- #
# a) Regression: drivers of payment per discharge and MSPB
# --------------------------------------------------------------------------- #
def regression_frame(t: dict) -> pd.DataFrame:
    h = t["mart_hospital"]
    d = h[h["in_inpatient"] & (h["hospital_type"] == "Acute Care Hospitals")].copy()
    d["log_ppd"] = np.log(d["medicare_payment_per_discharge"])
    d["log_cmi"] = np.log(d["case_mix_index"])
    # readmission ratio rescaled: +1 unit = ERR 0.1 higher (e.g. 1.00 -> 1.10)
    d["err_x10"] = (d["err_mean"] - 1) * 10
    d["size_band"] = d["size_band"].str[2:]      # drop sort prefix for labels
    return d


RHS_BASE = ("C(size_band, Treatment('Small (<500)')) + C(ownership_group, Treatment('Non-profit'))"
            " + C(region, Treatment('South')) + star_rating + err_x10")

BLOCKS = {
    "Size band": "C(size_band, Treatment('Small (<500)'))",
    "Ownership": "C(ownership_group, Treatment('Non-profit'))",
    "Region": "C(region, Treatment('South'))",
    "Star rating": "star_rating",
    "Readmission ratio": "err_x10",
    "Case mix (DRG mix)": "log_cmi",
    "Urban/rural": "C(urban_rural)",
}


def _fit(formula: str, data: pd.DataFrame):
    return smf.ols(formula, data=data).fit(cov_type="HC3")


def _tidy(res, log_outcome: bool) -> pd.DataFrame:
    ci = res.conf_int()
    out = pd.DataFrame({"coef": res.params, "std_err": res.bse, "p_value": res.pvalues,
                        "ci_low": ci[0], "ci_high": ci[1]})
    if log_outcome:  # % change in the outcome
        for c in ("coef", "ci_low", "ci_high"):
            out[c.replace("coef", "pct_effect").replace("ci_", "pct_ci_")] = (np.exp(out[c]) - 1) * 100
    out.index = [clean_term(i) for i in out.index]
    return out


def clean_term(term: str) -> str:
    if "[T." in term:
        var = term.split("(")[1].split(",")[0].split(")")[0]
        lvl = term.split("[T.")[1].rstrip("]")
        name = {"size_band": "Size", "ownership_group": "Ownership", "region": "Region",
                "urban_rural": "Location"}.get(var, var)
        return f"{name}: {lvl}"
    return {"star_rating": "Star rating (+1 star)", "err_x10": "Readmission ratio (+0.1)",
            "log_cmi": "Case-mix index (log)", "Intercept": "Intercept"}.get(term, term)


def diagnostics(res, data: pd.DataFrame) -> dict:
    X = res.model.exog
    names = res.model.exog_names
    vifs = {clean_term(n): float(variance_inflation_factor(X, i)) for i, n in enumerate(names) if n != "Intercept"}
    bp_lm, bp_p, _, _ = het_breuschpagan(res.resid, X)
    jb, jb_p, skew, kurt = jarque_bera(res.resid)
    plain = smf.ols(res.model.formula, data=data).fit()
    cooks = plain.get_influence().cooks_distance[0]
    n = int(res.nobs)
    no_infl = plain.model.data.frame.loc[cooks <= 4 / n]
    refit = smf.ols(res.model.formula, data=no_infl).fit(cov_type="HC3")
    return {
        "n": n,
        "max_vif": max(vifs.values()), "vif": vifs,
        "breusch_pagan_p": float(bp_p),
        "jarque_bera_p": float(jb_p), "resid_skew": float(skew), "resid_kurtosis": float(kurt),
        "influential_points_cooks_gt_4_over_n": int((cooks > 4 / n).sum()),
        "r2_without_influential_points": float(refit.rsquared),
        "condition_number": float(plain.condition_number),
    }


def run_regressions(t: dict) -> dict:
    d = regression_frame(t)
    need = ["log_ppd", "mspb_ratio", "size_band", "ownership_group", "region",
            "star_rating", "err_x10", "log_cmi", "urban_rural"]
    ppd_data = d.dropna(subset=[c for c in need if c != "mspb_ratio"])
    mspb_data = d.dropna(subset=need)

    models = {
        # as specified: size, ownership, region, star rating, readmission ratio
        "ppd_base": (f"log_ppd ~ {RHS_BASE}", ppd_data, True),
        # adds the case-mix index (what kind of patients/DRGs) and urban/rural
        "ppd_casemix": (f"log_ppd ~ {RHS_BASE} + log_cmi + C(urban_rural)", ppd_data, True),
        "mspb_base": (f"mspb_ratio ~ {RHS_BASE}", mspb_data, False),
        "mspb_casemix": (f"mspb_ratio ~ {RHS_BASE} + log_cmi + C(urban_rural)", mspb_data, False),
    }
    out = {}
    for key, (f, data, is_log) in models.items():
        res = _fit(f, data)
        # unique R^2 of each block = R^2(full) - R^2(full without that block)
        unique = {}
        for block, term in BLOCKS.items():
            if term not in f:
                continue
            reduced = f.replace(f" + {term}", "").replace(f"{term} + ", "")
            unique[block] = res.rsquared - smf.ols(reduced, data=data).fit().rsquared
        out[key] = {
            "formula": f, "n": int(res.nobs), "r2": float(res.rsquared), "adj_r2": float(res.rsquared_adj),
            "f_pvalue": float(res.f_pvalue), "table": _tidy(res, is_log),
            "unique_r2": pd.Series(unique).sort_values(ascending=False),
            "diagnostics": diagnostics(res, data),
        }
    # robustness: state fixed effects instead of 4 census regions
    rhs_state = RHS_BASE.replace("C(region, Treatment('South'))", "C(state)")
    fe = smf.ols(f"log_ppd ~ {rhs_state} + log_cmi + C(urban_rural)", data=ppd_data).fit()
    out["ppd_casemix_state_fe_r2"] = float(fe.rsquared)
    # robustness: star rating as categories instead of linear
    cat = _fit(f"log_ppd ~ {RHS_BASE.replace('star_rating', 'C(star_rating)')} + log_cmi + C(urban_rural)", ppd_data)
    out["ppd_casemix_star_categorical_r2"] = float(cat.rsquared)
    return out


# --------------------------------------------------------------------------- #
# b) Cost of excess readmissions
# --------------------------------------------------------------------------- #
def excess_readmission_costs(t: dict) -> dict:
    hc = t["mart_hospital_condition"].copy()
    h = t["mart_hospital"].set_index("ccn")
    total_inpatient = t["int_drg_national"]["medicare_payment"].sum()

    scored = hc[hc["excess_readmissions_annual"].notna()]
    by_condition = (scored.groupby("condition_code")
                    .agg(hospitals_with_counts=("ccn", "nunique"),
                         eligible_discharges_per_year=("discharges_annual", "sum"),
                         hospitals_err_above_1=("excess_readmission_ratio", lambda s: int((s > 1).sum())),
                         net_excess_readmissions_per_year=("excess_readmissions_annual", "sum"),
                         positive_excess_readmissions_per_year=("positive_excess_annual", "sum"),
                         cost_low=("excess_cost_annual_low", "sum"),
                         cost_base=("excess_cost_annual_base", "sum"),
                         cost_high=("excess_cost_annual_high", "sum"))
                    .sort_values("cost_base", ascending=False))
    by_condition["avg_cost_per_excess_readmission"] = by_condition["cost_base"] / by_condition["positive_excess_readmissions_per_year"]
    by_condition["share_of_excess_cost"] = by_condition["cost_base"] / by_condition["cost_base"].sum()
    by_condition.index = [CONDITION_LABELS[c] for c in by_condition.index]

    # Upper bound for rows where CMS suppressed the counts (<11 readmissions in 3 yrs):
    # excess = predicted readmissions x (1 - 1/ERR) and predicted readmissions <= ~10.
    supp = hc[hc["counts_suppressed"] & (hc["excess_readmission_ratio"] > 1)].copy()
    supp["excess_ub_annual"] = 10 * (1 - 1 / supp["excess_readmission_ratio"]) / supp["period_years"]
    suppressed_ub_cost = float((supp["excess_ub_annual"] * supp["cost_per_readmission_base"]).sum())

    # Segment rankings (hospital-level totals joined to characteristics)
    seg_src = scored.merge(h[["size_band", "ownership_group", "region", "star_rating", "urban_rural"]],
                           left_on="ccn", right_index=True, how="left")
    seg_src["star_rating"] = seg_src["star_rating"].map(lambda v: f"{int(v)} star" if pd.notna(v) else "Not rated")
    segments = {}
    for dim in ["size_band", "ownership_group", "region", "star_rating", "urban_rural"]:
        g = (seg_src.groupby(seg_src[dim].fillna("Unknown"))
             .agg(hospitals=("ccn", "nunique"),
                  eligible_discharges_per_year=("discharges_annual", "sum"),
                  positive_excess_readmissions=("positive_excess_annual", "sum"),
                  excess_cost_base=("excess_cost_annual_base", "sum"))
             .sort_values("excess_cost_base", ascending=False))
        g["share_of_excess_cost"] = g["excess_cost_base"] / g["excess_cost_base"].sum()
        g["excess_cost_per_1000_discharges"] = g["excess_cost_base"] / g["eligible_discharges_per_year"] * 1000
        segments[dim] = g

    total_base = float(scored["excess_cost_annual_base"].sum())
    return {
        "by_condition": by_condition,
        "segments": segments,
        "total_cost_low": float(scored["excess_cost_annual_low"].sum()),
        "total_cost_base": total_base,
        "total_cost_high": float(scored["excess_cost_annual_high"].sum()),
        "net_cost_base": float(scored["net_excess_cost_annual_base"].sum()),
        "positive_excess_readmissions_per_year": float(scored["positive_excess_annual"].sum()),
        "net_excess_readmissions_per_year": float(scored["excess_readmissions_annual"].sum()),
        "eligible_discharges_per_year": float(scored["discharges_annual"].sum()),
        "rows_with_counts": int(len(scored)), "rows_total": int(len(hc)),
        "rows_suppressed_err_gt_1": int(len(supp)),
        "suppressed_upper_bound_cost": suppressed_ub_cost,
        "share_of_inpatient_payments": total_base / total_inpatient,
        "share_of_inpatient_payments_incl_suppressed_ub": (total_base + suppressed_ub_cost) / total_inpatient,
        # CMS's own HRRP penalty formula, for contrast: sum of base DRG payments for the
        # condition x (ERR - 1). We approximate with Medicare payment for condition DRGs.
        "cms_style_penalty_proxy": float(
            (scored["excess_readmission_ratio"].clip(lower=1) - 1)
            .mul(scored["discharges_annual"] * scored["cost_per_readmission_base"]).sum()),
    }


# --------------------------------------------------------------------------- #
# c) High- vs low-volume hospitals on readmissions
# --------------------------------------------------------------------------- #
def rank_biserial(u: float, n1: int, n2: int) -> float:
    """Rank-biserial correlation from Mann-Whitney U (U of group 1)."""
    return 2 * u / (n1 * n2) - 1


def volume_vs_readmissions(t: dict) -> dict:
    h = t["mart_hospital"]
    d = h[h["in_inpatient"] & h["err_mean"].notna()].copy()
    q1, q3 = d["discharges"].quantile([0.25, 0.75])
    high = d.loc[d["discharges"] >= q3, "err_mean"]
    low = d.loc[d["discharges"] <= q1, "err_mean"]

    mw = stats.mannwhitneyu(high, low, alternative="two-sided")
    r_rb = rank_biserial(mw.statistic, len(high), len(low))
    welch = stats.ttest_ind(high, low, equal_var=False)
    pooled_sd = np.sqrt(((len(high) - 1) * high.var() + (len(low) - 1) * low.var()) / (len(high) + len(low) - 2))
    cohens_d = (high.mean() - low.mean()) / pooled_sd
    levene = stats.levene(high, low, center="median")
    shapiro_high = stats.shapiro(high.sample(min(len(high), 500), random_state=RNG_SEED)).pvalue
    shapiro_low = stats.shapiro(low.sample(min(len(low), 500), random_state=RNG_SEED)).pvalue
    hl_shift = float(np.median(np.subtract.outer(high.values, low.values)))  # Hodges-Lehmann
    rng = np.random.default_rng(RNG_SEED)
    boot = [np.median(rng.choice(high.values, len(high))) - np.median(rng.choice(low.values, len(low)))
            for _ in range(2000)]
    spearman = stats.spearmanr(d["discharges"], d["err_mean"])

    # per condition, same quartile split on overall hospital volume, Holm-corrected
    hc = t["mart_hospital_condition"].merge(d[["ccn", "discharges"]], on="ccn")
    rows = []
    for c, g in hc.dropna(subset=["excess_readmission_ratio"]).groupby("condition_code"):
        hi = g.loc[g["discharges"] >= q3, "excess_readmission_ratio"]
        lo = g.loc[g["discharges"] <= q1, "excess_readmission_ratio"]
        if len(hi) < 20 or len(lo) < 20:
            continue
        r = stats.mannwhitneyu(hi, lo, alternative="two-sided")
        rows.append({"condition": CONDITION_LABELS[c], "n_high": len(hi), "n_low": len(lo),
                     "median_err_high": hi.median(), "median_err_low": lo.median(),
                     "p_value": r.pvalue, "rank_biserial": rank_biserial(r.statistic, len(hi), len(lo))})
    per_cond = pd.DataFrame(rows)
    per_cond["p_holm"] = multipletests(per_cond["p_value"], method="holm")[1]

    by_band = (d.assign(size_band=d["size_band"].str[2:]).groupby("size_band")["err_mean"]
               .agg(["count", "median", "mean", "std"]))
    return {
        "volume_cutoffs": {"low_max_discharges": float(q1), "high_min_discharges": float(q3)},
        "n_high": int(len(high)), "n_low": int(len(low)),
        "median_err_high": float(high.median()), "median_err_low": float(low.median()),
        "mean_err_high": float(high.mean()), "mean_err_low": float(low.mean()),
        "sd_err_high": float(high.std()), "sd_err_low": float(low.std()),
        "mann_whitney_u": float(mw.statistic), "mann_whitney_p": float(mw.pvalue),
        "rank_biserial": float(r_rb),
        "hodges_lehmann_shift": hl_shift,
        "median_diff_boot_ci95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
        "welch_t": float(welch.statistic), "welch_p": float(welch.pvalue), "cohens_d": float(cohens_d),
        "levene_p": float(levene.pvalue),
        "shapiro_p_high": float(shapiro_high), "shapiro_p_low": float(shapiro_low),
        "spearman_rho_volume_err": float(spearman.statistic), "spearman_p": float(spearman.pvalue),
        "per_condition": per_cond, "by_size_band": by_band,
        "_samples": {"high": high, "low": low, "all": d},
    }


# --------------------------------------------------------------------------- #
# d) Savings scenario
# --------------------------------------------------------------------------- #
def savings_scenario(t: dict, reduction: float = REDUCTION, share: float = TOP_N_DISCHARGE_SHARE) -> dict:
    h = t["mart_hospital"]
    hc = t["mart_hospital_condition"]
    ranked = h[h["in_inpatient"]].sort_values("national_volume_rank")
    top_n = int((ranked["cumulative_share_of_discharges"] < share).sum() + 1)

    def scenario(n: int | None, red: float) -> dict:
        ccns = ranked["ccn"] if n is None else ranked.head(n)["ccn"]
        sel = hc[hc["ccn"].isin(ccns)]
        return {
            "hospitals": int(len(ccns)),
            "hospitals_with_positive_excess": int(sel.loc[sel["positive_excess_annual"] > 0, "ccn"].nunique()),
            "positive_excess_readmissions": float(sel["positive_excess_annual"].sum()),
            "avoided_readmissions": float(sel["positive_excess_annual"].sum() * red),
            "saving_low": float(sel["excess_cost_annual_low"].sum() * red),
            "saving_base": float(sel["excess_cost_annual_base"].sum() * red),
            "saving_high": float(sel["excess_cost_annual_high"].sum() * red),
        }

    main = scenario(top_n, reduction)
    top = ranked.head(top_n)
    main.update({
        "top_n": top_n, "reduction": reduction,
        "top_n_share_of_hospitals": top_n / len(ranked),
        "top_n_share_of_discharges": float(top["discharges"].sum() / ranked["discharges"].sum()),
        "top_n_min_discharges": int(top["discharges"].min()),
        "top_n_share_of_excess_cost": float(
            hc[hc["ccn"].isin(top["ccn"])]["excess_cost_annual_base"].sum() / hc["excess_cost_annual_base"].sum()),
    })
    # sensitivity grid: N x reduction (base cost assumption)
    grid = []
    for n in [50, 100, 250, top_n, None]:
        for red in [0.05, 0.10, 0.20, 1.00]:
            s = scenario(n, red)
            grid.append({"N": "All" if n is None else n, "reduction": f"{red:.0%}", "saving_base": s["saving_base"]})
    sens = pd.DataFrame(grid).pivot(index="N", columns="reduction", values="saving_base")
    sens = sens[["5%", "10%", "20%", "100%"]]
    sens.index = sens.index.astype(str)
    return {"main": main, "sensitivity": sens}


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def _save(fig, name: str) -> Path:
    FIGURES.mkdir(parents=True, exist_ok=True)
    p = FIGURES / name
    fig.savefig(p, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return p


def chart_cost_by_condition(b: dict) -> Path:
    df = b["by_condition"].sort_values("cost_base")
    fig, ax = plt.subplots(figsize=(8, 4.2))
    y = np.arange(len(df))
    ax.barh(y, df["cost_base"] / 1e6, color=C_SERIES1, height=0.55)
    ax.errorbar(df["cost_base"] / 1e6, y,
                xerr=[(df["cost_base"] - df["cost_low"]) / 1e6, (df["cost_high"] - df["cost_base"]) / 1e6],
                fmt="none", ecolor=C_TEXT2, elinewidth=1, capsize=3)
    for yi, v, hi in zip(y, df["cost_base"], df["cost_high"]):
        ax.text(hi / 1e6 + 0.3, yi, money(v), va="center", color=C_TEXT, fontsize=9)
    ax.set_yticks(y, df.index)
    ax.set_xlabel("Annual Medicare cost of excess readmissions ($ millions)")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, df["cost_high"].max() / 1e6 * 1.2)
    ax.set_title("Excess readmission cost by condition (per year)")
    fig.text(0.0, -0.09, f"Bars = base estimate; whiskers = low-high range. Total base estimate "
             f"{money(b['total_cost_base'])} = {b['share_of_inpatient_payments']:.2%} of Medicare inpatient payments.\n"
             "Source: CMS HRRP FY2026 (Jul 2021-Jun 2024), Medicare Inpatient by Provider & Service CY2024.",
             fontsize=8, color=C_TEXT2)
    return _save(fig, "cost_by_condition.png")


def chart_savings(d: dict) -> Path:
    m = d["main"]
    vals = [m["saving_low"], m["saving_base"], m["saving_high"]]
    labels = ["Low", "Base", "High"]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    colors = [C_MUTED, C_SERIES1, C_MUTED]
    ax.bar(labels, np.array(vals) / 1e6, color=colors, width=0.5)
    for i, v in enumerate(vals):
        ax.text(i, v / 1e6, money(v, 2), ha="center", va="bottom", color=C_TEXT, fontsize=10)
    ax.set_ylabel("Estimated annual saving ($ millions)")
    ax.grid(axis="x", visible=False)
    ax.set_title(f"Savings if the top {m['top_n']} highest-volume hospitals cut excess readmissions {m['reduction']:.0%}")
    fig.text(0.0, -0.11,
             "Low = national avg payment for non-MCC condition DRGs; Base = hospital's avg Medicare payment for the\n"
             "condition's DRGs; High = hospital's avg total payment (Medicare + cost-sharing). "
             f"Top {m['top_n']} = {m['top_n_share_of_discharges']:.0%} of Medicare discharges.",
             fontsize=8, color=C_TEXT2)
    return _save(fig, "savings_scenario.png")


def chart_coefficients(reg: dict) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2), sharey=True)
    specs = [("ppd_base", "Payment per discharge (% difference)", True),
             ("mspb_base", "MSPB ratio (difference, 1.00 = national median)", False)]
    order = None
    for ax, (key, title, is_log) in zip(axes, specs):
        tb = reg[key]["table"].drop(index="Intercept")
        if order is None:
            order = list(tb.index[::-1])
        tb = tb.loc[order]
        col, lo, hi = ("pct_effect", "pct_ci_low", "pct_ci_high") if is_log else ("coef", "ci_low", "ci_high")
        y = np.arange(len(tb))
        sig = tb["p_value"] < 0.05
        ax.hlines(y, tb[lo], tb[hi], color=np.where(sig, C_SERIES1, C_MUTED), linewidth=2)
        ax.scatter(tb[col], y, s=36, color=np.where(sig, C_SERIES1, C_MUTED), zorder=3,
                   edgecolor=C_SURFACE, linewidth=1.5)
        ax.axvline(0, color=C_TEXT2, linewidth=0.8)
        ax.set_yticks(y, tb.index)
        ax.set_title(f"{title}\nR² = {reg[key]['r2']:.2f}, n = {reg[key]['n']:,}", fontsize=11)
        ax.grid(axis="y", visible=False)
    fig.suptitle("What is associated with higher Medicare cost? (OLS, 95% CI, robust SE)",
                 x=0.01, ha="left", fontweight="bold", color=C_TEXT)
    fig.text(0.01, -0.03, "Blue = statistically significant (p < 0.05); grey = not significant. Reference groups: "
             "Small (<500 discharges), Non-profit, South.\nObservational associations, not causal effects.",
             fontsize=8, color=C_TEXT2)
    fig.tight_layout()
    return _save(fig, "regression_coefficients.png")


def chart_state_ranking(t: dict) -> Path:
    s = t["mart_state_summary"].dropna(subset=["cmi_adjusted_payment_per_discharge"])
    s = s[s["hospitals_inpatient"] >= 5].sort_values("cmi_adjusted_payment_per_discharge")
    nat = s["medicare_payment"].sum() / (s["medicare_payment"] / s["cmi_adjusted_payment_per_discharge"]).sum()
    fig, ax = plt.subplots(figsize=(8, 11))
    y = np.arange(len(s))
    ax.hlines(y, s[["medicare_payment_per_discharge", "cmi_adjusted_payment_per_discharge"]].min(axis=1),
              s[["medicare_payment_per_discharge", "cmi_adjusted_payment_per_discharge"]].max(axis=1),
              color=C_GRID, linewidth=2)
    ax.scatter(s["medicare_payment_per_discharge"], y, s=28, color=C_MUTED, label="Actual payment per discharge",
               zorder=3)
    ax.scatter(s["cmi_adjusted_payment_per_discharge"], y, s=36, color=C_SERIES1,
               label="Case-mix adjusted (same patient mix as nation)", zorder=4)
    ax.axvline(nat, color=C_TEXT2, linewidth=0.8)
    ax.text(nat, len(s) + 0.3, f" national {money(nat)}", color=C_TEXT2, fontsize=8)
    ax.set_yticks(y, s["state"], fontsize=8)
    ax.set_xlabel("Medicare payment per discharge ($)")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"${v / 1e3:.0f}K"))
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    ax.set_title("States ranked by case-mix adjusted Medicare payment per discharge")
    fig.text(0.0, 0.0, "States with 5+ hospitals. Case-mix adjustment removes differences in DRG mix, leaving price\n"
             "(wage index, teaching and safety-net add-ons, outliers). Source: CMS Medicare Inpatient CY2024.",
             fontsize=8, color=C_TEXT2)
    return _save(fig, "state_ranking.png")


def chart_cost_drivers(t: dict, b: dict) -> Path:
    drg = t["int_drg_national"].sort_values("medicare_payment", ascending=False).head(8)
    labels = [f"DRG {c} {d[:38].title()}…" if len(d) > 38 else f"DRG {c} {d.title()}"
              for c, d in zip(drg["drg_code"], drg["drg_desc"])]
    vals = list(drg["medicare_payment"])
    labels.append("Excess readmissions, 6 HRRP conditions (est.)")
    vals.append(b["total_cost_base"])
    df = pd.DataFrame({"label": labels, "v": vals}).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    colors = [C_SERIES2 if "Excess" in l else C_SERIES1 for l in df["label"]]
    ax.barh(df["label"], df["v"] / 1e9, color=colors, height=0.6)
    for i, v in enumerate(df["v"]):
        ax.text(v / 1e9 + 0.08, i, money(v, 2), va="center", fontsize=9, color=C_TEXT)
    ax.set_xlabel("Annual Medicare inpatient payments ($ billions)")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, df["v"].max() / 1e9 * 1.15)
    ax.set_title("Where Medicare inpatient dollars go: top DRGs vs excess readmissions")
    fig.text(0.0, -0.09, f"Total Medicare inpatient payments in published DRG cells, CY2024: "
             f"{money(t['int_drg_national']['medicare_payment'].sum())}.", fontsize=8, color=C_TEXT2)
    return _save(fig, "cost_drivers_context.png")


def chart_mspb_components(ctx: dict) -> Path:
    m = ctx["mspb_components"].copy()
    m = m[m["share_of_national_episode_spend"] > 0.01].sort_values("share_of_national_episode_spend")
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    y = np.arange(len(m))
    ax.barh(y + 0.18, m["share_of_national_episode_spend"] * 100, height=0.34, color=C_SERIES1,
            label="Share of average episode spend")
    ax.barh(y - 0.18, m["share_of_cross_hospital_variation"] * 100, height=0.34, color=C_SERIES2,
            label="Share of hospital-to-hospital variation")
    ax.set_yticks(y, m.index, fontsize=9)
    ax.set_xlabel("%")
    ax.grid(axis="y", visible=False)
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    ax.set_title("MSPB episode: where spending goes vs what makes hospitals differ")
    fig.text(0.0, -0.09, "Episode = 3 days before admission to 30 days after discharge. Variation share = "
             "cov(component, total) / var(total) across hospitals.\nSource: CMS Medicare Hospital Spending by Claim, CY2024.",
             fontsize=8, color=C_TEXT2)
    return _save(fig, "mspb_components.png")


def chart_volume_err(c: dict) -> Path:
    d = c["_samples"]["all"].copy()
    d["band"] = d["size_band"].str[2:]
    bands = sorted(d["band"].unique(), key=lambda s: ["Small", "Medium", "Large", "Very"].index(s.split()[0]))
    fig, ax = plt.subplots(figsize=(8, 4.2))
    data = [d.loc[d["band"] == b_, "err_mean"] for b_ in bands]
    bp = ax.boxplot(data, orientation="horizontal", widths=0.5, patch_artist=True, showfliers=False,
                    medianprops={"color": C_TEXT, "linewidth": 1.5})
    for patch in bp["boxes"]:
        patch.set(facecolor="#cde2fb", edgecolor=C_SERIES1, linewidth=1)
    for el in ("whiskers", "caps"):
        for line in bp[el]:
            line.set(color=C_SERIES1, linewidth=1)
    ax.set_yticks(range(1, len(bands) + 1), [f"{b_}\n(n={len(x)})" for b_, x in zip(bands, data)], fontsize=9)
    ax.axvline(1, color=C_TEXT2, linewidth=0.8)
    ax.set_xlabel("Hospital average excess readmission ratio (1.00 = as expected)")
    ax.grid(axis="y", visible=False)
    ax.set_title("Readmission ratio by hospital size (Medicare discharges)")
    fig.text(0.0, -0.09, f"Top vs bottom volume quartile: Mann-Whitney p = {c['mann_whitney_p']:.2g}, "
             f"rank-biserial r = {c['rank_biserial']:.2f}. CMS shrinks low-volume ratios toward 1.00, limiting power.",
             fontsize=8, color=C_TEXT2)
    return _save(fig, "readmission_ratio_by_size.png")


def chart_state_map(t: dict) -> Path:
    s = t["mart_state_summary"].dropna(subset=["cmi_adjusted_payment_per_discharge"])
    fig = px.choropleth(
        s, locations="state", locationmode="USA-states", scope="usa",
        color="cmi_adjusted_payment_per_discharge", color_continuous_scale=["#cde2fb", "#2a78d6", "#0d366b"],
        hover_data={"state": True, "hospitals_inpatient": True, "medicare_payment_per_discharge": ":$,.0f",
                    "cmi_adjusted_payment_per_discharge": ":$,.0f", "median_mspb_ratio": ":.2f",
                    "excess_readmission_cost_annual_base": ":$,.0f"},
        labels={"cmi_adjusted_payment_per_discharge": "Case-mix adj. $/discharge"},
        title="Case-mix adjusted Medicare payment per discharge by state (CY2024)")
    p = FIGURES / "state_map.html"
    fig.write_html(p, include_plotlyjs="cdn")
    return p


# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #
def export_powerbi(t: dict) -> list[Path]:
    POWERBI.mkdir(parents=True, exist_ok=True)
    h = t["mart_hospital"].copy()
    h["size_band"] = h["size_band"].str[2:]
    hc = t["mart_hospital_condition"].copy()
    paths = []
    for name, df in [("hospital.csv", h), ("hospital_condition.csv", hc),
                     ("state_summary.csv", t["mart_state_summary"]),
                     ("drg_national.csv", t["int_drg_national"])]:
        p = POWERBI / name
        df.round(6).to_csv(p, index=False)
        paths.append(p)
    return paths


def _md_table(df: pd.DataFrame, floatfmt: str = "{:,.4g}") -> str:
    df = df.copy()
    cols = [str(c) for c in ([df.index.name or ""] + list(df.columns))]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for idx, row in df.iterrows():
        vals = [str(idx)] + [floatfmt.format(v) if isinstance(v, (float, np.floating)) else str(v) for v in row]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def _jsonable(o):
    if isinstance(o, (pd.DataFrame, pd.Series)):
        return None
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items() if not k.startswith("_") and _jsonable(v) is not None}
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    return o


def run_all(write: bool = True) -> dict:
    t = load_tables()
    ctx = cost_context(t)
    reg = run_regressions(t)
    b = excess_readmission_costs(t)
    c = volume_vs_readmissions(t)
    d = savings_scenario(t)
    results = {"context": ctx, "regression": reg, "excess_readmissions": b, "volume_test": c, "savings": d}
    if not write:
        return results

    figs = [chart_cost_by_condition(b), chart_savings(d), chart_coefficients(reg), chart_state_ranking(t),
            chart_cost_drivers(t, b), chart_mspb_components(ctx), chart_volume_err(c), chart_state_map(t)]
    exports = export_powerbi(t)

    summary = _jsonable(results)
    summary["regression"] = {k: ({kk: vv for kk, vv in v.items() if kk not in ("table", "unique_r2")}
                                 | {"unique_r2": v["unique_r2"].to_dict(),
                                    "coefficients": v["table"].round(6).to_dict(orient="index")}
                                 if isinstance(v, dict) else v) for k, v in reg.items()}
    summary["excess_readmissions"]["by_condition"] = b["by_condition"].round(4).to_dict(orient="index")
    summary["savings"]["sensitivity_base"] = d["sensitivity"].round(0).to_dict(orient="index")
    (REPORTS / "results.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")

    md = ["# Analysis results (auto-generated)\n",
          "Generated by `python/analysis.py`. Plain-language interpretation is in `reports/FINDINGS.md`; "
          "methodology in `docs/DECISIONS.md`.\n",
          "## 0. Context: where Medicare inpatient money goes\n",
          f"- Total Medicare inpatient payments (published DRG cells, CY2024): {money(ctx['total_medicare_inpatient_payment'], 2)} "
          f"over {ctx['total_discharges']:,} discharges at {ctx['hospitals_in_inpatient_file']:,} hospitals "
          f"({money(ctx['national_payment_per_discharge'])} per discharge).",
          f"- Largest single DRG: {ctx['top_drg']['code']} {ctx['top_drg']['desc']} = {money(ctx['top_drg']['medicare_payment'], 2)} "
          f"({ctx['top_drg']['share']:.1%}). Top 10 DRGs = {ctx['top10_drg_share']:.1%}; "
          f"{ctx['drgs_for_50pct_of_spend']} of {ctx['drg_count']} DRGs make up 50% of spend.",
          f"- Variance of log payment per discharge across hospitals: case mix contributes "
          f"{ctx['variance_decomposition']['contribution_case_mix']:.0%}, price contributes "
          f"{ctx['variance_decomposition']['contribution_price']:.0%}.\n",
          "### Top DRGs by Medicare spend\n", _md_table(ctx["top_drgs"].set_index("drg_code")), "",
          "### MSPB episode cost components\n", _md_table(ctx["mspb_components"]), ""]
    md.append("## a. Regression\n")
    for key in ("ppd_base", "ppd_casemix", "mspb_base", "mspb_casemix"):
        r = reg[key]
        md += [f"### `{key}`  (n = {r['n']:,}, R² = {r['r2']:.3f}, adj. R² = {r['adj_r2']:.3f})\n",
               f"`{r['formula']}`\n", _md_table(r["table"]), "",
               "Unique R² by block (drop in R² when the block is removed):\n",
               _md_table(r["unique_r2"].to_frame("unique_r2")), "",
               "Diagnostics: " + ", ".join(f"{k} = {v:.4g}" for k, v in r["diagnostics"].items()
                                          if not isinstance(v, dict)) + "\n"]
    md += [f"Robustness: state fixed effects instead of regions R² = {reg['ppd_casemix_state_fe_r2']:.3f}; "
           f"star rating as categories R² = {reg['ppd_casemix_star_categorical_r2']:.3f}.\n"]
    md += ["## b. Excess readmission cost\n",
           f"- Base {money(b['total_cost_base'])} per year (low {money(b['total_cost_low'])}, high {money(b['total_cost_high'])}); "
           f"{b['positive_excess_readmissions_per_year']:,.0f} excess readmissions/yr at hospitals above expected; "
           f"net across all hospitals {b['net_excess_readmissions_per_year']:,.0f}/yr.",
           f"- = {b['share_of_inpatient_payments']:.3%} of Medicare inpatient payments "
           f"({b['share_of_inpatient_payments_incl_suppressed_ub']:.3%} incl. upper bound for suppressed cells, "
           f"{money(b['suppressed_upper_bound_cost'])}).",
           f"- Coverage: {b['rows_with_counts']:,} of {b['rows_total']:,} hospital-condition rows have published counts.",
           f"- For contrast, a CMS-penalty-style figure (ERR-1) x index payments = {money(b['cms_style_penalty_proxy'])}.\n",
           _md_table(b["by_condition"]), ""]
    for dim, g in b["segments"].items():
        md += [f"### By {dim}\n", _md_table(g), ""]
    md += ["## c. High vs low volume\n",
           "\n".join(f"- {k}: {v:.4g}" if isinstance(v, float) else f"- {k}: {v}"
                     for k, v in c.items() if not k.startswith("_") and not isinstance(v, (pd.DataFrame, dict))),
           f"- volume cut-offs: {c['volume_cutoffs']}\n",
           _md_table(c["per_condition"].set_index("condition")), "", _md_table(c["by_size_band"]), ""]
    m = d["main"]
    md += ["## d. Savings scenario\n",
           "\n".join(f"- {k}: {v:,.4g}" if isinstance(v, float) else f"- {k}: {v}" for k, v in m.items()), "",
           "Sensitivity (base cost; rows = N hospitals, columns = reduction in excess readmissions):\n",
           _md_table(d["sensitivity"], "{:,.0f}"), ""]
    md += ["## Outputs\n"] + [f"- `{p.relative_to(ROOT)}`" for p in figs + exports]
    (REPORTS / "analysis_results.md").write_text("\n".join(md) + "\n")
    print(f"Wrote {len(figs)} figures, {len(exports)} CSVs, reports/results.json, reports/analysis_results.md")
    return results


if __name__ == "__main__":
    run_all()
