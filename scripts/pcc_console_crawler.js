// 工程會函釋抓取 — 貼進 planpe 查詢頁的 DevTools Console 執行
// 先 TEST=true 抓5筆驗證；確認OK後改 TEST=false 抓全部。下載的 JSON 交給 build_db.py 或上傳給 Claude 建庫。
(async () => {
  const TEST = true;        // ★抓全部時改成 false
  const TEST_LIMIT = 5, DELAY = 700, PAGE_SIZE = 100;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const csrf = (document.cookie.match(/XSRF-TOKEN=([^;]+)/) || [])[1] || '';
  const LIST = '/prms/explainLetter/readPrmsExplainLetter';
  const DETAIL = '/prms/explainLetter/readPrmsExplainLetterContentDetail?pkPrmsRuleContent=';
  const dl = (t, n) => { const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([t], {type:'application/json'})); a.download = n; a.click(); };
  const body = p => new URLSearchParams([['_csrf',csrf],['pkPrmsRuleType',''],['article',''],
    ['article2',''],['paragraph',''],['item',''],['keyword1',''],['links','and'],['keyword2',''],
    ['explainNumberNo',''],['date',''],['date',''],['date',''],['date',''],['sorts','createDate'],
    ['pageSize',String(PAGE_SIZE)],['startDate',''],['endDate',''],['startNetDate',''],
    ['endNetDate',''],['paginationPage',String(p)]]).toString();
  let pks = [], page = 0;
  while (true) {
    const html = await (await fetch(LIST,{method:'POST',credentials:'include',
      headers:{'Content-Type':'application/x-www-form-urlencoded'},body:body(page)})).text();
    const got = [...new Set([...html.matchAll(/readExplainLetter\((\d+)\)/g)].map(m=>m[1]))];
    console.log(`清單第${page}頁：pk ${got.length} 個`);
    if (got.length === 0) {
      if (page === 0) { console.warn('第1頁抓不到pk→下載 list_page0.html'); dl(html,'list_page0.html'); return; }
      break;
    }
    got.forEach(x => { if (!pks.includes(x)) pks.push(x); });
    if (TEST) break;
    page++; await sleep(DELAY);
  }
  if (TEST) pks = pks.slice(0, TEST_LIMIT);
  console.log(`要抓 ${pks.length} 則明細…`);
  const out = [];
  for (let i = 0; i < pks.length; i++) {
    try {
      const h = await (await fetch(DETAIL+pks[i]+'&_csrf='+encodeURIComponent(csrf),{credentials:'include'})).text();
      const el = new DOMParser().parseFromString(h,'text/html').querySelector('#printExplain');
      out.push({pk:pks[i], html: el ? el.outerHTML : ''});
    } catch(e){ out.push({pk:pks[i], html:'', err:String(e)}); }
    if ((i+1)%20===0) console.log(`明細 ${i+1}/${pks.length}`);
    window.__pcc = out; await sleep(DELAY);
  }
  dl(JSON.stringify(out), TEST ? 'pcc_test.json' : 'pcc_letters.json');
  console.log('✅ 完成，已下載 JSON');
  window.__pccDump = () => dl(JSON.stringify(window.__pcc||[]), 'pcc_partial.json');
})();
