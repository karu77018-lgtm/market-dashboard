"""A single low-cost scheduled probe; no repeated full Yahoo refresh on 403.

Two reasons to run the full refresh from a retry slot:
  * the published session is still provisional and Massive now confirms it;
  * the published session is older than the latest completed NYSE session
    (the main 21:45 UTC run failed or was skipped), so the page is a day behind.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from market_calendar import latest_completed_session  # noqa: E402

# Daily bars are not complete at the bell; the main run starts 1h45m after a
# regular close, so a retry slot only treats a session as overdue after that.
SETTLE = timedelta(minutes=105)


def session_is_stale(published: str, now: datetime) -> bool:
    return date.fromisoformat(published) < latest_completed_session(now, SETTLE)


def massive_confirms(session: str, key: str) -> bool:
    url = 'https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks/' + session
    url += '?' + urllib.parse.urlencode({'adjusted': 'true', 'include_otc': 'false'})
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + key})
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            payload = json.load(response)
            return str(payload.get('status', '')).upper() in {'OK', 'DELAYED'} and bool(payload.get('results'))
    except Exception:
        # Never log exception URLs/headers or retry an entitlement failure
        # in a tight loop. The next scheduled probe may try again.
        print('Massive confirmation is not available; retain provisional publication.')
        return False


def decide(manifest: dict, now: datetime, key: str, confirm=massive_confirms) -> tuple[bool, str]:
    session = manifest['session_date']
    if session_is_stale(session, now):
        return True, f'published session {session} is behind the latest completed NYSE session'
    ready = manifest.get('provider_status', {}).get('massive') == 'READY'
    if not ready and key and confirm(session, key):
        return True, 'Massive confirms the provisional session'
    return False, 'nothing to do'


def main():
    manifest = json.loads(Path('latest-manifest.json').read_text())
    run, reason = decide(manifest, datetime.now(timezone.utc), os.environ.get('MASSIVE_API_KEY', ''))
    value = 'true' if run else 'false'
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write('run_refresh=' + value + '\n')
    print('Delayed confirmation refresh: ' + value + ' (' + reason + ')')


if __name__ == '__main__':
    main()
