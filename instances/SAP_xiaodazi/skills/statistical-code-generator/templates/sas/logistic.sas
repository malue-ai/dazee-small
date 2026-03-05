/*============================================================
  Analysis:   {analysis_name}
  Endpoint:   {endpoint}
  SAP Section: {sap_section}
============================================================*/
proc logistic data=adam.{dataset};
  where {pop_flag} = 'Y';
  class {treatment_var}(ref='{ref_group}') {class_covariates};
  model {response_var}(event='1') = {treatment_var} {covariates} / cl;
run;
