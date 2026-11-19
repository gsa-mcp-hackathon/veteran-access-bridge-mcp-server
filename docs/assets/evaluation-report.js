/* Static, local-only filterable checkpoint viewer. No network destinations except the bundled JSON. */
(function(){
  const root=document.getElementById('vab-eval-report'); if(!root) return;
  const rows=[
    ['Server','2026-11-16','Linux backend regression','1,380 passed · 19 skipped','pass','Historical Linux suite; distinct from Windows'],
    ['MCP','2026-11-16','MCP contract probes','108 / 108 passed','pass','25-tool local configuration'],
    ['Security','2026-11-16','Hostile argument probes','76 / 76 passed','pass','Bounded local arguments'],
    ['Security','2026-11-16','Schema & scope assertions','261 / 261 passed','pass','Overlapping checks; not distinct test cases'],
    ['Voice','2026-11-16','Synthetic RTC booking','PASS · 1 appointment + 1 CRM note','pass','One dated call and persisted record'],
    ['Voice','2026-11-18','Spoken identity only','PASS · captions masked','pass','No booking attempted'],
    ['Server','2026-11-18','Windows full pytest','1,624 passed · 19 skipped · 1 failed','mixed','Platform-specific os.O_NOFOLLOW failure'],
    ['Developer','2026-11-18','Locked install','FAILED · lock update needed','open','Editable installation separately passed'],
    ['Developer','2026-11-18','Focused lint','FAILED · E501','open','Known existing line-length finding'],
    ['MCP','2026-11-18','Baseline local discovery','21 schemas','pass','In-process only'],
    ['MCP','2026-11-18','Enabled inventory and Avery','29 registered · 21 attached','pass','Inventory not behavioral pass']
  ];
  const controls=document.createElement('div');controls.className='eval-controls';
  const q=document.createElement('input');q.placeholder='Search checkpoints';q.setAttribute('aria-label','Search checkpoints');
  const cat=document.createElement('select');cat.setAttribute('aria-label','Category filter');
  ['All categories','Server','MCP','Security','Voice','Developer'].forEach((s,i)=>{let o=document.createElement('option');o.value=i?s:'';o.textContent=s;cat.appendChild(o)});
  const status=document.createElement('select');status.setAttribute('aria-label','Status filter');
  [['','All outcomes'],['pass','Passed / verified'],['mixed','Mixed'],['open','Open / failed']].forEach(a=>{let o=document.createElement('option');o.value=a[0];o.textContent=a[1];status.appendChild(o)});
  controls.append(q,cat,status); const count=document.createElement('p');count.className='eval-count';const wrap=document.createElement('div');wrap.style.overflowX='auto';
  const table=document.createElement('table');const head=document.createElement('thead');head.innerHTML='<tr><th>Checkpoint</th><th>Observed</th><th>Context</th></tr>';const body=document.createElement('tbody');table.append(head,body);wrap.appendChild(table);root.replaceChildren(controls,count,wrap);
  function render(){let found=rows.filter(r=>(!cat.value||r[0]===cat.value)&&(!status.value||r[4]===status.value)&&(!q.value||r.join(' ').toLowerCase().includes(q.value.toLowerCase())));count.textContent=found.length+' of '+rows.length+' recorded checkpoints — historical evidence only';body.replaceChildren();for(const r of found){const tr=document.createElement('tr');const a=document.createElement('td');const b=document.createElement('td');const c=document.createElement('td');a.textContent=r[2]+' · '+r[1];let s=document.createElement('span');s.className='eval-state '+r[4];s.textContent=r[3];b.appendChild(s);c.textContent=r[5];tr.append(a,b,c);body.appendChild(tr)} }
  [q,cat,status].forEach(x=>x.addEventListener('input',render));render();
})();
