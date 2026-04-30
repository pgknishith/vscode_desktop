"""Generate a JMeter JMX for PetStore load test (launch, login, logout).

This script uses the `perf_agent` utilities to assemble a JMX file that:
- Parameterizes credentials from `data/users.csv` (variables: user,pass)
- Correlates a token from the catalog page using a RegexExtractor (best-effort)
- Adds samplers for Launch (GET Catalog.action), Login (POST form), Logout (GET)
- Places samplers under a ThreadGroup and adds a ConstantTimer and a ResultCollector.

Assumptions (update the JMX manually or edit this script if the real site uses
different form field names or token names):
- Login form field names are `username` and `password`.
- A CSRF/session token is present in the Catalog page as an input with
  name containing "token" (regex used: name=\".*?token.*?\" value=\"(.*?)\").

If these assumptions don't match the real app, update the sampler parameters
or RegexExtractor pattern to match the page.
"""
from perf_agent import jmeter_utils as ju
from xml.etree import ElementTree as ET
import os


OUT = r'D:\VisualCode\petstore_load_test.jmx'
CSV_PATH = r'data/users.csv'


def build_http_sampler_element(name: str, domain: str, path: str, method: str = 'GET', protocol: str = 'https', port: int = None, params: dict = None, headers: dict = None, body: str = None, post_type: str = 'form') -> ET.Element:
    samp = ET.Element('HTTPSamplerProxy', {'guiclass': 'HttpTestSampleGui', 'testclass': 'HTTPSamplerProxy', 'testname': name})
    ET.SubElement(samp, 'stringProp', {'name': 'HTTPSampler.domain'}).text = domain
    if port is not None:
        ET.SubElement(samp, 'stringProp', {'name': 'HTTPSampler.port'}).text = str(port)
    ET.SubElement(samp, 'stringProp', {'name': 'HTTPSampler.protocol'}).text = protocol
    ET.SubElement(samp, 'stringProp', {'name': 'HTTPSampler.path'}).text = path
    ET.SubElement(samp, 'stringProp', {'name': 'HTTPSampler.method'}).text = method

    # args
    args_el = ET.Element('elementProp', {'name': 'HTTPsampler.Arguments', 'elementType': 'Arguments'})
    collection = ET.SubElement(args_el, 'collectionProp', {'name': 'Arguments.arguments'})
    if params:
        for k, v in params.items():
            arg = ET.SubElement(collection, 'elementProp', {'name': k, 'elementType': 'HTTPArgument'})
            ET.SubElement(arg, 'stringProp', {'name': 'Argument.name'}).text = str(k)
            ET.SubElement(arg, 'stringProp', {'name': 'Argument.value'}).text = str(v)
            ET.SubElement(arg, 'boolProp', {'name': 'HTTPArgument.always_encode'}).text = 'false'
    samp.append(args_el)

    if body is not None:
        ET.SubElement(samp, 'stringProp', {'name': 'HTTPSampler.postBodyRaw'}).text = 'true' if post_type == 'raw' else 'false'
        body_el = ET.Element('elementProp', {'name': 'HTTPsampler.PostBody', 'elementType': 'HTTPArgument'})
        ET.SubElement(body_el, 'stringProp', {'name': 'Argument.name'})
        ET.SubElement(body_el, 'stringProp', {'name': 'Argument.value'}).text = body
        ET.SubElement(body_el, 'boolProp', {'name': 'HTTPArgument.always_encode'}).text = 'false'
        samp.append(body_el)

    # If headers provided, create a HeaderManager element sibling when appending
    return samp


def main():
    tree = ju.create_jmx_template('PetStore Load Test')

    # ensure data folder exists and provide a sample CSV if missing
    os.makedirs('data', exist_ok=True)
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, 'w', encoding='utf-8') as f:
            f.write('user,pass\n')
            f.write('testuser,testpass\n')

    ju.add_csv_dataset(tree, CSV_PATH, ['user', 'pass'])

    # ThreadGroup
    ju.add_thread_group(tree, num_threads=10, ramp_time=20, name='PetStore Users')

    # Add a constant timer under the ThreadGroup
    timer = ET.Element('ConstantTimer', {'guiclass': 'ConstantTimerGui', 'testclass': 'ConstantTimer', 'testname': 'Think Time'})
    ET.SubElement(timer, 'stringProp', {'name': 'ConstantTimer.delay'}).text = '1000'
    # append timer directly under ThreadGroup
    tg_ht = ju.find_threadgroup_hashTree_by_name(tree.getroot(), 'PetStore Users')
    if tg_ht is None:
        raise RuntimeError('ThreadGroup hashTree not found')
    tg_ht.append(timer)
    tg_ht.append(ET.Element('hashTree'))

    domain = 'petstore.octoperf.com'

    # Launch Catalog (GET)
    launch = build_http_sampler_element('Launch Catalog', domain, '/actions/Catalog.action', method='GET', protocol='https')
    # create a TransactionController for Launch
    tc_launch = ET.Element('TransactionController', {'guiclass': 'TransactionControllerGui', 'testclass': 'TransactionController', 'testname': 'Launch Transaction'})
    # append controller and its hashTree under ThreadGroup
    tg_ht.append(tc_launch)
    launch_ht = ET.Element('hashTree')
    tg_ht.append(launch_ht)
    # append the sampler under the controller's hashTree
    launch_ht.append(launch)
    launch_ht.append(ET.Element('hashTree'))

    # Correlate a token from the Catalog page (best-effort). Adjust regex if needed.
    # Place the RegexExtractor under the Launch Transaction so it uses the Catalog response.
    reg = ET.Element('RegexExtractor', {'guiclass': 'RegexExtractorGui', 'testclass': 'RegexExtractor', 'testname': 'Catalog Token Extractor'})
    ET.SubElement(reg, 'stringProp', {'name': 'RegexExtractor.useHeaders'}).text = 'false'
    ET.SubElement(reg, 'stringProp', {'name': 'RegexExtractor.refname'}).text = 'sessionToken'
    ET.SubElement(reg, 'stringProp', {'name': 'RegexExtractor.regex'}).text = 'name=".*?token.*?" value="(.*?)"'
    ET.SubElement(reg, 'stringProp', {'name': 'RegexExtractor.template'}).text = '$1$'
    ET.SubElement(reg, 'stringProp', {'name': 'RegexExtractor.match_number'}).text = '1'
    ET.SubElement(reg, 'stringProp', {'name': 'RegexExtractor.default'}).text = 'NOT_FOUND'
    # append under the launch controller's hashTree
    launch_ht.append(reg)
    launch_ht.append(ET.Element('hashTree'))

    # Login (POST) - using CSV variables ${user} and ${pass}
    login_params = {'username': '${user}', 'password': '${pass}'}
    login = build_http_sampler_element('Login', domain, '/actions/Account.action', method='POST', protocol='https', params=login_params, post_type='form')
    tc_login = ET.Element('TransactionController', {'guiclass': 'TransactionControllerGui', 'testclass': 'TransactionController', 'testname': 'Login Transaction'})
    tg_ht.append(tc_login)
    login_ht = ET.Element('hashTree')
    tg_ht.append(login_ht)
    login_ht.append(login)
    login_ht.append(ET.Element('hashTree'))

    # Simple assertion to ensure login returned 200 (adjust as needed)
    assertion = ET.Element('ResponseAssertion', {'guiclass': 'AssertionGui', 'testclass': 'ResponseAssertion', 'testname': 'Login Response Code'})
    ET.SubElement(assertion, 'stringProp', {'name': 'Assertion.test_field'}).text = 'ResponseCode'
    ET.SubElement(assertion, 'stringProp', {'name': 'ResponseAssertion.pattern'}).text = '200'
    # append assertion under same hashTree as login so it runs after login
    login_ht.append(assertion)
    login_ht.append(ET.Element('hashTree'))

    # Logout (GET) - use query param signoff=true commonly used
    logout = build_http_sampler_element('Logout', domain, '/actions/Account.action', method='GET', protocol='https', params={'signoff': 'true'})
    tc_logout = ET.Element('TransactionController', {'guiclass': 'TransactionControllerGui', 'testclass': 'TransactionController', 'testname': 'Logout Transaction'})
    tg_ht.append(tc_logout)
    logout_ht = ET.Element('hashTree')
    tg_ht.append(logout_ht)
    logout_ht.append(logout)
    logout_ht.append(ET.Element('hashTree'))

    # Add a result collector to write JTL
    ju.add_simple_result_collector(tree, filename='petstore_results.jtl', name='PetStore Results')

    # Save JMX
    ju.save_jmx(tree, OUT)
    print('Wrote JMX to', OUT)


if __name__ == '__main__':
    main()
