"""
Extract the documentation from the Sherpa docstring,
returning restructured text format.

To do
-----

1. add more logic on where the documentation from the symbol
   comes from.

2. parse the ahelp documentation (or the pre-parsed data)
   for the necessary metadata. If it is pre-parsed then maybe
   it belongs in a different module.

"""

from collections import defaultdict
from importlib import import_module
from inspect import cleandoc, isclass, signature

from sherpa.ui.utils import ModelWrapper
from sherpa.astro.instrument import ARFModel, RMFModel, RSPModel, \
    PileupRMFModel, MultiResponseSumModel
from sherpa.instrument import ConvolutionModel, PSFModel
from sherpa.data import BaseData
from sherpa.models.basic import TableModel, UserModel
from sherpa.models.template import TemplateModel, \
    InterpolatingTemplateModel

from sherpa.astro import ui

from sphinx.ext.napoleon import Config
from sphinx.ext.napoleon.docstring import NumpyDocstring


__all__ = ("sym_to_rst", "sym_to_sig", "doc_to_rst", "unwanted",
           "find_synonyms")


# Any special configuration for the parsing?
#
# This uses ivar rather than attribute when parsing
# attributes - and I can not easily work out how to process
# the latter.
#
config = Config(napoleon_use_ivar=True)


def sym_to_docstring(name, sym):
    """Return the docstring for the symbol.

    This is needed to work around some subtleties in how models
    are wrapped. It also applies known "corrections" to the docstring.
    Fortunately there are no known required corrections.

    Parameters
    ----------
    name : str
        The name of the symbol
    sym
        The Sherpa symbol.

    Returns
    -------
    result : str or None
        The docstring (after removal of excess indentation).

    """

    if isinstance(sym, ModelWrapper):
        doc = str(sym)
    else:
        doc = sym.__doc__

    if doc is None:
        return None

    return cleandoc(doc)


def sym_to_rst(name, sym):
    """Return the docstring for the symbol.

    This is needed to work around some subtleties in how models
    are wrapped. It also applies known "corrections" to the docstring.

    Parameters
    ----------
    name : str
        The name of the symbol
    sym
        The Sherpa symbol.

    Returns
    -------
    result : str or None
        The docstring (after removal of excess indentation).

    """

    doc = sym_to_docstring(name, sym)
    if doc is None:
        return None

    return doc_to_rst(doc)


def sym_to_sig(name, sym):
    """Return the 'signature' for the symbol.

    Parameters
    ----------
    name : str
        The name of the symbol
    sym
        The Sherpa symbol. This can be None, in which case we
        grab it ourselves (currently only sherpa.astro.ui cases).

    Returns
    -------
    result, sym : str or None, symbol
        The signature and the symbol.

    Notes
    -----
    At present there is no "clever" processing of the
    signature.
    """

    if sym is None:
        sym = getattr(ui, name)

    if isinstance(sym, ModelWrapper):
        # TODO: do we want to say "powlaw1d.name" or "powlaw1d"?
        sig = name.lower()
    else:
        sig = signature(sym)
        if sig is not None:
            sig = "{}{}".format(name, sig)

    return sig, sym


def doc_to_rst(doc):
    """Return the RestructuredText version.

    Parameters
    ----------
    doc : str
        The docstring (after cleaning so that the excess indention
        has been removed).

    Returns
    -------
    result : docstring
        The parsed docstring.

    """

    return NumpyDocstring(doc, config)


unwanted_classes = (ARFModel, RMFModel, RSPModel, PileupRMFModel,
                    ConvolutionModel, PSFModel,
                    TableModel, UserModel,
                    TemplateModel, InterpolatingTemplateModel,
                    MultiResponseSumModel)


def unwanted(name, sym):
    """Is this a symbol we do not want to process?

    Use simple heuristics to remove unwanted symbols. This can include
    XSPEC models that require a newer XSPEC than we use in CIAO.

    Parameters
    ----------
    name : str
        The name of the symbol
    sym
        The Sherpa symbol.

    Returns
    -------
    flag : bool
        This is True if the symbol should not be used to create an
        ahelp file.

    """

    if name.startswith('_'):
        return True

    """
    if name in ['create_arf']:
        print("  - skipping {} as a known problem case".format(name))
        return True
    """

    if isclass(sym) and issubclass(sym, BaseData):
        return True

    # Does isclass handle 'class or subclass' so we don't need to?
    #
    if type(sym) == ModelWrapper and \
       (sym.modeltype in unwanted_classes or
        issubclass(sym.modeltype, unwanted_classes)):
        return True

    # Don't bother with objects
    #
    if type(sym) == type(object):
        return True

    # Check if an XSPEC model that requires a version of XSPEC newer
    # than we support in CIAO.
    # [expected to be used rarely]
    #
    if name.startswith("xs"):
        # The model-wrapper has a modeltype argument we can access to
        # get the actual model class.
        #
        doc = sym.modeltype.__doc__
        if "This model requires XSPEC 12.15.0 or later." in doc:
            return True

        if "This model requires XSPEC 12.14.1 or later." in doc:
            return True

    return False


def syms_from_module(modulename):
    """Create docstrings from the symbols in modulename.

    Parameters
    ----------
    modulename : str
        The module to load - e.g. 'sherpa.astro.ui'.

    Returns
    -------
    out : dict
        The keys are 'name', 'file', and 'docstrings'. The name
        and file are the "dunder" versions of the module, and
        docstrings is a list of dicts. Each of these dicts has
        keys of 'name', 'symbol', 'signature', and 'docstring'.

    """

    module = import_module(modulename)
    out = {'name': module.__name__,
           'file': module.__file__,
           'docstrings': []}

    # There was a time sherpa.astro.ui failed this test as erf[c?]
    # was repeated.
    #
    assert len(module.__all__) == len(set(module.__all__))

    for name in sorted(module.__all__):

        sym = getattr(module, name)
        if unwanted(name, sym):
            continue

        store = {'name': name,
                 'symbol': sym,
                 'signature': sym_to_sig(name, sym)[0],
                 'docstring': sym_to_docstring(name, sym)}

        out['docstrings'].append(store)

    return out


def find_synonyms():
    """Return the synonym mapping.

    We have some routines available under different names - should all
    be long and short forms such as covariance/covar but I can not
    guarantee this - which we need to identify (i.e. don't create a
    help file for the synonym but add it as a refkeyword. This *only*
    looks at sherpa.astro.ui at this time.

    Returns
    -------
    synonyms, originals : dict, dict
        For synonyms the keys are the synonyms and the values are the
        ahelp names, for originals the keys are the ahelp names and the
        values are lists of synonyms (should only be 1 but just in case).

    """

    synonyms = {}
    originals = defaultdict(list)

    # Loop through all symbols just in case
    #
    for name in ui.__all__:

        sym = getattr(ui, name)
        try:
            sname = sym.__name__
        except AttributeError:
            # For now skip these
            continue

        if sname == name:
            continue

        assert name not in synonyms, name
        synonyms[name] = sname
        originals[sname].append(name)

    # Convert originals from a defaultdict to a normal dict, so
    # can use 'key in originals' as a check.
    #
    return synonyms, dict(originals)
