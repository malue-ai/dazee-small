/*============================================================
  Analysis:   Safety Summary - Adverse Events
  SAP Section: {sap_section}
============================================================*/
proc freq data=adam.adae;
  where saffl = 'Y' and trtemfl = 'Y';
  tables {treatment_var}*(aebodsys aedecod) / nocum nopercent;
run;
proc freq data=adam.adae;
  where saffl = 'Y' and aeser = 'Y';
  tables {treatment_var}*(aebodsys aedecod) / nocum nopercent;
run;
