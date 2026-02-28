"""Utilities to parse JMeter result files (CSV/JTL) and produce simple summaries."""
import csv
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Sample:
    timestamp: int
    elapsed: int
    label: str
    responseCode: str
    success: bool


def parse_jtl_csv(path: str, encoding: str = 'utf-8') -> List[Sample]:
    """Parse a JMeter CSV/JTL file and return a list of Sample objects.

    Expects a header row with at least: timeStamp,elapsed,label,responseCode,success
    """
    samples: List[Sample] = []
    with open(path, 'r', encoding=encoding, newline='') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                ts = int(float(row.get('timeStamp') or 0))
            except Exception:
                ts = 0
            try:
                elapsed = int(row.get('elapsed') or 0)
            except Exception:
                elapsed = 0
            label = row.get('label', '')
            responseCode = row.get('responseCode', '')
            success_raw = row.get('success', 'true')
            success = str(success_raw).lower() in ('true', '1')
            samples.append(Sample(timestamp=ts, elapsed=elapsed, label=label, responseCode=responseCode, success=success))
    return samples


def parse_jtl_xml(path: str, encoding: str = 'utf-8') -> List[Sample]:
    """Parse a JMeter XML JTL file and return a list of Sample objects.

    This parser accepts common JMeter XML result element names like
    'httpSample', 'sample', or 'sampleResult' and reads attributes:
    - t or lt or time: elapsed
    - ts: timestamp (ms)
    - lb: label
    - rc: responseCode
    - s: success (true/false)
    """
    import xml.etree.ElementTree as ET

    tree = ET.parse(path)
    root = tree.getroot()
    samples: List[Sample] = []
    # find all sample-like elements
    for elem in root.iter():
        tag = elem.tag
        if tag in ('httpSample', 'sample', 'sampleResult'):
            # elapsed: attr 't' or 'lt' or 'time'
            elapsed = 0
            for k in ('t', 'lt', 'time'):
                if k in elem.attrib:
                    try:
                        elapsed = int(float(elem.attrib[k]))
                        break
                    except Exception:
                        elapsed = 0
            ts = 0
            if 'ts' in elem.attrib:
                try:
                    ts = int(float(elem.attrib['ts']))
                except Exception:
                    ts = 0
            label = elem.attrib.get('lb', elem.attrib.get('label', ''))
            rc = elem.attrib.get('rc', elem.attrib.get('responseCode', ''))
            s_raw = elem.attrib.get('s', 'true')
            success = str(s_raw).lower() in ('true', '1')
            samples.append(Sample(timestamp=ts, elapsed=elapsed, label=label, responseCode=rc, success=success))
    return samples


def parse_jtl(path: str, encoding: str = 'utf-8') -> List[Sample]:
    """Auto-detect JTL format (CSV vs XML) and parse accordingly."""
    # simple detection: if file starts with '<' treat as XML
    with open(path, 'r', encoding=encoding, errors='ignore') as fh:
        start = fh.read(200).lstrip()
    if start.startswith('<'):
        return parse_jtl_xml(path, encoding=encoding)
    else:
        return parse_jtl_csv(path, encoding=encoding)


def summarize_samples(samples: List[Sample]) -> Dict[str, Optional[float]]:
    """Return a simple summary: count, avg, min, max, errors, throughput (per sec).

    Throughput is computed as samples / duration_seconds (based on timestamps).
    """
    if not samples:
        return {
            'count': 0,
            'avg': None,
            'min': None,
            'max': None,
            'errors': 0,
            'error_rate': None,
            'p90': None,
            'p95': None,
            'p99': None,
            'duration_seconds': None,
            'throughput': None,
        }
    count = len(samples)
    elapsed_times = [s.elapsed for s in samples]
    elapsed_sorted = sorted(elapsed_times)
    avg = sum(elapsed_times) / count
    mn = min(elapsed_times)
    mx = max(elapsed_times)
    errors = sum(1 for s in samples if not s.success)
    error_rate = (errors / count) * 100 if count else None
    timestamps = sorted(s.timestamp for s in samples if s.timestamp)
    if len(timestamps) >= 2:
        duration_ms = timestamps[-1] - timestamps[0]
        duration_s = duration_ms / 1000.0 if duration_ms > 0 else 0
        throughput = count / duration_s if duration_s > 0 else None
        duration_seconds = duration_s
    else:
        throughput = None
        duration_seconds = None

    return {
        'count': count,
        'avg': avg,
        'min': mn,
        'max': mx,
        'errors': errors,
        'error_rate': error_rate,
        'p90': _percentile_sorted(elapsed_sorted, 90),
        'p95': _percentile_sorted(elapsed_sorted, 95),
        'p99': _percentile_sorted(elapsed_sorted, 99),
        'duration_seconds': duration_seconds,
        'throughput': throughput,
    }


def summarize_by_label(samples: List[Sample]) -> Dict[str, Dict[str, Optional[float]]]:
    """Return summaries grouped by sample label."""
    grouped: Dict[str, List[Sample]] = {}
    for sample in samples:
        grouped.setdefault(sample.label or 'UNKNOWN', []).append(sample)
    return {label: summarize_samples(group) for label, group in grouped.items()}


def build_performance_report(
    samples: List[Sample],
    sla_p95_ms: Optional[float] = None,
    sla_error_rate_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """Build a report payload with summary, endpoint breakdown, and SLA status."""
    overall = summarize_samples(samples)
    by_label = summarize_by_label(samples)

    sla: Dict[str, Any] = {}
    if sla_p95_ms is not None:
        p95 = overall.get('p95')
        sla['p95'] = {
            'target_ms': sla_p95_ms,
            'actual_ms': p95,
            'pass': p95 is not None and p95 <= sla_p95_ms,
        }
    if sla_error_rate_pct is not None:
        error_rate = overall.get('error_rate')
        sla['error_rate'] = {
            'target_pct': sla_error_rate_pct,
            'actual_pct': error_rate,
            'pass': error_rate is not None and error_rate <= sla_error_rate_pct,
        }
    if sla:
        sla['overall_pass'] = all(item.get('pass') for item in sla.values() if isinstance(item, dict))

    return {
        'overall': overall,
        'by_label': by_label,
        'sla': sla,
    }


def _percentile_sorted(sorted_values: List[int], percentile: float) -> Optional[float]:
    """Calculate percentile using linear interpolation; input must be sorted."""
    if not sorted_values:
        return None
    if percentile <= 0:
        return float(sorted_values[0])
    if percentile >= 100:
        return float(sorted_values[-1])

    position = (len(sorted_values) - 1) * (percentile / 100.0)
    lower_idx = int(math.floor(position))
    upper_idx = int(math.ceil(position))
    if lower_idx == upper_idx:
        return float(sorted_values[lower_idx])
    lower_value = sorted_values[lower_idx]
    upper_value = sorted_values[upper_idx]
    fraction = position - lower_idx
    return float(lower_value + (upper_value - lower_value) * fraction)
