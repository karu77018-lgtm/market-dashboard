/* Generated page regression gate: real exported data, desktop and iPhone widths. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {spawn}=require('node:child_process');
const {chromium}=require('playwright');
const root=require('node:path').resolve(__dirname,'..');
const index=JSON.parse(fs.readFileSync(root+'/market-history/index.json'));
const mc=JSON.parse(fs.readFileSync(root+'/data/mc57.json'));
const server=spawn('python',['-m','http.server','8798','--bind','127.0.0.1'],{cwd:root,stdio:'ignore'});
const url=process.env.MARKET_UI_URL||'http://127.0.0.1:8798/source-mc57.html';
async function verify(page,width){
  await page.setViewportSize({width,height:900});
  const requests=[]; page.on('request',r=>requests.push(r.url()));
  await page.goto(url,{waitUntil:'networkidle'});
  assert.equal(await page.locator('.mh-tools button:disabled').count(),0,'no unavailable period choices');
  const sparks=page.locator('svg.spark');
  assert(await sparks.count()>0,'legacy macro sparklines present');
  const noAxis=await sparks.evaluateAll(items=>items.filter(e=>!e.nextElementSibling?.classList.contains('mh-spark-axis')).length);
  assert.equal(noAxis,0,'every legacy time sparkline has observation date axis');
  const narrowAxes=await sparks.evaluateAll(items=>items.filter(e=>{const r=e.getBoundingClientRect(),a=e.nextElementSibling?.getBoundingClientRect();return r.width>0&&(!a||a.width<r.width*.8);}).length);
  assert.equal(narrowAxes,0,'date axes span their graph including grid rate cards');
  const tabs=page.locator('nav a.tabx');
  assert.equal(await tabs.count(),11,'all original tabs including Jev');
  assert.equal(await page.locator('.mh-card [data-window="2y"][aria-pressed="true"]').count(),await page.locator('.mh-card[data-history-key]').count());
  assert(!requests.some(u=>/-(?:5|10)y\.json/.test(u)),'initial page must not request 5/10Y');
  for(let i=0;i<await tabs.count();i++){
    const href=await tabs.nth(i).getAttribute('href');await tabs.nth(i).click();
    assert(await page.locator(href).isVisible(),'tab remains visible: '+href);
  }
  await page.locator('nav a[href="#t-rotation"]').click();
  for(const key of ['leadership','concentration','relative']){
    const card=page.locator('#t-rotation [data-history-key="'+key+'"]');
    const initial=JSON.parse(fs.readFileSync(root+'/market-history/'+index.files[key]['2y']));
    if(Object.values(initial.availability).some(x=>x.status!=='READY')){assert.equal(await card.count(),0,'unavailable initial chart hidden: '+key);continue;}
    for(const win of ['2y','5y','10y']){
      const j=JSON.parse(fs.readFileSync(root+'/market-history/'+index.files[key][win]));
      if(Object.values(j.availability).some(x=>x.status!=='READY')){assert.equal(await card.locator('[data-window="'+win+'"]').count(),0);continue;}
      await card.locator('[data-window="'+win+'"]').click();
      await page.waitForFunction(({key,win})=>document.querySelector('#t-rotation [data-history-key="'+key+'"]').dataset.loadedWindow===win,{key,win});
      assert(await card.locator('.mh-plot svg').isVisible());
      const ticks=await card.locator('.mh-plot svg text').allTextContents();
      assert.equal(new Set(ticks).size,ticks.length,'unique readable y-axis labels: '+key);
      if(key.startsWith('mc57-group-'))assert(ticks.every(v=>Number(v)>=0&&Number(v)<=100),'participation axis stays 0..100');
      assert(!(await card.locator('.mh-status').innerText()).includes('DATA UNAVAILABLE'));
      for(const [label,a] of Object.entries(j.series)){
        const normalized=await page.evaluate(a=>window.MarketHistory.normalize(a),a);
        assert.equal(normalized.find(Number.isFinite),100,label+' normalized period start');
      }
    }
  }
  const heat=page.locator('#t-rotation [data-history-key="gics11"]');
  const heatAvailable=[21,63,126].every(h=>JSON.parse(fs.readFileSync(root+'/market-history/'+index.files.gics11[h]['2y'])).status==='READY');
  if(!heatAvailable)assert.equal(await heat.count(),0,'unavailable heatmap hidden');
  for(const horizon of heatAvailable?[21,63,126]:[])for(const win of ['2y','5y','10y']){
    const expected=JSON.parse(fs.readFileSync(root+'/market-history/'+index.files.gics11[horizon][win]));
    if(expected.status!=='READY'){assert.equal(await heat.locator('[data-window="'+win+'"]').count(),0,'incomplete GICS period hidden');continue;}
    await heat.locator('[data-horizon="'+horizon+'"]').click();
    await heat.locator('[data-window="'+win+'"]').click();
    await page.waitForFunction(({horizon,win})=>{const c=document.querySelector('[data-history-key="gics11"]');return c.dataset.loadedHorizon===String(horizon)&&c.dataset.loadedWindow===win;},{horizon,win});
    const j=JSON.parse(fs.readFileSync(root+'/market-history/'+index.files.gics11[horizon][win]));
    assert.equal(await heat.locator('tbody tr').count(),11);
    const displayed=await heat.locator('tbody tr td:first-child').allTextContents();
    assert.deepEqual(displayed.map(Number),Array.from({length:11},(_,i)=>i+1));
    assert.deepEqual(j.rows.at(-1).ranks,j.current.ranks,'heatmap latest and rank flow share ranks');
    const top=Object.keys(j.current.ranks).filter(k=>j.current.ranks[k]<=3).map(k=>j.sectors[k]);
    const bottom=Object.keys(j.current.ranks).filter(k=>j.current.ranks[k]>=9).map(k=>j.sectors[k]);
    const flow=await heat.locator('.mh-rank-flow').innerText();
    for(const s of [...top,...bottom])assert(flow.includes(s));
    assert.equal(await heat.locator('.mh-top').count(),3);assert.equal(await heat.locator('.mh-bottom').count(),3);
  }
  const overflow=await page.locator('#t-rotation .mh-card').evaluateAll(cards=>cards.filter(c=>{const r=c.getBoundingClientRect();return r.left< -1||r.right>innerWidth+1;}).map(c=>c.dataset.historyKey));
  assert.deepEqual(overflow,[],'new cards fit viewport '+width);
  await page.locator('nav a[href="#t-market"]').click();
  for(const key of ['vixcycle','credit','defensive','vixterm','indices','mc57-group-0','mc57-group-1','mc57-group-2','mc57-group-3']){
    if(!index.files[key])continue;
    const card=page.locator('.mh-existing[data-history-key="'+key+'"],.mh-card[data-history-key="'+key+'"]');
    if(!await card.count())continue;
    for(const win of ['2y','5y','10y']){
      const data=JSON.parse(fs.readFileSync(root+'/market-history/'+index.files[key][win]));
      if(Object.values(data.availability).some(v=>v.status!=='READY')){assert.equal(await card.locator('[data-window="'+win+'"]').count(),0);continue;}
      await card.locator('[data-window="'+win+'"]').click();
      await page.waitForFunction(({key,win})=>document.querySelector('.mh-existing[data-history-key="'+key+'"],.mh-card[data-history-key="'+key+'"]').dataset.loadedWindow===win,{key,win});
      assert(await card.locator('.mh-plot svg').isVisible());
      const ticks=await card.locator('.mh-plot svg text').allTextContents();
      assert.equal(new Set(ticks).size,ticks.length,'distinct y-axis labels: '+key);
      if(key.startsWith('mc57-group-'))assert(ticks.every(v=>Number(v)>=0&&Number(v)<=100),'0..100 bounded participation');
    }
  }
  const vix=page.locator('.vixcy .mh-plot');
  if(await vix.count()){const box=await vix.evaluate(el=>{const r=el.getBoundingClientRect(),v=el.querySelector('svg').getBoundingClientRect();return {host:r.bottom,svg:v.bottom};});assert(box.svg<=box.host+1,'VIX chart not cropped');}
  const current=page.locator('[data-history-key="mc57"]');
  for(const win of ['2y','5y','10y']){
    await current.locator('[data-window="'+win+'"]').click();
    await page.waitForFunction(win=>document.querySelector('[data-history-key="mc57"]').dataset.loadedWindow===win,win);
    const j=JSON.parse(fs.readFileSync(root+'/market-history/'+index.files.mc57[win]));
    assert.equal(j.dates.at(-1),mc.session_date);assert.equal(j.series.MC57.at(-1),mc.mc57);
    assert.deepEqual(await current.locator('.mh-score-band').evaluateAll(es=>es.map(e=>[e.getAttribute('fill'),e.getAttribute('opacity')])),[['#df5454','0.07'],['#d97936','0.07'],['#7f7c70','0.07'],['#25c25f','0.07'],['#1e9b4c','0.07']],'legacy MC57 score background retained every period');
  }
  const group=page.locator('.mh-card[data-history-key="mc57-group-0"]');
  const seriesButtons=group.locator('[data-series-toggle]');
  assert.equal(await seriesButtons.count(),4);
  const originalPaths=await group.locator('svg path').count();
  await seriesButtons.nth(0).click();assert.equal(await group.locator('svg path').count(),originalPaths-1);
  await seriesButtons.nth(0).click();assert.equal(await group.locator('svg path').count(),originalPaths);
  for(let i=0;i<4;i++)await seriesButtons.nth(i).click();
  assert.equal(await group.locator('svg path').count(),1,'last visible series cannot be hidden');
  const spacing=await group.evaluate(c=>c.querySelector(':scope > .sub').getBoundingClientRect().top-c.querySelector('.mh-plot > .dax').getBoundingClientRect().bottom);
  assert(spacing>=7,'date labels separated from description');
  const text=await page.locator('.mkt20-read').first().innerText();
  assert(!/Blue|Green|Yellow|Red|地合いは青/.test(text),'commentary independent of NQSAR');
  await page.screenshot({path:root+'/work/market-ui-'+width+'.png',fullPage:false});
  console.log('PASS desktop/mobile, 11 tabs, MC57 3 windows, leadership/cap/relative 3 windows, GICS available combinations (unavailable hidden), normalized=100, viewport='+width);
}
(async()=>{
  let browser;
  try{
    for(let i=0;i<50;i++){try{if((await fetch('http://127.0.0.1:8798')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
    browser=await chromium.launch({headless:true});
    for(const width of [1348,390,375]){const page=await browser.newPage();await verify(page,width);await page.close();}
  }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
