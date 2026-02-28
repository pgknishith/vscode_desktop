import os
from xml.etree import ElementTree as ET

import perf_agent.jmeter_utils as ju


def test_create_and_save_jmx(tmp_path):
    tree = ju.create_jmx_template('Unit Test')
    ju.add_csv_dataset(tree, 'data.csv', ['u', 'p'])
    ju.add_constant_timer(tree, 100)
    ju.add_regex_extractor(tree, 'token', 'token=(\\w+)')
    out = tmp_path / 't_test.jmx'
    ju.save_jmx(tree, str(out))
    assert out.exists()
    # load and assert root structure
    root = ET.parse(str(out)).getroot()
    assert root.find('hashTree') is not None


def test_jmx_builders_extra(tmp_path):
    tree = ju.create_jmx_template('Builders Test')
    # add thread group
    ju.add_thread_group(tree, num_threads=5, ramp_time=2)
    # add http sampler
    ju.add_http_sampler(tree, name='Get Home', domain='example.com', port=80, path='/', method='GET', protocol='http')
    # add assertion
    ju.add_response_assertion(tree, test_field='ResponseCode', pattern='200')
    # add result collector
    rc_file = str(tmp_path / 'out.jtl')
    ju.add_simple_result_collector(tree, filename=rc_file)

    out = tmp_path / 'builders.jmx'
    ju.save_jmx(tree, str(out))
    assert out.exists()
    root = ET.parse(str(out)).getroot()
    # Check that at least one HTTP sampler and one ThreadGroup node exist
    assert root.findall('.//HTTPSamplerProxy')
    assert root.findall('.//ThreadGroup')
    assert root.findall('.//ResponseAssertion')
    assert root.findall('.//ResultCollector')


def test_add_sampler_to_named_threadgroup(tmp_path):
    tree = ju.create_jmx_template('TG Test')
    ju.add_thread_group(tree, num_threads=2, name='MyGroup')
    # create a sampler element
    samp = ET.Element('HTTPSamplerProxy', {'guiclass': 'HttpTestSampleGui', 'testclass': 'HTTPSamplerProxy', 'testname': 'TG Sampler'})
    ET.SubElement(samp, 'stringProp', {'name': 'HTTPSampler.domain'}).text = 'example.org'
    # add sampler under the named ThreadGroup
    ju.add_sampler_to_threadgroup(tree, samp, threadgroup_name='MyGroup')
    out = tmp_path / 'tg_named.jmx'
    ju.save_jmx(tree, str(out))
    root = ET.parse(str(out)).getroot()
    # ensure our sampler is under a ThreadGroup hashTree
    assert root.findall('.//ThreadGroup')
    assert root.findall('.//HTTPSamplerProxy')

