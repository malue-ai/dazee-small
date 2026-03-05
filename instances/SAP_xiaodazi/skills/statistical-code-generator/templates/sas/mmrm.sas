/*============================================================
  Analysis:   {analysis_name}
  Endpoint:   {endpoint}
  SAP Section: {sap_section}
============================================================*/
data analysis; set adam.{dataset};
  where {pop_flag} = 'Y' and {visit_var} in ({visit_list}) and not missing({response_var}) and not missing({baseline_var});
run;
proc mixed data=analysis method=reml;
  class {subject_var} {treatment_var}(ref='{ref_group}') {visit_var} {class_covariates};
  model {response_var} = {treatment_var} {visit_var} {treatment_var}*{visit_var} {baseline_var} {baseline_var}*{visit_var} {covariates} / ddfm={df_method} solution;
  repeated {visit_var} / subject={subject_var} type={cov_structure};
  lsmeans {treatment_var}*{visit_var} / slice={visit_var}='{primary_timepoint}' diff cl;
  ods output Diffs=diffs LSMeans=lsmeans;
run;
