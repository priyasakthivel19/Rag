const $ = id => document.getElementById(id);
const fileInput=$('fileInput'), drop=$('drop'), fileList=$('fileList'), buildBtn=$('buildBtn'),
      status=$('status'), chat=$('chat'), questionInput=$('questionInput'), sendBtn=$('sendBtn'),
      minScore=$('minScore'), minScoreVal=$('minScoreVal'), topSub=$('topSub'),
      themeToggle=$('themeToggle'), streamToggle=$('streamToggle'),
      exportTxtBtn=$('exportTxtBtn'), exportPdfBtn=$('exportPdfBtn'), clearChatBtn=$('clearChatBtn');

const HISTORY_KEY = 'rag_chat_messages_v1';
const THEME_KEY = 'rag_chat_theme';

let pending = [];   // files chosen but not yet uploaded
let known = [];     // filenames already on the server
let history = [];   // {role, content}  - sent to the LLM
let messages = [];  // {role, content, sources, retrieved, usedDocs, latency} - shown + saved

minScore.oninput = () => minScoreVal.textContent = minScore.value;

// ============================== Theme ==============================
function applyTheme(t){
  document.documentElement.setAttribute('data-theme', t);
  themeToggle.textContent = t === 'light' ? '☀️' : '🌙';
  localStorage.setItem(THEME_KEY, t);
}
themeToggle.onclick = () => {
  const cur = document.documentElement.getAttribute('data-theme') || 'dark';
  applyTheme(cur === 'light' ? 'dark' : 'light');
};
applyTheme(localStorage.getItem(THEME_KEY) || 'dark');

// ============================== File picking ==============================
drop.onclick = () => fileInput.click();
['dragover','dragleave','drop'].forEach(ev=>drop.addEventListener(ev, e=>{
  e.preventDefault();
  drop.classList.toggle('drag', ev==='dragover');
}));
drop.addEventListener('drop', e=>{
  addFiles([...e.dataTransfer.files].filter(f=>f.type==='application/pdf'));
});
fileInput.onchange = () => addFiles([...fileInput.files]);

function addFiles(list){
  for(const f of list){
    if(!pending.find(x=>x.name===f.name) && !known.includes(f.name)) pending.push(f);
  }
  renderFileList();
}
function renderFileList(){
  fileList.innerHTML='';
  known.forEach(name=>{
    const row=document.createElement('div'); row.className='fileItem';
    row.innerHTML = `<span class="name">✅ ${name}</span>`;
    const rm=document.createElement('button'); rm.textContent='✕'; rm.title='Remove';
    rm.onclick=async()=>{
      await fetch('/api/files/'+encodeURIComponent(name), {method:'DELETE'});
      known = known.filter(n=>n!==name);
      renderFileList();
      setStatus('Removed ' + name + '. Click "Build index" to apply the change.', 'warn');
    };
    row.appendChild(rm);
    fileList.appendChild(row);
  });
  pending.forEach((f,i)=>{
    const row=document.createElement('div'); row.className='fileItem';
    row.innerHTML = `<span class="name">📄 ${f.name}</span>`;
    const rm=document.createElement('button'); rm.textContent='✕'; rm.title='Cancel';
    rm.onclick=()=>{pending.splice(i,1); renderFileList();};
    row.appendChild(rm);
    fileList.appendChild(row);
  });
  buildBtn.disabled = pending.length===0 && known.length===0;
}

function setStatus(text, cls){
  status.textContent = text;
  status.className = cls || '';
}

// ============================== Build index ==============================
buildBtn.onclick = async () => {
  buildBtn.disabled = true;
  try{
    if(pending.length){
      setStatus('Uploading PDFs...', 'warn');
      const fd = new FormData();
      pending.forEach(f=>fd.append('files', f));
      const res = await fetch('/api/upload', {method:'POST', body:fd});
      if(!res.ok) throw new Error('Upload failed: '+(await res.text()));
      const data = await res.json();
      known.push(...data.saved);
      pending = [];
      renderFileList();
    }
    setStatus('Parsing, chunking, embedding on the server...', 'warn');
    const res = await fetch('/api/build_index', {method:'POST'});
    if(!res.ok) throw new Error(await res.text());
    const stats = await res.json();
    if(stats.pages === 0){
      setStatus('No text extracted — these may be scanned/image PDFs (need OCR).', 'warn');
    } else {
      setStatus(`Indexed ✅ ${stats.files} file(s), ${stats.pages} pages, ${stats.chunks} chunks`, 'ok');
    }
    topSub.textContent = `${stats.chunks} chunks indexed`;
  } catch(err){
    setStatus('Error: '+err.message, 'warn');
  }
  buildBtn.disabled = false;
};

// ============================== Chat rendering ==============================
function escapeHtml(s){
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function renderBotInner(m){
  let html = escapeHtml(m.content).replace(/\n/g,'<br>');
  html += m.usedDocs
    ? '<span class="badge">from your PDFs</span>'
    : '<span class="badge general">general knowledge</span>';
  if(m.sources && m.sources.length){
    html += `<div class="sources"><details><summary>📎 ${m.sources.length} source(s)</summary>`;
    m.sources.forEach(s=>{
      html += `<div class="srcRow">${s.source} — page ${s.page} (score ${s.score.toFixed(2)})</div>`;
    });
    html += `</details></div>`;
  }
  if(m.latency !== undefined){
    html += `<div class="sources">⏱ ${m.latency}s</div>`;
  }
  return html;
}
function addMsgEl(role, html){
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.innerHTML = html;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}
function addTyping(){
  return addMsgEl('bot', '<div class="typing"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>');
}

function renderAllMessages(){
  chat.innerHTML = messages.length
    ? ''
    : '<div class="msg system">Ask anything. PDF-related questions use your uploaded documents; everything else is answered from general knowledge.</div>';
  messages.forEach(m=>{
    if(m.role === 'user'){
      addMsgEl('user', escapeHtml(m.content));
    } else {
      addMsgEl('bot', renderBotInner(m));
    }
  });
}

function saveMessages(){
  try{ localStorage.setItem(HISTORY_KEY, JSON.stringify(messages)); }catch(e){}
}
function loadMessages(){
  try{
    const raw = localStorage.getItem(HISTORY_KEY);
    if(raw){
      messages = JSON.parse(raw);
      history = messages.map(m=>({role:m.role, content:m.content}));
      renderAllMessages();
    }
  }catch(e){ messages=[]; history=[]; }
}

// ============================== Ask (streaming + non-streaming) ==============================
async function send(){
  const q = questionInput.value.trim();
  if(!q) return;
  questionInput.value='';

  messages.push({role:'user', content:q});
  addMsgEl('user', escapeHtml(q));
  saveMessages();

  const min_score = parseFloat(minScore.value);

  if(streamToggle.checked){
    await sendStreaming(q, min_score);
  } else {
    await sendNonStreaming(q, min_score);
  }
}

async function sendNonStreaming(q, min_score){
  const typingEl = addTyping();
  try{
    const res = await fetch('/api/ask', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({question:q, history, min_score})
    });
    if(!res.ok) throw new Error(await res.text());
    const out = await res.json();
    typingEl.remove();
    const m = {role:'assistant', content:out.answer, sources:out.sources, usedDocs:out.used_docs, latency:out.latency};
    messages.push(m);
    addMsgEl('bot', renderBotInner(m));
    history.push({role:'user', content:q});
    history.push({role:'assistant', content:out.answer});
    saveMessages();
  } catch(err){
    typingEl.remove();
    addMsgEl('bot', '⚠️ '+escapeHtml(err.message));
  }
}

async function sendStreaming(q, min_score){
  const el = addMsgEl('bot', '<span class="streamText"></span><span class="cursor"></span>');
  const textEl = el.querySelector('.streamText');
  let meta = {used_docs:false, sources:[]};
  let full = '';

  try{
    const res = await fetch('/api/ask_stream', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({question:q, history, min_score})
    });
    if(!res.ok || !res.body) throw new Error(await res.text());

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';

    while(true){
      const {done, value} = await reader.read();
      if(done) break;
      buf += decoder.decode(value, {stream:true});

      let idx;
      while((idx = buf.indexOf('\n\n')) !== -1){
        const rawEvent = buf.slice(0, idx);
        buf = buf.slice(idx+2);
        const lines = rawEvent.split('\n');
        const evLine = lines.find(l=>l.startsWith('event:'));
        const dataLine = lines.find(l=>l.startsWith('data:'));
        if(!dataLine) continue;
        const type = evLine ? evLine.slice(6).trim() : 'message';
        const data = JSON.parse(dataLine.slice(5).trim());

        if(type === 'meta'){
          meta = data;
        } else if(type === 'token'){
          full += data.text;
          textEl.textContent = full;
          chat.scrollTop = chat.scrollHeight;
        } else if(type === 'error'){
          throw new Error(data.message);
        } else if(type === 'done'){
          full = data.answer || full;
        }
      }
    }

    el.querySelector('.cursor')?.remove();
    const m = {role:'assistant', content:full, sources:meta.sources||[], usedDocs:meta.used_docs, latency:undefined};
    el.innerHTML = renderBotInner(m);
    messages.push(m);
    history.push({role:'user', content:q});
    history.push({role:'assistant', content:full});
    saveMessages();
  } catch(err){
    el.innerHTML = '⚠️ '+escapeHtml(err.message);
  }
}

sendBtn.onclick = send;
questionInput.addEventListener('keydown', e=>{ if(e.key==='Enter') send(); });

clearChatBtn.onclick = () => {
  messages = [];
  history = [];
  saveMessages();
  renderAllMessages();
};

// ============================== Export ==============================
function chatAsText(){
  if(!messages.length) return 'No conversation yet.';
  return messages.map(m=>{
    const who = m.role === 'user' ? 'You' : 'Bot';
    let block = `${who}: ${m.content}`;
    if(m.role === 'assistant' && m.sources && m.sources.length){
      block += '\nSources: ' + m.sources.map(s=>`${s.source} p.${s.page} (${s.score})`).join('; ');
    }
    return block;
  }).join('\n\n');
}
exportTxtBtn.onclick = () => {
  const blob = new Blob([chatAsText()], {type:'text/plain'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'rag_chat_' + new Date().toISOString().slice(0,19).replace(/[:T]/g,'-') + '.txt';
  a.click();
  URL.revokeObjectURL(a.href);
};
exportPdfBtn.onclick = () => {
  // Uses the browser's native print dialog with "Save as PDF" - no external library needed.
  window.print();
};

// ============================== Initial load ==============================
loadMessages();

(async () => {
  try{
    const res = await fetch('/api/status');
    const data = await res.json();
    known = data.files;
    minScore.value = data.default_min_score;
    minScoreVal.textContent = data.default_min_score;
    renderFileList();
    if(data.has_index){
      setStatus('Index ready ✅ (loaded from storage/)', 'ok');
    }
  } catch(e){
    setStatus('Cannot reach backend — is uvicorn running?', 'warn');
  }
})();
