#!/usr/bin/env python3
import asyncio, json, os, signal, time
from pathlib import Path
import requests, websockets

HTTP="https://webapi.moomoo.com"
WS="wss://webapi-quote.moomoo.com/ws"
STATE=Path(os.environ.get("MOOMOO_STATE","/var/lib/moomoo-collector/oauth.json"))
CONFIG=Path(os.environ.get("MOOMOO_CONFIG","/etc/moomoo-collector/config.json"))

def load_json(p):
    return json.loads(p.read_text())
def save_state(v):
    STATE.parent.mkdir(parents=True,exist_ok=True)
    tmp=STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(v)); os.chmod(tmp,0o600); tmp.replace(STATE)
def refresh(s):
    r=requests.post(HTTP+"/oauth2/token",data={"grant_type":"refresh_token","refresh_token":s["refresh_token"],"client_id":s["client_id"]},timeout=30)
    r.raise_for_status(); v=r.json(); s["access_token"]=v["access_token"]; s["expires_at"]=int(time.time())+int(v.get("expires_in",7200))-120; save_state(s); return s
def token(s):
    return refresh(s) if int(s.get("expires_at",0))<=int(time.time()) else s

async def run_once():
    cfg=load_json(CONFIG); s=token(load_json(STATE))
    out=Path(cfg["output_dir"]); out.mkdir(parents=True,exist_ok=True)
    day=time.strftime("%Y-%m-%d",time.gmtime()); path=out/(day+".ndjson")
    async with websockets.connect(WS,ping_interval=20,ping_timeout=20,max_size=4*1024*1024) as ws:
        await ws.send(json.dumps({"action":"auth","data":{"auth_type":"oauth2","authorization":"Bearer "+s["access_token"]}}))
        auth=json.loads(await asyncio.wait_for(ws.recv(),20))
        if auth.get("code",0)!=0: raise RuntimeError("websocket auth rejected")
        symbols=cfg["symbols"]; sub={"id":"collector-sub","action":"subscribe"}
        if cfg.get("quote"): sub["quote"]=symbols
        if cfg.get("ticker"): sub["ticker"]=symbols
        if cfg.get("order_book"): sub["order_book"]=symbols
        if cfg.get("kline_1m"): sub["kline"]=[{"symbol":x,"period":"1m","adjust":"none"} for x in symbols]
        await ws.send(json.dumps(sub)); last_sub=time.monotonic()
        with path.open("a",buffering=1) as f:
            while True:
                if time.monotonic()-last_sub>=300:
                    await ws.send(json.dumps(sub)); last_sub=time.monotonic()
                try: raw=await asyncio.wait_for(ws.recv(),30)
                except asyncio.TimeoutError: continue
                f.write(json.dumps({"received_at_ms":int(time.time()*1000),"payload":json.loads(raw)},separators=(",",":"))+"\n")

async def main():
    delay=2
    while True:
        try: await run_once(); delay=2
        except asyncio.CancelledError: raise
        except Exception as e:
            print("collector reconnect:",type(e).__name__,flush=True); await asyncio.sleep(delay); delay=min(delay*2,60)
if __name__=="__main__":
    asyncio.run(main())
