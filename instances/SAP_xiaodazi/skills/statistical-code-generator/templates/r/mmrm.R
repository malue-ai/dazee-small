#=============================================================
# Analysis:   {analysis_name}
# Endpoint:   {endpoint}
# SAP Section: {sap_section}
#=============================================================
library(mmrm); library(emmeans)
dat <- {dataset} |> subset({pop_flag} == "Y" & {visit_var} %in% c({visit_list_r}) &
  !is.na({response_var}) & !is.na({baseline_var}))
fit <- mmrm({response_var} ~ {treatment_var} * {visit_var} + {baseline_var} * {visit_var} +
  {covariates_r} + us({visit_var} | {subject_var}), data = dat, method = "{df_method_r}")
summary(fit)
emm <- emmeans(fit, ~ {treatment_var} | {visit_var})
pairs(emm, reverse = TRUE) |> confint()
