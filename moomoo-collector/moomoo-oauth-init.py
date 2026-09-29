#!/usr/bin/env python3
# Interactive one-time OAuth bootstrap. It never prints tokens after exchange.
import base64, hashlib, json, os, secrets, urllib.parse
from pathlib import Path
import requests

HOST="https://webapi.moomoo.com"
REDIRECT="http://localhost:60355/callback"
STATE_FILE=Path.home()/".moomoo-oauth-pending.json"
TOKEN_FILE=Path("/var/lib/moomoo-collector/oauth.json")

def b64u(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def register():
    body={"redirect_uris":[REDIRECT],"token_endpoint_auth_method":"none","grant_types":["authorization_code","refresh_token"],"response_types":["code"],"client_name":"V38 moomoo read-only collector"}
    r=requests.post(HOST+"/oauth2/register",json=body,timeout=30); r.raise_for_status(); return r.json()
def start():
    reg=register(); verifier=b64u(secrets.token_bytes(48)); state=secrets.token_urlsafe(24)
    challenge=b64u(hashlib.sha256(verifier.encode()).digest())
    STATE_FILE.write_text(json.dumps({"client_id":reg["client_id"],"verifier":verifier,"state":state}))
    os.chmod(STATE_FILE,0o600)
    q={"client_id":reg["client_id"],"code_challenge":challenge,"code_challenge_method":"S256","redirect_uri":REDIRECT,"response_type":"code","state":state,"scope":"quote:read"}
    print("Open this URL in your browser and authorize quote:read only:\n")
    print(HOST+"/oauth2/authorize/confirm?"+urllib.parse.urlencode(q))
    print("\nAfter authorization, run this script again with --finish '<redirect URL>'.")
def finish(url):
    pending=json.loads(STATE_FILE.read_text()); q=urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    if q.get("state",[None])[0]!=pending["state"]: raise SystemExit("state mismatch")
    code=q.get("code",[None])[0]
    if not code: raise SystemExit("authorization code missing")
    r=requests.post(HOST+"/oauth2/token",data={"grant_type":"authorization_code","code":code,"client_id":pending["client_id"],"redirect_uri":REDIRECT,"code_verifier":pending["verifier"]},timeout=30); r.raise_for_status(); t=r.json()
    scopes=set(t.get("scope","").split())
    if "trade:write" in scopes: raise SystemExit("refusing token with trade:write")
    TOKEN_FILE.parent.mkdir(parents=True,exist_ok=True)
    TOKEN_FILE.write_text(json.dumps({"client_id":pending["client_id"],"access_token":t["access_token"],"refresh_token":t["refresh_token"],"expires_at":int(__import__("time").time())+int(t.get("expires_in",7200))-120}))
    os.chmod(TOKEN_FILE,0o600); STATE_FILE.unlink(missing_ok=True)
    print("OAuth token stored securely; token values were not printed.")
if __name__=="__main__":
    import sys
    finish(sys.argv[2]) if len(sys.argv)>2 and sys.argv[1]=="--finish" else start()
