/*============================================================
  Analysis:   {analysis_name}
  Endpoint:   {endpoint}
  SAP Section: {sap_section}
============================================================*/
proc phreg data=adam.{dataset};
  where {pop_flag} = 'Y';
  class {treatment_var}(ref='{ref_group}') {class_covariates};
  model {time_var}*{censor_var}(0) = {treatment_var} {covariates} / risklimits;
run;
proc lifetest data=adam.{dataset} plots=survival(atrisk);
  where {pop_flag} = 'Y'; time {time_var}*{censor_var}(0); strata {treatment_var};
run;
