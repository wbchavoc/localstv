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


def network_for(entry, metadata):
    """Identify US broadcast affiliates without relying on broadcast_area alone."""
    meta = metadata.get(entry['id'], {})
    name = entry['name']
    combined = ' '.join((name, entry['id'], str(meta.get('name') or '')))
    network_value = meta.get('network') or ''
    if isinstance(network_value, dict):
        network_value = network_value.get('name') or network_value.get('id') or ''
    network_value = str(network_value).upper().strip()
    # Do not confuse national news, sports and cable networks with local affiliates.
    if re.search(r'\b(FOX NEWS|FOX BUSINESS|FOX SPORTS|NBC NEWS|NBC SPORTS|CBS NEWS|CBS SPORTS|ABC NEWS|NEWS LIVE)\b', combined, re.I):
        return None
    # TV station call signs (K/W...) or a clearly named local station.
    has_callsign = bool(re.search(r'\b[KW][A-Z]{2,4}(?:-TV|-DT)?\b', combined, re.I))
    has_local_marker = bool(re.search(r'\b(?:LOCAL|AFFILIATE|CHANNEL\s*\d+|\bCH\s*\d+)\b', combined, re.I))
    if not (has_callsign or has_local_marker):
        return None
    # Prefer explicit metadata; its network can be an ID such as ABC.us.
    for network in NETWORKS:
        if re.match(r'^' + network + r'(?:\b|[._-])', network_value):
            return network
    # Some streams have incomplete network metadata but name the affiliation.
    for network in NETWORKS:
        if re.search(r'(?<![A-Z])' + network + r'(?![A-Z])', name, re.I):
            return network
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
