"""Release discovery only. Never installs code or accesses user image data."""
import json
import re

RELEASES_URL = 'https://github.com/qoalsrb88/BMK-AI-Studio/releases'
API_URL = 'https://api.github.com/repos/qoalsrb88/BMK-AI-Studio/releases?per_page=100'
MAX_RESPONSE = 1024 * 1024


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'v?\d+\.\d+\.\d+', value):
        raise ValueError('Unsupported release version')
    return tuple(map(int, value.removeprefix('v').split('.')))


def available_release(payload, current, include_beta=True):
    if len(payload) > MAX_RESPONSE:
        raise ValueError('Release response too large')
    releases = json.loads(payload)
    if not isinstance(releases, list):
        raise ValueError('Invalid release list')
    current_version = version_tuple(current)
    candidates = []
    for release in releases:
        if not isinstance(release, dict) or release.get('draft') is not False:
            continue
        if not isinstance(release.get('prerelease'), bool):
            continue
        if release['prerelease'] and not include_beta:
            continue
        tag = release.get('tag_name')
        try:
            version = version_tuple(tag)
        except ValueError:
            continue
        if version > current_version:
            candidates.append((version, {'version': tag.removeprefix('v'),
                                        'beta': release['prerelease'],
                                        'url': RELEASES_URL + '/tag/' + tag}))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None

