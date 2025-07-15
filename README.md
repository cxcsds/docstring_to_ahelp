# Create ahelp files from Sherpa

You need a CIAO installation (tested with conda) in which you have installed

  sphinx<8

We then start the process with the following - the exact warning messages
depends on what version of the code and what version of CIAO is being
analyzed:

```
% mkdir test
% ./docstring_to_help/doc2ahelp.py test
# Data1D
 - skipping as unwanted
# Data1DInt
 - skipping as unwanted
# Data2D
 - skipping as unwanted
# Data2DInt
 - skipping as unwanted
# DataARF
 - skipping as unwanted
# DataIMG
 - skipping as unwanted
# DataIMGInt
 - skipping as unwanted
# DataPHA
 - skipping as unwanted
# DataRMF
 - skipping as unwanted
# Prior
 - skipping as unwanted
# _session
 - skipping as unwanted
# _sherpa_version
 - skipping as unwanted
# _sherpa_version_string
 - skipping as unwanted
# absorptionedge
# absorptiongaussian
# absorptionlorentz
# absorptionvoigt
 - skipping absorption/emissionvoigt symbols
# accretiondisk
# add_model
# add_user_pars
...
# xsagnsed
# xsagnslim
 - skipping as XSPEC 12.11.0 model
# xsapec
# xsbapec
# xszxipab
# xszxipcf
## absorptionedge
Created: test/absorptionedge.xml
## absorptiongaussian
Created: test/absorptiongaussian.xml
## absorptionlorentz
Created: test/absorptionlorentz.xml
...
## contour_source
Created: test/contour_source.xml
## copy_data
copy_data - DBG: - copy_data has no SEE ALSO
Created: test/copy_data.xml
## cos
Created: test/cos.xml
## covar
Created: test/covar.xml
## covariance
Created: test/covariance.xml
## create_arf
create_arf - NOTE: no text in DESC block
Created: test/create_arf.xml
...
## get_chisqr_plot
Created: test/get_chisqr_plot.xml
## get_conf
get_conf - INFO: No parameters or return value
Created: test/get_conf.xml
## get_conf_opt
Created: test/get_conf_opt.xml
...
## int_unc
Created: test/int_unc.xml
## integrate1d
 - ERROR PROCESSING: <bullet_list bullet="-"><list_item><paragraph>was changed from the default (tolerance for 64-bit float) to
the 32-bit float tolerance (to avoid a warning message when
evaluating mdl);</paragraph></list_item><list_item><paragraph>and must be changed before being applied to the model to
integrate (smdl) in this case.</paragraph></list_item></bullet_list>
## jdpileup
Created: test/jdpileup.xml
## xsgrbcomp
Created: test/xsgrbcomp.xml
## xsgrbjet
 - ahelp metadata skipped as Unable to find ahelp for ['xsgrbjet']
Created: test/xsgrbjet.xml
## xsgrbm
Created: test/xsgrbm.xml
## xszxipcf
Created: test/xszxipcf.xml

Processed 711 files, skipped 42.
Errored out: ['integrate1d']

Also:
  test/models.xml
  test/xs.xml

```

The first step is to check these messages to see which we accept and
which we need to address. The problems to address include

- an update in XSPEC meaning new models
  - note that there are some un-reported items that will need
    updating (e.g. the "CIAO x.y supports XSPEC z1.z2.z3" lines)
- a change in sphinx/OTS that changes how the text is processed

Individual files can be checked with `ahelp` (although it does not set
up the `See Also` section, so you will only see the values from the
existing CIAO installation):

```
% ahelp -f test/xsgrbcomp.xml
```

We can compare the ahelp files to CIAO with `compare_ahelp_files.py` -
although note that this is not a very-clever check:

```
% ./docstring_to_ahelp/compare_ahelp_files.py test
Processing 713 XML files.
# There were 5 new file(s).
   0  name=xszxipab
   1  name=xsgrbjet
   2  name=xsvwdem
   3  name=xsvvwdem
   4  name=xswdem

# There were 55 file(s) Sherpa found in CIAO but not new.
   0  name=get_resid_prof_prefs  key=get_resid_prof_prefs
   1  name=prof_fit_resid  key=prof_fit_resid
   2  name=cstat  key=cstat
   3  name=neldermead  key=neldermead
   4  name=chi2gehrels  key=chi2gehrels
   5  name=integrate  key=integrate
   6  name=get_source_prof  key=get_source_prof
   7  name=sherpa_utils  key=sherpa_utils
   8  name=levmar  key=levmar
   9  name=wstat  key=wstat
  10  name=sherpa_contrib  key=sherpa_contrib
  11  name=get_chart_spectrum  key=get_chart_spectrum
  12  name=sherpa_chart  key=sherpa_chart
  13  name=prof_fit  key=prof_fit
  14  name=integrate1d  key=integrate1d
  15  name=get_instmap_weights  key=get_instmap_weights
  16  name=leastsq  key=leastsq
  17  name=script  key=script
  18  name=chi2datavar  key=chi2datavar
  19  name=get_marx_spectrum  key=get_marx_spectrum
  20  name=chi2constvar  key=chi2constvar
  21  name=datastack  key=datastack
  22  name=get_model_prof_prefs  key=get_model_prof_prefs
  23  name=get_model_prof  key=get_model_prof
  24  name=sherparc  key=sherparc
  25  name=save_instmap_weights  key=save_instmap_weights
  26  name=prof_resid  key=prof_resid
  27  name=chi2modvar  key=chi2modvar
  28  name=plot_instmap_weights  key=plot_instmap_weights
  29  name=chi2xspecvar  key=chi2xspecvar
  30  name=get_source_prof_prefs  key=get_source_prof_prefs
  31  name=chisquare  key=chisquare
  32  name=cash  key=cash
  33  name=estimate_weighted_expmap  key=estimate_weighted_expmap
  34  name=prof_delchi  key=prof_delchi
  35  name=plot_marx_spectrum  key=plot_marx_spectrum
  36  name=save_marx_spectrum  key=save_marx_spectrum
  37  name=pyblocxs  key=pyblocxs
  38  name=prof_model  key=prof_model
  39  name=renorm  key=renorm
  40  name=sherpa_marx  key=sherpa_marx
  41  name=save_chart_spectrum  key=save_chart_spectrum
  42  name=get_fit_prof  key=get_fit_prof
  43  name=get_delchi_prof_prefs  key=get_delchi_prof_prefs
  44  name=prof_data  key=prof_data
  45  name=get_data_prof  key=get_data_prof
  46  name=tablemodel  key=tablemodel
  47  name=gridsearch  key=gridsearch
  48  name=prof_source  key=prof_source
  49  name=sherpa_profiles  key=sherpa_profiles
  50  name=prof_fit_delchi  key=prof_fit_delchi
  51  name=get_resid_prof  key=get_resid_prof
  52  name=get_data_prof_prefs  key=get_data_prof_prefs
  53  name=plot_chart_spectrum  key=plot_chart_spectrum
  54  name=get_delchi_prof  key=get_delchi_prof
```

## Debugging

Unfortunately the following report isn't very useful (note that the
skipping metadata line is not the cause of the error):

```
## xszkerrbb
 - ahelp metadata skipped as Unable to find ahelp for ['xszkerrbb']
 - ERROR PROCESSING: <versionchanged><paragraph>4.14.0
The fcol parameter was incorrectly labelled as hd: both names
can be used to access this parameter.</paragraph><paragraph>The default a, Mbh, fcol, and lflag parameter values have
changed from 0, 1, 1.7, and 0 to 0.5, 1e7, 2.0, and 1 to match
XSPEC.</paragraph></versionchanged>
```

We can use `extract_docstrings.py` to get the docstrings into separate
files and then `view_docstring.py` to display it, which should help
point out where the error is:

```
% ls delme/
ls: cannot access 'delme/': No such file or directory
% ./docstring_to_ahelp/extract_docstrings.py sherpa.astro.ui delme
Created delme with 722 txt files
% less delme/txt/xszkerrbb.txt
The XSPEC zkerrbb model: multi-temperature blackbody model for thin accretion disk around a Kerr black hole.

The model is described at [1]_.

.. versionchanged:: 4.14.0
   The fcol parameter was incorrectly labelled as hd: both names
   can be used to access this parameter.

   The default a, Mbh, fcol, and lflag parameter values have
   changed from 0, 1, 1.7, and 0 to 0.5, 1e7, 2.0, and 1 to match
   XSPEC.

Attributes
----------
eta
    The ratio of the disk power produced by a torque at the disk
    inner boundary to the disk power arising from accretion. See
    [1]_ for more details.
...
% ./docstring_to_ahelp/view_docstring.py delme/txt/xszkerrbb.txt
SKIPPING AHELP METADATA: Unable to find ahelp for ['xszkerrbb']
Traceback (most recent call last):
  File "./docstring_to_ahelp/view_docstring.py", line 98, in <module>
    convert_and_view(args.infile)
  File "./docstring_to_ahelp/view_docstring.py", line 71, in convert_and_view
    xmldoc = convert_docutils(name, rst_doc, sig,
  File "/home/dburke/sherpa/ahelp/docstring_to_ahelp/parsers/docutils.py", line 2253, in convert_docutils
    desc, nodes = find_desc(nodes)
  File "/home/dburke/sherpa/ahelp/docstring_to_ahelp/parsers/docutils.py", line 1228, in find_desc
    for b in make_para_blocks(para):
  File "/home/dburke/sherpa/ahelp/docstring_to_ahelp/parsers/docutils.py", line 967, in make_para_blocks
    out = converter(para)
  File "/home/dburke/sherpa/ahelp/docstring_to_ahelp/parsers/docutils.py", line 807, in convert_versionwarning
    assert nblock == 1, block
AssertionError: <versionchanged><paragraph>4.14.0
The fcol parameter was incorrectly labelled as hd: both names
can be used to access this parameter.</paragraph><paragraph>The default a, Mbh, fcol, and lflag parameter values have
changed from 0, 1, 1.7, and 0 to 0.5, 1e7, 2.0, and 1 to match
XSPEC.</paragraph></versionchanged>
```

Once the errors are ironed out then you want to make a directory to
store the results - probably versioned so that as CIAO is updated we can
see changes:

```
% mkdir ahelp_xml1
% ./docstring_to_ahelp/doc2ahelp.py ahelp_xml1 > log.ahelp_xml1
copy_data - DBG: - copy_data has no SEE ALSO
create_arf - NOTE: no text in DESC block
get_conf - INFO: No parameters or return value
get_conf_results - INFO: No parameters or return value
get_confidence_results - INFO: No parameters or return value
get_covar - INFO: No parameters or return value
get_covar_results - INFO: No parameters or return value
get_covariance_results - INFO: No parameters or return value
get_functions - INFO: No parameters or return value
get_proj - INFO: No parameters or return value
get_proj_results - INFO: No parameters or return value
get_projection_results - INFO: No parameters or return value
get_sampler_name - INFO: No parameters or return value
get_specresp - DBG: - get_specresp has no SEE ALSO
get_split_plot - INFO: No parameters or return value
get_split_plot - DBG: - get_split_plot has no SEE ALSO
histogram1d - DBG: - histogram1d has no SEE ALSO
histogram2d - DBG: - histogram2d has no SEE ALSO
list_pileup_model_ids - NOTE: no text in DESC block
list_psf_ids - NOTE: no text in DESC block
rebin - DBG: - rebin has no SEE ALSO
% ./docstring_to_ahelp/compare_ahelp_files.py ahelp_xml1

Processing 722 XML files.
# There were 13 new file(s).
   0  name=xsagnslim
   1  name=xszxipab
   2  name=xslog10con
   3  name=xszkerrbb
   4  name=xslogconst
   5  name=xsismdust
   6  name=xsgrbjet
   7  name=xsolivineabs
   8  name=xsvwdem
   9  name=xsvvwdem
  10  name=xswdem
  11  name=xsthcomp
  12  name=xsbwcycl

# There were 54 file(s) Sherpa found in CIAO but not new.
   0  name=get_resid_prof_prefs  key=get_resid_prof_prefs
   1  name=prof_fit_resid  key=prof_fit_resid
   2  name=cstat  key=cstat
   3  name=neldermead  key=neldermead
   4  name=chi2gehrels  key=chi2gehrels
   5  name=integrate  key=integrate
   6  name=get_source_prof  key=get_source_prof
   7  name=sherpa_utils  key=sherpa_utils
   8  name=levmar  key=levmar
   9  name=wstat  key=wstat
  10  name=sherpa_contrib  key=sherpa_contrib
  11  name=get_chart_spectrum  key=get_chart_spectrum
  12  name=sherpa_chart  key=sherpa_chart
  13  name=prof_fit  key=prof_fit
  14  name=get_instmap_weights  key=get_instmap_weights
  15  name=leastsq  key=leastsq
  16  name=script  key=script
  17  name=chi2datavar  key=chi2datavar
  18  name=get_marx_spectrum  key=get_marx_spectrum
  19  name=chi2constvar  key=chi2constvar
  20  name=datastack  key=datastack
  21  name=get_model_prof_prefs  key=get_model_prof_prefs
  22  name=get_model_prof  key=get_model_prof
  23  name=sherparc  key=sherparc
  24  name=save_instmap_weights  key=save_instmap_weights
  25  name=prof_resid  key=prof_resid
  26  name=chi2modvar  key=chi2modvar
  27  name=plot_instmap_weights  key=plot_instmap_weights
  28  name=chi2xspecvar  key=chi2xspecvar
  29  name=get_source_prof_prefs  key=get_source_prof_prefs
  30  name=chisquare  key=chisquare
  31  name=cash  key=cash
  32  name=estimate_weighted_expmap  key=estimate_weighted_expmap
  33  name=prof_delchi  key=prof_delchi
  34  name=plot_marx_spectrum  key=plot_marx_spectrum
  35  name=save_marx_spectrum  key=save_marx_spectrum
  36  name=pyblocxs  key=pyblocxs
  37  name=prof_model  key=prof_model
  38  name=renorm  key=renorm
  39  name=sherpa_marx  key=sherpa_marx
  40  name=save_chart_spectrum  key=save_chart_spectrum
  41  name=get_fit_prof  key=get_fit_prof
  42  name=get_delchi_prof_prefs  key=get_delchi_prof_prefs
  43  name=prof_data  key=prof_data
  44  name=get_data_prof  key=get_data_prof
  45  name=tablemodel  key=tablemodel
  46  name=gridsearch  key=gridsearch
  47  name=prof_source  key=prof_source
  48  name=sherpa_profiles  key=sherpa_profiles
  49  name=prof_fit_delchi  key=prof_fit_delchi
  50  name=get_resid_prof  key=get_resid_prof
  51  name=get_data_prof_prefs  key=get_data_prof_prefs
  52  name=plot_chart_spectrum  key=plot_chart_spectrum
  53  name=get_delchi_prof  key=get_delchi_prof
```
