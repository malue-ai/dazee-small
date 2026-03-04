#=============================================================
# Analysis:   {analysis_name}
# Endpoint:   {endpoint}
# SAP Section: {sap_section}
#=============================================================
library(MASS); library(emmeans)
dat <- {dataset} |> subset({pop_flag} == "Y" & {duration_var} > 0) |>
  transform(log_dur = log({duration_var} / 365.25))
fit <- glm.nb({response_var} ~ {treatment_var} + {covariates_r} + offset(log_dur), data = dat)
summary(fit)
emm <- emmeans(fit, ~ {treatment_var}, type = "response", offset = 0)
pairs(emm, reverse = TRUE) |> confint()
