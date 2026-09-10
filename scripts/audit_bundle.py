"""Read-only size/provenance audit. Does not remove runtime libraries."""
import argparse
from collections import Counter
import json
from pathlib import Path
from package_release import inspect_bundle


def summarize(report):
    groups = Counter()
    for item in report['files']:
        groups['/'.join(item['path'].split('/')[:2])] += item['bytes']
    total = report['total_bytes']
    return {
        'build': report['build'], 'file_count': report['file_count'],
        'total_bytes': total,
        'components': [{'path': path, 'bytes': size,
                        'percent': round(size * 100 / total, 2) if total else 0}
                       for path, size in groups.most_common()],
        'compatibility': 'Local audit only; another physical PC is not tested.',
        'optimization': 'Build CPU edition in a separate CPU environment; never strip CUDA DLLs from the NVIDIA edition.',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = summarize(inspect_bundle(args.bundle))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({k: report[k] for k in ('file_count', 'total_bytes', 'components')}, indent=2))
