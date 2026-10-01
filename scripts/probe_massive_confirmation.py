"""A single low-cost scheduled probe; no repeated full Yahoo refresh on 403."""
import json
import os
import urllib.request
import urllib.parse
from pathlib import Path


def main():
    manifest = json.loads(Path('latest-manifest.json').read_text())
    session = manifest['session_date']
    ready = manifest.get('provider_status', {}).get('massive') == 'READY'
    key = os.environ.get('MASSIVE_API_KEY', '')
    run = False
    if not ready and key:
        url = 'https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks/' + session
        url += '?' + urllib.parse.urlencode({'adjusted': 'true', 'include_otc': 'false'})
        req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + key})
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                payload = json.load(response)
                run = str(payload.get('status', '')).upper() in {'OK', 'DELAYED'} and bool(payload.get('results'))
        except Exception:
            # Never log exception URLs/headers or retry an entitlement failure
            # in a tight loop. The next scheduled probe may try again.
            print('Massive confirmation is not available; retain provisional publication.')
    value = 'true' if run else 'false'
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write('run_refresh=' + value + '\n')
    print('Delayed confirmation refresh: ' + value)


if __name__ == '__main__':
    main()
