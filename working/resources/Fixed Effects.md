# Fixed Effects for the Mitch Dashboard

## Source And Scope

This note is governed by `resources/Fixed_Effects.txt` and is written for the Hurricane Mitch nighttime-lights dashboard. The core principle is that each fixed-effects specification answers a different causal question because it keeps different identifying variation and removes different information.

Treatment is binary in the current dashboard planning: treated municipalities are compared with control municipalities.

## 1. What Fixed Effects Are In Plain Language

Fixed effects are sets of indicators that absorb average differences across units or periods. They remove variation along a chosen dimension before estimating the treatment effect.

For example, municipality fixed effects compare a municipality to itself over time, rather than comparing high-light cities to low-light rural places in levels. Year fixed effects remove shocks common to all included units in the same calendar year. Country-year fixed effects remove shocks common to all municipalities inside the same country and year.

Fixed effects are not magic. They decide which comparisons remain.

## 2. Fixed Effects Are Not Just "Good" By Default

Adding fixed effects changes the question being answered.

A specification with few fixed effects may compare broad treated and control differences, but it risks confounding treatment with permanent place differences and common shocks.

A specification with many fixed effects can make comparisons more local, but it may also remove the very effect the researcher wants. In disaster economics, this matters a lot. If most of Honduras was affected by Mitch, then a Honduras-only model with year fixed effects removes the common Honduran post-Mitch shock. That model can identify whether more-exposed Honduran municipalities did worse than less-exposed Honduran municipalities, but it cannot estimate the average national Honduras loss.

## 3. What Each Fixed Effect Removes

Year fixed effects remove shocks common to all units in the selected sample in a given year. In a Honduras-only panel, year fixed effects remove national Honduras year shocks. In a pooled regional panel, year fixed effects remove region-wide calendar-year shocks common to all included countries.

Municipality fixed effects remove time-invariant municipal differences: baseline brightness, geography, long-run urbanization, stable infrastructure, persistent administrative differences, and other fixed local characteristics.

Country fixed effects remove time-invariant country-level differences: average national light levels, institutions, geography, and persistent country characteristics. If municipality fixed effects are included and each municipality is nested in exactly one country, country fixed effects are redundant because the municipality indicators already absorb permanent country differences.

Country-year fixed effects remove every country-specific year shock: national macro conditions, policy changes, reconstruction paths, sensor-year country differences, and national disaster shocks in that country-year. In a pooled municipal panel, country-year fixed effects subsume separate country fixed effects and year fixed effects. In a Honduras-only panel, country-year fixed effects are equivalent to year fixed effects.

Municipality-specific trends remove municipality-specific linear time paths. They ask whether treated municipalities deviate from their own prior trends more than control municipalities do. They are robustness devices, not automatic defaults.

## 4. Which Identifying Variation Remains

| Specification | Identifying variation that remains | Question answered | Information lost |
| --- | --- | --- | --- |
| Honduras only, no FE | Cross-municipality and over-time differences in Honduras | Are treated Honduran municipalities darker after Mitch than controls? | No protection against permanent municipal differences or national time shocks |
| Honduras only + municipality FE + year FE | Within-Honduras, across-municipality changes after removing municipal baselines and common Honduras year shocks | Did more-exposed Honduran municipalities lose more lights than less-exposed Honduran municipalities? | Average national Honduras post-Mitch shock |
| Honduras only + municipality FE + year FE + municipality trends | Deviations from municipality-specific time paths | Did more-exposed municipalities fall below their own prior trends more than controls? | Some real disaster effects if they resemble trend changes; much low-frequency variation |
| Regional pooled + municipality FE + year FE | Within-municipality changes across the region, net of common regional year shocks | Across Central America, did treated municipalities do worse after Mitch? | Permanent municipal differences; region-wide year shocks; still leaves country-specific post-1998 divergence |
| Regional pooled + municipality FE + country FE + year FE | Same as municipality FE + year FE when municipalities are nested in countries | Substantively the same as regional municipality FE + year FE | Country FE add no new information once municipality FE are included |
| Regional pooled + municipality FE + country-year FE | Within each country-year, across municipalities with different treatment status | Within a country in a given year, did treated municipalities do worse than controls? | All average country-year effects, including average national disaster loss |
| Country-level panel: country FE + year FE | Across countries over time | Did more-exposed countries have worse post-Mitch paths than less-exposed countries? | Municipal exposure-gradient information; many local differences |
| Synthetic-control / national counterfactual for Honduras | Honduras compared with a constructed national counterfactual | How did Honduras as a whole perform relative to a no-Mitch counterfactual Honduras? | Municipal/local treatment-gradient interpretation |

## 5. Mitch-Specific Specifications

### Honduras Only, No FE

This is descriptive and fragile. It compares treated and control Honduran municipalities across years without removing fixed municipal differences or common time shocks. It can show broad patterns, but it should not be treated as a credible causal specification.

### Honduras Only + Municipality FE + Year FE

This is a local differential-damage design. It asks whether more-exposed Honduran municipalities changed more after Mitch than less-exposed Honduran municipalities, after removing each municipality's baseline level and each year shock common to Honduras.

If most of Honduras was affected by Mitch, the year fixed effects remove the common Honduran post-Mitch shock. Therefore this specification does not estimate the average national effect of Mitch on Honduras. It estimates relative local damage within Honduras.

### Honduras Only + Municipality FE + Year FE + Municipality Trends

This asks whether treated Honduran municipalities deviated from their own prior trends more than control municipalities did. It can be useful if pre-trends differ and there are enough pre-treatment years. It can also over-control if the disaster effect appears as a persistent path change that the trend structure absorbs.

This should be a robustness option, not the default.

### Regional Pooled + Municipality FE + Year FE

This asks whether treated municipalities across the region did worse than control municipalities, after removing municipality baselines and shocks common to all countries in each year.

The weakness is country-specific divergence. Honduras, Nicaragua, Guatemala, and other countries may have different post-1998 macro paths. Plain year fixed effects do not remove those country-specific paths.

### Regional Pooled + Municipality FE + Country FE + Year FE

When municipalities are nested inside countries, country fixed effects are redundant with municipality fixed effects. This specification should not be presented as meaningfully different from regional pooled + municipality FE + year FE unless municipality FE are off.

### Regional Pooled + Municipality FE + Country-Year FE

This is the cleanest local within-country comparison. It asks whether, within the same country and same year, treated municipalities did worse than control municipalities.

But it removes all average country-year shocks. For Mitch, that means it cannot estimate average national losses for Honduras, Nicaragua, or any other country. It identifies relative exposure differences inside each country-year.

### Country-Level Panel: Country FE + Year FE

This changes the unit of analysis from municipalities to countries. It asks whether more-exposed countries had worse post-Mitch paths than less-exposed countries, net of country baselines and common calendar-year shocks.

This is closer to a national-impact question, but the number of countries is small, so the design is fragile.

### Synthetic-Control / National Counterfactual For Honduras

This is the appropriate family of designs for a claim like "how much did Honduras as a whole lose because of Mitch?" It compares Honduras to a constructed counterfactual path from donor countries or regions.

This is not the same project as the municipality DiD. It answers a national-loss question rather than a local exposure-gradient question.

## 6. UI Implications For Later

The future regression tab should make the identifying question explicit whenever a user changes the specification.

Meaningful choices:

- Honduras-only, no FE: allowed as descriptive, with a warning.
- Honduras-only + municipality FE + year FE: meaningful for local differential damage.
- Honduras-only + municipality FE + year FE + municipality trends: meaningful as robustness if enough pre-period data are present.
- Regional pooled + municipality FE + year FE: meaningful but vulnerable to country-specific post-1998 divergence.
- Regional pooled + municipality FE + country-year FE: meaningful for within-country local differential damage.
- Country-level country FE + year FE: meaningful only in a separate country-level mode.
- Synthetic-control / national counterfactual: meaningful only as a separate national-counterfactual mode.

Choices that should be disabled or clearly marked as redundant:

- Country FE in Honduras-only mode, because there is only one country.
- Country FE when municipality FE are already selected in a nested municipal panel.
- Separate country FE and year FE when country-year FE are selected, because country-year FE subsume them.
- Country-year FE in Honduras-only mode, because it collapses to year FE.
- Municipality trends without municipality FE.
- Municipality trends with too few pre-treatment years to estimate trends credibly.

Warnings and tooltips should explain:

- "This specification estimates relative local damage, not average national loss."
- "Year FE in Honduras-only mode absorb common Honduran post-Mitch shocks."
- "Country-year FE remove all average country-level disaster effects in each year."
- "Municipality FE absorb permanent country differences when municipalities are nested in countries."
- "Municipality trends are a robustness check; they can over-control persistent disaster effects."

## 7. Future Regression Tab Concept

The future regression tab should be modular but guarded.

It should allow the user to choose the analysis scope:

- Honduras only.
- Pooled regional municipal panel.
- Country-level panel.
- Synthetic-control / national counterfactual mode.

For municipal DiD modes, it should allow meaningful fixed-effects options:

- Municipality FE.
- Year FE.
- Country FE only when municipality FE are off and the panel is regional.
- Country-year FE only for regional pooled municipal models.
- Municipality trends only as a robustness option with warnings.

For each selected specification, the tab should display a plain-language sentence:

```text
This specification answers: [question]
It does not answer: [lost or absorbed estimand]
Identifying variation: [remaining comparison]
```

The tab should not imply that more fixed effects are always better. It should show that fixed effects trade off confounding control against the loss of broad disaster-impact variation.

