#!/usr/bin/env python3
"""Build an M3U of publicly listed US ABC/CBS/FOX/NBC local affiliates.

Only listed streams are included; no claim is made that every stream works,
or that a stream carries a particular NFL game. Canadian stream hosting is allowed.
"""
import json
import re
import time
import urllib.request
from collections import OrderedDict
from pathlib import Path

BASE = 'https://iptv-org.github.io'
SOURCES = [f'{BASE}/iptv/countries/us.m3u', f'{BASE}/iptv/countries/ca.m3u']
METADATA = f'{BASE}/api/channels.json'
OUT = Path(__file__).with_name('channels.m3u')
NETWORKS = ('ABC', 'CBS', 'FOX', 'NBC')


def fetch(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Local-TV-Builder/1.0'})
            with urllib.request.urlopen(req, timeout=40) as response:
                return response.read().decode('utf-8-sig', errors='replace')
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def split_extinf(line):
    quoted = False
    for i, c in enumerate(line):
        if c == '"':
            quoted = not quoted
        elif c == ',' and not quoted:
            return line[:i], line[i + 1:]
    raise ValueError('Invalid EXTINF: missing separator')


def parse(text):
    if not text.lstrip().startswith('#EXTM3U'):
        raise ValueError('Source is not an M3U playlist')
    pending = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith('#EXTINF:'):
            pending = [line]
        elif pending and line.startswith('#'):
            pending.append(line)
        elif pending and line:
            header, name = split_extinf(pending[0])
            tvg = re.search(r'\btvg-id="([^"]*)"', header)
            yield {'id': tvg.group(1) if tvg else '', 'name': name.strip(),
                   'url': line, 'lines': pending[:]}
            pending = []


def is_us_local(meta):
    areas = meta.get('broadcast_area') or []
    return any(isinstance(a, str) and a.startswith(('s/US-', 'c/US-')) for a in areas)


def network_for(entry, metadata):
    meta = metadata.get(entry['id'], {})
    network = (meta.get('network') or '').strip().upper()
    if network in NETWORKS and is_us_local(meta):
        return network
    # Avoid guessing affiliation from names such as 'FOX News' or 'NBC Sports'.
    # Require verified metadata; exclude national network and Canadian networks.
    return None


def main():
    metadata_list = json.loads(fetch(METADATA))
    metadata = {c['id']: c for c in metadata_list if c.get('id')}
    groups = {network: OrderedDict() for network in NETWORKS}
    source_count = 0
    for source in SOURCES:
        items = list(parse(fetch(source)))
        print(f'{source}: {len(items)} streams')
        source_count += len(items)
        for entry in items:
            network = network_for(entry, metadata)
            if network:
                groups[network].setdefault(entry['url'], entry)
    if source_count < 10:
        raise RuntimeError('Sources returned too few streams; existing playlist preserved')
    if not any(groups.values()):
        raise RuntimeError('No verified local affiliates found; existing playlist preserved')
    output = ['#EXTM3U']
    for network in NETWORKS:
        for entry in sorted(groups[network].values(), key=lambda e: (e['name'].casefold(), e['url'])):
            header, name = split_extinf(entry['lines'][0])
            header = re.sub(r'\s+group-title="[^"]*"', '', header)
            header += f' group-title="{network}"'
            output.extend([header + ',' + name, *entry['lines'][1:], entry['url']])
        print(f'{network}: {len(groups[network])} streams')
    tmp = OUT.with_suffix('.m3u.tmp')
    tmp.write_text('\n'.join(output) + '\n', encoding='utf-8')
    tmp.replace(OUT)
    print(f'Wrote {OUT}')


if __name__ == '__main__':
    main()
