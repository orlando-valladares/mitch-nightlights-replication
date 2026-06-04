# Difference-in-Differences for the Mitch Dashboard

## Source And Scope

This note is governed by the attached Angrist/Pischke Chapter 5 PDF, `resources/AngristPr_Chapter5_Econometrics.pdf`, especially the section on "Pre and Post, Treatment and Control," the four-cell Card/Krueger example, regression DD, the causal-effect graph with a treatment-state counterfactual after treatment, event-study-style leads and lags, and the discussion of state-specific trends as a robustness check. It is written for the Hurricane Mitch nighttime-lights dashboard. In this project, Pass 1 treats treatment as binary: municipalities are either treated or control.

## 1. What DiD Is In Plain Language

Difference-in-differences asks whether the treated group changed differently after an event than a comparison group changed over the same period. The control group's change is used as the estimate of what would have happened to the treated group in the absence of treatment.

For the Mitch dashboard, the basic question is:

Did exposed municipalities experience a different post-Mitch path in nighttime lights than otherwise comparable, less-exposed or unexposed municipalities?

The DiD comparison is:

```text
(post - pre change for treated municipalities)
-
(post - pre change for control municipalities)
```

This is not simply a treated-control difference after Mitch. It is a difference in changes.

## 2. Canonical 2x2 Setup

The canonical Angrist/Pischke setup has two groups and two periods:

| Group | Before treatment | After treatment | Change |
| --- | --- | --- | --- |
| Treated | Y_T_pre | Y_T_post | Y_T_post - Y_T_pre |
| Control | Y_C_pre | Y_C_post | Y_C_post - Y_C_pre |

The four cells are:

1. Treated before.
2. Treated after.
3. Control before.
4. Control after.

The DiD estimand is:

```text
DD = (Y_T_post - Y_T_pre) - (Y_C_post - Y_C_pre)
```

The key identifying idea is parallel trends: absent treatment, the treated group would have changed like the control group. The groups may differ in levels before treatment; DiD allows that. What matters is whether the untreated trend for the treated group would have paralleled the control trend.

## 3. Canonical Regression-DD Setup

The canonical two-period regression is:

```text
Y_mt = alpha + gamma Treated_m + lambda Post_t
       + delta (Treated_m * Post_t) + e_mt
```

Where:

- `Y_mt` is the outcome for municipality `m` in year or period `t`.
- `Treated_m` equals 1 for treated municipalities and 0 for control municipalities.
- `Post_t` equals 1 after treatment and 0 before treatment.
- `Treated_m * Post_t` marks treated municipalities in the post period.
- `delta` is the DiD estimate.

The main effects matter. `Treated_m` absorbs a baseline treated-control level difference. `Post_t` absorbs a common post-period change affecting both groups. The interaction is the extra post-period change for the treated group relative to the control group.

## 4. Raw-Means Graph

The raw-means graph is descriptive. It should show the group means that make the DiD comparison visible.

The treated actual line is the observed mean outcome for treated municipalities by year.

The control actual line is the observed mean outcome for control municipalities by year.

The treated counterfactual line is the implied path for treated municipalities after treatment if they had followed the control group's change from the chosen clean pre-treatment base year.

For a post-treatment year `t`, using base year `b`, the raw-means counterfactual is:

```text
Treated counterfactual_t
  = treated actual mean_b
  + (control actual mean_t - control actual mean_b)
```

This line is built from group means, not from fixed-effects regression coefficients.

## 5. The Counterfactual Line Should Only Be Drawn After Treatment

The treated counterfactual line should only appear in the post-treatment period.

For this dashboard:

- Pre-period: show actual treated and actual control only.
- Transition year: mark 1998 separately because Mitch occurred late in the year.
- Post-period: show actual treated, actual control, and treated counterfactual.

The counterfactual is a post-treatment object. It answers: "Where would the treated group have been after treatment if it had followed the control group's post-treatment change?"

## 6. Why A Pre-Period Counterfactual Line Is Misleading

Drawing a dashed treated counterfactual line through pre-treatment years is misleading for this project.

First, before treatment, the treated group is observed in its untreated state. There is no missing treated-without-treatment outcome to impute in the pre-period.

Second, a pre-period dashed line can make ordinary pre-treatment treated-control differences look like estimated treatment effects. That is not the Angrist/Pischke four-cell logic. The pre-period is where we inspect whether treated and control trends are plausible comparisons.

Third, it blurs the visual role of the graph. The graph should use pre-period actual means to evaluate comparability, then show the post-treatment counterfactual only where the treatment-state counterfactual is actually missing.

## 7. Raw-Means DiD Graph Versus Regression DiD Estimate

The raw-means graph and the regression estimate are related, but they are not the same object in every specification.

In the simplest two-group, two-period saturated DD regression, the interaction coefficient equals the four-cell DiD contrast.

In a multi-year panel, a graph of yearly raw means is descriptive. The vertical gap between treated actual and treated counterfactual in a post year is the raw-means DiD gap for that year:

```text
raw gap_t = treated actual mean_t - treated counterfactual_t
```

That raw graphical gap should not be oversold as the fixed-effects regression estimate. Once the regression includes municipality fixed effects, year fixed effects, country-year fixed effects, trends, weights, filters, or a different sample, the coefficient answers the question for that regression specification. The graph should say what it shows, and the regression table should say what it estimates.

## 8. Dynamic / Event-Study Extension

With many years, DiD can be extended by interacting the treated indicator with individual years. A simple dynamic specification is:

```text
Y_mt = alpha_m + lambda_t
       + sum_{y != base} delta_y (Treated_m * 1[year_t = y])
       + e_mt
```

The omitted base year is the comparison year. In this project, the natural clean base is usually 1997.

The coefficients before the treatment period are pre-treatment coefficients. They are used to inspect whether treated and control groups were already diverging before Mitch. They are not treatment effects.

The coefficients after treatment are dynamic post-treatment effects relative to the omitted base year and the control group's path.

The transition year, 1998, should be handled explicitly. It is not a clean pre-treatment year because Mitch occurred in late October and early November 1998, and it is not a clean full post-treatment year in annual data.

## 9. Mitch-Specific Timing

For the Mitch dashboard, annual timing should be:

- 1992-1997: pre-treatment years.
- 1997: preferred clean pre-treatment base year.
- 1998: impact / transition year.
- 1999 onward: post-treatment years.

The reason is substantive. Hurricane Mitch occurred late in 1998. Annual nighttime-lights measures for 1998 may partly reflect pre-disaster conditions, immediate disruption, sensor/year aggregation, or transition dynamics. Using 1998 as the main base year risks anchoring the counterfactual on a contaminated year.

Therefore, the default raw DiD display should generally use 1997 as the clean base and treat 1999 onward as the post period.

## 10. How The Graph Should Look In This Project

The dashboard graph should follow this structure:

1. Use a binary treatment/control classification.
2. Plot treated actual means as a solid line.
3. Plot control actual means as a solid line.
4. In the pre-period, show only the two actual lines.
5. Mark 1998 as an impact / transition year.
6. For 1999 onward, add a dashed treated counterfactual line.
7. Compute the dashed post-treatment counterfactual from the 1997 treated-control base and the control group's post-1997 changes.
8. Explain that the vertical post-year gap between treated actual and treated counterfactual is the raw-means DiD gap for that year.
9. Do not label that raw gap as the fixed-effects regression effect unless the regression is exactly the same four-cell/saturated comparison.

The intended graph is therefore:

```text
Pre-period:       treated actual, control actual
1998:             impact / transition marker
Post-period:      treated actual, control actual, treated counterfactual
```

## 11. What The Current Dashboard Got Wrong

The current dashboard's old raw-means graph was not faithful enough to the canonical DiD visualization.

The main problem was the counterfactual line. The dashboard computed a treated counterfactual for every year:

```text
cf_y = treated_base + (control_y - control_base)
```

and plotted it through both pre- and post-treatment years. That made the counterfactual appear to exist before treatment. In the Angrist/Pischke logic, the pre-period should show actual means only; the counterfactual is needed after treatment because the treated-without-treatment outcome is unobserved then.

The old graph also used 1998 as the base year whenever 1998 existed. For Mitch, that is not the clean default. 1998 is an impact / transition year, while 1997 is generally the last clean pre-treatment base.

The old dashboard also blurred three distinct objects:

- the descriptive raw-means DiD graph;
- the regression-DD/event-study coefficients;
- later fixed-effects regression effects.

Those objects should be separated in labels, tabs, tooltips, and interpretation.

## 12. What The Dashboard Should And Should Not Claim

The dashboard should claim:

- The raw-means graph shows treated and control average nighttime-lights paths.
- The post-treatment dashed line is a treated counterfactual implied by the control group's change from the base year.
- The vertical post-treatment gap is a raw-means DiD gap.
- Event-study pre-coefficients are useful diagnostics for pre-trends.
- Regression estimates depend on the selected fixed effects and sample.

The dashboard should not claim:

- That a pre-period dashed counterfactual is a treatment effect.
- That a raw graphical post gap automatically equals a fixed-effects regression coefficient.
- That a Honduras-only municipality FE + year FE model estimates the average national effect of Mitch on Honduras.
- That adding more fixed effects is always better.
- That state-specific or municipality-specific trends are automatic defaults. Following Angrist/Pischke, trends are better treated as robustness checks that require enough credible pre-treatment trend information.

