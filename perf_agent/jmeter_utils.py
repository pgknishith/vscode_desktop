"""Lightweight JMX manipulation utilities.

This module provides small helpers to generate and modify simple JMX files
for parameterization (CSV Data Set Config), basic correlation (Regex Extractor),
and timers (Constant Timer).

Note: These utilities produce minimal JMX fragments suitable for programmatic
editing. For production-grade JMX editing prefer using JMeter GUI or a robust
XML template that matches the JMeter version you target.
"""
from xml.etree import ElementTree as ET
from xml.dom import minidom
from typing import List, Optional


def _prettify(elem: ET.Element) -> str:
    rough_string = ET.tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent='  ')


def _testplan_children_hashTree(root: ET.Element) -> ET.Element:
    """Return the hashTree that contains the TestPlan's children (creates if missing)."""
    parent = root.find('hashTree')
    if parent is None:
        raise RuntimeError('Malformed JMX: missing root hashTree')
    children_ht = parent.find('hashTree')
    if children_ht is None:
        children_ht = ET.SubElement(parent, 'hashTree')
    return children_ht


def create_jmx_template(test_name: str = 'Perf Test') -> ET.ElementTree:
    """Create a minimal JMeter Test Plan XML tree.

    Returns an ElementTree object representing the JMX.
    """
    root = ET.Element('jmeterTestPlan', {
        'version': '1.2',
        'properties': '5.0',
        'jmeter': '5.4.1'
    })

    hashTree = ET.SubElement(root, 'hashTree')

    testPlan = ET.SubElement(hashTree, 'TestPlan', {'guiclass': 'TestPlanGui', 'testclass': 'TestPlan', 'testname': test_name})
    ET.SubElement(testPlan, 'stringProp', {'name': 'TestPlan.comments'})
    ET.SubElement(testPlan, 'boolProp', {'name': 'TestPlan.functional_mode'}).text = 'false'
    ET.SubElement(testPlan, 'boolProp', {'name': 'TestPlan.serialize_threadgroups'}).text = 'false'

    ET.SubElement(hashTree, 'hashTree')

    return ET.ElementTree(root)


def save_jmx(tree: ET.ElementTree, path: str) -> None:
    """Save the ElementTree to path with UTF-8 encoding and pretty formatting."""
    xml = _prettify(tree.getroot())
    with open(path, 'w', encoding='utf-8') as f:
        f.write(xml)


def add_csv_dataset(tree: ET.ElementTree, filename: str, variable_names: List[str], delimiter: str = ',', recycle: bool = True, stop_thread: bool = False) -> None:
    """Add a CSV Data Set Config (parameterization) to the TestPlan level.

    This adds the element under the first hashTree for simplicity.
    """
    root = tree.getroot()
    # place CSV under the TestPlan's children hashTree
    ht = _testplan_children_hashTree(root)

    csv = ET.Element('CSVDataSet', {'guiclass': 'TestBeanGUI', 'testclass': 'CSVDataSet', 'testname': 'CSV Data Set Config'})
    ET.SubElement(csv, 'stringProp', {'name': 'filename'}).text = filename
    ET.SubElement(csv, 'stringProp', {'name': 'fileEncoding'})
    ET.SubElement(csv, 'stringProp', {'name': 'variableNames'}).text = ','.join(variable_names)
    ET.SubElement(csv, 'stringProp', {'name': 'delimiter'}).text = delimiter
    ET.SubElement(csv, 'boolProp', {'name': 'quotedData'}).text = 'false'
    ET.SubElement(csv, 'boolProp', {'name': 'recycle'}).text = 'true' if recycle else 'false'
    ET.SubElement(csv, 'boolProp', {'name': 'stopThread'}).text = 'true' if stop_thread else 'false'

    # append CSV and a following hashTree
    ht.append(csv)
    ht.append(ET.Element('hashTree'))


def add_constant_timer(tree: ET.ElementTree, delay_ms: int, name: Optional[str] = None) -> None:
    """Add a Constant Timer to the TestPlan level (delay in milliseconds)."""
    root = tree.getroot()
    # place default timers under TestPlan children by default
    ht = _testplan_children_hashTree(root)
    timer_name = name or f'Constant Timer {delay_ms}ms'
    timer = ET.Element('ConstantTimer', {'guiclass': 'ConstantTimerGui', 'testclass': 'ConstantTimer', 'testname': timer_name})
    ET.SubElement(timer, 'stringProp', {'name': 'ConstantTimer.delay'}).text = str(delay_ms)

    ht.append(timer)
    ht.append(ET.Element('hashTree'))


def add_regex_extractor(tree: ET.ElementTree, ref_name: str, regex: str, template: str = '$1$', match_number: str = '1', default: str = '') -> None:
    """Add a RegexExtractor (correlation) to the TestPlan level.

    For simplicity it is added at TestPlan level; in real usage you should add
    it under a specific sampler's hashTree.
    """
    root = tree.getroot()
    # place extractor under TestPlan children by default (users can move it under specific samplers)
    ht = _testplan_children_hashTree(root)
    if ht is None:
        raise RuntimeError('Malformed JMX: missing hashTree')

    reg = ET.Element('RegexExtractor', {'guiclass': 'RegexExtractorGui', 'testclass': 'RegexExtractor', 'testname': 'Regex Extractor'})
    ET.SubElement(reg, 'stringProp', {'name': 'RegexExtractor.useHeaders'}).text = 'false'
    ET.SubElement(reg, 'stringProp', {'name': 'RegexExtractor.refname'}).text = ref_name
    ET.SubElement(reg, 'stringProp', {'name': 'RegexExtractor.regex'}).text = regex
    ET.SubElement(reg, 'stringProp', {'name': 'RegexExtractor.template'}).text = template
    ET.SubElement(reg, 'stringProp', {'name': 'RegexExtractor.match_number'}).text = match_number
    ET.SubElement(reg, 'stringProp', {'name': 'RegexExtractor.default'}).text = default

    ht.append(reg)
    ht.append(ET.Element('hashTree'))


def add_thread_group(tree: ET.ElementTree, num_threads: int = 1, ramp_time: int = 1, duration: Optional[int] = None, name: Optional[str] = None) -> None:
    """Add a simple ThreadGroup element at the TestPlan level.

    This is a minimal representation suitable for generating JMX files programmatically.
    """
    root = tree.getroot()
    # place ThreadGroup under TestPlan children hashTree
    ht = _testplan_children_hashTree(root)

    tg_name = name or f'Thread Group ({num_threads})'
    tg = ET.Element('ThreadGroup', {'guiclass': 'ThreadGroupGui', 'testclass': 'ThreadGroup', 'testname': tg_name})
    ET.SubElement(tg, 'stringProp', {'name': 'ThreadGroup.num_threads'}).text = str(num_threads)
    ET.SubElement(tg, 'stringProp', {'name': 'ThreadGroup.ramp_time'}).text = str(ramp_time)
    if duration is not None:
        ET.SubElement(tg, 'stringProp', {'name': 'ThreadGroup.duration'}).text = str(duration)

    ht.append(tg)
    ht.append(ET.Element('hashTree'))


def find_threadgroup_hashTree(root: ET.Element) -> Optional[ET.Element]:
    """Return the hashTree element that follows the last ThreadGroup element.

    We use this to append samplers/assertions under the thread group's hashTree.
    """
    # find all ThreadGroup elements and then locate their following hashTree siblings
    # ThreadGroups are children inside the TestPlan's children hashTree
    parent = root.find('hashTree')
    if parent is None:
        return None
    children_ht = parent.find('hashTree')
    if children_ht is None:
        return None
    tgs = children_ht.findall('ThreadGroup')
    if not tgs:
        return None
    last_tg = tgs[-1]
    # top-level children of the TestPlan-level hashTree are alternating elements and hashTrees
    # look inside TestPlan children hashTree for alternating element/hashTree
    parent = root.find('hashTree')
    if parent is None:
        return None
    children_ht = parent.find('hashTree')
    if children_ht is None:
        return None
    children = list(children_ht)
    for i, child in enumerate(children):
        if child is last_tg and i + 1 < len(children):
            sibling = children[i+1]
            if sibling.tag == 'hashTree':
                return sibling
    return None


def add_sampler_to_last_threadgroup(tree: ET.ElementTree, sampler: ET.Element) -> None:
    """Add a sampler element and its following hashTree under the last ThreadGroup."""
    root = tree.getroot()
    tg_ht = find_threadgroup_hashTree(root)
    if tg_ht is None:
        raise RuntimeError('No ThreadGroup hashTree found to add sampler')
    tg_ht.append(sampler)
    tg_ht.append(ET.Element('hashTree'))


def find_threadgroup_hashTree_by_name(root: ET.Element, tg_name: str) -> Optional[ET.Element]:
    """Return the hashTree element that follows the ThreadGroup with the exact name tg_name."""
    # find ThreadGroup by attribute testname inside TestPlan children hashTree
    parent = root.find('hashTree')
    if parent is None:
        return None
    children_ht = parent.find('hashTree')
    if children_ht is None:
        return None
    children = list(children_ht)
    for i, child in enumerate(children):
        if child.tag == 'ThreadGroup' and (child.get('testname') or '') == tg_name and i + 1 < len(children):
            sibling = children[i+1]
            if sibling.tag == 'hashTree':
                return sibling
    return None


def add_sampler_to_threadgroup(tree: ET.ElementTree, sampler: ET.Element, threadgroup_name: Optional[str] = None) -> None:
    """Add a sampler under a named ThreadGroup (or the last one if name is None)."""
    root = tree.getroot()
    if threadgroup_name:
        tg_ht = find_threadgroup_hashTree_by_name(root, threadgroup_name)
    else:
        tg_ht = find_threadgroup_hashTree(root)
    if tg_ht is None:
        raise RuntimeError('No ThreadGroup hashTree found to add sampler')
    tg_ht.append(sampler)
    tg_ht.append(ET.Element('hashTree'))


def add_http_sampler(tree: ET.ElementTree, name: str, domain: str, port: Optional[int] = None, path: str = '/', method: str = 'GET', protocol: str = 'http') -> None:
    """Add a basic HTTP Sampler (HTTPSamplerProxy) at TestPlan level.

    Parameters are intentionally minimal; extend as needed for headers, body, params.
    """
    root = tree.getroot()
    ht = root.find('hashTree')
    if ht is None:
        raise RuntimeError('Malformed JMX: missing hashTree')

    samp = ET.Element('HTTPSamplerProxy', {'guiclass': 'HttpTestSampleGui', 'testclass': 'HTTPSamplerProxy', 'testname': name})
    ET.SubElement(samp, 'stringProp', {'name': 'HTTPSampler.domain'}).text = domain
    if port is not None:
        ET.SubElement(samp, 'stringProp', {'name': 'HTTPSampler.port'}).text = str(port)
    ET.SubElement(samp, 'stringProp', {'name': 'HTTPSampler.protocol'}).text = protocol
    ET.SubElement(samp, 'stringProp', {'name': 'HTTPSampler.path'}).text = path
    ET.SubElement(samp, 'stringProp', {'name': 'HTTPSampler.method'}).text = method

    # default placeholders for optional parts
    ET.SubElement(samp, 'elementProp', {'name': 'HTTPsampler.Arguments', 'elementType': 'Arguments'})

    ht.append(samp)
    ht.append(ET.Element('hashTree'))


def add_http_sampler_full(tree: ET.ElementTree, name: str, domain: str, port: Optional[int] = None, path: str = '/', method: str = 'GET', protocol: str = 'http', headers: Optional[dict] = None, params: Optional[dict] = None, body: Optional[str] = None, post_type: str = 'raw') -> None:
    """Add an HTTP sampler with optional headers, query params, and body/form data.

    - headers: dict of headerName->value (adds HeaderManager element)
    - params: dict of paramName->value (adds as arguments)
    - body: string for POST/PUT raw body
    - post_type: 'raw' or 'form'
    """
    # create the sampler
    samp = ET.Element('HTTPSamplerProxy', {'guiclass': 'HttpTestSampleGui', 'testclass': 'HTTPSamplerProxy', 'testname': name})
    ET.SubElement(samp, 'stringProp', {'name': 'HTTPSampler.domain'}).text = domain
    if port is not None:
        ET.SubElement(samp, 'stringProp', {'name': 'HTTPSampler.port'}).text = str(port)
    ET.SubElement(samp, 'stringProp', {'name': 'HTTPSampler.protocol'}).text = protocol
    ET.SubElement(samp, 'stringProp', {'name': 'HTTPSampler.path'}).text = path
    ET.SubElement(samp, 'stringProp', {'name': 'HTTPSampler.method'}).text = method

    # add parameters as Arguments (name/value pairs)
    args_el = ET.Element('elementProp', {'name': 'HTTPsampler.Arguments', 'elementType': 'Arguments'})
    collection = ET.SubElement(args_el, 'collectionProp', {'name': 'Arguments.arguments'})
    if params:
        for k, v in params.items():
            arg = ET.SubElement(collection, 'elementProp', {'name': k, 'elementType': 'HTTPArgument'})
            ET.SubElement(arg, 'stringProp', {'name': 'Argument.name'}).text = str(k)
            ET.SubElement(arg, 'stringProp', {'name': 'Argument.value'}).text = str(v)
            ET.SubElement(arg, 'boolProp', {'name': 'HTTPArgument.always_encode'}).text = 'false'

    # attach args to sampler
    samp.append(args_el)

    # add body if provided
    if body is not None:
        ET.SubElement(samp, 'stringProp', {'name': 'HTTPSampler.postBodyRaw'}).text = 'true' if post_type == 'raw' else 'false'
        # add post body as elementProp
        body_el = ET.Element('elementProp', {'name': 'HTTPsampler.PostBody', 'elementType': 'HTTPArgument'})
        ET.SubElement(body_el, 'stringProp', {'name': 'Argument.name'})
        ET.SubElement(body_el, 'stringProp', {'name': 'Argument.value'}).text = body
        ET.SubElement(body_el, 'boolProp', {'name': 'HTTPArgument.always_encode'}).text = 'false'
        samp.append(body_el)

    # add header manager as a child if headers provided
    ht = tree.getroot().find('hashTree')
    if ht is None:
        raise RuntimeError('Malformed JMX: missing hashTree')

    if headers:
        header_manager = ET.Element('HeaderManager', {'guiclass': 'HeaderPanel', 'testclass': 'HeaderManager', 'testname': f'Headers for {name}'})
        coll = ET.SubElement(header_manager, 'collectionProp', {'name': 'HeaderManager.headers'})
        for hk, hv in headers.items():
            he = ET.SubElement(coll, 'elementProp', {'name': hk, 'elementType': 'Header'})
            ET.SubElement(he, 'stringProp', {'name': 'Header.name'}).text = str(hk)
            ET.SubElement(he, 'stringProp', {'name': 'Header.value'}).text = str(hv)
        # append sampler and header manager with their hashTrees
        ht.append(samp)
        ht.append(ET.Element('hashTree'))
        ht.append(header_manager)
        ht.append(ET.Element('hashTree'))
    else:
        ht.append(samp)
        ht.append(ET.Element('hashTree'))


def add_response_assertion(tree: ET.ElementTree, test_field: str = 'ResponseData', pattern: str = '', name: Optional[str] = None) -> None:
    """Add a ResponseAssertion element for basic assertions.

    test_field is one of JMeter's test field names (e.g., ResponseData, ResponseCode).
    """
    root = tree.getroot()
    # place assertion under TestPlan children by default
    ht = _testplan_children_hashTree(root)
    if ht is None:
        raise RuntimeError('Malformed JMX: missing hashTree')

    ra_name = name or f'Response Assertion ({test_field})'
    ra = ET.Element('ResponseAssertion', {'guiclass': 'AssertionGui', 'testclass': 'ResponseAssertion', 'testname': ra_name})
    ET.SubElement(ra, 'stringProp', {'name': 'Assertion.test_field'}).text = test_field
    ET.SubElement(ra, 'stringProp', {'name': 'ResponseAssertion.pattern'}).text = pattern

    ht.append(ra)
    ht.append(ET.Element('hashTree'))


def add_simple_result_collector(tree: ET.ElementTree, filename: Optional[str] = None, name: Optional[str] = None) -> None:
    """Add a ResultCollector (listener) that can write results to a file (CSV/JTL).

    If filename is provided, it will be added as the 'filename' property.
    """
    root = tree.getroot()
    # place result collector under TestPlan children
    ht = _testplan_children_hashTree(root)
    if ht is None:
        raise RuntimeError('Malformed JMX: missing hashTree')

    rc_name = name or 'Result Collector'
    rc = ET.Element('ResultCollector', {'guiclass': 'ViewResultsFullVisualizer', 'testclass': 'ResultCollector', 'testname': rc_name})
    if filename:
        ET.SubElement(rc, 'stringProp', {'name': 'filename'}).text = filename

    ht.append(rc)
    ht.append(ET.Element('hashTree'))


if __name__ == '__main__':
    # quick demo to create a jmx file
    tree = create_jmx_template('Demo Test')
    add_csv_dataset(tree, 'data.csv', ['user', 'pass'])
    add_constant_timer(tree, 500)
    add_regex_extractor(tree, 'token', '"token":"(.*?)"')
    save_jmx(tree, 'demo_generated.jmx')
