/*============================================================
  Analysis:   {analysis_name}
  Endpoint:   {endpoint}
  SAP Section: {sap_section}
  Generated:  {timestamp} by SAP Creation Assistant
============================================================*/
data analysis; set adam.{dataset}; where {pop_flag} = 'Y';
  if {duration_var} > 0 then log_dur = log({duration_var} / 365.25); else delete;
run;
proc glimmix data=analysis;
  class {subject_var} {class_vars};
  model {response_var} = {treatment_var} {covariates} / dist=negbin link=log offset=log_dur solution;
  {contrast_statements}
  lsmeans {treatment_var} / ilink cl;
  ods output ParameterEstimates=parms Contrasts=contrasts LSMeans=lsmeans;
run;
data results; set contrasts;
  rate_ratio = exp(Estimate); rr_lcl = exp(Estimate - 1.96*StdErr); rr_ucl = exp(Estimate + 1.96*StdErr);
run;
proc print data=results noobs; var Label rate_ratio rr_lcl rr_ucl Probt; title "{analysis_name}"; run;
