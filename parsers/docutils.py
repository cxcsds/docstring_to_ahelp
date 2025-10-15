"""
Convert docutils to ahelp or SXML DTD for Sherpa documentation.

TODO:
  - references are just converted to <integer> in the text when something
    "nicer" could be done (e.g. links or at least [<integer>]).
    There is some attempt to handle this, but incomplete. A similar
    situation holds for "symbols" - do we add `` around them or not?

"""

from collections import OrderedDict
from inspect import Signature
import inspect
import re
import sys
import types
import typing

from xml.etree import ElementTree

from docutils import nodes

from sherpa.astro.xspec import XSAdditiveModel, XSConvolutionKernel, \
    XSMultiplicativeModel
from sherpa.data import Data
from sherpa.fit import FitResults
from sherpa.models.model import Model
from sherpa.optmethods import OptMethod
from sherpa.plot import MultiPlot
from sherpa.stats import Stat
from sherpa.ui.utils import ModelWrapper


CIAOVER = "CIAO 4.18"
XSPECVER = "12.14.0k"
LASTMOD = "December 2025"


objname = '<unset>'


def set_parent(name):
    """Used to report messages"""
    global objname
    objname = name


def dbg(msg, info='DBG'):
    sys.stderr.write(f"{objname} - {info}: {msg}\n")


def convert_version_number(v):
    """Convert from Sherpa to CIAO numbering

    Not all Sherpa releases map to a CIAO release.

    CIAO releases:
       4.18
       4.17
       4.16
       4.15
       4.14
       4.13
       4.12.1
       4.12
       4.11
       4.10
       4.9
       4.8.2 / 4.8.1
       4.8

    """

    toks = v.split('.')
    assert len(toks) == 3, v
    assert toks[0] == '4', v

    if toks[2] == '0':
        # Generic naming, drop the .0
        return f'{toks[0]}.{toks[1]}'
    elif v.startswith('4.17.'):
        return '4.18'
    elif v.startswith('4.16.'):
        return '4.17'
    elif v.startswith('4.15.'):
        return '4.16'
    elif v.startswith('4.14.'):
        return '4.15'
    elif v.startswith('4.13.'):
        return '4.14'
    elif v == '4.12.2':
        return '4.13'
    elif v == '4.10.1':
        return '4.11'

    return v


def splitWhile(pred, xs):
    """Split input when the predicate fails.

    Parameters
    ----------
    pred : function reference
        Elements are let through while pred(x) is True.
    xs : sequence of x

    Returns
    -------
    ls, rs : list, list
        The elements in xs for which pred(x) holds, and then
        the remainder.

    Examples
    --------

    >>> splitWhile(lambda x: x < 5, [1, 2, 5, 3, 4])
    ([1, 2], [5, 3, 4])

    >>> splitWhile(lambda x: x > 5, [1, 2, 5, 3, 4])
    ([], [1, 2, 5, 3, 4])

    >>> splitWhile(lambda x: x > 0, [1, 2, 5, 3, 4])
    ([1, 2, 5, 3, 4], [])

    """

    ls = []
    rs = []
    n = len(xs)
    idx = 0
    while idx < n:
        x = xs[idx]
        if not pred(x):
            break

        ls.append(x)
        idx += 1

    while idx < n:
        rs.append(xs[idx])
        idx += 1

    return ls, rs


def is_para(node):
    """Is this a paragraph node?

    This is a simple wrapper as currently not sure whether we
    want to check on paragraph only, or include sub-classes.

    Parameters
    ----------
    node : docutils.node

    Returns
    -------
    flag : bool

    """

    # return isinstance(node, nodes.paragraph)
    return node.tagname == 'paragraph'


XSMODEL_RE = re.compile('^XS[a-z0-9]+$')

XSVERSION_WARNING = re.compile(r'^This model requires XSPEC 12\.\d\d\.\d or later.$')


# Just check that we understand the links between reference and target
# nodes. This is really "just for fun".
#
references = set()

def process_reference(node):
    """Extract the text and link from a reference node."""

    assert node.tagname == "reference"
    name = node.get("name")

    # Hmmm, we can have this multiple times, and I am not sure why
    # (is it that the code gets re-run without clearing the references
    # store?)
    #if name in references:
    #    raise ValueError(f"Multiple name={name} are being set; is this a problem?\n{node}")

    if name is not None:
        references.add(name.lower())

    return node.astext(), node.get("refuri")


def process_target(node):
    """Check we know about this target."""

    # It looks like we only get these when the reference tag set its
    # name attribute.
    #
    assert node.tagname == "target"
    names = node.get("names")
    assert len(names) == 1  # I guess could have multipe
    if names[0].lower() not in references:
        raise ValueError(f"Found un-referenced target block '{names[0]}':\n{node}")


def astext(node):
    """Extract the text contents of the node.

    This is essentially `astext` method on the node but with
    some extra processing to handle some of the tags we can
    handle (e.g. footnote references).

    Parameters
    ----------
    node : docutils.node

    Returns
    -------
    txt : str

    Notes
    -----
    This is not a principled set of conversion rules. It is based
    on the input data.
    """

    if node.tagname == 'system_message':
        dbg(f"- skipping message: {node}")
        return ''

    if node.tagname == '#text':
        return node.astext()

    if node.tagname == 'reference':
        return node.astext()

    # assume that the footnote contains a single item of
    # text
    if node.tagname == 'footnote':
        assert node[0].tagname == 'label', node
        ctr = f"[{node[0].astext()}]"

        # handle different variants; should these use astext()?
        #
        if node[1].tagname == 'paragraph':
            # this drops any links
            cts = astext(node[1])
        elif node[1].tagname == 'enumerated_list':
            # not sure if going to want to handle differently
            # to above.
            cts = astext(node[1])
        else:
            raise ValueError(f"Unexpected node {node[1].tagname} in {node}")

        return f"{ctr} {cts}"

    if node.tagname == 'footnote_reference':
        return f"[{node.astext()}]"

    if node.tagname == 'title_reference':
        # Limited support: hard-coded to match the current documentation
        # as it's not obvious it's easy to fix.
        #
        out = node.astext()

        if out in ["sherpa.sim", "sherpa.utils",
                   "sherpa.astro.datastack", "sherpa.ui",
                   "sherpa.astro.ui", "sherpa.utils.logging"]:
            return f"`{out}`"

        if out.startswith("sherpa.") or out.startswith("~"):
            toks = out.split(".")
            assert len(toks) > 1, "Unexpected reference: `{out}`"
            ltok = toks[-1]

            # special case models
            #
            if ltok in ["JDPileup", "PSFModel"]:
                return f"`{ltok.lower()}`"

            return f"`{ltok}`"

        # if out.startswith('sherpa.'):
        #     assert False, "title_reference: " + out

        assert not out.startswith('sherpa'), f"reference <{out}>"

        return f"`{out}`"

    if node.tagname == 'literal':
        # Limited speacial case here:
        #   leave non-Sherpa names as is (hard-coded to True, False, StringIO at the momnt)
        #   XSmodel -> xsmodel
        #
        out = node.astext()
        if out in ['True', 'False', 'StringIO']:
            return out

        if out.startswith('XS') and re.match(XSMODEL_RE, out) is None:
            assert False, "literal: " + out

        if out.startswith('sherpa.'):
            assert out

        if re.match(XSMODEL_RE, out):
            return out.lower()

        return out.lower()

    if node.tagname == 'emphasis':
        # what should be done here?
        return node.astext()

    if node.tagname == 'strong':
        # what should be done here?
        return node.astext()

    if node.tagname == "reference":
        # Sometimes we can make targets into a link,
        # and sometimes we can't. However, not
        # sure we ever get to here so just error out.
        #
        txt = make_href_text(node)
        raise NotImplementedError(f"Unexpected reference: {txt}")

    if node.tagname == "target":
        # assume we can just skip this
        process_target(node)
        return ""

    if node.tagname == "citation_reference":
        # This is new in CIAO 4.16. I guess this should just be:
        return f"[{node.astext()}]"

    assert node.tagname in ['paragraph', 'list_item',
                            'enumerated_list'], node

    # Recurse into this "container".
    #
    out = []
    for tag in node:
        # print("DBG: [{}] tag={}".format(node.tagname, tag.tagname))
        out.append(astext(tag))

    out = " ".join(out)
    return out


def make_syntax_block(lines):
    """Create a SYNTAX block.

    Parameters
    ----------
    lines : list of str
        The contents of the SYNTAX block. It can not be empty

    Returns
    -------
    el : ElementTree.Element
        The SYNTAX block
    """

    assert len(lines) > 0

    syn = ElementTree.Element("SYNTAX")
    for l in lines:
        ElementTree.SubElement(syn, 'LINE').text = l

    return syn


def make_href(node):
    """Create a HREF block from a reference node.

    Parameters
    ----------
    node

    Returns
    -------
    el : ElementTree.Element
        The HREF block
    """

    txt, uri = process_reference(node)

    href = ElementTree.Element("HREF")
    href.text = txt
    href.set("link", uri)

    return href


def make_href_text(node):
    """Create text from a reference node.

    Parameters
    ----------
    node

    Returns
    -------
    txt : str
        The contents of the node with no markup
    """

    txt, uri = process_reference(node)
    return f"{txt} [{uri}]"


def convert_para(para, complex=True):
    """Add the paragraph to the ahelp PARA block.

    Parameters
    ----------
    para : docutils.node
        The contents to add. It is expected to be paragraph but
        can be other specialized cases
    complex : bool, optional
        If set then the paragraph can contain HREF blocks,
        otherwise only plain text (this does not fully model
        the PARA block, but is hopefully sufficient for us).

    Returns
    -------
    out : ElementTree.Element

    See Also
    --------
    astext

    Notes
    -----
    This is an expensive way of calling para.astext() but lets me note
    what non-text nodes we have to deal with. With support for
    references it has become a bit-more complex.

    """

    text = []
    # reported = set([])

    if para.tagname != "paragraph":
        msg = f"- paragraph handling {para.tagname}"
        dbg(msg)

    # Handling of the text is a bit complex now that we handle
    # HREF links.
    #
    out = ElementTree.Element("PARA")
    href = None

    refs = []
    for n in para:

        if n.tagname == "target":
            # Assume we can just skip this.
            #
            process_target(n)
            continue

        if n.tagname == "reference":

            # Do we make an XML tag or just add text?
            #
            if not complex:
                txt, uri = process_reference(n)
                text.append(make_href_text(n))
                continue

            if href is None:
                out.text = "\n".join(text)
            else:
                href.tail = "\n".join(text)

            text = []

            href = make_href(n)
            out.append(href)

            continue

        text.append(astext(n))

    if href is None:
        out.text = "\n".join(text)
    else:
        href.tail = "\n".join(text)

    return out


def convert_doctest_block(para):
    """Create a VERBATIM block.

    Parameters
    ----------
    para : docutils.nodes.doctest_block
        The contents to add.

    Returns
    -------
    out : ElementTree.Element

    Notes
    -----
    At present this enforces xml:space="preserve".
    """

    assert para.tagname == 'doctest_block', para
    assert para.get('xml:space') == 'preserve', para

    verbatim = ElementTree.Element('VERBATIM')
    verbatim.text = para.astext()
    return verbatim


def convert_literal_block(para):
    """Create a VERBATIM block.

    Parameters
    ----------
    para : docutils.nodes.literal_block
        The contents to add.

    Returns
    -------
    out : ElementTree.Element

    See Also
    --------
    convert_doctest_block

    Notes
    -----
    At present this enforces xml:space="preserve".

    """

    assert para.tagname == 'literal_block', para
    assert para.get('xml:space') == 'preserve', para

    verbatim = ElementTree.Element('VERBATIM')
    verbatim.text = para.astext()
    return verbatim


def convert_list_items(para):
    """Convert list_item tags to an ahelp LIST.

    """

    out = ElementTree.Element('LIST')
    for el in para:
        assert el.tagname == 'list_item', el
        ElementTree.SubElement(out, 'ITEM').text = astext(el)

    return out


def convert_block_quote(para):
    """Create the contents of a block_quote.

    Support for bullet_list, enumerated_list, and doctest_block.

    Parameters
    ----------
    para : docutils.nodes.block_quote
        The contents to add.

    Returns
    -------
    out : ElementTree.Element

    See Also
    --------
    convert_enumerated_list

    To do
    -----
    This needs to handle complicated cases, where the list
    items contain markup.
    """

    assert para.tagname == 'block_quote', para
    if para[0].tagname in ['bullet_list', 'enumerated_list']:
        assert len(para) == 1, (len(para), para)
        return convert_list_items(para[0])

    if all([p.tagname == 'doctest_block' for p in para]):
        # Treat as a single VERBATIM block
        #
        # Is this sufficient?
        ls = [p.astext() for p in para]
        out = ElementTree.Element('VERBATIM')
        out.text = "\n\n".join(ls)  # note double new line
        return out

    # Do we need to worry about multi-paragraph blocks?
    #
    if para[0].tagname == 'paragraph':
        assert len(para) == 1, (len(para), para)
        out = ElementTree.Element('VERBATIM')
        out.text = astext(para[0])
        return out

    raise ValueError(f"Unexpected block_quote element in:\n{para}")


def convert_enumerated_list(para):
    """Create a list block.

    Parameters
    ----------
    para : docutils.nodes.enumerated_list
        The contents to add.

    Returns
    -------
    out : ElementTree.Element

    See Also
    --------
    convert_block_quote, convert_bullet_list

    To do
    -----
    This needs to handle complicated cases, where the list
    items contain markup.
    """

    assert para.tagname == 'enumerated_list', para
    # assert len(para) == 1, (len(para), para)
    return convert_list_items(para)


def convert_bullet_list(para):
    """Create a list block.

    Parameters
    ----------
    para : docutils.nodes.bullet_list
        The contents to add.

    Returns
    -------
    out : ElementTree.Element

    See Also
    --------
    convert_block_quote, convert_enumerated_list

    To do
    -----
    This needs to handle complicated cases, where the list
    items contain markup.
    """

    assert para.tagname == 'bullet_list', para
    # assert len(para) == 1, (len(para), para)
    return convert_list_items(para)


def convert_definition_list_as_paras(para):
    """Create a definition list.

    This returns a set of paragraphs, with titles being the
    list headers, and the contents being the paragrph contents.

    Parameters
    ----------
    para : docutils.nodes.enumerated_list
        The contents to add.

    Returns
    -------
    out : list of ElementTree.Element

    Notes
    -----
    At present each list item creates a single paragraph. This may
    have to change.

    """

    assert para.tagname == 'definition_list', para

    out = []
    for el in para:
        assert el.tagname == 'definition_list_item', el
        assert el[0].tagname == 'term', el
        assert el[0][0].tagname in ['literal', '#text'], el
        assert el[1].tagname == 'definition', el
        assert el[1][0].tagname == 'paragraph', el
        assert len(el[1]) == 1, el

        xml = convert_definition(el[1])
        xml.set('title', el[0].astext())
        out.append(xml)

    return out


def convert_definition_list_as_table(para):
    """Convert a definition list into a table.

    This requires a simple structure: each definition can only
    contain a single paragraph and doesn't contain any complex
    markup.

    Parameters
    ----------
    para : docutils.nodes.enumerated_list
        The contents to add.

    Returns
    -------
    out : list of ElementTree.Element

    """

    assert para.tagname == 'definition_list', para

    out = ElementTree.Element('TABLE')

    # add a fake first row to set up the headers
    #
    row0 = ElementTree.SubElement(out, 'ROW')
    ElementTree.SubElement(row0, 'DATA').text = 'Item'
    ElementTree.SubElement(row0, 'DATA').text = 'Definition'

    for el in para:
        assert el.tagname == 'definition_list_item', el
        assert el[0].tagname == 'term', el
        assert el[0][0].tagname in ['literal', '#text'], el
        assert el[1].tagname == 'definition', el
        assert el[1][0].tagname == 'paragraph', el
        assert len(el[1]) == 1, el

        row = ElementTree.SubElement(out, 'ROW')
        ElementTree.SubElement(row, 'DATA').text = el[0].astext()

        # It would be nice if we could error out if el[1]
        # contained any markup (well. markup we can't easily
        # convert).
        #
        ElementTree.SubElement(row, 'DATA').text = astext(el[1][0])

    return [out]


def convert_definition_list(para):
    """How do we convert a definition list?

    For now use a table.
    """

    # So far this is okay
    # dbg('CHECK CONVERSION OF DL', info='TODO')
    return convert_definition_list_as_table(para)


def convert_definition(para):
    """Create a definition.

    This is just the default paragraph handling.

    Parameters
    ----------
    para : docutils.nodes.definition
        The contents to add.

    Returns
    -------
    out : ElementTree.Element

    """

    assert para.tagname == 'definition', para

    text = []
    for n in para:
        text.append(astext(n))

    out = ElementTree.Element("PARA")
    out.text = "\n".join(text)
    return out


"""

<definition_list_item>
  <term>The pre-defined abundance tables are:</term>
  <definition>
    <bullet_list bullet="-">
      <list_item>
        <paragraph>'angr', from <footnote_reference ids="id2" refname="2">2</footnote_reference></paragraph>
      </list_item>
      <list_item>
        <paragraph>'aspl', from <footnote_reference ids="id3" refname="3">3</footnote_reference></paragraph></list_item><list_item><paragraph>'feld', from <footnote_reference ids="id4" refname="4">4</footnote_reference>, except for elements not listed which
are given 'grsa' abundances</paragraph></list_item><list_item><paragraph>'aneb', from <footnote_reference ids="id5" refname="5">5</footnote_reference></paragraph></list_item><list_item><paragraph>'grsa', from <footnote_reference ids="id6" refname="6">6</footnote_reference></paragraph></list_item><list_item><paragraph>'wilm', from <footnote_reference ids="id7" refname="7">7</footnote_reference>, except for elements not listed which
are given zero abundance</paragraph></list_item><list_item><paragraph>'lodd', from <footnote_reference ids="id8" refname="8">8</footnote_reference></paragraph></list_item></bullet_list></definition></definition_list_item>

"""


def add_table_row(out, el):
    """Given a table row, add it to the table.

    Parameters
    ----------
    out : ElementTree.Element
        A TABLE block.
    el : nodes.thead or nodes.tbody
        The row to add.
    """

    assert el.tagname in ['thead', 'tbody'], el
    for row in el:
        assert row.tagname == 'row'

        xrow = ElementTree.SubElement(out, 'ROW')
        for entry in row:
            assert entry.tagname == 'entry'
            # an entry can be empty
            if len(entry) == 0:
                txt = ''
            else:
                assert len(entry) == 1, len(entry)
                assert entry[0].tagname == 'paragraph'
                txt = entry.astext()

            ElementTree.SubElement(xrow, 'DATA').text = txt


def convert_table(tbl):
    """Create a table block.

    Parameters
    ----------
    tbl : docutils.nodes.table
        The contents to add.

    Returns
    -------
    out : ElementTree.Element

    """

    assert tbl.tagname == 'table', tbl

    # only one table group
    assert len(tbl) == 1
    tgroup = tbl[0]
    assert tgroup.tagname == 'tgroup', tgroup
    ncols = int(tgroup.get('cols'))
    assert ncols >= 1

    out = ElementTree.Element('TABLE')
    for el in tgroup:
        if el.tagname == 'colspec':
            continue

        if el.tagname in ['thead', 'tbody']:
            add_table_row(out, el)
            continue

        raise ValueError(f"Unexpected tag: {el.tagname}")

    return out


def convert_note(note):
    """Create a note block.

    Parameters
    ----------
    note : docutils.nodes.note
        The contents to add.

    Returns
    -------
    out : ElementTree.Element

    """

    assert note.tagname == 'note'

    # Assume:
    #  1 paragraph - text
    #  2 paragrahs - first is title, second is text
    #
    # could be mode though
    assert all([n.tagname == 'paragraph' for n in note]), note

    # could handle this, but would need to return [Element]
    #
    assert len(note) < 3, (len(note), note)

    if len(note) == 1:
        title = 'Note'
        out = convert_para(note[0])
    else:
        title = astext(note[0])
        out = convert_para(note[1])

    out.set('title', title)

    # SPECIAL CASE xsthcomp
    # - it contains a note that is not relevant for CIAO, as it
    #   refers to a change in XSPEC models 12.11.0 to 12.11.1
    #   and we have no CIAO version with 12.11.0
    #
    if title == 'Parameter renames in XSPEC 12.11.1':
        return None

    return out


def convert_warning(note):
    """Create a warning block.

    Parameters
    ----------
    note : docutils.nodes.note
        The contents to add.

    Returns
    -------
    out : ElementTree.Element

    """

    assert note.tagname == 'warning'

    # Assume:
    #  1 paragraph - text
    #  2 paragrahs - first is title, second is text (although not handled yet)
    #
    # could be mode though
    assert all([n.tagname == 'paragraph' for n in note]), note

    # could handle this, but would need to return [Element]
    #
    assert len(note) < 3, (len(note), note)

    if len(note) == 1:
        title = 'Warning'
        out = convert_para(note[0])
    else:
        raise NotImplementedError("need to handle")
        title = astext(note[0])
        out = convert_para(note[1])

    out.set('title', title)

    return out


store_versions = None


def reset_stored_versions():
    global store_versions
    store_versions = {'versionadded': [], 'versionchanged': [],
                      'titles': set()}


def convert_versionwarning(block):
    """Create a versionxxx block.

    This is handled differently to normal nodes as we want to
    move this out of the main text and into an ADESC block at
    the end. The data is added to store_versions rather than
    returning anything,

    Parameters
    ----------
    block : rst.versionnode
        The contents to add.

    """

    # safety check to ensure we don't have these blocks in other
    # parts of the document.
    #
    if 'DONE' in store_versions:
        raise ValueError(f"Unexpected block {block}")

    if block.tagname == 'versionadded':
        lbl = 'Added'
    elif block.tagname == 'versionchanged':
        lbl = 'Changed'
    else:
        assert False, block

    # Assume:
    #  first word of the first paragraph is the version
    #
    assert all([is_para(n) for n in block]), block

    # Note: I have no idea what the structure here is - i.e.
    # can we have multiple blocks or multiple elements
    # within a block. So this is just a bunch of
    # "logic" written to handle whatever we find...
    #
    # nblock = len(block)
    # if nblock != 1:
    #     raise RuntimeError("Need to handle multi-para versionxxx block: {}".format(block))

    # The assumption is that the first token is the version
    b0 = astext(block[0])
    toks = b0.split(maxsplit=1)

    version = convert_version_number(toks[0])
    title = f'{lbl} in CIAO {version}'

    out = ElementTree.Element("PARA")
    if title not in store_versions["titles"]:
        out.set('title', title)
        store_versions["titles"].add(title)

    # Skip the
    #  "This model requires XSPEC xxx or later."
    # paragraph.
    #
    xspec_version = "This model requires XSPEC 12.14.0 or later."
    if len(toks) > 1:
        if not re.match(XSVERSION_WARNING, toks[1]):
            out.text = toks[1]

    store_versions[block.tagname].append(out)

    for blk in block[1:]:
        if not is_para(blk):
            raise RuntimeError(blk)

        out = ElementTree.Element("PARA")
        out.text = astext(blk)
        store_versions[block.tagname].append(out)

    return None


def convert_comment_versionwarning(block):
    """Create a versionxxx block from an incorrect tag

    I wrote '.. versionadded: 4.12.2' which was missing the
    second colon, and this gets mapped to a comment block,
    so catch this case.

    Very hacky and based on convert_versionwarning

    Parameters
    ----------
    block : rst.versionnode
        The contents to add.

    """

    # safety check to ensure we don't have these blocks in other
    # parts of the document.
    #
    if 'DONE' in store_versions:
        raise ValueError(f"Unexpected block {block}")

    assert len(block) == 1

    astxt = astext(block[0])
    idx = astxt.find(':')
    assert idx > 0

    tagname = astxt[:idx]

    if tagname == 'versionadded':
        lbl = 'Added'
    elif tagname == 'versionchanged':
        lbl = 'Changed'
    else:
        assert False, block

    astxt = astxt[idx + 1:]
    toks = astxt.split('\n', maxsplit=1)

    version = convert_version_number(toks[0].strip())
    title = f'{lbl} in CIAO {version}'

    out = ElementTree.Element("PARA")
    out.set('title', title)

    if len(toks) == 2:
        out.text = toks[1]

    if len(toks) > 2:
        raise RuntimeError(f"Need to handle multi-para versionxxx block: {block}")

    store_versions[tagname].append(out)
    return None


def convert_field_body(fbody):
    """Create a field_body block.

    Parameters
    ----------
    fbody : docutils.nodes.field_body
        The contents to add.

    Returns
    -------
    out : ElementTree.Element

    """

    assert fbody.tagname == 'field_body'

    if not all([n.tagname == 'paragraph' for n in fbody]):
        raise ValueError(f"Expected only paragragh in {fbody}")

    # could handle multiple blocks, but would need to return [Element]
    #
    n = len(fbody)
    if n == 0:
        # do we want this?
        return ElementTree.Element('PARA')
    elif n == 1:
        return convert_para(fbody[0], complex=False)
    else:
        raise ValueError(f"Need to handle {n} blocks")


para_converters = {'doctest_block': convert_doctest_block,
                   'block_quote': convert_block_quote,
                   'enumerated_list': convert_enumerated_list,
                   'definition_list': convert_definition_list,
                   'definition': convert_definition,
                   'bullet_list': convert_bullet_list,
                   'table': convert_table,
                   'note': convert_note,
                   'warning': convert_warning,
                   'versionadded': convert_versionwarning,
                   'versionchanged': convert_versionwarning,
                   'comment': convert_comment_versionwarning,
                   'field_body': convert_field_body,
                   'literal_block': convert_literal_block}

# return a list
para_mconverters = ['definition_list']


def make_para_blocks(para):
    """Create one or more PARA blocks.

    Parameters
    ----------
    para : docutils.node
        The paragraph block (or one to be converted to a paragraph block).

    Returns
    -------
    el : list of ElementTree.Element
        The PARA block(s), which can be empty.

    Notes
    -----
    Unlike add_syntax_block, the input is the docutils element since
    there can be a range of contents.

    FOR NOW DO NOT TRY TO BE TOO CLEVER WITH THE PROCESSING.

    To do
    -----
    Do we want to process <title_reference>text</title_reference>
    in any special way?

    """

    if para.tagname == 'system_message':
        msg = f"- skipping message: {para.astext()}"
        dbg(msg)
        return []

    # TODO: convert all the "conversion" routines to return a list
    single = True

    if is_para(para):
        converter = convert_para

    else:
        try:
            converter = para_converters[para.tagname]
        except KeyError:
            raise ValueError(f"Unsupported paragraph type:\ntagname={para.tagname}\n{para}")

        single = para.tagname not in para_mconverters

    out = converter(para)
    if out is None:
        return []

    if single:
        out = [out]

    return out

def cleanup_re(regexp, txt):
    m = re.match(regexp, txt)
    if m is None:
        return txt

    ntxt = m[1] + m[2] + m[3]
    return cleanup_re(regexp, ntxt)


CLASS_RE = re.compile(r"(.+)<class 'sherpa\..+\.([^\.]+)'>(.+)")

def cleanup_sig_class(sig):
    """<class 'sherpa.*.X'> -> X"""
    return cleanup_re(CLASS_RE, sig)


FUNCTION_RE = re.compile("(.+)<function ([^ ]+) at 0x[^>]+>(.+)")

def cleanup_sig_function(sig):
    """<function foo at 0x...> -> foo"""
    return cleanup_re(FUNCTION_RE, sig)


def cleanup_sig(sig):
    """Try to make the default Python signature less intimidating.

    Heuristics:


    """

    sig = cleanup_sig_class(sig)
    sig = cleanup_sig_function(sig)
    return sig


def find_syntax(name, sig, indoc):
    """Return the syntax line, if present, and the remaining document.

    Parameters
    ----------
    name : str
        The name of the symbol being processed.
    sig : str or None
        The Python signature of this symbol, if available. It is
        used when there is no syntax line.
    indoc : list of nodes
        The document.

    Returns
    -------
    syntax, remaining : ElementTree.Element or None, list of nodes
        The contents of the syntax block, and the remaining nodes.

    """

    # Use the syntax from the document in preference to the
    # signature line.
    #
    # To do:
    # Improve the conversion of the signature to text, in particular
    # for classes.
    #
    if sig is not None:
        argline = make_syntax_block([cleanup_sig(sig)])
    else:
        argline = None

    node = indoc[0]
    if not is_para(node):
        return argline, indoc

    txt = node.astext().strip()
    if not txt.startswith(f'{name}('):
        return argline, indoc

    # I do not think we have any files that hit this section,
    # so ignore for now.
    #
    assert False, f"Need to understand this: {txt}"
    assert txt.endswith(')'), txt

    dbg("- using SYNTAX block from file", info='WARN')
    out = make_syntax_block([txt])
    return out, indoc[1:]


# Check if this is still used
def add_pars_to_syntax(syntax, fieldlist):
    """Do we add a summary of the parameter information to SYNTAX?

    """

    if syntax is None or fieldlist is None:
        return syntax

    partypes = []
    for par in fieldlist['params']:
        try:
            partypes.append((par['name'], par['type']))
        except KeyError:
            continue

    if len(partypes) == 0:
        return syntax

    ElementTree.SubElement(syntax, 'LINE').text = ''

    # TODO: Do we need a header line?
    for pname, ptype in partypes:
        ps = make_para_blocks(ptype)
        assert len(ps) == 1
        ptxt = f'{pname} - {ps[0].text}'
        ElementTree.SubElement(syntax, 'LINE').text = ptxt

    return syntax


def add_xspec_model_to_syntax(syntax, name, symbol):
    """Add the info about XSPEC models."""

    ElementTree.SubElement(syntax, 'LINE').text = ''

    if issubclass(symbol.modeltype, XSAdditiveModel):
        mdesc = 'an additive'
    elif issubclass(symbol.modeltype, XSMultiplicativeModel):
        mdesc = 'a multiplicative'
    elif issubclass(symbol.modeltype, XSConvolutionKernel):
        mdesc = 'a convolution'
    else:
        raise RuntimeError(f"Unexpected XSPEC model component: {name}")

    mline = f'The {name} model is {mdesc} model component.'
    ElementTree.SubElement(syntax, 'LINE').text = mline


# Check if this is still used.
def add_annotated_sig_to_syntax(syntax, annotated_sig):
    """Add the annotated signature to the SYNTAX block."""

    assert annotated_sig is not None
    for l in ["",
              "The types of the arguments are:",
              "",
              # The LINE block strips leading/trailing spaces
              str(annotated_sig)
              ]:
        ElementTree.SubElement(syntax, 'LINE').text = l


def augment_examples(examples, symbol):
    """Add in examples based on the symbol (at present models only).

    """

    if symbol is None:
        return examples

    if not isinstance(symbol, ModelWrapper):
        return examples

    mtype = symbol.modeltype.__name__.lower()
    strval = str(symbol.modeltype('mdl'))

    if examples is None:
        examples = ElementTree.Element('QEXAMPLELIST')

    example = ElementTree.Element('QEXAMPLE')

    syn = ElementTree.SubElement(example, 'SYNTAX')
    line = ElementTree.SubElement(syn, 'LINE')
    line.text = f'>>> create_model_component("{mtype}", "mdl")'
    line = ElementTree.SubElement(syn, 'LINE')
    line.text = '>>> print(mdl)'

    desc = ElementTree.SubElement(example, 'DESC')
    para = ElementTree.SubElement(desc, 'PARA')
    para.text = f'Create a component of the {mtype} model ' + \
                'and display its default parameters. The output is:'

    verb = ElementTree.SubElement(desc, 'VERBATIM')
    verb.text = strval

    examples.insert(0, example)

    return examples


def find_synopsis(indoc):
    """Return the synopsis contents, if present, and the remaining document.

    Parameters
    ----------
    indoc : list of nodes
        The document.

    Returns
    -------
    synopsis, tags, remaining : ElementTree.Element or None, set of str, list of nodes
        The contents of the SYNOPSIS block, words which can be used in the
        refkeywords attribute, and the remaining nodes.

    Notes
    -----
    Assumes the first paragraph is the synopsis. Could restrict to
    only those blocks where the paragraph is a single line, but not
    clear it is worth it (or that is a valid assumption).
    """

    node = indoc[0]
    if not isinstance(node, nodes.paragraph):
        return None, '', indoc

    syn = node.astext().strip()

    def clean(v):
        # assuming only have one of these conditions to process, so the
        # order of operations does not matter
        for c in [',', '.', ':', '"', "'"]:
            if v.endswith(c):
                v = v[:-1]
            if v.startswith(c):
                v = v[1:]

        return v

    # return a sorted list of keys to make comparisons easier
    #
    keys = [clean(k) for k in syn.lower().split()]
    keywords = set(keys)

    out = ElementTree.Element('SYNOPSIS')
    out.text = syn
    return out, keywords, indoc[1:]


def find_desc(indoc, synonyms=None):
    """Return the basic description, if present, and the remaining document.

    Parameters
    ----------
    indoc : list of nodes
        The document.
    synonyms : list of str or None
        Any synonyms.

    Returns
    -------
    desc, remaining : ElementTree.Element or None, list of nodes
        The contents of the DESC block, and the remaining nodes.

    Notes
    -----
    Stops at a rubric, field_list, or container (e.g. see also) block.

    The output does **not** contain any parameter information,
    since this is added lately.

    There is special-case handling when the desc block only contains
    versionadded/changed blocks, as we then don't want any DESC
    block.

    """

    def want(x):
        return x.tagname not in ['rubric', 'field_list', 'container', 'seealso']

    pnodes, rnodes = splitWhile(want, indoc)
    if len(pnodes) == 0 and synonyms is None:
        return None, indoc

    out = ElementTree.Element('DESC')

    # Add in any synonyms
    if synonyms is not None:
        # Technically can have multiple, but in reality we only have
        # pairs.
        assert len(synonyms) == 1, synonyms

        p = ElementTree.Element('PARA')
        p.text = f"The function is also called {synonyms[0]}()."

        out.append(p)

    for para in pnodes:
        for b in make_para_blocks(para):
            if b is None:
                continue
            out.append(b)

    # assert len(out) > 0
    if len(out) == 0:
        dbg("no text in DESC block", info='NOTE')

    # should we return None if out is empty?
    return out, rnodes


def find_fieldlist(indoc):
    """Return the parameter info, if present, and the remaining document.

    It is not clear how object attributes are converted - i.e. do they
    also map to a field_list block? I have switched the default
    Napoleon configuration so that theyt use ivar blocks for the
    model attributes.

    Parameters
    ----------
    indoc : list of nodes
        The document.

    Returns
    -------
    fl, remaining : list or None, list of nodes
        The contents of the field_list block, and the remaining nodes.

    Notes
    -----
    This does not convert to ahelp, since this information may be
    used in multiple places. The assumption is that we have (where
    'name' is the parameter name, or names::

      field_name = 'param name'
      field_name = 'type name'
      field_name = 'returns'
      field_name = 'raises'

      field_name = 'ivar'

    The parsing of the raises block may depend on how the :exc: role
    is parsed - at present it creates a "literal" object which means
    that the exception type is included in the body. Maybe this will
    change if it is handled differently?

    I also need to look at how return information is encoded.
    """

    if len(indoc) == 0:
        return None, indoc

    node = indoc[0]

    # TODO: should this use isinstance instead?
    if node.tagname != 'field_list':
        return None, indoc

    # Use an OrderedDict rather than a list, with the idea that
    # the field_name value can be used to determine whether we are
    # adding a new entry or appending to an existing entry.
    #
    # This means that raises and returns have a "fake" name added,
    # and will contain multiple elements.
    #
    params = OrderedDict()
    returns = []
    raises = []

    for field in node:
        assert field.tagname == 'field', field

        name = None
        body = None

        for f in field:
            n = f.tagname
            if n == 'field_name':
                # Assume it is okay to remove styling here
                name = f.astext()

            elif n == 'field_body':
                body = f

            else:
                raise ValueError(f"Unexpected field member:\n{f}")

        toks = name.split(' ', 1)
        t0 = toks[0]
        ntoks = len(toks)
        assert t0 in ['param', 'ivar', 'type', 'rtype', 'raises', 'returns'], name
        if t0 == 'raises':
            # Has there been a change in how the raises section is
            # encoded, or is it more that when I originally wrote
            # this I had no examples which returned several tokens?
            #
            # It looks like we don't do anything with this at the moment
            # anyway.
            if ntoks == 1:
                raises.append(body)
            else:
                raises.append({'tokens': toks[1:], 'body': body})

            continue

        elif t0 in ['returns', 'rtype']:
            assert ntoks == 1, (toks, name)
            returns.append((t0, body))
            continue

        assert ntoks == 2, name
        pname = toks[1]

        # NOTE: for attributes (and parameters, but don't think have any
        # like this), can have multiple "ivar p1", "ivar p2" lines
        # before the description. Need to amalgamate.
        #
        # Heuristic
        #    preceding name ends in a comma
        #    field_body of preceding is empty
        #    assume this happens at most once
        #
        if t0 == 'ivar' and len(params) > 0:
            prev_key = list(params.keys())[-1]
            prev_val = params[prev_key]

            # strip() is probably not needed, but just in case
            if prev_key.strip().endswith(',') and len(prev_val['ivar']) == 0:

                # edit the params structure, but as removing the
                # last item it is okay (ie ordering is maintained).
                #
                del params[prev_key]
                new_key = f"{prev_key} {pname}"

                prev_val['name'] = new_key
                prev_val['ivar'] = body
                params[new_key] = prev_val
                continue

        try:
            store = params[pname]
        except KeyError:
            params[pname] = {'name': pname}
            store = params[pname]

        store[t0] = body

    out = list(params.values())
    return {'params': out, 'returns': returns, 'raises': raises}, \
        indoc[1:]


def find_seealso(indoc):
    """Return the See Also info, if present, and the remaining document.

    Parameters
    ----------
    indoc : list of nodes
        The document.

    Returns
    -------
    seealso, remaining : list of str or None, list of nodes
        The symbol names (only) in the See Also block, and the
        remaining nodes.

    Notes
    -----
    This does not convert to ahelp. There are expected to be two types:
    a definition_list, which has name and summary, and a collection of
    paragraphs, which just contains the names. The return value is the
    same, in both cases
    """

    if len(indoc) == 0:
        return None, indoc

    node = indoc[0]

    # TODO: should this use isinstance instead?
    if node.tagname != 'seealso':
        return None, indoc

    if node[0].tagname == 'definition_list':
        assert len(node) == 1
        names = []
        for n in node[0]:
            assert n.tagname == 'definition_list_item', n
            assert n[0].tagname == 'term', n
            assert n[0][0].tagname in ['literal', '#text'], n
            names.append(n[0][0].astext())

    elif node[0].tagname == 'paragraph':
        assert len(node) == 1, node  # expected to fail
        names = []
        for n in node[0]:
            assert n.tagname in ['literal', '#text'], n
            names.append(n.astext())

    else:
        raise ValueError(f"Unexpected see also contents:\n{node}")

    # Strip out "," fragments.
    #
    names = [n for n in names if n.strip() != ',']

    # Some names can contain the full module path, so clean them
    # up, and then remove duplicates (shouldn't be any).
    #
    # I don't think there should be any see also symbol with a '.' in it
    # for any other reason than it is part of a module path.
    #
    out = []
    for n in names:
        if n.startswith('sherpa.'):
            n = n.split('.')[-1]
        elif n.find('.') != -1:
            sys.stderr.write(f"ERROR: invalid seealso {names}\n")
            sys.exit(1)

        if n not in out:
            out.append(n)

    if len(names) != len(out):
        msg = f"- see also contains duplicates: {names}"
        dbg(msg)

    return out, indoc[1:]


def find_notes(name, indoc):
    """Return the notes section, if present, and the remaining document.

    Parameters
    ----------
    name : str
        The name of the symbol being documented.
    indoc : list of nodes
        The document.

    Returns
    -------
    notes, remaining : Element or None, list of nodes
        An ADESC block  and the remaining nodes.

    Notes
    -----
    If this is a note to say that this XSPEC model is only available
    with a given XSPEC version then we

    - if it's old, ignore it
    - if it's new, add it to the versionadded store instead

    """

    if len(indoc) == 0:
        return None, indoc

    node = indoc[0]

    # TODO: should this use isinstance instead?
    if node.tagname != 'rubric':
        return None, indoc

    if node.astext().strip() != 'Notes':
        return None, indoc

    # look for the next rubric that is not a 'Notes' section
    #
    lnodes, rnodes = splitWhile(lambda x: x.tagname != 'rubric',
                                indoc[1:])

    # Strip out any paragraph which matches:
    #
    # This model is only available when used with XSPEC 12.9.1 or later.
    #
    # for various XSPEC versions.
    #
    # Note that (at present) there is no attempt to remove the
    # sentence from a block of text (ie if there is additional material),
    # since it looks like it doesn't happen (but it could).
    #
    # Unfortunately I have not used exactly the same text for different
    # versions: 12.14.0 uses
    #
    # This model requires XSPEC 12.14.0 or later.
    #
    # See also ../helpers.py which also includes this logic.
    #
    def version(v):
        return 'This model is only available when used with ' + \
            f'XSPEC {v} or later.'

    v1291 = version('12.9.1')
    v12100 = version('12.10.0')
    v12101 = version('12.10.1')
    v12110 = version('12.11.0')  # there's no 12.11.1 only models
    v12120 = version('12.12.0')

    # I want to warn about 12.12.1 models, but it turns out in
    # CIAO 4.15 we don't support the three new models, as they
    # require XFLT changes we currently do not support.
    # I leave this in as a reminder.
    #
    v12121 = version('12.12.1')

    # These are new to CIAO 4.16 - cglumin is the only one
    v12130 = version('12.13.0')

    # These are new to CIAO 4.17.
    v12140 = "This model requires XSPEC 12.14.0 or later."

    # These are new in 4.18 but we don't provide this version
    # of XSPEC and so we drop them.
    #
    v12150 = "This model requires XSPEC 12.15.0 or later."

    # First remove all the old "added in XSPEC x.y.z" lines
    #
    def wanted(n):
        txt = n.astext()
        return txt not in [v1291, v12100, v12101, v12110, v12120,
                           v12130, v12140]

    lnodes = list(filter(wanted, lnodes))
    if len(lnodes) == 0:
        # print(" - NOTE section is about XSPEC version")
        return None, rnodes

    # What happens if this is a 12.12.1 only model? It is not
    # supported in CIAO 4.15 so we have to remove it. However
    # we do not expect this. These models are also not supported
    # in 4.16 (so when we do add support it's going to get
    # complicated)
    #
    def not_wanted(n):
        txt = n.astext()
        # return txt == v12121
        return txt in [v12121, v12150]

    unodes = list(filter(not_wanted, lnodes))
    if len(unodes) > 0:
        raise RuntimeError(f"ERR: looks like {name} is unsupported in CIAO")

    # We now need to decide whether this is text we want to output
    # or something we want to change into a 'versionadded' command.
    #
    # Do we have an XSPEC version relevant to this CIAO release?
    #
    # CIAO 4.12 used 12.10.1
    # CIAO 4.13 has 12.11.0 and 12.11.1 (but only 12.11.0 has new models)
    #   but we are only going out with XSPEC 12.10.1
    # CIAO 4.14 uses 12.12.0
    # CIAO 4.15 uses 12.12.0  (actually 12.12.1)
    # CIAO 4.16 uses 12.13.0  (as of May 2023)
    # CIAO 4.17 uses 12.14.0k, which has new models
    # CIAO 4.18 uses 12.14.0k, and has new models compared to 4.17
    #
    any_notes = False
    out = ElementTree.Element("ADESC", {'title': 'Notes'})

    # Do we want to process the contents or add them as a versionadded entry?
    #
    for para in lnodes:
        if v12140 in para.astext():

            print(para.astext())
            raise NotImplementedError("this has got too complex")

            npara = ElementTree.Element("PARA", {'title': 'New in CIAO 4.17'})
            npara.text = f'The {name} model (added in XSPEC 12.14.0) is new in CIAO 4.17.'
            store_versions['versionadded'].append(npara)
            continue

        for b in make_para_blocks(para):
            out.append(b)

        any_notes = True

    if any_notes:
        assert len(out) > 0
        return out, rnodes
    else:
        return None, rnodes


def find_warning(indoc):
    """Extract a warning section, if it exists.

    Parameters
    ----------
    indoc : list of nodes
        The document.

    Returns
    -------
    warning, remaining : Element or None, list of nodes
        An DESC block and the remaining nodes.

    """

    if len(indoc) == 0:
        return None, indoc

    node = indoc[0]
    if node.tagname != 'warning':
        return None, indoc

    assert len(node.children) == 1

    # This probably needs to handle more-complocated structures,
    # but stay simple for now.
    #
    out = ElementTree.Element("ADESC", {'title': 'Warning'})
    cts = ElementTree.SubElement(out, 'PARA')
    cts.text = astext(node.children[0])

    return out, indoc[1:]


def find_references(indoc):
    """Return the references section, if present, and the remaining document.

    Parameters
    ----------
    indoc : list of nodes
        The document.

    Returns
    -------
    refs, remaining : Element or None, list of nodes
        An ADESC block  and the remaining nodes.

    """

    if len(indoc) == 0:
        return None, indoc

    node = indoc[0]

    # TODO: should this use isinstance instead?
    if node.tagname != 'rubric':
        return None, indoc

    if node.astext().strip() != 'References':
        return None, indoc

    # look for the next rubric
    #
    lnodes, rnodes = splitWhile(lambda x: x.tagname != 'rubric',
                                indoc[1:])

    out = ElementTree.Element("ADESC", {'title': 'References'})
    para = ElementTree.SubElement(out, 'PARA')
    syntax = ElementTree.SubElement(para, 'SYNTAX')

    for footnote in lnodes:
        # This used to be a footnote but as of CIAO 4.16 it
        # can now be much more.
        #
        if footnote.tagname == 'footnote':
            # Assume the structure is
            # <footnote ids="footnote-1" names="1">
            #   <label>1</label>
            #   <paragraph>Calzetti, Kinney, Storchi-Bergmann, 1994, ApJ, 429, 582
            #     <reference refuri="https://adsabs.harvard.edu/abs/1994ApJ...429..582C">https://adsabs.harvard.edu/abs/1994ApJ...429..582C</reference>
            #   </paragraph>
            # </footnote>
            #
            # Or
            #
            # <footnote ids="footnote-1" names="1">
            #   <label>1</label>
            #   <paragraph>
            #     <reference refuri="https://heasarc.gsfc.nasa.gov/xanadu/xspec/manual/XSmodelEdge.html">https://heasarc.gsfc.nasa.gov/xanadu/xspec/manual/XSmodelEdge.html</reference>
            #   </paragraph>
            # </footnote>
            #
            # Or
            #
            # <footnote ids="footnote-1" names="1">
            #   <label>1</label>
            #   <paragraph>
            #     <reference refuri="https://heasarc.gsfc.nasa.gov/xanadu/xspec/manual/XSabund.html">https://heasarc.gsfc.nasa.gov/xanadu/xspec/manual/XSabund.html</reference>\nNote that this may refer to a newer version than the\ncompiled version used by Sherpa; use <title_reference>get_xsversion</title_reference> to\ncheck.
            #   </paragraph>
            # </footnote>'
            #

            assert len(footnote) == 2, (len(footnote), str(footnote))
            assert footnote[0].tagname == "label", str(footnote[0])
            assert footnote[1].tagname == "paragraph", str(footnote[1])

            line = ElementTree.SubElement(syntax, 'LINE')

            # strip out the paragraph text from the reference URI
            # Assume @refuri is the same as the text contents of reference
            #
            if len(footnote[1]) == 2:
                # Assume we have text and a reference URI
                assert footnote[1][1].astext().startswith("http"), footnote[1][1]

                href = ElementTree.SubElement(line, 'HREF')
                href.text = f"[{footnote[0].astext()}] {footnote[1][0].astext()}"
                href.set("link", footnote[1][1].astext())

            elif len(footnote[1]) == 1:

                # Do we have a URL?
                l = footnote[0].astext()
                r = footnote[1].astext()
                if r.startswith("http"):
                    href = ElementTree.SubElement(line, 'HREF')
                    href.text = f"[{l}]"
                    href.set("link", r)

                else:
                    line.text = f"[{l}] {r}"

            elif footnote[1][0].tagname == "reference" and \
                 footnote[1][0].get("refuri").startswith("http"):

                refuri = footnote[1][0].get("refuri")

                # Need to add extra text, that may itself contain things
                # that need further processing.
                #
                href = ElementTree.SubElement(line, 'HREF')

                if footnote[1][0].astext() == refuri:
                    href.text = f"[{footnote[0].astext()}]"
                else:
                    href.text = f"[{footnote[0].astext()}] {footnote[1][0].astext()}"

                href.set("link", refuri)

                # Add in the extra text (for now no post-processing).
                #
                dump = "".join(footnote[1][idx].astext()
                               for idx in range(1, len(footnote[1])))
                href.tail = dump

            else:
                assert False, ("footnote structure", len(footnote[1]),
                               str(footnote))

        elif footnote.tagname == 'paragraph':
            # Assume the structure is
            #  <paragraph>
            #    <reference name="K. A. Arnaud, I. M. George & A. F. Tennant, "The OGIP Spectral File Format"" refuri="https://heasarc.gsfc.nasa.gov/docs/heasarc/ofwg/docs/spectra/ogip_92_007/ogip_92_007.html">K. A. Arnaud, I. M. George & A. F. Tennant, "The OGIP Spectral File Format"
            #     </reference>
            #     <target ids="['k-a-arnaud-i-m-george-a-f-tennant-the-ogip-spectral-file-format']" names="['k. a. arnaud, i. m. george & a. f. tennant, "the ogip spectral file format"']" refuri="https://heasarc.gsfc.nasa.gov/docs/heasarc/ofwg/docs/spectra/ogip_92_007/ogip_92_007.html"/>
            #  </paragraph>
            #

            assert len(footnote) == 2, (len(footnote), str(footnote))
            assert footnote[0].tagname == "reference", ("REFERENCE", str(footnote))
            assert footnote[1].tagname == "target", ("TARGET", str(footnote))

            assert footnote[0].get("refuri").startswith("http"), ("URI", footnote[0].get("refuri"))

            line = ElementTree.SubElement(syntax, 'LINE')
            href = ElementTree.SubElement(line, 'HREF')
            href.text = footnote[0].astext()
            href.set("link", footnote[0].get("refuri"))

        elif footnote.tagname == "citation":
            # Assume the structure is
            #    <citation ids= names=>  -- ignore these attributes
            #      <label>...</label>
            #      <paragraph>
            #        <reference refurl=>...</reference>
            #      </paragraph>
            #    </citation>
            #
            assert len(footnote) == 2, (len(footnote), str(footnote))
            assert footnote[0].tagname == "label", str(footnote[0])
            assert footnote[1].tagname == "paragraph", str(footnote[1])
            assert footnote[1].astext().startswith("http"), footnote[1]

            line = ElementTree.SubElement(syntax, 'LINE')
            href = ElementTree.SubElement(line, 'HREF')
            href.text = footnote[0].astext()
            href.set("link", footnote[1].astext())

        elif footnote.tagname == "enumerated_list":
            # Assume structure is
            # <enumerated_list enumtype="arabic" prefix="" suffix=".">
            #  <list_item>
            #   <paragraph>
            #    <reference name="Cash, W. ..." refuri="...">Cash, W. ...</reference>
            #    <target ids="['cash-w-parameter-estimation-in-astronomy-through-application-of-the-likelihood-ratio-apj-vol-228-p-939-947-1979']" names="['cash, w. "parameter estimation in astronomy through application of the likelihood ratio", apj, vol 228, p. 939-947 (1979).']" refuri="https://adsabs.harvard.edu/abs/1979ApJ...228..939C"/>
            #   </paragraph>
            #  </list_item>
            #  <list_item>
            #    ..
            #  </list_item>
            # </enumerated_list>
            #
            # A paragraph may not have a reference item
            #
            for subelem in footnote:
                assert subelem.tagname == "list_item", (subelem.tagname,
                                                        str(subelem))

                assert subelem[0].tagname == "paragraph", subelem
                para = subelem[0]

                line = ElementTree.SubElement(syntax, 'LINE')

                if para[0].tagname == "reference":
                    reference = para[0]
                    assert reference.get("refuri").startswith("http"), reference

                    href = ElementTree.SubElement(line, 'HREF')
                    href.text = reference.astext()
                    href.set("link", reference.get("refuri"))

                else:
                    assert len(para) == 1, len(para)

                    # Assume this is correct
                    line.text = para.astext()

        else:
            assert False, (footnote.tagname, str(footnote))

    return out, rnodes


# this does not extend across a newline
SHERPA_MODEL_SETTING_RE = re.compile(r">>> (.+) = sherpa.models\.[^\(]+\.([A-Z][a-zA-Z0-9]+)()")
SHERPA_XSMODEL_SETTING_RE = re.compile(">>> (.+) = XS([a-zA-Z0-9]+)()")
SHERPA_MODELS_RE = re.compile(r"(.+)sherpa.models\.[^\(]+\.([A-Z][a-zA-Z0-9]+)(.+)")


def cleanup_sherpa_model_setting(txt):
    """Convert >>> mdl = sherpa.models.xxx.Foo() to >>> foo.mdl

    This should be called before cleanup_sherpa_models
    """

    def convert(intxt):
        m = re.match(SHERPA_MODEL_SETTING_RE, intxt)
        if m is None:
            return intxt

        out = f'>>> {m[2].lower()}.{m[1]}'
        # dbg(intxt + ' :: ' + out, info='SETTING')
        return out

    out = []
    for line in txt.split('\n'):
        out.append(convert(line))

    return '\n'.join(out)


def cleanup_sherpa_xsmodel_setting(txt):
    """Convert >>> mdl = XSfoo() to >>> xsfoo.mdl

    This should be called before cleanup_sherpa_models
    """

    def convert(intxt):
        m = re.match(SHERPA_XSMODEL_SETTING_RE, intxt)
        if m is None:
            return intxt

        out = f'>>> xs{m[2].lower()}.{m[1]}'
        # dbg(intxt + ' :: ' + out, info='XSSETTING')
        return out

    out = []
    for line in txt.split('\n'):
        out.append(convert(line))

    return '\n'.join(out)


def cleanup_sherpa_models(txt):
    """Convert sherpa.models.xxx.Foo( to foo("""

    def convert(intxt):
        m = re.match(SHERPA_MODELS_RE, intxt)
        if m is None:
            return intxt

        txt = m[1] + m[2].lower() + m[3]
        out = convert(txt)
        # dbg(intxt + ' :: ' + out, info='RENAME')
        return out

    out = []
    for line in txt.split('\n'):
        out.append(convert(line))

    return '\n'.join(out)


def convert_example_text(txt):
    """Apply any expected conversions for example text.

    Parameters
    ----------
    txt : str
        The input text

    Returns
    -------
    converted : str
        The converted text.

    Notes
    -----
    Conversions are:
        >>> mdl = sherpa.models.xxx.FooBar3D() -> >>> foobar3d.mdl()
        >>> mdl = XSfoo() -> >>> xsfoo.mdl
        sherpa.models.xxx.FooBar3D( -> foobar3d(

    """

    txt = cleanup_sherpa_model_setting(txt)
    txt = cleanup_sherpa_xsmodel_setting(txt)
    txt = cleanup_sherpa_models(txt)

    return txt


def find_examples(indoc):
    """Return the examples section, if present, and the remaining document.

    Parameters
    ----------
    indoc : list of nodes
        The document.

    Returns
    -------
    examples, remaining : Element or None, list of nodes
        A QEXAMPLELIST block and the remaining nodes.

    Notes
    -----
    The base is text + examples. There's some support to handle multiple
    text + example blocks, but it is very hacky.

    The example text has to be parsed to

       convert model names to lower case and the UI
         approach (XSapec() -> xspec.mdl)
       remove namespace identifiers (e.g. sherpa.models.basic)

    """

    if len(indoc) == 0:
        return None, indoc

    node = indoc[0]

    # TODO: should this use isinstance instead?
    if node.tagname != 'rubric':
        return None, indoc

    # Support Example as well as Examples
    txt = node.astext().strip()
    if txt not in ['Examples', 'Example']:
        return None, indoc

    if txt == 'Example':
        msg = " - has an Example, not Examples, block"
        dbg(msg)

    # look for the next rubric
    #
    lnodes, rnodes = splitWhile(lambda x: x.tagname != 'rubric',
                                indoc[1:])

    out = ElementTree.Element("QEXAMPLELIST")

    # Split the example section up into examples. Use several heuristics.
    #
    # Expect an example to be optional text blocks then code. However,
    # if we have code block, text block where text starts with lower case,
    # code block then this is all part of the same example. An example
    # of this last case is 'ignore2d'.
    #
    # Note: I could make a code-only examples use the SYNTAX block
    #       but for now do not bother with this
    #
    desc = None
    for para in lnodes:

        # some repeated checks here and in make_para_blocks
        #
        name = para.tagname
        assert name in ['paragraph', 'doctest_block',
                        'block_quote', 'literal_block',
                        'bullet_list'  # integrate1d in CIAO 4.14
                        ], para

        if desc is None:
            # Can we identify a sentence that is actually
            # part of the previous example?
            #
            if name == 'paragraph' and len(out) >= 1 and \
               para.astext()[0].islower():
                qex = out[-1]
                assert qex.tag == 'QEXAMPLE'
                desc = qex[-1]
                assert desc.tag == 'DESC'

            else:
                example = ElementTree.SubElement(out, 'QEXAMPLE')
                desc = ElementTree.SubElement(example, 'DESC')

        for p in make_para_blocks(para):

            # We could try to edit the text before conversion, but
            # it's easier to do here, if uglier.
            #
            assert isinstance(p, ElementTree.Element)

            if p.tag in ['PARA', 'VERBATIM']:
                p.text = convert_example_text(p.text)

            elif p.tag == 'LIST':
                for item in p:
                    item.text = convert_example_text(item.text)

            else:
                raise RuntimeError(f"Did not expect {p.tag} in example text")

            desc.append(p)

        # Do we start a new example?
        #
        if name not in ['paragraph', 'bullet_list']:
            desc = None

    return out, rnodes


# assume minimum-length to avoid removing valid text
#    0x7ff6d11ee660
HEX_PAT = re.compile('0x[0-9a-f]{8,16}')

def remove_address(arg: str) -> str:
    """Replace 0xHEX by 0x..."""

    return re.sub(HEX_PAT, '0x...', arg)


def annotate_type(ann) -> str:
    """There must be an easier way to do this"""

    if ann is None:
        return 'None'

    def check(val):
        return issubclass(type(ann), val)

    def clean(arg):
        """Remove all occurrences of 'typing.'"""
        out = str(arg)
        return out.replace('typing.', '')

    # Ugh - these checks are both annoying and awkward and I don't
    # have the time to step back and go "this is the wrong way to do
    # this".
    #
    if ann == type(None):
        return 'None'

    if ann == typing.Any:
        return 'Any'

    # Check we catch this correctly
    if ann == typing.Callable:
        return clean(ann)

    if type(ann) == typing._UnionGenericAlias:
        # Try to replace Union[a, b, ...] with a | b | ...
        # but this relies on me understanding the setup here,
        # which I don't!
        #
        args = [annotate_type(arg) for arg in ann.__args__]
        return " | ".join(args)

    if type(ann) in [types.UnionType, types.GenericAlias,
                     typing._GenericAlias,
                     typing._CallableGenericAlias]:
        return clean(ann)

    if issubclass(ann, (bool, int, float, str)):
        return ann.__name__

    if issubclass(ann, (Data, FitResults, Model, MultiPlot, OptMethod,
                        Stat)):
        return ann.__name__

    raise ValueError(f"Unknown annotation {type(ann)} '{ann}'")
    # return 'UNKNOWN'


def split_sig(name: str, sig: Signature) -> list[str]:
    """Do we split up a signature?"""

    # Assume we have
    #    symbol(par1[: ...][ = ...], ...)[ -> ...]
    #
    # We want to break in          ^
    # but there can be commas in the type or default value
    #
    out = []

    spacer = "   "
    current = f"{spacer}{name}("
    namelen = len(name) + len(spacer)
    indent = " " * (namelen + 1)
    first = True
    for pname, par in sig.parameters.items():
        if first:
            first = False
        else:
            out.append(current + ",")
            current = indent

        current += pname
        if par.annotation != inspect._empty:
            # print(f"{pname} --> {par.annotation}  {type(par.annotation)}")  # DBG
            current += ": " + annotate_type(par.annotation)

        if par.default != inspect._empty:
            current += f" = {remove_address(repr(par.default))}"

    # If there's no return annotation we can just end the current
    # item with ")" and leave.
    #
    if sig.return_annotation == inspect._empty:
        current += ")"
        out.append(current)
        return out

    # print(f"return --> {sig.return_annotation}  {type(sig.return_annotation)}")  # DBG
    retval = ") -> " + annotate_type(sig.return_annotation)

    if first:
        # No arguments, so include the output annotation
        #
        current += retval
        out.append(current)
        return out

    # Multiple arguments so place the return annotation on a new line
    # (and indent one less than indent so that matches opening bracket).
    #
    out.append(current)
    current = ' ' * namelen + retval
    out.append(current)
    return out


def add_syntax_as_para(adesc, name: str, sig: Signature):
    "Add information about the sig to the parameters block."

    p = ElementTree.SubElement(adesc, 'PARA')
    p.text = 'The types of the arguments are:'

    # Use a VERBATIM block to make the spacing work out.
    #
    out = ElementTree.SubElement(adesc, 'VERBATIM')
    out.text = "\n".join(split_sig(name, sig))


def extract_params(fieldinfo,
                   name: str,
                   sig: Signature | None = None):
    """Extract the parameter information from a fieldlist.

    We used to use paragraphs, but now use a table for the
    parameter/attribute values.

    The sig argument is currently unused as for CIAO 4.17 it
    was felt to add no extra inforamtion to the fieldinfo
    data. This can be reviewed for 4.18.

    """

    if fieldinfo is None:
        return None

    parinfo = fieldinfo['params']
    retinfo = fieldinfo['returns']

    is_attrs = any(['ivar' in p for p in parinfo])

    nparams = len(parinfo)
    nret = len(retinfo)
    if nparams == 0 and nret == 0:
        assert len(fieldinfo['raises']) != 0
        # msg = " - looks like only has a raises block, so skipping"
        # dbg(msg)
        return None

    if is_attrs:
        funcname = 'object'
        value = 'attribute'
    else:
        funcname = 'function'
        value = 'parameter'

    # For now only handle the simple case for the return values
    #
    rvals = [r[1] for r in retinfo if r[0] == 'returns']
    assert len(rvals) < 2, retinfo
    if len(rvals) > 0:
        assert rvals[0].tagname == 'field_body'

        # If their is no text (other than the name of the return value)
        # then skip it. I hope this is sufficient
        #
        if len(astext(rvals[0][0]).strip().split()) == 1:
            return_value = None
        else:
            return_value = convert_field_body(rvals[0])

    else:
        return_value = None

    # If there are no parameters and no return value we can return now
    #
    if nparams == 0 and return_value is None:
        dbg('No parameters or return value', info='INFO')
        return None

    adesc = ElementTree.Element("ADESC",
                                {'title': f'{value.upper()}S'})

    # For CIAO 4.17 we do not add this information.
    #
    # if sig is not None:
    #     add_syntax_as_para(adesc, name, sig)

    p = ElementTree.SubElement(adesc, 'PARA')
    if nparams == 0:
        p.text = f'This {funcname} has no {value}s'
    elif nparams == 1:
        p.text = f'The {value} for this {funcname} is:'
    else:
        p.text = f'The {value}s for this {funcname} are:'

    if nparams > 0:
        tbl = ElementTree.SubElement(adesc, 'TABLE')

        # We could directly query the signature for information
        # on the default values.
        #

        # Do we have any "type" information?
        #
        has_type = False
        for par in parinfo:
            if 'type' in par:
                has_type = True
                break

        # add a fake first row to set up the headers
        #
        row0 = ElementTree.SubElement(tbl, 'ROW')
        ElementTree.SubElement(row0, 'DATA').text = value.capitalize()
        if has_type:
            ElementTree.SubElement(row0, 'DATA').text = 'Type information'
        ElementTree.SubElement(row0, 'DATA').text = 'Definition'

        for par in parinfo:

            row = ElementTree.SubElement(tbl, 'ROW')
            ElementTree.SubElement(row, 'DATA').text = par['name']

            # Keys are name, param, and type.
            #          name, ivar
            #
            if has_type:
                try:
                    tinfo = par['type']
                    conv = convert_field_body(tinfo)
                    txt = conv.text
                except KeyError:
                    txt = ''

                ElementTree.SubElement(row, 'DATA').text = txt

            if 'param' in par:
                block = convert_field_body(par['param'])
                text = block.text

            elif 'ivar' in par:
                block = convert_field_body(par['ivar'])
                text = block.text

            else:
                # Not description, so an empty paragraph.
                text = ''

            ElementTree.SubElement(row, 'DATA').text = text

    if return_value is None:
        return adesc

    p = ElementTree.SubElement(adesc, 'PARA', {'title': 'Return value'})
    p.text = 'The return value from this function is:'
    adesc.append(return_value)
    return adesc


def create_seealso(name, seealso, symbol=None):
    """Come up with the seealsogroups metadata.

    Parameters
    ----------
    name : str
        The name of the symbol being documented.
    seealso : list of str
        The symbols that have been manually selected as being related
        to name.
    symbol
        The symbol to document (e.g. sherpa.astro.ui.load_table or
        sherpa.astro.ui.xsapec) or None.

    Returns
    -------
    seealso, displayseealso : str, str
        The proposed seealsogroup and displayseealsogroup settings
        in the ahelp file.

    Notes
    -----
    The idea is to create pairs of tokens (name, s) where s is each
    element of seealso, so that ahelp can match the two. This could be
    changed to handle all routines, but we do not have a symmetrical
    relationship in the manual "See Also" sections, so this would miss
    out. It may be that we need to use displayseealsogroup instead;
    let's see.

    I could restrict this to only those symbols that aren't connected
    by the seealso grouping from the original ahelp files, but I
    have not the energy to try that.

    We add in displayseealso entries for Sherpa and XSPEC models
    (to shmodels and xsmodels respectively). It doesn't seem to be
    that useful.
    """

    def mkmodels():
        if symbol is None:
            return ''

        if not isinstance(symbol, ModelWrapper):
            return ''

        if issubclass(symbol.modeltype,
                          (XSAdditiveModel, XSMultiplicativeModel, XSConvolutionKernel)):
            mdls = 'xs'
        else:
            mdls = 'sh'

        return f'{mdls}models'

    dsg = mkmodels()

    if seealso is None:
        if dsg == '':
            msg = f"- {name} has no SEE ALSO"
            dbg(msg)
        return '', dsg

    # remove case and sort lexicographically.
    #
    def convert(t1, t2):
        if t1 < t2:
            return f"{t1}{t2}"

        return f"{t2}{t1}"

    nlower = name.lower()
    pairs = [convert(nlower, s.lower()) for s in seealso]

    # Sort the pairs to ensure ordering
    pairs.sort()

    out = ' '.join(pairs)
    return out, dsg


def find_context(name, symbol=None):
    """What is the ahelp context for this symbol?

    If we can not find a context, use sherpaish so that it can
    be easily identified.

    Parameters
    ----------
    name : str
    symbol
        The symbol to document (e.g. sherpa.astro.ui.load_table or
        sherpa.astro.ui.xsapec) or None.

    Returns
    -------
    context : str

    """

    if symbol is not None:
        if isinstance(symbol, ModelWrapper):
            return 'models'

    # Hard code some values: the CIAO 4.10 contexts for Sherpa are
    #
    #   confidence
    #   contrib
    #   data
    #   filtering
    #   fitting
    #   info
    #   methods
    #   modeling
    #   models
    #   plotting
    #   psfs
    #   saving
    #   sherpa
    #   statistics
    #   utilities
    #   visualization
    #
    # NOTE: some of these should get picked up from ahelp files
    #       (ie this is unneeded)
    #
    if name in ['get_conf_results', 'get_confidence_results',
                'get_conf_opt',
                'get_covar_results', 'get_covar_opt',
                'get_proj_results', 'get_proj_opt']:
        return 'confidence'

    if name.startswith('get_method'):
        return 'methods'

    if name in ['fit_bkg', 'get_fit_results']:
        return 'fitting'

    if name in ['ignore2d_image', 'notice2d_image']:
        return 'filtering'

    if name in ['get_bkg_model', 'get_bkg_source',
                'get_model_pars', 'get_model_type',
                'get_num_par_frozen', 'get_num_par_thawed',
                'get_xsabund',
                'get_xscosmo',
                'get_xsxsect',
                'get_xsxset',
                'load_template_interpolator',
                'load_xstable_model',
                'get_xschatter', 'set_xschatter',
                'set_bkg_full_model']:
        return 'modeling'

    if name in ['get_sampler_name', 'get_sampler_opt',
                'get_stat_name']:
        return 'statistics'

    if name.startswith('plot_') or name.find('_plot') != -1:
        return 'plotting'

    if name.startswith('group') or \
       name in ['create_arf', 'create_rmf',
                'get_bkg_arf', 'get_bkg_rmf',
                'load_ascii_with_errors',
                'resample_data']:
        return 'data'

    if name in ['multinormal_pdf', 'multit_pdf']:
        return 'utilities'

    if name in ['get_data_contour', 'get_data_contour_prefs',
                'get_data_image', 'get_fit_contour',
                'get_kernel_contour', 'get_kernel_image',
                'get_model_contour', 'get_model_contour_prefs',
                'get_model_image',
                'get_psf_contour', 'get_psf_image',
                'get_ratio_contour', 'get_ratio_image',
                'get_resid_contour', 'get_resid_image',
                'get_source_contour', 'get_source_image']:
        return 'visualization'

    if name in ['get_functions', 'list_pileup_model_ids',
                'list_psf_ids']:
        return 'info'

    if name == 'delete_pileup_model':
        return 'model'

    return 'sherpaish'


def merge_metadata(xmlattrs, metadata=None):
    """Combine metadata from the ahelp file and docstring.

    Parameters
    ----------
    xmlattrs : dict
        The structure of the metadata, assumed to be taken from
        the docstring. It is required to have an entry for
        all entries.
    metadata : dict, optional
        The return of find_metadata

    Returns
    -------
    attrs : dict
        The combined metadata. Individual values may be combined
        or over-ridden by the metadata value.

    """

    xmlattrs = xmlattrs.copy()

    def append_values(k, v):
        """Attend space-separated values"""

        vals = xmlattrs[k].split() + v.split()
        newvals = sorted(list(set(vals)))
        return ' '.join(newvals)

    if metadata is not None:
        for k, v in metadata.items():

            assert k in xmlattrs

            # So we over-write or append?
            #
            if k in ['seealsogroups', 'displayseealsogroups', 'refkeywords']:
                xmlattrs[k] = append_values(k, v)
            else:
                xmlattrs[k] = v

    return xmlattrs


def convert_docutils(name: str,
                     doc,
                     sig: str,
                     # annotated_sig=None,
                     actual_sig: Signature | None = None,
                     symbol=None, metadata=None, synonyms=None,
                     dtd='ahelp'):
    """Given the docutils documentation, convert to ahelp DTD.

    Parameters
    ----------
    name : str
    doc
        The document (restructured text)
    sig : str or None
        The signature of the name (will be over-ridden by the
        document, if given).
    annotated_sig
        The annotation signature, if present.
    actual_sig : Signature
        The annotated signature object.
    symbol
        The symbol to document (e.g. sherpa.astro.ui.load_table or
        sherpa.astro.ui.xsapec) or None.
    metadata : dict or None, optional
        The AHELP metadata for this file (the return value of
        parsers.ahelp.find_metadata).
    synonmys : list of str or None
        The synonyms available for this symbol. It is expected that,
        if given, the array has one element but do not require it
        (but the array must not be empty if given).
    dtd : {'ahelp', 'sxml'}, optional
        The DTD to use.

    Returns
    -------
    ahelp
        The ahelp version of the documentation.

    Notes
    -----
    Should synonyms be added to the SYNTAX block?

    At the moment there is limited support for the "sxml" DTD - i.e.
    all that is changed is the top element; there is no attempt to
    take advantage of the extra features that the cxcdocumentationpage
    DTD affords.
    """

    if dtd not in ['ahelp', 'sxml']:
        raise ValueError("Unrecognized dtd value")

    assert synonyms is None or len(synonyms) > 0, synonyms

    # used to parse the versionadded/changed tags
    reset_stored_versions()

    # Basic idea is parse, augment/fill in, and then create the
    # ahelp structure, but it is likely this is going to get
    # confused.
    #
    nodes = list(doc)
    syntax, nodes = find_syntax(name, sig, nodes)
    synopsis, refkeywords, nodes = find_synopsis(nodes)
    desc, nodes = find_desc(nodes, synonyms=synonyms)

    # For XSPEC models, add a note about
    # additive/multiplicative/convolution to the SYNTAX block (could
    # go in the description but let's try here for now).
    #
    if isinstance(symbol, ModelWrapper) and \
       issubclass(symbol.modeltype, (XSAdditiveModel, XSMultiplicativeModel, XSConvolutionKernel)):
        assert syntax is not None

        add_xspec_model_to_syntax(syntax, name, symbol)

    # Can have parameters and then a "raises" section, or just one,
    # or neither. Really they should both be before the See Also
    # block (are they automatically merged in this case?),
    # but that is not currently guaranteed (e.g. fake_pha)
    #
    # Note that I have edited fake_pha and plot_pvalue so that
    # fieldlist2 should now always be None, but this has not
    # yet made it into the distribution. So the assumption is
    # to skip fieldlist2 if set, but should probably have some
    # safety check to warn if it shouldn't be (i.e. contents are
    # not a raises block), and we also need to remove raises
    # from fieldlist1, as this isn't wanted for ahelp.
    #
    # ^^^ The paragraph above needs reviewing for CIAO 4.12
    #
    fieldlist1, nodes = find_fieldlist(nodes)

    warnings, nodes = find_warning(nodes)

    seealso, nodes = find_seealso(nodes)

    fieldlist2, nodes = find_fieldlist(nodes)

    if fieldlist2 is not None:
        dbg("- ignoring section fieldlist")

    # This has been separated fro the extraction of the field list
    # to support experimentation.
    #
    params = extract_params(fieldlist1, name, actual_sig)

    # Do we want to include the parameter overview in the syntax
    # block? We used to, but let's try to just have those in the
    # params block.
    #
    # add_pars_to_syntax(syntax, fieldlist1)

    # support see-also here
    #
    if seealso is None:
        seealso, nodes = find_seealso(nodes)
        if seealso is not None:
            msg = "- seealso is in wrong place"
            dbg(msg)

    notes, nodes = find_notes(name, nodes)

    # hack to merge notes if duplicate (seen in testing; should be fixed
    # in the docstring)
    #
    notes2, nodes = find_notes(name, nodes)
    if notes2 is not None:
        msg = "multiple NOTES sections"
        dbg(msg, info='ERROR')

    refs, nodes = find_references(nodes)
    examples, nodes = find_examples(nodes)

    # Do we augment the examples?
    #
    examples = augment_examples(examples, symbol)

    if refs is None:
        refs, nodes = find_references(nodes)
        if refs is not None:
            msg = "References after EXAMPLES"
            dbg(msg)

    # assert nodes == [], nodes
    if nodes != []:
        dbg(f"ignoring trailing:\n{nodes}", info='WARN')
        return nodes

    # Augment the blocks
    #
    if syntax is None:
        # create the syntax block
        dbg(f"does {name} need a SYNTAX block?", info='TODO')

    # Try and come up with an automated 'See Also' solution
    #
    seealsotags, displayseealsotags = create_seealso(name, seealso, symbol=symbol)

    # Do we have versionadded/changed data?
    #
    # stick them into a single ADESC block
    versioninfo = ElementTree.Element('ADESC')
    versioninfo.set('title', 'Changes in CIAO')

    for key in store_versions.keys():
        assert key in ['versionadded', 'versionchanged', 'titles'], key

    # assume the versionchanged is in descending numerical order
    # so we display the latest version first, and end up with the
    # version-added information.
    #
    # There's a hack for a CIAO 4.14 case where we have both a added and changed for 4.14,
    # since in this case we can drop the changed info
    #
    added = 0

    # This is hard-coded to the cases I know about
    skippy1 = [p.get('title') == 'Changed in CIAO 4.14' for p in store_versions['versionchanged']]
    skippy2 = [p.get('title') == 'New in CIAO 4.14' for p in store_versions['versionadded']]
    if any(skippy1) and any(skippy2):
        if name not in ['xsagnslim', 'xsbwcycl', 'xszkerrbb']:
            raise RuntimeError("problem")

        store_versions['versionchanged'] = []

    for p in store_versions['versionchanged']:
        versioninfo.append(p)
        added += 1

    for p in store_versions['versionadded']:
        versioninfo.append(p)

        # special case the Voigt1D / PseudoVoigt1D models for CIAO 4.13
        #
        if name in ['pseudovoigt1d', 'voigt1d']:
            assert p.text is None
            p.text = 'The pseudovoigt1d and voigt1d models were added in CIAO 4.13 ' + \
                     'and replace the absorptionvoigt and emissionvoigt models.'

        added += 1

    if added == 0:
        versioninfo = None

    # Ensure we don't come across any more versionxxx tags
    # - although now we've changed the processing it isn't
    #   really useful
    store_versions['DONE'] = []

    # Create the output
    #
    rootname = None
    if dtd == 'ahelp':
        rootname = 'cxchelptopics'
    elif dtd == 'sxml':
        rootname = 'cxcdocumentationpage'
    else:
        raise RuntimeError(f'unknown dtd={dtd}')

    root = ElementTree.Element(rootname)
    outdoc = ElementTree.ElementTree(root)

    # These should now be included
    """
    # Special case the refkeywords for [pseudo]voigt1d
    #
    if name in ['pseudovoigt1d', 'voigt1d']:
        refkeywords.add('absorptionvoigt')
        refkeywords.add('emissionvoigt')
        refkeywords.add('absorption')
        refkeywords.add('emission')

    # Special case the ahelp files that used to contain "multiple"
    # commands - this is not all of them but these ones no-longer
    # exist so I want to retain the knowledge for anyone used to
    # 'ahelp get_fit'.
    #
    for oname in ['get_fit', 'get_kernel', 'get_ratio', 'get_resid']:
        if name.startswith(f'{oname}_'):
            refkeywords.add(oname)
    """

    # special case a few of the new XSPEC models
    #
    if name == 'xszkerrbb':
        refkeywords.add('kerrbb')
        refkeywords.add('xskerrbb')

    refkeywords = sorted(list(refkeywords))

    # so plot_bkg_ratio gets split to 'plot', 'bkg', 'ratio'
    if '_' in name:
        refkeywords += name.split('_')

    xmlattrs = merge_metadata({'pkg': 'sherpa',
                               'key': name,
                               'refkeywords': ' '.join(refkeywords),
                               'seealsogroups': seealsotags,
                               'displayseealsogroups': displayseealsotags,
                               'context': None},
                              metadata)

    if xmlattrs['context'] is None:
        context = find_context(name, symbol)
        xmlattrs['context'] = context
        if context == 'sherpaish':
            dbg(f"- fall back context=sherpaish for {name}")

    # Add in any synonyms to the refkeywords (no check is made to
    # see if they are already there).
    #
    if synonyms is not None:
        xmlattrs['refkeywords'] = ' '.join(synonyms) + ' ' + \
                                  xmlattrs['refkeywords']

    entry = ElementTree.SubElement(root, 'ENTRY', xmlattrs)

    for n in [synopsis, syntax, desc, examples, params,
              warnings, notes, notes2, refs, versioninfo]:
        if n is None:
            continue

        entry.append(n)

    # Add the "standard" postamble.
    #
    # VERY HACKY way to determine talking about an XSPEC routine
    #
    if name.find('xs') != -1:
        xspec = ElementTree.SubElement(entry, 'ADESC',
                                       {'title': 'XSPEC version'})
        xpara = ElementTree.SubElement(xspec, 'PARA')
        xpara.text = f'{CIAOVER} comes with support for version ' + \
                     f'{XSPECVER} of the XSPEC models. This can be ' + \
                     'checked with the following:'

        cstr = "% python -c 'from sherpa.astro import xspec; " + \
               "print(xspec.get_xsversion())'"

        xpara2 = ElementTree.SubElement(xspec, 'PARA')
        xsyn = ElementTree.SubElement(xpara2, 'SYNTAX')
        ElementTree.SubElement(xsyn, 'LINE').text = cstr
        ElementTree.SubElement(xsyn, 'LINE').text = XSPECVER

    bugs = ElementTree.SubElement(entry, 'BUGS')
    para = ElementTree.SubElement(bugs, 'PARA')
    para.text = 'See the '
    attrs = {'link': 'https://cxc.harvard.edu/sherpa/bugs/'}
    link = ElementTree.SubElement(para, 'HREF', attrs)
    link.text = 'bugs pages on the Sherpa website'
    link.tail = ' for an up-to-date listing of known bugs.'

    ElementTree.SubElement(entry, 'LASTMODIFIED').text = LASTMOD

    return outdoc
