"""Utility routines."""

import os
from inspect import signature
import sys
from typing import Any, Callable, Optional, Sequence, Union

import numpy as np

from xml.etree import ElementTree

from sherpa.ui.utils import ModelWrapper
from sherpa.astro.xspec import XSModel, XSAdditiveModel, XSMultiplicativeModel, XSConvolutionKernel
from sherpa.astro import ui

from sherpa.astro.data import DataARF, DataPHA, DataRMF
from sherpa.data import Data
from sherpa.fit import FitResults
from sherpa.models.model import Model
from sherpa.optmethods import OptMethod
from sherpa.plot import MultiPlot
from sherpa.stats import Stat
from sherpa.ui.utils import ModelWrapper


from parsers.ahelp import find_metadata
from parsers.docutils import convert_docutils, merge_metadata
from parsers.rst import parse_restructured
from parsers.sherpa import sym_to_rst, sym_to_sig


# Replace the actual Sherpa version, which uses Python 3.9 compatible
# syntax, with Python 3.10 versions:
#
# from sherpa.ui.utils import ModelType
# from sherpa.utils.types import IdType
# from sherpa.utils.random import RandomType

IdType = int | str
RandomType = np.random.Generator | np.random.RandomState
ModelType = Model | str



# CIAO 4.18
LASTMOD = "December 2025"


def save_doc(outfile, xmldoc):
    """Write the ahelp XML to a file.

    The DTD needs to be passed in as we manually hack it in,
    and have lost it in xmldoc, which could partly be me but is
    partly ElementTree too.
    """

    root = xmldoc.getroot().tag
    if root == 'cxchelptopics':
        dtdname = 'CXCHelp.dtd'
    elif root == 'cxcdocumentationpage':
        dtdname = '/data/da/Docs/sxml_manuals/dtds/CXCDocPage.dtd'
    else:
        raise ValueError("Unrecognized root element: {}".format(root))

    docstr = '<!DOCTYPE {} SYSTEM "{}">'.format(root, dtdname)

    # See https://stackoverflow.com/a/43922805
    #
    with open(outfile, 'wb') as f:
        f.write('<?xml version="1.0" encoding="UTF-8" ?>'.encode('utf8'))
        f.write(docstr.encode('utf8'))
        xmldoc.write(f, 'utf-8')


def add_model_list(caption, models, xspec=True,
                   new_elements=None):
    """Return a TABLE element describing the models.

    This needs to be updated for each CIAO release.

    new_elements is a hacky way to send back a list of any new
    elements;  just send it an empty list and it will be
    updated with the new elements.
    """

    tbl = ElementTree.Element('TABLE')
    ElementTree.SubElement(tbl, 'CAPTION').text = caption

    row0 = ElementTree.SubElement(tbl, 'ROW')

    # Do we need to beef this up?
    has_new = False

    # CIAO 4.17 included XSPEC 12.14.0k
    # CIAO 4.18 included XSPEC 12.14.0k at present
    #    but it has new models compared to 4.17.
    #
    if xspec:
        has_new = True

    # has_new = False  # change if XSPEC gets updated

    if has_new:
        ElementTree.SubElement(row0, 'DATA').text = 'New'

    ElementTree.SubElement(row0, 'DATA').text = 'Model name'
    ElementTree.SubElement(row0, 'DATA').text = 'Description'

    for name in sorted(models):
        sym = getattr(ui, name).modeltype
        desc = sym.__doc__.split("\n")[0]

        # Assume it is 'The XSPEC <> model: ...' but note that <> is
        # not necessarily the <> name (it should be)
        #
        hdr = 'The XSPEC {} model: '.format(name[2:])
        hdr2 = 'The XSPEC {} convolution model: '.format(name[2:])
        if desc.lower().startswith(hdr.lower()):
            desc = desc[len(hdr):]
        elif desc.lower().startswith(hdr2.lower()):
            desc = desc[len(hdr2):]

        # else:
        #     sys.stderr.write("Name mis-match {} vs {}\n".format(name, desc))
        #     idx = desc.find(': ')
        #     if idx == -1:
        #         raise ValueError(desc)
        #
        #     desc = desc[idx + 2:]

        row = ElementTree.SubElement(tbl, 'ROW')

        # HACKY way to determine if this is new or not - I would like to
        # query the model's metadata but we don't encode this information.
        # So I just have to look for the string
        # 'This model is only available when used with XSPEC 12.11.0 or later.'
        # as CIAO 4.13 went out with XSPEC 12.10.1s.
        #
        # It is not clear if this logic is even relevant any more, as
        # it looks like this is now handled in
        # docutils.convert_versionwarning.
        #
        # It is also awkward for 4.18 since, at present, we have the same
        # XSPEC version as 4.17 but we do have new models, so you can't
        # just check for "XSPEC 12.14.0" as some of them were added in
        # CIAO 4.17 and some in 4.18. Aha - these new models require
        # XSPEC 12.15.0, and so we do not want to process them here.
        #
        if xspec:

            doc = sym().__doc__

            # Unfortunately the format has changed by accident.
            #def is_new(major, minor, micro):
            #    return doc.find(f'This model is only available when used with XSPEC {major}.{minor}.{micro} or later.') > -1

            def is_new(major, minor, micro):
                return doc.find(f'This model requires XSPEC {major}.{minor}.{micro} or later.') > -1

            # new = is_new(12, 11, 0) or is_new(12, 11, 1) or is_new(12, 12, 0)

            # CIAO 4.15 went out with 12.12.1c
            #      4.16 is 12.13.1e
            #      4.17    12.14.0k
            #      4.18    12.14.0k
            # new = is_new(12, 14, 0)
            new = False

            # As we are not showing the new column we don't do this
            ElementTree.SubElement(row, 'DATA').text = 'NEW' if new else ''

            if new and new_elements is not None:
                new_elements.append(name)

        elif has_new:
            raise NotImplementedError(name)  # do not expect this in 4.16.0
            # ElementTree.SubElement(row, 'DATA').text = 'NEW' if name in ['pseudovoigt1d', 'voigt1d'] else ''

        ElementTree.SubElement(row, 'DATA').text = name
        ElementTree.SubElement(row, 'DATA').text = desc

    return tbl


def list_xspec_models(outdir, dtd='ahelp'):
    """Create the xs ahelp page.

    Parameters
    ----------
    outdir : string
        The output directory, which must already exist.
    dtd : {'ahelp', 'sxml'}, optional
        The DTD to use.

    Returns
    -------
    outfile
        The name of the file.
    """

    if not os.path.isdir(outdir):
        sys.stderr.write("ERROR: outdir={} does not exist\n".format(outdir))
        sys.exit(1)

    if dtd not in ['ahelp', 'sxml']:
        raise ValueError("Invalid dtd argument")

    # We loop through the ui symbols rather than directly inspect the
    # contents of sherpa.astro.xspec to make sure we are using the
    # UI-available names.
    #
    add_models = []
    mul_models = []
    con_models = []

    for name in dir(ui):

        sym = getattr(ui, name)
        if not isinstance(sym, ModelWrapper):
            continue

        mclass = sym.modeltype
        if issubclass(mclass, XSAdditiveModel):
            add_models.append(name)
        elif issubclass(mclass, XSMultiplicativeModel):
            mul_models.append(name)
        elif issubclass(mclass, XSConvolutionKernel):
            con_models.append(name)

    def check(label, models):
        if len(models) == 0:
            raise ValueError("Unable to find any {} models".format(label))

        unexpected = [n for n in models if not n.startswith('xs')]
        if len(unexpected) > 0:
            raise ValueError("{}: {}".format(label, unexpected))

    check('additive', add_models)
    check('multiplicative', mul_models)
    check('convolution', con_models)

    # CIAO 4.18
    # new_add_models = []
    should_be_empty = []

    atbl = add_model_list('Additive XSPEC models', add_models,
                          new_elements=should_be_empty)
    mtbl = add_model_list('Multiplicative XSPEC models', mul_models,
                          new_elements=should_be_empty)
    ctbl = add_model_list('Convolution XSPEC models', con_models,
                          new_elements=should_be_empty)

    if should_be_empty != []:
        print(should_be_empty)
        assert False, "expected no new add/mul/con models in 4.18"

    #if new_add_models != []:
    #    print(new_add_models)
    #    assert False, "expected no new add models in 4.18"

    rootname = None
    if dtd == 'ahelp':
        rootname = 'cxchelptopics'
    elif dtd == 'sxml':
        rootname = 'cxcdocumentationpage'
    else:
        raise RuntimeError('unknown dtd={}'.format(dtd))

    metadata = find_metadata('xs')
    if metadata is None:
        raise IOError('no ahelp for XS')

    xmlattrs = merge_metadata({'pkg': 'sherpa',
                               'key': 'xs',
                               'refkeywords': 'xspec models',
                               'seealsogroups': 'sh.models',
                               'displayseealsogroups': '',
                               'context': None},
                              metadata)

    if xmlattrs['context'] is None:
        raise IOError("No context for XS!")

    def add_para(parent, text, title=None):
        out = ElementTree.SubElement(parent, 'PARA')
        out.text = text
        if title is not None:
            out.set('title', title)

        return out

    # do we want the patch version here? Ideally.
    xspec_major_version = '12.14.0k'
    xspec_version = f'{xspec_major_version}'

    root = ElementTree.Element(rootname)

    root.append(ElementTree.Comment("THIS IS AUTO-GENERATED TEXT"))

    outdoc = ElementTree.ElementTree(root)
    entry = ElementTree.SubElement(root, 'ENTRY', xmlattrs)
    ElementTree.SubElement(entry, 'SYNOPSIS').text = 'XSPEC model functions.'

    desc = ElementTree.SubElement(entry, 'DESC')

    add_para(desc, f'''Sherpa in CIAO 4.18 includes the "additive", "multiplicative", and "convolution"
    models of XSPEC version {xspec_version}, and are available by adding the prefix
    "xs" before the XSPEC model name (in lower case). As examples: in Sherpa the XSPEC
    phabs model is called "xsphabs", the vapec model is "xcvapec", and the cflux model
    is "xscflux".
    ''')

    add_para(desc, '''The additive (atable), multiplicative (mtable), and exponential
    (etable) XSPEC table models are supported by the
    load_xstable_model command. Models that provide redshift and
    escale parameters are supported, but those models with multiple
    spectra per set of parameters (where the NXFLTEXP keyword is set
    to a value greater than 1) are not.''',
             title='XSPEC table models')

    add_para(desc, '''XSPEC models based on physical processes (e.g. line models
        such as raymond or absorption models such as wabs) assume that
        the dataspace is defined in keV.  On the other hand, Sherpa
        models are always calculated based on the input data scale.
        Thus when XSPEC models are combined with Sherpa models, the
        user should be careful to ensure that both components have the
        same dataspace units; otherwise, calculated model amplitudes
        may be incorrect.''',
             title='Important note:')

    add_para(desc, '''These models also expect that the x-values will always be
        energy bins.  When the analysis setting is using non-energy
        bins and an XSPEC model is defined, Sherpa converts the bins
        to energy before sending them to the XSPEC model.  After the
        XSPEC model finishes, Sherpa converts back to the original
        units. Sherpa also scales the model values appropriately
        (e.g., if counts/keV came out of the XSPEC model and Sherpa is
        working with wavelength, then Sherpa scales the output of the
        XSPEC model to counts/Angstrom).''')

    adesc = ElementTree.SubElement(entry, 'ADESC')
    adesc.set('title', 'Unavailable XSPEC models')
    add_para(adesc, f'''The "smaug", "polconst", "pollin", and "polpow" models, and the
        mixing-model components of XSPEC {xspec_version}
        are NOT included in CIAO.''')

    adesc = ElementTree.SubElement(entry, 'ADESC')
    adesc.set('title', 'Available XSPEC models')
    para = add_para(adesc, f'''The available XSPEC models are listed below.  Refer to the
        ahelp page for each model (e.g. "ahelp xsabsori") or the ''')

    href = ElementTree.SubElement(para, 'HREF')
    href.set('link', "https://heasarc.gsfc.nasa.gov/docs/xanadu/xspec/manual/manual.html")
    href.text = "XSPEC User's Guide"

    tail_text = '''for more information.  Note that the ahelp
       files describe the version of the XSPEC model included in
       CIAO, while the XSPEC User's Guide may reference a newer
       version with different options.'''

    # Add if we get new modes for this release.
    #
    #tail_text += ''' If the first column is labelled NEW then
    #   the model is new to CIAO 4.17.'''

    href.tail = tail_text

    adesc.append(atbl)
    adesc.append(mtbl)
    adesc.append(ctbl)

    adesc = ElementTree.SubElement(entry, 'ADESC')
    adesc.set('title', 'Parameter names')
    para = add_para(adesc, f'''Sherpa uses names, rather than numbers, to access parameter values (e.g.
        to set them, change whether a parameter is frozen, adjust the limits,
        or access the latest value). Prior to XSPEC version 12.9.0, the parameter
        names for the XSPEC models were not guaranteed to be valid Python
        symbols, and so Sherpa has converted the problematic names.
        The names used by Sherpa are given in the ahelp page for the model
        - e.g.''')

    href = ElementTree.SubElement(para, 'HREF')
    href.set('link', "https://cxc.harvard.edu/sherpa/ahelp/xspowerlaw.html")
    href.text = "ahelp xspowerlaw"

    # add to end of href
    href.tail = "- and by printing the model component:"

    verb = ElementTree.SubElement(adesc, 'VERBATIM')
    verb.text = """
sherpa> set_source(xsphabs.gal * xspowerlaw.pl)
sherpa> print(gal)
xsphabs.gal
   Param        Type          Value          Min          Max      Units
   -----        ----          -----          ---          ---      -----
   gal.nH       thawed            1            0        1e+06 10^22 atoms / cm^2
sherpa> print(pl)
xspowerlaw.pl
   Param        Type          Value          Min          Max      Units
   -----        ----          -----          ---          ---      -----
   pl.PhoIndex  thawed            1           -3           10
   pl.norm      thawed            1            0        1e+24
    """

    adesc = ElementTree.SubElement(entry, 'ADESC')
    adesc.set('title', 'Parameter limits')

    add_para(adesc, '''A small number of XSPEC models support parameter
    values outside the XSPEC hard-limit range, such as the
    fpl parameter of xsoptxagn, which can be set to a negative value.
    To support these models the hard-limits can be changed for
    an XSPEC parameter with the hard_min and hard_max arguments
    to the set method:''')

    para = add_para(adesc, '')
    syntax = ElementTree.SubElement(para, 'SYNTAX')
    ElementTree.SubElement(syntax, 'LINE').text = "sherpa> create_model_component('xsoptxagn', 'cpt')"
    ElementTree.SubElement(syntax, 'LINE').text = "sherpa> cpt.fpl.min"
    ElementTree.SubElement(syntax, 'LINE').text = "0.0"
    ElementTree.SubElement(syntax, 'LINE').text = "sherpa> cpt.fpl.set(hard_min=-1)"
    ElementTree.SubElement(syntax, 'LINE').text = "sherpa> cpt.fpl.min"
    ElementTree.SubElement(syntax, 'LINE').text = "-1.0"

    add_para(adesc, '''It is strongly suggested that the parameter is frozen when
    it is set outside the original limits.''')

    adesc = ElementTree.SubElement(entry, 'ADESC')
    adesc.set('title', 'Changing the chatter level of XSPEC models')

    add_para(adesc, '''The default chatter level for XSPEC models - i.e. how much information
        they will print to the screen when evaluated - is set to 10,
        matching the default XSPEC version. The chatter setting can be
        changed with set_xschatter - for example:''')

    para = add_para(adesc, '')
    syntax = ElementTree.SubElement(para, 'SYNTAX')
    ElementTree.SubElement(syntax, 'LINE').text = 'sherpa> set_xschatter(0)'
    ElementTree.SubElement(syntax, 'LINE').text = 'sherpa> plot_fit()'
    ElementTree.SubElement(syntax, 'LINE').text = 'sherpa> set_xschatter(10)'

    add_para(adesc, '''The current XSPEC chatter level is returned by the
        get_xschatter level.''')

    add_para(adesc, '''The Python docstrings for these functions provide more
        information, and can be read with the help() function:''')

    para = add_para(adesc, '')
    syntax = ElementTree.SubElement(para, 'SYNTAX')
    ElementTree.SubElement(syntax, 'LINE').text = 'sherpa> help(set_xschatter)'
    ElementTree.SubElement(syntax, 'LINE').text = 'sherpa> help(get_xschatter)'

    adesc = ElementTree.SubElement(entry, 'ADESC')
    adesc.set('title', 'Accessing the XSPEC state')

    add_para(adesc, '''Several routines are provided to change (or report) the
        XSPEC state (i.e. settings that may influence the model
        calculations). These include (please use the Python help
        command for more information on these functions):''')

    add_para(adesc, '''The get_xsabund(), set_xsabund(),
        get_xsabundances(), set_xsabundances(), and show_xsabund()
        routines.''',
             title='Abundance')

    add_para(adesc, 'The get_xsxsect() and set_xsxsect() routines.',
             title='Cross section')

    add_para(adesc, 'The get_xscosmo() and set_xscosmo() routines.',
             title='Cosmology')

    add_para(adesc, '''The XSPEC SET command is handled by the set_xsxset()
        routine, and once a value is set it can be retrieved
        with get_xsxset().''',
             title='Using the SET command')

    add_para(adesc, '''The sherpa.astro.xspec module contains the get_xspath_manager()
        and get_xspath_model() to return the current paths to the
        XSPEC directories, and set_xspath_manager() to change the path.''',
             title='Manager and model paths')

    add_para(adesc, '''The sherpa.astro.xspec module contains the get_xsstate() and
        set_xsstate() routines which can be used to find and set all
        of the above values.''',
             title='All XSPEC settings')

    adesc = ElementTree.SubElement(entry, 'ADESC')
    adesc.set('title', 'Checking the XSPEC module version')

    add_para(adesc, '''The XSPEC module contains the get_xsversion routine, which returns a string
        containing the XSPEC patch level used in Sherpa. As an example:''')

    para = add_para(adesc, '')
    syntax = ElementTree.SubElement(para, 'SYNTAX')
    ElementTree.SubElement(syntax, 'LINE').text = 'sherpa> from sherpa.astro import xspec'
    ElementTree.SubElement(syntax, 'LINE').text = 'sherpa> xspec.get_xsversion()'
    ElementTree.SubElement(syntax, 'LINE').text = f"'{xspec_version}'"

    # If we have changes to talk about
    if False:
        # TO BE UPDATED
        adesc = ElementTree.SubElement(entry, 'ADESC')
        adesc.set('title', 'Changes in CIAO 4.17')

        add_para(adesc, f'''The XSPEC models have been updated to release {xspec_version}
        in CIAO 4.17, from version 12.13.1e in CIAO 4.16. There are 50 new additive models, although a number of them are
        essentially just renamed versions of existing models (see the XSPEC model documentation for
        more details):''',
                 title='XSPEC model updates')

        outlist = ElementTree.SubElement(adesc, 'LIST')

        out = ElementTree.SubElement(outlist, 'ITEM')
        out.text = ", ".join(new_add_models) + "."

        #out = ElementTree.SubElement(outlist, 'ITEM')
        #out.text = "Multiplicative: " + ", ".join(["xsismdust", "xslog10con", "xslogconst", "xsolivineabs", "xszxipab"]) + "."

        #out = ElementTree.SubElement(outlist, 'ITEM')
        #out.text = "Convolution: " + ", ".join(["xscglumin"]) + "."

        add_para(adesc, '''The default parameter values of a number of
        models have been adjusted to match changes made in XSPEC 12.14.0.
        Of particular note are models which now use a default redshift
        if 0.1 rather than 0, and models with a switch parameter which now
        default to 2 rather than 1 (indicating the use of APEC for
        interpolation rather than mekal). The switch parameter may also
        now have an upper limit of 3, indicating the use of SPEX data
        for the interpolation, rather than 2. Several models have seen
        some parameters marked as frozen or thawed to match XSPEC 12.14.0.
        Please
        see the individual model ahelp pages for more information.''',
                 title="Changes to default parameter values")

        add_para(adesc, '''A number of models now use the XSPEC capitalization
        for the redshift parameter (that is, 'redshift' or 'Redshift',
        depending on the model). Since Sherpa's parameter interface
        is case insensitive this does not change the behaviour of Sherpa
        scripts, but screen or file output will use the new
        capitalization.''',
                 title="Parameter name changes")

        add_para(adesc, '''The show_xsabund(), get_xsabundances(), and
        set_xsabundances() commands have been added in this release. They
        allow users to get, set, or see all the abundances in one go -
        rather than the existing get_xsabund() and set_xsabund() commands,
        which support access via a pre-set table or individual element name.''',
                 title="Abundance settings")

    # Not yet ready
    # add_para(adesc, '''XSPEC models can now be regridded, that is, evaluated with a
    # finer energy response or cover a larer range than the instrument response.
    # The regrid method is used to create a new version of the model which evaluates
    # the model on the higher-resolution grid and then resamples it to match the
    # instrument model.''',
    #          title='Changing the energy grid of a model')

    bugs = ElementTree.SubElement(entry, 'BUGS')

    para = add_para(bugs, 'For a list of known bugs and issues with the XSPEC models, please visit the')

    href = ElementTree.SubElement(para, 'HREF')
    href.set('link', 'https://heasarc.gsfc.nasa.gov/docs/xanadu/xspec/bugs.html')
    href.text = 'XSPEC bugs page.'

    add_para(bugs, '''To check the XSPEC version used by Sherpa, use the
    get_xsversion routine from the xspec module:''')

    para = add_para(bugs, '')
    syntax = ElementTree.SubElement(para, 'SYNTAX')
    ElementTree.SubElement(syntax, 'LINE').text = 'sherpa> from sherpa.astro import xspec'
    ElementTree.SubElement(syntax, 'LINE').text = 'sherpa> xspec.get_xsversion()'
    ElementTree.SubElement(syntax, 'LINE').text = f"'{xspec_version}'"


    lastmod = ElementTree.SubElement(entry, 'LASTMODIFIED')
    lastmod.text = LASTMOD

    suffix = 'sxml' if dtd == 'sxml' else 'xml'
    outfile = os.path.join(outdir, 'xs.{}'.format(suffix))
    save_doc(outfile, outdoc)

    return outfile


def list_sherpa_models(outdir, dtd='ahelp'):
    """Create the models ahelp page.

    Parameters
    ----------
    outdir : string
        The output directory, which must already exist.
    dtd : {'ahelp', 'sxml'}, optional
        The DTD to use.

    Returns
    -------
    outfile
        The name of the file.
    """

    if not os.path.isdir(outdir):
        sys.stderr.write("ERROR: outdir={} does not exist\n".format(outdir))
        sys.exit(1)

    if dtd not in ['ahelp', 'sxml']:
        raise ValueError("Invalid dtd argument")

    # Hard-coded list of names to exclude
    #
    excluded = ['arfmodel', 'arfmodelnopha', 'arfmodelpha',
                'rmfmodel', 'rmfmodelnopha', 'rmfmodelpha',
                'rspmodel', 'rspmodelnopha', 'rspmodelpha',
                'pileuprmfmodel',
                'multiresponsesummodel',
                'knninterpolator',
                'psfmodel',
                'convolutionmodel',
                'tablemodel',
                'template', 'templatemodel',
                'interpolatingtemplatemodel',
                'usermodel',
                'integrate1d'  # WHAT TO DO ABOUT THIS
    ]

    models1 = []
    models2 = []
    for name in dir(ui):
        if name in excluded:
            continue

        sym = getattr(ui, name)
        if not isinstance(sym, ModelWrapper):
            continue

        mclass = sym.modeltype
        if issubclass(mclass, XSModel):
            continue

        if mclass.__doc__ is None:
            raise ValueError(f"Name={name}")

        if mclass.ndim == 1:
            models1.append(name)
        elif mclass.ndim == 2:
            models2.append(name)
        elif name in ['absorptionvoigt', 'emissionvoigt']:
            models1.append(name)
        else:
            raise ValueError((name, mclass.ndim))

    def check(label, models):
        if len(models) == 0:
            raise ValueError("Unable to find any {} models".format(label))

    check('sherpa 1D', models1)
    check('sherpa 2D', models2)

    stbl1 = add_model_list('One-dimensional Sherpa models', models1, xspec=False)
    stbl2 = add_model_list('Two-dimensional Sherpa models', models2, xspec=False)

    rootname = None
    if dtd == 'ahelp':
        rootname = 'cxchelptopics'
    elif dtd == 'sxml':
        rootname = 'cxcdocumentationpage'
    else:
        raise RuntimeError('unknown dtd={}'.format(dtd))

    metadata = find_metadata('models')
    if metadata is None:
        raise IOError('no ahelp for models')

    xmlattrs = merge_metadata({'pkg': 'sherpa',
                               'key': 'models',
                               'refkeywords': 'sherpa models',
                               'seealsogroups': 'sh.models',
                               'displayseealsogroups': '',
                               'context': None},
                              metadata)

    if xmlattrs['context'] is None:
        raise IOError("No context for models!")

    def add_para(parent, text, title=None):
        out = ElementTree.SubElement(parent, 'PARA')
        out.text = text
        if title is not None:
            out.set('title', title)

        return out

    root = ElementTree.Element(rootname)

    root.append(ElementTree.Comment("THIS IS AUTO-GENERATED TEXT"))

    outdoc = ElementTree.ElementTree(root)
    entry = ElementTree.SubElement(root, 'ENTRY', xmlattrs)
    ElementTree.SubElement(entry, 'SYNOPSIS').text = 'Summary of Sherpa models (excluding XSPEC).'

    desc = ElementTree.SubElement(entry, 'DESC')

    para = add_para(desc, '''The following table lists most of the models available within Sherpa.
        See ''')

    href = ElementTree.SubElement(para, 'HREF')
    href.set('link', 'https://cxc.harvard.edu/sherpa/ahelp/xs.html')
    href.text = '"ahelp xs"'

    href.tail = ' for those models provided by XSPEC, '

    href = ElementTree.SubElement(para, 'HREF')
    href.set('link', 'https://cxc.harvard.edu/sherpa/ahelp/tablemodel.html')
    href.text = '"ahelp tablemodel"'

    href.tail = ' for table models, and '

    href = ElementTree.SubElement(para, 'HREF')
    href.set('link', 'https://cxc.harvard.edu/sherpa/ahelp/load_user_model.html')
    href.text = '"ahelp load_user_model"'

    href.tail = ' for user-supplied models, respectively.'

    # Tables galore
    desc.append(stbl1)
    desc.append(stbl2)

    adesc = ElementTree.SubElement(entry, 'ADESC')
    adesc.set('title', 'Are models evaluated at a point or across a bin?')

    para = add_para(adesc, '''The integration of models in Sherpa is controlled by an
     integration flag in each model structure.  Refer to''')

    href = ElementTree.SubElement(para, 'HREF')
    href.set('link', 'https://cxc.harvard.edu/sherpa/ahelp/integrate.html')
    href.text = '"ahelp integrate"'

    href.tail = ' for information on integrating model components.'

    bugs = ElementTree.SubElement(entry, 'BUGS')

    para = add_para(bugs, 'See the')

    href = ElementTree.SubElement(para, 'HREF')
    href.set('link', 'htps://cxc.harvard.edu/sherpa/bugs/')
    href.text = 'bugs pages on the Sherpa website'

    href.tail = ' for an up-to-date listing of known bugs.'

    lastmod = ElementTree.SubElement(entry, 'LASTMODIFIED')
    lastmod.text = LASTMOD

    suffix = 'sxml' if dtd == 'sxml' else 'xml'
    outfile = os.path.join(outdir, 'models.{}'.format(suffix))
    save_doc(outfile, outdoc)

    return outfile


def process_symbol(name, sym, dtd='ahelp',
                   annotations="keep",
                   ahelp=None, synonyms=None, debug=False):

    orig_ann = None
    if hasattr(sym, "__annotations__"):
        if annotations == "delete":
            # This is a global change, as any future access to the
            # annotations for this symbol will get None.
            #
            sym.__annotations__ = None

        elif sym.__annotations__ is None:
            pass

        elif len(sym.__annotations__) == 0:
            # What does annotations = {} mean? For now drop it as it
            # doesn't help us, and it's easiest not to have to worry
            # about different ways to say "empty".
            #
            sym.__annotations__ = None

        else:
            # temporarily over-ride the annotations
            #
            orig_ann = sym.__annotations__
            sym.__annotations__ = None

    sig, _ = sym_to_sig(name, sym)

    # Restore the annotations, if set. Note that we convert them from
    # strings, and try to handle Optional/Union -> a | .... This is
    # not ideal.
    #
    if orig_ann is not None:
        for k, v in orig_ann.items():
            if v == 'None':
                orig_ann[k] = None
                continue

            if v == 'Any':
                orig_ann[k] = Any
                continue

            if v == 'bool':
                orig_ann[k] = bool
                continue

            if v == 'int':
                orig_ann[k] = int
                continue

            if v == 'float':
                orig_ann[k] = float
                continue

            if v == 'str':
                orig_ann[k] = str
                continue

            if v == 'str | float':
                orig_ann[k] = str | float
                continue

            if v in ['Optional[int]',
                     'int | None']:
                orig_ann[k] = int | None
                continue

            if v in ['Optional[str]',
                     'str | None']:
                orig_ann[k] = str | None
                continue

            if v == 'list[str]':
                orig_ann[k] = list[str]
                continue

            if v == 'Sequence[str]':
                assert False  # do we need this
                orig_ann[k] = Sequence[str]
                continue

            if v in ['Optional[Sequence[str]]',
                     'Sequence[str] | None']:
                orig_ann[k] = Sequence[str] | None
                continue

            if v == 'dict[str, np.ndarray]':
                orig_ann[k] = dict[str, np.ndarray]
                continue

            if v == 'dict[str, float]':
                orig_ann[k] = dict[str, float]
                continue

            if v == 'tuple[tuple[np.ndarray, ...], np.ndarray]':
                orig_ann[k] = tuple[tuple[np.ndarray, ...], np.ndarray]
                continue

            if v == 'tuple[float, float, float]':
                orig_ann[k] = tuple[float, float, float]
                continue

            if v == 'IdType':
                orig_ann[k] = IdType
                continue

            if v == 'list[IdType]':
                orig_ann[k] = list[IdType]
                continue

            if v in ['Optional[IdType]',
                     'IdType | None']:
                orig_ann[k] = IdType | None
                continue

            if v == 'Sequence[IdType]':
                orig_ann[k] = Sequence[IdType]
                continue

            if v in ['Optional[Sequence[IdType]]',
                     'Sequence[IdType] | None']:
                orig_ann[k] = Sequence[IdType] | None
                continue

            if v in ['Union[IdType, Sequence[IdType]]',
                     'IdType | Sequence[IdType]']:
                orig_ann[k] = IdType | Sequence[IdType]
                continue

            if v in ['Optional[Union[IdType, Sequence[IdType]]]',
                     'IdType | Sequence[IdType] | None']:
                orig_ann[k] = IdType | Sequence[IdType] | None
                continue

            if v == 'Stat':
                orig_ann[k] = Stat
                continue

            if v in ['Union[str, Stat]',
                     'str | Stat']:
                orig_ann[k] = str | Stat
                continue

            if v == 'OptMethod':
                orig_ann[k] = OptMethod
                continue

            if v in ['Union[OptMethod, str]',
                     'OptMethod | str']:
                orig_ann[k] = OptMethod | str
                continue

            if v in ['Optional[RandomType]',
                     'RandomType | None']:
                orig_ann[k] = RandomType | None
                continue

            if v == 'Data':
                orig_ann[k] = Data
                continue

            if v == 'DataARF':
                orig_ann[k] = DataARF
                continue

            if v == 'DataPHA':
                orig_ann[k] = DataPHA
                continue

            if v == 'DataRMF':
                orig_ann[k] = DataRMF
                continue

            if v == 'Model':
                orig_ann[k] = Model
                continue

            if v == 'FitResults':
                orig_ann[k] = FitResults
                continue

            if v == 'MultiPlot':
                orig_ann[k] = MultiPlot
                continue

            if v == 'ModelType':
                orig_ann[k] = ModelType
                continue

            if v == 'Callable':
                orig_ann[k] = Callable
                continue

            if v == 'Callable[[str, Model], None]':
                orig_ann[k] = Callable[[str, Model], None]
                continue

            if v in ['Optional[Callable[[str, Model], None]]',
                     'Callable[[str, Model], None] | None']:
                orig_ann[k] = Callable[[str, Model], None] | None
                continue

            if v == 'str | dict[str, str]':
                orig_ann[k] = str | dict[str, str]
                continue

            if isinstance(v, str):
                # let me know uf there's more annotations to fix
                assert False, ("process_symbol:annotation",
                               k, v, type(v))

        sym.__annotations__ = orig_ann

    sherpa_doc = sym_to_rst(name, sym)
    if sherpa_doc is None:
        print("  - has no doc")
        return None

    if debug:
        print("---- formats")
        print("-- Sherpa:\n{}".format(sherpa_doc))

    rst_doc = parse_restructured(name, sherpa_doc)
    if debug:
        print("-- RestructuredText:\n{}".format(rst_doc))

    if orig_ann is not None:
        # annotated_sig, _ = sym_to_sig(name, sym)
        actual_sig = signature(sym)
    else:
        # annotated_sig = None
        actual_sig = None

    doc = convert_docutils(name, rst_doc, sig, dtd=dtd,
                           actual_sig=actual_sig,
                           # annotated_sig=annotated_sig,
                           symbol=sym, metadata=ahelp,
                           synonyms=synonyms)
    return doc
