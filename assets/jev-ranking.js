(function () {
  'use strict';
  var section = document.getElementById('t-jev');
  if (!section) return;
  function esc(x) { return String(x == null ? '—' : x).replace(/[&<>"']/g, function(c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function num(x) { return x !== null && x !== undefined && Number.isFinite(Number(x)); }
  function pct(x) { return num(x) ? Math.round(Number(x)*100)+'%' : '—'; }
  function rs(x) { return num(x) ? Math.round(Number(x)) : '—'; }
  fetch('data/jev-ranking.json', {cache:'no-store'}).then(function(r) {
    if (!r.ok) throw Error('ranking unavailable');
    return r.json();
  }).then(function(p) {
    if (!Array.isArray(p.rows)) throw Error('invalid ranking');
    var meta = document.querySelector('meta[name="dashboard-source-sha256"]');
    var currentSession = window.CALC && window.CALC.asof;
    var fresh = Boolean(meta && p.source_html_sha256 === meta.content && p.session_date === currentSession);
    section.dataset.rankingState = fresh ? 'current' : 'previous';
    section.querySelector('.jev-asof').textContent = (fresh ? '' : '前回分（表示中のページと評価対象が不一致） ／ ') + '対象セッション '+(p.session_date || '—')+' ／ 評価時点 '+(p.available_at || '—');
    section.querySelector('.msec-q').textContent = p.rows.length+'銘柄をJev 3回評価'+(p.status === 'partial' ? '（一部評価失敗）' : '');
    var host = section.querySelector('.jev-empty').parentElement;
    if (!p.rows.length) { host.querySelector('.jev-empty').textContent='Jev評価データはまだありません。'; return; }
    var body = p.rows.map(function(row, i) {
      var score = num(row.expected_value_score) ? (Number(row.expected_value_score)>=0?'+':'')+Number(row.expected_value_score).toFixed(1) : '—';
      return '<tr class="jev-click" tabindex="0" role="button" data-ticker="'+esc(row.ticker)+'" aria-label="'+esc(row.ticker)+'の銘柄情報を開く">'+
        '<td class="jev-ticker"><b>'+esc(row.ticker)+'</b><span>'+esc((row.candidate_sources || ['候補']).join(' / '))+'</span></td>'+
        '<td class="jev-score">'+score+'</td><td class="jev-rank">'+(i+1)+'</td><td class="jev-rs">'+[row.rs21,row.rs63,row.rs189].map(rs).join('・')+'</td>'+
        '<td>'+pct(row.catalyst_probability)+'</td><td>'+pct(row.risk_probability)+'</td>'+
        '<td class="jev-driver">'+esc(row.top_catalyst_label)+'<span>'+pct(row.top_catalyst_probability)+'</span></td>'+
        '<td class="jev-driver">'+esc(row.top_risk_label)+'<span>'+pct(row.top_risk_probability)+'</span></td></tr>';
    }).join('');
    host.innerHTML='<div class="jev-table-wrap"><table class="ptab jev-table"><thead><tr><th class="l">銘柄・候補元</th><th>期待値</th><th>#</th><th>RS 21・63・189</th><th>好材料</th><th>リスク</th><th class="l">最大の好材料</th><th class="l">最大のリスク</th></tr></thead><tbody>'+body+'</tbody></table></div>';
    host.querySelectorAll('[data-ticker]').forEach(function(row) {
      function open() { if(typeof window.showDet === 'function') window.showDet(row.dataset.ticker); }
      row.addEventListener('click', open);
      row.addEventListener('keydown', function(e) { if(e.key==='Enter'||e.key===' ') { e.preventDefault(); open(); } });
    });
  }).catch(function() {
    section.dataset.rankingState='unavailable';
    section.querySelector('.msec-q').textContent='取得できませんでした';
    section.querySelector('.jev-empty').textContent='Jev評価を取得できませんでした。再読み込みしてください。';
  });
})();
