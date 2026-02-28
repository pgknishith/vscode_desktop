import os
from perf_agent import result_parser as rp


def test_parse_and_summarize(tmp_path):
    csv_file = tmp_path / 'sample.jtl'
    # create a small CSV with header
    csv_file.write_text('timeStamp,elapsed,label,responseCode,success\n')
    csv_file.write_text(csv_file.read_text() + '1000,200,Home,200,True\n')
    csv_file.write_text(csv_file.read_text() + '1500,300,Login,500,False\n')
    samples = rp.parse_jtl(str(csv_file))
    assert len(samples) == 2
    summary = rp.summarize_samples(samples)
    assert summary['count'] == 2
    assert summary['min'] == 200
    assert summary['max'] == 300
    assert summary['errors'] == 1
    assert summary['avg'] == 250
    assert summary['error_rate'] == 50
    assert summary['p95'] is not None


def test_parse_xml_jtl(tmp_path):
    xml_file = tmp_path / 'sample_xml.jtl'
    content = '<testResults>\n'
    content += '<httpSample t="200" ts="1000" lb="Home" rc="200" s="true"/>\n'
    content += '<httpSample t="300" ts="1500" lb="Login" rc="500" s="false"/>\n'
    content += '</testResults>\n'
    xml_file.write_text(content)
    samples = rp.parse_jtl(str(xml_file))
    assert len(samples) == 2
    summary = rp.summarize_samples(samples)
    assert summary['count'] == 2
    assert summary['min'] == 200
    assert summary['max'] == 300
    assert summary['errors'] == 1


def test_build_performance_report_with_sla(tmp_path):
    csv_file = tmp_path / 'sample.jtl'
    csv_file.write_text(
        'timeStamp,elapsed,label,responseCode,success\n'
        '1000,100,Login,200,True\n'
        '2000,400,Login,500,False\n'
        '3000,200,Search,200,True\n'
    )

    samples = rp.parse_jtl(str(csv_file))
    report = rp.build_performance_report(samples, sla_p95_ms=500, sla_error_rate_pct=40)

    assert 'overall' in report
    assert 'by_label' in report
    assert 'Login' in report['by_label']
    assert report['overall']['count'] == 3
    assert report['overall']['error_rate'] == (1 / 3) * 100
    assert report['sla']['p95']['pass'] is True
    assert report['sla']['error_rate']['pass'] is True
    assert report['sla']['overall_pass'] is True
