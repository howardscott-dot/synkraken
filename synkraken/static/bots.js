"use strict";
const $ = id => document.getElementById(id);
const state = {workspace: {}, bots: [], rooms: [], selected: null, data: {}, loading: false,
  pending: false, drafts: new Map(), requests: new Map(), timelineKey: '', cardKey: '', revision: 0};
const providerNames = {openrouter: 'OpenRouter', anthropic: 'Anthropic', openai: 'OpenAI', grok: 'Grok', minimax: 'MiniMax', ollama: 'Local · Ollama'};
function el(tag, className, text) { const n = document.createElement(tag); if(className) n.className = className; if(text !== undefined) n.textContent = text; return n; }
function button(label, action, parent) { const n = el('button','',label); n.type = 'button'; n.onclick = action; if(parent) parent.append(n); return n; }
async function api(path, body, method) {
  const response = await fetch('/api' + path, {method: method || (body === undefined ? 'GET' : 'POST'), headers: {'Content-Type':'application/json'}, ...(body === undefined ? {} : {body: JSON.stringify(body)}), cache:'no-store'});
  const value = await response.json(); if(!response.ok) throw Error(value.error || 'The request could not finish'); return value;
}
function notice(text='') { $('notice').textContent=text; $('notice').hidden=!text; }
function current() { return state.bots.find(b=>b.bot_id === state.selected?.id); }
function key() { return state.selected ? state.selected.kind + ':' + state.selected.id : 'setup'; }
function initials(name) { return name.split(/\s+/).slice(0,2).map(x=>x[0]).join('').toUpperCase(); }
const avatarColors={lagoon:'#55c7bd',violet:'#b0a0ee',coral:'#ef9f91',amber:'#edc56c',blue:'#86b9e8',mint:'#9bd5a7'};
function avatar(bot={}) {
  const node=el('span','avatar'+(bot.status==='working'?' working':''));
  const color=avatarColors[bot.avatar_color]||avatarColors.lagoon;
  const shapes={
    kraken:'<path d="M18 37C18 8 62 8 62 37V49Q70 64 59 65Q54 65 52 55Q48 74 40 59Q32 74 28 55Q26 65 21 65Q10 64 18 49Z"/>',
    ray:'<path d="M40 17Q52 17 58 31L74 49Q77 58 61 54L48 50Q44 63 40 70Q36 63 32 50L19 54Q3 58 6 49L22 31Q28 17 40 17Z"/>',
    diver:'<rect x="16" y="18" width="48" height="47" rx="21"/><path d="M54 23V12Q54 7 61 7H65V14H62V28Z"/>'};
  node.innerHTML=`<svg viewBox="0 0 80 80" aria-hidden="true"><g fill="${color}">${shapes[bot.avatar_style]||shapes.kraken}</g><ellipse cx="40" cy="37" rx="19" ry="13" fill="#173b48"/><ellipse cx="33" cy="36" rx="4" ry="6" fill="#f4fcff"/><ellipse cx="47" cy="36" rx="4" ry="6" fill="#f4fcff"/><circle cx="34" cy="38" r="2" fill="#173b48"/><circle cx="48" cy="38" r="2" fill="#173b48"/><path d="M36 53Q40 56 44 53" fill="none" stroke="#173b48" stroke-width="2" stroke-linecap="round"/></svg>`;
  return node;
}
function drawAvatarPicker(bot) {
  const picker=$('avatar-picker');picker.replaceChildren();
  state.avatarDraft={avatar_style:bot?.avatar_style||'kraken',avatar_color:bot?.avatar_color||'lagoon'};
  const redraw=()=>{
    $('settings-avatar').replaceChildren(avatar(state.avatarDraft));
    for(const b of picker.querySelectorAll('button'))b.setAttribute('aria-pressed',String(state.avatarDraft[b.dataset.field]===b.dataset.value));
  };
  for(const [field,values] of [['avatar_style',['kraken','ray','diver']],['avatar_color',Object.keys(avatarColors)]]) {
    const row=el('div','avatar-options');picker.append(row);
    for(const value of values){const b=button('',()=>{state.avatarDraft[field]=value;redraw();},row);b.dataset.field=field;b.dataset.value=value;b.setAttribute('aria-label',value+' '+(field==='avatar_style'?'character':'colour'));
      if(field==='avatar_style')b.append(avatar({avatar_style:value}));else{b.style.background=avatarColors[value];b.className='colour-swatch';}}
  }
  redraw();
}
async function capabilitiesCard() {
  if($('capability-card')){$('capability-card').remove();return;}
  const bot=current();if(!bot){notice('Connect your first model, then add capabilities from here.');return;}
  const card=cardShell('Equip this bot','Choose something to discuss. Changes are reviewed in chat before they are applied.');card.id='capability-card';
  button('Close',()=>card.remove(),card).className='card-close';
  const search=el('input');search.type='search';search.placeholder='Find a capability';search.setAttribute('aria-label','Find a capability');card.append(search);
  const rows=el('div','capability-list');card.append(rows);
  const groups=[
    ['Browser','Navigate pages and work on the web.',['browser_open','browser_read','browser_click','browser_type','browser_scroll']],
    ['Memory','Keep useful context between conversations.',['memory_read','memory_write']],
    ['Files','Read and write in this bot’s workspace.',['workspace_list','read_file','write_file']],
    ['Portable skills','Use the skills available on this host.',['skills_list','skill_read']],
    ['Delegation','Discuss which bots may work together.',[]],
    ['Model connections','Connect another provider or choose a different model.',[]]
  ];
  const fill=()=>{rows.replaceChildren();for(const [name,description,tools] of groups.filter(g=>(g[0]+' '+g[1]).toLowerCase().includes(search.value.toLowerCase()))) {
    const row=el('div','capability-row');const enabled=tools.length&&tools.every(t=>bot.tools?.includes(t));
    row.append(el('strong','',name),el('p','',description));
    button(enabled?'Discuss settings':'Discuss in chat',async()=>{await select({kind:'bot',id:state.workspace.home_bot_id});$('message').value=`Help me ${enabled?'review':'set up'} ${name.toLowerCase()} for ${bot.name}.`;$('message').focus();},row);rows.append(row);
    if(enabled)row.append(el('span','capability-status','Enabled'));
  }};search.oninput=fill;fill();
  try {const catalog=await api('/v1/workspace/capabilities');if(!card.isConnected)return;
    card.append(el('p','',catalog.skills.length?`Available skills: ${catalog.skills.map(s=>s.name).join(', ')}`:'No portable skills found on this host.'));
    card.append(el('p','capability-status','MCP connections and app plugins are not available in this build yet.'));
  }catch(e){card.append(el('p','card-error',e.message));}
}
function inlineMarkdown(node,text) {
  const pattern=/(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g;let start=0;
  for(const match of text.matchAll(pattern)){
    node.append(document.createTextNode(text.slice(start,match.index)));const value=match[0];
    if(value.startsWith('`'))node.append(el('code','',value.slice(1,-1)));
    else if(value.startsWith('**'))node.append(el('strong','',value.slice(2,-2)));
    else{const parts=value.match(/^\[([^\]]+)\]\((.+)\)$/);const link=el('a','',parts[1]);link.href=parts[2];link.target='_blank';link.rel='noopener noreferrer';node.append(link);}
    start=match.index+value.length;
  }
  node.append(document.createTextNode(text.slice(start)));
}
function markdown(text) {
  const result=el('div','bubble formatted'),lines=String(text).split('\n');let i=0;
  const cells=line=>line.trim().replace(/^\||\|$/g,'').split('|').map(s=>s.trim());
  while(i<lines.length){const line=lines[i];if(!line.trim()){i++;continue;}
    if(line.startsWith('```')){let code=[];i++;while(i<lines.length&&!lines[i].startsWith('```'))code.push(lines[i++]);i++;const pre=el('pre');pre.append(el('code','',code.join('\n')));result.append(pre);continue;}
    if(line.includes('|')&&i+1<lines.length&&/^\s*\|?\s*:?-{3,}/.test(lines[i+1])){const table=el('table'),head=el('tr');for(const value of cells(line)){const th=el('th');inlineMarkdown(th,value);head.append(th);}table.append(head);i+=2;while(i<lines.length&&lines[i].includes('|')){const row=el('tr');for(const value of cells(lines[i++])){const td=el('td');inlineMarkdown(td,value);row.append(td);}table.append(row);}const wrapper=el('div','table-scroll');wrapper.append(table);result.append(wrapper);continue;}
    const heading=line.match(/^(#{1,6})\s+(.+)/);if(heading){const h=el('h'+Math.min(heading[1].length+1,6));inlineMarkdown(h,heading[2]);result.append(h);i++;continue;}
    if(/^\s*[-*]\s+/.test(line)){const list=el('ul');while(i<lines.length&&/^\s*[-*]\s+/.test(lines[i])){const item=el('li');inlineMarkdown(item,lines[i++].replace(/^\s*[-*]\s+/,''));list.append(item);}result.append(list);continue;}
    const paragraph=el('p');inlineMarkdown(paragraph,line);result.append(paragraph);i++;
  }
  return result;
}
function message(text, user=false, timestamp) {
  const row=el('article','message'+(user?' user':'')); row.append(user?el('div','bubble',text):markdown(text));
  if(timestamp) row.append(el('time','',new Date(timestamp).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})));
  $('timeline').append(row); return row;
}
function roster() {
  const query=$('search').value.toLowerCase(); $('roster').replaceChildren();
  const bots=state.bots.length?state.bots:[{bot_id:'setup',name:'SynKraken',job:''}];
  for(const bot of bots.filter(b=>(b.name+' '+b.job).toLowerCase().includes(query))) {
    const n=button('',()=>select(bot.bot_id==='setup'?null:{kind:'bot',id:bot.bot_id}));
    n.className='bot-item'+((state.selected?.id===bot.bot_id || (!state.selected && bot.bot_id==='setup'))?' selected':'');
    n.setAttribute('aria-label',bot.name); n.setAttribute('aria-pressed',String(state.selected?.id===bot.bot_id));
    n.append(avatar(bot),el('span','bot-name',bot.name));
    if(bot.label||bot.job) n.append(el('span','bot-role',bot.label||bot.job)); $('roster').append(n);
  }
  $('channel-section').hidden=!state.rooms.length; $('channels').replaceChildren();
  for(const room of state.rooms) { const b=button(room.name,()=>select({kind:'room',id:room.name}),$('channels')); b.className='channel-item'; }
}
function header() {
  const bot=current(), setup=!state.selected;
  document.body.classList.toggle('setting-up',setup);
  $('title').textContent=bot?.name || (state.selected?.kind==='room'?state.selected.id:'SynKraken');
  $('header-avatar').replaceChildren(avatar(bot));
  $('presence').textContent=setup?'Setup':bot?.status==='working'?'Working…':bot?.status==='unavailable'?'Connection needed':'';
  const working=state.pending||bot?.status==='working';
  document.querySelectorAll('[data-wait-idle]').forEach(b=>b.disabled=working);
  $('send').disabled=working; $('stop').hidden=!bot?.last_run||bot.status!=='working';
  $('message').placeholder=setup?(state.workspace.step==='model'?'Which model would you like to use?':'Talk to SynKraken…'):`Talk to ${$('title').textContent}…`;
  $('composer-note').textContent=setup?'One model to start. Build the rest in conversation.':'';
}
async function select(selected) {
  state.drafts.set(key(),$('message').value); state.selected=selected; state.revision++; state.timelineKey=''; state.cardKey='';
  $('message').value=state.drafts.get(key())||''; $('inspector').hidden=true;
  try { localStorage.setItem('synkraken.chat.selection',JSON.stringify(selected)); } catch {}
  notice(); roster(); header(); await loadConversation();
}
function cardShell(title, description) {
  const card=el('section','input-card'); card.append(el('h2','',title)); if(description)card.append(el('p','',description));
  $('input-cards').append(card); return card;
}
function privateField(card,label,name) {
  const id='secure-'+name+'-'+crypto.randomUUID(); const caption=el('label','',label); caption.htmlFor=id;
  const input=el('input'); input.id=id; input.name=name; input.type='password'; input.autocomplete='off'; input.spellcheck=false; input.required=true; input.maxLength=4096;
  card.append(caption,input); return input;
}
async function submitCard(card, action, refreshAfter=true) {
  const buttons=[...card.querySelectorAll('button')]; buttons.forEach(b=>b.disabled=true);
  let error=card.querySelector('.card-error'); if(!error){error=el('p','card-error');error.setAttribute('role','alert');card.append(error);} error.textContent='';
  try { await action(); notice(); card.querySelectorAll('input').forEach(input=>input.value=''); if(refreshAfter){state.cardKey=''; await refresh(true);} }
  catch(e){error.textContent=e.message;}
  finally {buttons.forEach(b=>b.disabled=false);}
}
function connectionCard(provider, cardId='') {
  const name=providerNames[provider];
  const card=cardShell(provider==='ollama'?'Connect your local model':`Connect ${name}`,
    provider==='ollama'?'SynKraken will use the model server on localhost:11434.':
    'Credentials go directly to the encrypted host vault. They are never sent as chat messages. The master key stays in your host keychain. Cloud sync is not connected.');
  const save=payload=>cardId?api('/v1/chat-cards/'+cardId,payload):api('/v1/workspace/setup',{action:'connect',...payload});
  if(provider==='ollama') {button('Use local model',()=>submitCard(card,()=>save({})),card);return;}
  if(['anthropic','openai','grok'].includes(provider)) card.append(el('p','auth-status','Account sign-in is not connected in this build yet. An API key is an optional, separately billed connection.'));
  if(provider==='minimax') card.append(el('p','','Using a Coding/Token Plan? Use its Subscription Key from Billing → Token Plan. A pay-as-you-go API key uses a separate balance. Choose a model available on your plan.'));
  const actions=el('div','actions');card.append(actions);
  if(provider==='openrouter') button('Sign in with OpenRouter',()=>submitCard(card,async()=>{
    const flow=await api('/v1/workspace/oauth/start',{card_id:cardId});
    actions.replaceChildren();
    const link=el('a','action','Continue to OpenRouter ↗');link.href=flow.authorization_url;link.target='_blank';link.rel='noopener noreferrer';actions.append(link);
    card.append(el('p','','After authorizing, paste the one-time code here. It expires after ten minutes.'));
    const input=privateField(card,'One-time authorization code','code');
    button('Finish sign-in',()=>submitCard(card,()=>api('/v1/workspace/oauth/finish',{flow_id:flow.flow_id,code:input.value})),card);
    button('Start sign-in again',()=>{state.cardKey='';renderCards();},card);
  },false),actions);
  button(provider==='openrouter'?'Use an API key instead':'Enter API key',()=>{
    actions.replaceChildren(); const input=privateField(card,`${name} API key`,'api_key');
    button('Save securely',()=>submitCard(card,()=>save({api_key:input.value})),card); input.focus();
  },actions);
}
function renderSetup() {
  const w=state.workspace;const signature=JSON.stringify(w);
  if(state.timelineKey===signature) return;
  state.timelineKey=signature; $('timeline').replaceChildren();
  message('Which provider should power your first conversation? You can mix models later.');
  if(w.provider_kind) {
    message(providerNames[w.provider_kind],true);
    message('Name the model you want to start with. Use the model ID from your provider.');
    if(w.model){message(w.model,true);message('Connect below, then start talking. Your first bot is a blank slate; you decide what it becomes.');}
  }
  renderCards();
}
function renderCards() {
  const cards=state.selected?state.data.cards||[]:[];
  const signature=JSON.stringify([key(),state.selected?cards:state.workspace,state.data.runs?.[0]?.error]);
  if(signature===state.cardKey) return;
  state.cardKey=signature; $('input-cards').replaceChildren();
  if(!state.selected) {
    const w=state.workspace;
    if(!w.provider_kind) {
      const card=cardShell('Your default model','Choose where to connect.');const actions=el('div','actions');card.append(actions);
      for(const [provider,name] of Object.entries(providerNames).filter(([id])=>id!=='ollama')) button(name,()=>submitCard(card,()=>api('/v1/workspace/setup',{action:'select',provider})),actions);
      const local=el('details');local.append(el('summary','','Use a model on this device'));button(providerNames.ollama,()=>submitCard(card,()=>api('/v1/workspace/setup',{action:'select',provider:'ollama'})),local);card.append(local);
      if(w.providers?.length) {
        card.append(el('p','','You already have provider connections. Choose one and enter a model in chat, or add another above.'));
        for(const p of w.providers) button(p.name,()=>{state.existingProvider=p.provider_id;notice('Type the model ID for '+p.name+' in the message box.');$('message').focus();},actions);
      }
    } else if(w.step==='model'&&w.provider_kind==='minimax') {
      const card=cardShell('Choose your MiniMax model','Pick a model included in your account, or type another model ID in chat.');const actions=el('div','actions');card.append(actions);
      for(const model of ['MiniMax-M3','MiniMax-M2.7','MiniMax-M2.5'])button(model,()=>submitCard(card,()=>api('/v1/workspace/setup',{action:'model',model})),actions);
    } else if(w.step==='connect') {connectionCard(w.provider_kind);button('Choose a different model or provider',()=>{api('/v1/workspace/setup',{action:'restart'}).then(()=>refresh(true)).catch(e=>notice(e.message));},$('input-cards').lastElementChild);}
    return;
  }
  for(const item of cards.filter(c=>c.status==='pending')) {
    if(item.kind==='connection') {connectionCard(item.provider,item.card_id);continue;}
    if(item.kind==='capability') {
      const card=cardShell('Enable '+item.capability+' for '+item.target_name,item.reason);
      card.append(el('p','','This enables the requested tools. Websites still require their own access approval.'));
      const apply=button('Enable and continue',()=>submitCard(card,async()=>{
        await api('/v1/chat-cards/'+item.card_id,{approve:true});
      }),card);apply.dataset.waitIdle='true';apply.disabled=current()?.status==='working';
      button('Not now',()=>submitCard(card,()=>api('/v1/chat-cards/'+item.card_id,{cancel:true})),card);continue;
    }
    if(item.kind==='browser_access') {
      const card=cardShell('Browser access',`Allow this bot to navigate and interact with ${item.origin}? Other sites remain blocked until allowed.`);
      const allow=button('Allow site and continue',()=>submitCard(card,async()=>{
        await api('/v1/chat-cards/'+item.card_id,{approve:true});
        showDrawer('browser');
      }),card);allow.dataset.waitIdle='true';allow.disabled=current()?.status==='working';
      button('Dismiss',()=>submitCard(card,()=>api('/v1/chat-cards/'+item.card_id,{cancel:true})),card);continue;
    }
    const card=cardShell(item.kind==='credential'?`Secure input · ${item.service}`:`Update ${item.target_name}`,
      item.kind==='credential'?`${item.purpose}\nEncrypted on this host. Not shared with the model. Saving does not sign in to the service. Cloud sync is not connected.`:'Review this change from your conversation.');
    if(item.kind==='credential') {
      const username=privateField(card,'Username','username'),password=privateField(card,'Password','password');
      button('Save securely',()=>submitCard(card,()=>api('/v1/chat-cards/'+item.card_id,{username:username.value,password:password.value})),card);
    } else {
      for(const [name,value] of Object.entries(item.changes||{})) card.append(el('p','',`${name.replaceAll('_',' ')}: ${Array.isArray(value)?value.join(', '):value}`));
      button('Apply change',()=>submitCard(card,()=>api('/v1/chat-cards/'+item.card_id,{approve:true})),card);
    }
    button('Dismiss',()=>submitCard(card,()=>api('/v1/chat-cards/'+item.card_id,{cancel:true})),card);
  }
  const bot=current(), provider=state.workspace.providers?.find(p=>p.provider_id===bot?.provider_id);
  const error=state.data.runs?.[0]?.error||'';
  if(provider&&/HTTP (402|401)/.test(error)) {
    const minimax=provider.base_url==='https://api.minimax.io/anthropic/v1';
    const card=cardShell(minimax?'Reconnect MiniMax':'Reconnect your provider',minimax?
      'For a Coding/Token Plan, use the Subscription Key from Billing → Token Plan. Pay-as-you-go API keys use a separate balance. Your bots and conversations will stay here.':
      'Check the account and allowance for this connection, or replace its key below. Your bots and conversations will stay here.');
    if(minimax){const link=el('a','action','Find your MiniMax Subscription Key ↗');link.href='https://platform.minimax.io/docs/token-plan/quickstart';link.target='_blank';link.rel='noopener noreferrer';card.append(link);}
    const input=privateField(card,minimax?'MiniMax Subscription Key or API key':'Replacement API key','replacement_key');
    button('Update connection',()=>submitCard(card,async()=>{
      if(!input.value.trim())throw Error('Enter your replacement key in the secure field.');
      await api('/v1/providers/'+provider.provider_id,{api_key:input.value.trim()},'PATCH');
      input.value='';card.replaceChildren(el('h2','','Connection updated'),el('p','','Send your message again to try the updated connection.'));
    },false),card);
  }

}
function renderConversation() {
  const data=state.data, bot=current();
  const signature=JSON.stringify([key(),data.messages,data.runs,data.cards,bot?.status,bot?.avatar_style,bot?.avatar_color]);
  if(state.timelineKey!==signature) {
    state.timelineKey=signature;const timeline=$('timeline');const nearBottom=timeline.scrollHeight-timeline.scrollTop-timeline.clientHeight<120;
    const oldScroll=timeline.scrollTop;timeline.replaceChildren();
    if(!data.messages?.length) {const empty=el('div','empty');empty.append(avatar(bot),el('h2','','What shall we work on?'),el('p','','Start with a conversation. Give your bot a role whenever you’re ready.'));timeline.append(empty);}
    for(const item of data.messages||[]) {
      const row=message(item.error||item.body||'No response was recorded.',item.source==='operator'||item.metadata?.role==='user',item.timestamp);
      if(item.ok===false)row.classList.add('error');
    }
    if(bot?.status==='working') timeline.append(el('p','thinking','Working…'));
    for(const card of (data.cards||[]).filter(c=>c.status!=='pending')) timeline.append(el('div','receipt',
      `${card.kind==='credential'?'Secure input saved on this host':card.kind==='connection'?'Provider connection':card.kind==='browser_access'?`Browser access · ${card.origin}`:`Change to ${card.target_name}`} · ${card.status}`));
    for(const event of data.run_events||[]) {
      if(event.event_type!=='tool_finished'||event.data?.name!=='create_bot')continue;
      try {const created=JSON.parse(event.data.result);if(!created.created||!state.bots.some(b=>b.bot_id===created.bot_id))continue;
        const card=el('section','input-card');card.append(el('h2','',created.name+' is ready'));
        button('Talk to '+created.name,()=>select({kind:'bot',id:created.bot_id}),card);timeline.append(card);
      }catch{}
    }
    const run=data.runs?.[0];
    if(run){const details=el('details','run-disclosure');details.append(el('summary','',run.status==='done'?'Activity':`Run ${run.status}`));
      if(run.error)details.append(el('p','',run.error));
      for(const event of data.run_events||[]) {const n=el('p','',event.event_type.replaceAll('_',' ')+(event.data?.name?' · '+event.data.name:''));if(event.data?.result)n.append(el('pre','',event.data.result));details.append(n);}timeline.append(details);}
    timeline.scrollTop=nearBottom?timeline.scrollHeight:oldScroll;
  }
  renderCards();renderContext();if(!$('inspector').hidden&&!$('browser-pane').hidden)refreshBrowser();
}
function showDrawer(mode) {
  $('inspector').hidden=false;
  for(const name of ['context','browser','settings']) {$(name+'-pane').hidden=name!==mode;$('show-'+name).classList.toggle('selected',name===mode);}
  if(mode==='settings') {
    const bot=current();
    drawAvatarPicker(bot);
    $('settings-name').value=bot?.name||'';$('settings-label').value=bot?.label||'';
    $('settings-description').value=bot?.instructions||'';$('settings-status').textContent='';
  } else if(mode==='browser')refreshBrowser();else renderContext();
}
async function refreshBrowser() {
  const id=current()?.bot_id;if(!id){$('browser-status').textContent='Finish setup to open a bot browser.';return;}
  try {const browser=await api('/v1/bots/'+id+'/browser');if(current()?.bot_id!==id)return;
    $('browser-image-button').hidden=!browser.image;
    if(browser.image&&$('browser-image').src!==browser.image)$('browser-image').src=browser.image;
    $('browser-status').textContent=browser.open?(browser.title+' · '+browser.url):'This bot’s browser has not opened a page yet.';
    if(document.activeElement!==$('browser-url')&&browser.url)$('browser-url').value=browser.url;
  }catch(e){$('browser-status').textContent=e.message;}
}
async function browserAction(payload) {
  const bot=current();if(!bot){notice('Finish setup first.');return;}
  try {const result=await api('/v1/bots/'+bot.bot_id+'/browser',payload);await refresh(true);await refreshBrowser();if(result.status==='waiting_for_user')notice('Allow the site in the conversation card to continue.');}
  catch(e){$('browser-status').textContent=e.message;}
}
$('show-context').onclick=()=>showDrawer('context');$('show-settings').onclick=()=>showDrawer('settings');$('show-browser').onclick=()=>showDrawer('browser');
$('basic-settings').onsubmit=async event=>{
  event.preventDefault();const bot=current();if(!bot)return;
  try {await api('/v1/bots/'+bot.bot_id,{...state.avatarDraft,name:$('settings-name').value,label:$('settings-label').value,instructions:$('settings-description').value},'PATCH');$('settings-status').textContent='Saved';await refresh(true);}
  catch(e){$('settings-status').textContent=e.message;}
};
$('browser-address').onsubmit=event=>{event.preventDefault();browserAction({action:'open',url:$('browser-url').value});};
$('browser-refresh').onclick=()=>browserAction({action:'read'});$('browser-up').onclick=()=>browserAction({action:'scroll',direction:'up'});$('browser-down').onclick=()=>browserAction({action:'scroll',direction:'down'});
$('browser-image-button').onclick=event=>{const rect=$('browser-image').getBoundingClientRect();browserAction({action:'point',x:(event.clientX-rect.left)*1200/rect.width,y:(event.clientY-rect.top)*800/rect.height});};
function renderContext() {
  const bot=current();$('context').replaceChildren();$('activity').replaceChildren();
  if(!bot){$('context').append(el('p','','Choose your default model to begin.'));return;}
  for(const [label,text] of [['Model',bot.model||bot.runtime?.model],['Role',bot.job],['Instructions',bot.instructions],['Memory',state.data.memories?.map(m=>m.body).join('\n')]]) {
    if(text)$('context').append(el('div','label',label),el('p','',text));
  }
  for(const run of (state.data.runs||[]).slice(0,10)) $('activity').append(el('p','',`${run.body.slice(0,100)}\n${run.status}`));
}
async function loadConversation() {
  if(!state.selected){renderSetup();return;}
  const selected=state.selected,revision=state.revision;
  try {const data=await api(selected.kind==='bot'?`/v1/bots/${selected.id}/conversation`:`/v1/rooms/${encodeURIComponent(selected.id)}/messages?limit=100`);
    if(revision!==state.revision)return;state.data=data;renderConversation();}
  catch(e){notice(e.message);}
}
async function refresh(force=false) {
  if(state.loading&&!force)return;state.loading=true;
  try {
    const [workspace,bots,rooms]=await Promise.all([api('/v1/workspace'),api('/v1/bots'),api('/v1/rooms')]);
    state.workspace=workspace;state.bots=bots.bots;state.rooms=rooms.rooms;
    if(state.selected?.kind==='bot'&&!current())state.selected=null;
    if(!state.selected&&workspace.home_bot_id){state.selected={kind:'bot',id:workspace.home_bot_id};state.timelineKey='';state.cardKey='';state.revision++;}
    $('connection').textContent='Local workspace'; roster();header();await loadConversation();
  } catch(e){$('connection').textContent='Connection interrupted';notice(e.message);}
  finally{state.loading=false;}
}
$('composer').onsubmit=async event=>{
  event.preventDefault();const body=$('message').value.trim();if(!body||state.pending)return;
  const selected=state.selected,selectionKey=key();state.pending=true;header();notice();
  try {
    if(!selected) {
      if(state.existingProvider){await api('/v1/workspace/setup',{action:'use_existing',provider_id:state.existingProvider,model:body});state.existingProvider=null;}
      else if(!state.workspace.provider_kind){const provider=Object.keys(providerNames).find(p=>p===body.toLowerCase());if(!provider)throw Error('Choose a provider in the card above, then type your model.');await api('/v1/workspace/setup',{action:'select',provider});}
      else if(state.workspace.step==='model')await api('/v1/workspace/setup',{action:'model',model:body});
      else throw Error('Use the secure card above to connect. Keep credentials out of chat.');
    } else if(selected.kind==='bot') {
      let request=state.requests.get(selectionKey);if(!request||request.body!==body){request={body,id:crypto.randomUUID()};state.requests.set(selectionKey,request);}
      await api(`/v1/bots/${selected.id}/runs`,{body,request_key:request.id});state.requests.delete(selectionKey);
    } else await api('/v1/messages',{source:'operator',target:'room:'+selected.id,body});
    state.drafts.delete(selectionKey);if(selectionKey===key())$('message').value='';
  }catch(e){notice(e.message);}finally{state.pending=false;await refresh(true);header();}
};
$('message').onkeydown=event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();$('composer').requestSubmit();}};
$('new-chat').onclick=async()=>{if(state.workspace.home_bot_id){await select({kind:'bot',id:state.workspace.home_bot_id});$('message').value='Create a new bot ';$('message').focus();}else{$('message').focus();}};
$('search').oninput=roster;
$('capabilities-toggle').onclick=capabilitiesCard;
$('details-toggle').onclick=()=>{if($('inspector').hidden)showDrawer('context');else $('inspector').hidden=true;};
$('stop').onclick=async()=>{try{await api('/v1/bot-runs/'+current().last_run.run_id+'/cancel',{});notice('Stopping after the current operation finishes.');}catch(e){notice(e.message);}};
try{const saved=JSON.parse(localStorage.getItem('synkraken.chat.selection'));if(saved&&['bot','room'].includes(saved.kind)&&typeof saved.id==='string')state.selected=saved;}catch{}
document.querySelector('.brand-mark').replaceChildren(avatar());
refresh();setInterval(()=>{if(!document.hidden)refresh();},3000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
