const state = { data: null, conversationId: null, renderedConversationId: null, jobQuery: '', creatives: [], creativeId: null, creativeSaveTimer: null, generationDays: 30, generationMode: 'AI_DECIDE', generationRequest: null, capabilities: [], transactions: [], masterCapabilityId: null, tiktokAccount: null, contentPlan: null, calendarDate: new Date(new Date().getFullYear(), new Date().getMonth(), 1), token: sessionStorage.getItem('infenergyToken') || '' };
const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char]));

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(path, { ...options, headers });
  const responseText = await response.text();
  let data = {};
  if (responseText) {
    try { data = JSON.parse(responseText); }
    catch { data = { error: responseText }; }
  }
  if (response.status === 401 || response.status === 403) showLogin('That password was not accepted.');
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function showLogin(error = '') {
  $('#app-shell').hidden = true;
  $('#login-screen').hidden = false;
  $('#login-error').textContent = error;
  $('#login-password').focus();
}

function showApp() {
  $('#login-screen').hidden = true;
  $('#app-shell').hidden = false;
  $('#login-error').textContent = '';
}

async function login(password) {
  state.token = password;
  const response = await fetch('/api/os/state', { headers: { Authorization: `Bearer ${password}` } });
  if (!response.ok) {
    state.token = '';
    sessionStorage.removeItem('infenergyToken');
    throw new Error('That password was not accepted.');
  }
  sessionStorage.setItem('infenergyToken', password);
  showApp();
  await load();
}

function toast(text) { const el = $('#toast'); el.textContent = text; el.classList.add('show'); setTimeout(() => el.classList.remove('show'), 2600); }
function inlineMarkup(value) { return esc(value).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>'); }
function richText(content) {
  const lines = String(content || '').split(/\r?\n/), output = [];
  for (let index = 0; index < lines.length;) {
    const line = lines[index].trim();
    if (!line) { index += 1; continue; }
    if (line.startsWith('|') && line.endsWith('|')) {
      const tableLines = [];
      while (index < lines.length && lines[index].trim().startsWith('|')) tableLines.push(lines[index++].trim());
      const rows = tableLines.filter((row) => !/^\|?[\s:|-]+\|?$/.test(row)).map((row) => row.slice(1, -1).split('|').map((cell) => cell.trim()));
      if (rows.length) output.push(`<div class="message-table"><table>${rows.map((row, rowIndex) => `<tr>${row.map((cell) => `<${rowIndex ? 'td' : 'th'}>${inlineMarkup(cell)}</${rowIndex ? 'td' : 'th'}>`).join('')}</tr>`).join('')}</table></div>`);
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) items.push(lines[index++].replace(/^\s*[-*]\s+/, ''));
      output.push(`<ul>${items.map((item) => `<li>${inlineMarkup(item)}</li>`).join('')}</ul>`);
      continue;
    }
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) { output.push(`<h${heading[1].length + 2}>${inlineMarkup(heading[2])}</h${heading[1].length + 2}>`); index += 1; continue; }
    output.push(`<p>${inlineMarkup(line)}</p>`); index += 1;
  }
  return output.join('');
}
function message(role, content, status = '') { const wrap = document.createElement('div'); wrap.className = `message ${role} ${status}`; wrap.innerHTML = role === 'assistant' ? `<span class="avatar">I</span><div><strong>Infenergy Intelligence</strong><div class="rich-message">${richText(content)}</div></div>` : `<div><strong>Owner</strong><p>${esc(content)}</p></div>`; $('#messages').append(wrap); $('#messages').scrollTop = $('#messages').scrollHeight; }
function operationOutput(source) {
  const execution = source?.execution || source || {};
  const candidates = [source?.creative, execution.result?.output, execution.result, execution.after_state?.output, execution.after_state];
  return candidates.find((item) => item?.package) || null;
}
function mediaUrl(path) {
  if (/^https?:\/\//i.test(String(path || ''))) return String(path);
  const fileName = String(path || '').replaceAll('\\', '/').split('/').pop();
  return fileName ? `/media/${encodeURIComponent(fileName)}` : '';
}
function executionMessage() {
  const wrap = document.createElement('div');
  wrap.className = 'message assistant';
  wrap.innerHTML = '<span class="avatar">I</span><div class="execution-message"><strong>Infenergy Intelligence</strong><div class="execution-live" role="status"><span class="execution-spinner"></span><div><b>Approval accepted</b><small>Waiting for the durable transaction to start…</small></div></div></div>';
  $('#messages').append(wrap);
  $('#messages').scrollTop = $('#messages').scrollHeight;
  return wrap;
}
function updateExecutionMessage(wrap, transaction) {
  const status = transaction?.status || 'PLANNING';
  const running = ['PLANNING', 'RUNNING'].includes(status);
  const title = status === 'RUNNING' ? 'Creating and validating deliverables' : status === 'FAILED' ? 'Execution failed' : status === 'COMPLETED' ? 'Deliverables complete' : 'Approval accepted';
  const detail = transaction?.id ? `Transaction ${transaction.id} · ${humanize(status)} · updated ${relativeTime(transaction.updated_at)}` : 'Waiting for the durable transaction to start…';
  wrap.querySelector('.execution-live').className = `execution-live ${tone(status)}`;
  wrap.querySelector('.execution-live').innerHTML = `${running ? '<span class="execution-spinner"></span>' : `<span class="execution-state">${status === 'FAILED' ? '!' : '✓'}</span>`}<div><b>${esc(title)}</b><small>${esc(detail)}</small></div>`;
}
function renderDeliverables(source, target = null) {
  const execution = source?.execution || source || {};
  const output = operationOutput(source);
  if (!output) return false;
  const packageValue = output.package || {};
  const slides = packageValue.carousel_slides || [];
  const assets = packageValue.carousel_assets || output.assets || [];
  const copies = packageValue.platform_posts || {};
  const validation = output.asset_validation || [];
  const transactionId = execution.transaction_id || execution.id || source?.id || '';
  const rollbackAvailable = Boolean(execution.rollback_available || execution.rollback_data && Object.keys(execution.rollback_data).length);
  const images = assets.map((asset, index) => {
    const url = mediaUrl(typeof asset === 'string' ? asset : asset.public_url || asset.local_path || asset.path || asset.url);
    const slide = slides[index] || {};
    return `<article class="deliverable-slide">${url ? `<a href="${esc(url)}" target="_blank" rel="noopener"><img src="${esc(url)}" alt="Carousel slide ${index + 1}" loading="lazy"></a>` : ''}<div><b>${index + 1}/${Math.max(assets.length, slides.length)}</b><strong>${esc(slide.on_image_headline || slide.headline || `Slide ${index + 1}`)}</strong><span>${esc(slide.on_image_subline || slide.supporting || '')}</span></div></article>`;
  }).join('');
  const captions = Object.entries(copies).map(([platform, value]) => `<article><strong>${esc(humanize(platform))}</strong><p>${esc(value?.final_caption || value || '')}</p></article>`).join('');
  const validCount = validation.filter((item) => item.valid).length;
  const html = `<div class="deliverables"><div class="deliverables-head"><div><span class="kicker">Generated work</span><h3>${esc(packageValue.title || packageValue.objective || 'Carousel package')}</h3></div>${pill(output.status || execution.status || 'COMPLETED')}</div><div class="deliverable-facts"><span><b>${slides.length || assets.length}</b> slides</span><span><b>${validCount || assets.length}/${validation.length || assets.length}</b> assets validated</span><span><b>${Object.keys(copies).length}</b> platform captions</span></div><div class="publication-safety"><b>Not scheduled · Not published</b><span>The generated package is ready for your review. Publishing still requires a separate action.</span></div>${images ? `<div class="section-label spaced">Rendered slides · select an image to open full size</div><div class="deliverable-grid">${images}</div>` : ''}${captions ? `<div class="section-label spaced">Platform captions</div><div class="platform-copy-grid">${captions}</div>` : ''}<footer><code>${esc(transactionId)}</code><span>${rollbackAvailable ? 'Rollback available' : 'Durable result recorded'}</span></footer></div>`;
  if (target) {
    target.querySelector('.execution-message').innerHTML = `<strong>Infenergy Intelligence</strong>${html}`;
  } else {
    const wrap = document.createElement('div');
    wrap.className = 'message assistant';
    wrap.innerHTML = `<span class="avatar">I</span><div class="execution-message"><strong>Infenergy Intelligence</strong>${html}</div>`;
    $('#messages').append(wrap);
  }
  $('#messages').scrollTop = $('#messages').scrollHeight;
  return true;
}
function syncConversation(conversation) {
  if (!conversation?.id || state.renderedConversationId === conversation.id) return;
  $('#messages').innerHTML = '';
  const messages = conversation.messages || [];
  if (messages.length) messages.forEach((item) => message(item.role === 'user' ? 'user' : 'assistant', item.content, item.metadata?.timed_out ? 'blocked' : ''));
  else message('assistant', 'Ready to inspect, plan, research, create, operate, and improve Infenergy. Mutations remain policy-governed.');
  state.renderedConversationId = conversation.id;
}
function empty(title, detail = '') { return `<div class="empty-state"><span>✓</span><strong>${esc(title)}</strong>${detail ? `<p>${esc(detail)}</p>` : ''}</div>`; }
function humanize(value) { return String(value || 'Unknown').replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase()); }
function relativeTime(value) { if (!value) return 'Not recorded'; const date = new Date(value); if (Number.isNaN(date.getTime())) return String(value); const seconds = Math.round((date.getTime() - Date.now()) / 1000); for (const [size, unit] of [[31536000, 'year'], [2592000, 'month'], [86400, 'day'], [3600, 'hour'], [60, 'minute']]) { if (Math.abs(seconds) >= size) return new Intl.RelativeTimeFormat('en', { numeric: 'auto' }).format(Math.round(seconds / size), unit); } return 'just now'; }
function dateTime(value) { if (!value) return '—'; const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }); }
function tone(status) { const value = String(status || '').toUpperCase(); if (['OPERATIONAL', 'ACTIVE', 'COMPLETED', 'PUBLISHED', 'READY', 'SUCCESS', 'HEALTHY'].some((word) => value.includes(word))) return 'good'; if (['FAILED', 'BLOCKED', 'DENIED', 'CANCELED', 'ERROR', 'MISSING', 'DEGRADED'].some((word) => value.includes(word))) return 'bad'; if (['WAITING', 'PAUSED', 'PLANNING', 'DRY_RUN', 'UNPLANNED', 'PENDING'].some((word) => value.includes(word))) return 'warn'; return 'neutral'; }
function pill(label, status = label) { return `<span class="pill ${tone(status)}"><i></i>${esc(humanize(label))}</span>`; }
function percent(value) { const number = Number(value || 0); return Math.max(0, Math.min(100, number <= 1 ? number * 100 : number)); }
function approvalSummary(item) { const request = item.request || {}; const scope = request.permissions?.scope || {}; const range = scope.start_date && scope.end_date ? `${scope.start_date}–${scope.end_date}` : ''; const schedule = request.content_date ? [request.content_date, request.slot || 'midday', request.scheduled_at ? dateTime(request.scheduled_at) : 'automatic slot time'].join(' · ') : ''; const platforms = request.platforms || request.package?.platforms || request.package?.platform_policy?.platforms || []; const purpose = request.objective || request.name || request.rationale || request.package?.objective || request.campaign || scope.campaign || ''; return [purpose, schedule || range, platforms.length ? platforms.map(humanize).join(', ') : ''].filter(Boolean).join(' · ') || 'Owner authorization required'; }

function creativeFormData() {
  return {
    title: $('#creative-title').value.trim() || 'Untitled creative',
    idea: $('#creative-idea').value.trim(),
    slide_count: Number($('#creative-slides').value || 6),
    platform: $('#creative-platform').value,
    platforms: [...document.querySelectorAll('.creative-channel:checked')].map((item) => item.value),
  };
}

function renderCreativeList() {
  $('#creative-list').innerHTML = state.creatives.length ? state.creatives.map((item) => `<button type="button" class="creative-list-item ${item.id === state.creativeId ? 'active' : ''}" data-creative-id="${esc(item.id)}"><strong>${esc(item.title || 'Untitled creative')}</strong><small>${esc(humanize(item.status || 'DRAFT'))} · ${esc(relativeTime(item.updated_at))}</small></button>`).join('') : empty('No saved ideas', 'Click New idea to begin.');
}

function renderCreative(creative) {
  state.creativeId = creative?.id || null;
  $('#creative-empty').hidden = Boolean(creative);
  $('#creative-form').hidden = !creative;
  if (!creative) { renderCreativeList(); return; }
  $('#creative-title').value = creative.title || 'Untitled creative';
  $('#creative-idea').value = creative.idea || '';
  $('#creative-slides').value = creative.slide_count || 6;
  $('#creative-platform').value = creative.platform || 'instagram_feed';
  document.querySelectorAll('.creative-channel').forEach((item) => { item.checked = (creative.platforms || []).includes(item.value); });
  $('#creative-save-state').textContent = 'Saved';
  const schedule = creative.schedule || {};
  if (schedule.content_date) $('#creative-date').value = schedule.content_date;
  if (schedule.scheduled_at) $('#creative-time').value = String(schedule.scheduled_at).slice(11, 16);
  if (schedule.slot) $('#creative-slot').value = schedule.slot;
  const preflight = creative.preflight || {};
  $('#creative-result').innerHTML = creative.status === 'SCHEDULED' ? `<div class="creative-success"><strong>✓ Checked, approved, and scheduled</strong><span>${esc(dateTime(schedule.scheduled_at))} · ${(schedule.platforms || []).map(humanize).join(', ')}</span></div>` : preflight.passed === false ? `<div class="inline-alert">Preflight needs attention before scheduling.</div>` : '';
  const slides = creative.package?.carousel_slides || [];
  const copy = creative.package?.platform_posts || {};
  $('#creative-preview').innerHTML = slides.length ? `<div class="section-label">Slide copy</div><div class="slide-copy-grid">${slides.map((slide, index) => `<article><b>${index + 1}/${slides.length}</b><strong>${esc(slide.on_image_headline)}</strong><span>${esc(slide.on_image_subline)}</span></article>`).join('')}</div><div class="section-label spaced">Platform copies</div><div class="platform-copy-grid">${Object.entries(copy).map(([platform, value]) => `<article><strong>${esc(humanize(platform))}</strong><p>${esc(value.final_caption || '')}</p></article>`).join('')}</div>` : '';
  renderCreativeList();
}

async function loadCreatives(preferredId = state.creativeId) {
  const result = await api('/api/os/creatives');
  state.creatives = result.creatives || [];
  const selected = state.creatives.find((item) => item.id === preferredId) || state.creatives[0] || null;
  renderCreative(selected);
}

async function loadGenerationRequests() {
  const result = await api('/api/os/generation-requests');
  const request = (result.requests || [])[0];
  if (request) renderGenerationRequest(request);
}

async function saveCreative({ quiet = false } = {}) {
  if (!state.creativeId) return null;
  $('#creative-save-state').textContent = 'Saving…';
  const result = await api(`/api/os/creatives/${state.creativeId}`, { method: 'POST', body: JSON.stringify(creativeFormData()) });
  const creative = result.creative;
  const index = state.creatives.findIndex((item) => item.id === creative.id);
  if (index >= 0) state.creatives[index] = creative; else state.creatives.unshift(creative);
  $('#creative-save-state').textContent = 'Saved';
  renderCreativeList();
  if (!quiet) toast('Creative saved');
  return creative;
}

function queueCreativeSave() {
  if (!state.creativeId) return;
  $('#creative-save-state').textContent = 'Unsaved changes…';
  clearTimeout(state.creativeSaveTimer);
  state.creativeSaveTimer = setTimeout(() => saveCreative({ quiet: true }).catch((error) => { $('#creative-save-state').textContent = 'Save failed'; toast(error.message); }), 500);
}

const generationFields = [
  ['content_type', 'Content type'], ['format', 'Format'], ['style', 'Style'], ['topic', 'Topic'], ['platform', 'Platform'],
  ['infenergy_usage', 'Infenergy usage'], ['product_usage', 'Product usage'], ['campaign', 'Campaign'], ['tone', 'Tone'],
  ['objective', 'Objective'], ['cta', 'CTA'], ['publishing_date', 'Publishing date'], ['publishing_time', 'Publishing time'],
  ['creative_instructions', 'Creative instructions'],
];

function generationControl(field, label, value = { mode: 'AUTO', value: '' }, scope = 'request') {
  const custom = value?.mode === 'CUSTOM';
  return `<label class="delegated-control" data-control-field="${esc(field)}" data-control-scope="${esc(scope)}"><span>${esc(label)}</span><div><select aria-label="${esc(label)} control"><option value="AUTO" ${custom ? '' : 'selected'}>Auto · System decides</option><option value="CUSTOM" ${custom ? 'selected' : ''}>Custom · You decide</option></select><input value="${esc(value?.value || '')}" placeholder="Tell the AI what you want" ${custom ? '' : 'disabled'}></div></label>`;
}

function readGenerationControls(container) {
  return Object.fromEntries([...container.querySelectorAll('.delegated-control')].map((control) => {
    const mode = control.querySelector('select').value;
    return [control.dataset.controlField, { mode, value: mode === 'CUSTOM' ? control.querySelector('input').value.trim() : '' }];
  }));
}

function renderGenerationControls() {
  $('#generation-controls').innerHTML = generationFields.map(([field, label]) => generationControl(field, label)).join('');
}

function renderGenerationRequest(request) {
  state.generationRequest = request;
  const customCount = Object.values(request.controls || {}).filter((value) => value.mode === 'CUSTOM').length;
  $('#generation-result').innerHTML = `<article class="panel generation-plan"><div class="generation-plan-head"><div><p class="kicker">${esc(request.start_date)} — ${esc(request.end_date)}</p><h2>${esc(request.horizon_days)}-day content program</h2><p>${esc(request.guidance || 'Infenergy Intelligence is deciding every unspecified detail.')}</p></div><div>${pill(request.status)}<span>${customCount} custom · ${generationFields.length - customCount} delegated</span></div></div><div class="generation-day-grid">${(request.day_cards || []).map((day) => renderGenerationDay(day)).join('')}</div></article>`;
}

function renderGenerationDay(day) {
  const date = new Date(`${day.date}T12:00:00`);
  const posts = day.posts || [];
  return `<article class="generation-day" data-day-date="${esc(day.date)}"><header><div><span>${esc(date.toLocaleDateString([], { month: 'short', day: 'numeric' }))}</span><strong>${esc(date.toLocaleDateString([], { weekday: 'long' }))}</strong></div>${pill(day.status)}</header><div class="day-frequency"><label><span>Posts this day</span><select data-day-frequency><option value="AUTO" ${day.frequency?.mode === 'CUSTOM' ? '' : 'selected'}>Auto · AI decides</option><option value="0" ${day.frequency?.value === '0' ? 'selected' : ''}>No post</option><option value="1" ${day.frequency?.value === '1' ? 'selected' : ''}>1 post</option><option value="2" ${day.frequency?.value === '2' ? 'selected' : ''}>2 posts</option><option value="3" ${day.frequency?.value === '3' ? 'selected' : ''}>3 posts</option></select></label></div>${posts.length ? `<div class="day-posts">${posts.map((post) => `<article data-generation-post="${esc(post.id)}"><strong>${esc(post.concept)}</strong><span>${esc(post.content_type)} · ${esc(post.format)}</span><small>${esc(post.platforms)} · ${esc(post.campaign)}</small><div class="day-actions"><button type="button" data-edit-day>Edit controls</button><button type="button" data-regenerate>Regenerate</button></div></article>`).join('')}</div>` : '<p class="day-empty">No post recommended. Add one by changing Posts this day.</p>'}<details data-day-controls><summary>Day controls</summary><div class="day-controls">${generationFields.map(([field, label]) => generationControl(field, label, day.controls?.[field], day.date)).join('')}</div><button type="button" class="creative-button secondary" data-generate-day>Generate This Day</button></details></article>`;
}

function generationRequestData() {
  const start = $('#generation-start').value || new Date().toISOString().slice(0, 10);
  const productionWindow = Math.min(Number($('#generation-production-window').value || 30), state.generationDays);
  return { start_date: start, days: state.generationDays, control_mode: state.generationMode, guidance: $('#generation-guidance').value.trim(), controls: readGenerationControls($('#generation-controls')), production_window_days: productionWindow, rolling_production: $('#generation-rolling').checked };
}

function generationDayData(card) {
  const frequency = card.querySelector('[data-day-frequency]').value;
  return {
    frequency: { mode: frequency === 'AUTO' ? 'AUTO' : 'CUSTOM', value: frequency === 'AUTO' ? '' : frequency },
    controls: readGenerationControls(card),
  };
}

async function persistGenerationDay(card) {
  const dayDate = card.dataset.dayDate;
  const result = await api(`/api/os/generation-requests/${state.generationRequest.id}/days/${dayDate}`, {
    method: 'PATCH', body: JSON.stringify(generationDayData(card)),
  });
  renderGenerationRequest(result.request);
  return result.request.day_cards.find((day) => day.date === dayDate);
}

function generationCommand(day, post) {
  const requestValues = Object.entries(state.generationRequest.controls || {}).filter(([, control]) => control.mode === 'CUSTOM' && control.value).map(([field, control]) => `${humanize(field)}: ${control.value}`);
  const dayValues = Object.entries(day.controls || {}).filter(([, control]) => control.mode === 'CUSTOM' && control.value).map(([field, control]) => `${humanize(field)}: ${control.value}`);
  return [`Create a finished Infenergy social post for ${day.date}.`, `Concept: ${post.concept}.`, state.generationRequest.guidance, ...requestValues, ...dayValues].filter(Boolean).join(' ');
}

function capabilityExample(schema) {
  const example = {};
  const properties = schema?.properties || {};
  for (const key of schema?.required || []) {
    const type = properties[key]?.type;
    example[key] = type === 'array' ? [] : type === 'object' ? {} : type === 'boolean' ? false : type === 'integer' || type === 'number' ? 0 : '';
  }
  return example;
}

function selectedCapability() { return state.capabilities.find((item) => item.id === state.masterCapabilityId) || null; }

function renderMasterCapabilities() {
  const search = $('#master-search').value.trim().toLowerCase();
  const domain = $('#master-domain').value;
  const visible = state.capabilities.filter((item) => (!domain || item.domain === domain) && (!search || [item.id, item.name, item.description, item.domain].some((value) => String(value).toLowerCase().includes(search))));
  $('#master-capability-count').textContent = `${visible.length}/${state.capabilities.length}`;
  $('#master-capabilities').innerHTML = visible.length ? visible.map((item) => `<button type="button" class="master-capability ${item.id === state.masterCapabilityId ? 'active' : ''}" data-master-capability="${esc(item.id)}"><span>${esc(humanize(item.domain))}</span><strong>${esc(item.name)}</strong><code>${esc(item.id)}</code><small>${esc(item.description)}</small><footer>${pill(item.permission_requirement)}${item.supports_rollback ? '<b>↶ rollback</b>' : ''}</footer></button>`).join('') : empty('No matching capabilities');
}

function selectMasterCapability(capabilityId, argumentsValue = null, dryRun = null) {
  state.masterCapabilityId = capabilityId;
  const capability = selectedCapability();
  $('#master-empty').hidden = Boolean(capability);
  $('#master-form').hidden = !capability;
  if (!capability) return;
  $('#master-domain-label').textContent = capability.domain;
  $('#master-name').textContent = capability.name;
  $('#master-id').textContent = capability.id;
  $('#master-description').textContent = capability.description;
  $('#master-flags').innerHTML = `${pill(capability.risk_level)}${pill(capability.permission_requirement)}${capability.supports_rollback ? pill('Rollback ready', 'READY') : ''}`;
  $('#master-schema').textContent = JSON.stringify(capability.input_schema || {}, null, 2);
  $('#master-arguments').value = JSON.stringify(argumentsValue ?? capabilityExample(capability.input_schema), null, 2);
  $('#master-dry-run').checked = dryRun ?? (capability.risk_level !== 'READ');
  $('#master-dry-run').disabled = !capability.supports_dry_run;
  $('#master-result').innerHTML = '';
  renderMasterCapabilities();
}

function renderMasterTransactions() {
  const reversible = state.transactions.filter((item) => item.status === 'COMPLETED' && !item.dry_run && item.rollback_data && Object.keys(item.rollback_data).length).length;
  $('#master-metrics').innerHTML = [
    ['Capabilities', state.capabilities.length],
    ['Autonomous', state.capabilities.filter((item) => item.permission_requirement === 'AUTONOMOUS').length],
    ['Approval gated', state.capabilities.filter((item) => item.permission_requirement === 'EXECUTE_WITH_APPROVAL').length],
    ['Rollback ready', state.capabilities.filter((item) => item.supports_rollback).length],
    ['Undo available', reversible],
  ].map(([label, value]) => `<div class="metric panel"><b>${value}</b><span>${esc(label)}</span></div>`).join('');
  $('#master-transactions').innerHTML = state.transactions.length ? `<div class="master-transaction-list">${state.transactions.slice(0, 30).map((item) => { const operation = item.operations?.[0] || {}; const canRollback = item.status === 'COMPLETED' && !item.dry_run && item.rollback_data && Object.keys(item.rollback_data).length; const hasDeliverables = Boolean(operationOutput(item)); return `<article><div><strong>${esc(operation.capability || item.name || 'Operation')}</strong><code>${esc(item.id)}</code></div>${pill(item.status)}<span>${esc(relativeTime(item.updated_at))}</span><div class="transaction-actions">${hasDeliverables ? `<button data-view-deliverables="${esc(item.id)}">View deliverables</button>` : ''}${canRollback ? `<button class="secondary" data-master-rollback="${esc(item.id)}">Rollback</button>` : !hasDeliverables ? '<small>Recorded</small>' : ''}</div></article>`; }).join('')}</div>` : empty('No transactions recorded');
}

async function loadMaster() {
  const [capabilityResult, transactionResult] = await Promise.all([api('/api/os/capabilities'), api('/api/os/transactions')]);
  state.capabilities = capabilityResult.capabilities || [];
  state.transactions = transactionResult.transactions || [];
  const domains = [...new Set(state.capabilities.map((item) => item.domain))].sort();
  const selectedDomain = $('#master-domain').value;
  $('#master-domain').innerHTML = `<option value="">All domains</option>${domains.map((item) => `<option value="${esc(item)}">${esc(humanize(item))}</option>`).join('')}`;
  $('#master-domain').value = domains.includes(selectedDomain) ? selectedDomain : '';
  if (state.masterCapabilityId && !selectedCapability()) state.masterCapabilityId = null;
  renderMasterCapabilities();
  renderMasterTransactions();
}

function renderMasterResult(result) {
  const pending = result.status === 'WAITING_APPROVAL' && result.approval_id;
  $('#master-result').innerHTML = `<div class="master-result-head">${pill(result.status)}${result.transaction_id ? `<code>${esc(result.transaction_id)}</code>` : ''}</div>${pending ? `<div class="master-approval"><strong>Exact-request owner approval required</strong><p>${esc(result.reason || 'Governance requires approval before this mutation executes.')}</p><button data-master-approval="${esc(result.approval_id)}">Approve & execute once</button></div>` : ''}<details open><summary>Verified operation result</summary><pre>${esc(JSON.stringify(result, null, 2))}</pre></details>${result.rollback_available ? `<button class="master-rollback-primary" data-master-rollback="${esc(result.transaction_id)}">Rollback this operation</button>` : ''}`;
}

function renderToday(attention, events) {
  const signals = attention.map((item) => { const score = Number(item.score || item.materiality || 0); return `<article class="signal-card"><div class="card-top"><span class="kicker">Executive attention</span><strong class="score">${score.toFixed(1)}</strong></div><h3>${esc(item.title || item.subject || 'Material signal')}</h3><p>${esc(item.summary || item.description || 'Requires owner review.')}</p><div class="meta-line">${pill(item.status || 'OPEN')}<span>${esc(relativeTime(item.created_at))}</span></div></article>`; }).join('');
  const recent = events.slice(0, 8).map((event) => { const payload = event.payload || {}; const detail = [payload.capability && humanize(payload.capability), payload.status && humanize(payload.status)].filter(Boolean).join(' · '); return `<article class="event-card"><div class="event-icon ${tone(payload.status || event.type)}">${tone(payload.status || event.type) === 'good' ? '✓' : '•'}</div><div><h3>${esc(humanize(event.type || 'System event'))}</h3><p>${esc(detail || `${humanize(event.subject_type || 'system')} update recorded`)}</p><small>${esc(relativeTime(event.recorded_at || event.occurred_at))}</small></div></article>`; }).join('');
  $('#today-content').innerHTML = signals || recent ? `${signals ? `<div class="section-label">Priority signals</div><div class="dashboard-grid">${signals}</div>` : ''}${recent ? `<div class="section-label ${signals ? 'spaced' : ''}">Recent operations</div><div class="event-list">${recent}</div>` : ''}` : empty('Everything is clear', 'No material signals or recent events require attention.');
}

function renderJobs(jobs) {
  if (!jobs.length) { $('#jobs-table').innerHTML = empty('No jobs in the execution fabric', 'Create a research mission or preview the rolling 120-day plan.'); return; }
  const query = state.jobQuery.toLowerCase();
  const visible = jobs.filter((job) => !query || [job.id, job.objective, job.type, job.status].some((value) => String(value || '').toLowerCase().includes(query)));
  if (!visible.length) { $('#jobs-table').innerHTML = empty('No matching jobs', `Nothing matched “${state.jobQuery}”.`); return; }
  $('#jobs-table').innerHTML = `<div class="data-table"><div class="table-head"><span>Job</span><span>Status</span><span>Progress</span><span>Updated</span></div>${visible.map((job) => { const progress = percent(job.progress); const result = job.result && Object.keys(job.result).length ? JSON.stringify(job.result, null, 2) : ''; return `<div class="job-record"><div class="table-row"><div><strong>${esc(job.objective || humanize(job.type))}</strong><code class="job-id">${esc(job.id)}</code><small>${esc(humanize(job.type))}${job.current_step ? ` · ${esc(humanize(job.current_step))}` : ''}</small></div><div>${pill(job.status)}</div><div class="progress-cell"><div class="progress"><i style="width:${progress}%"></i></div><small>${Math.round(progress)}%</small></div><div><span>${esc(relativeTime(job.updated_at))}</span><small>${job.steps?.length || 0} steps</small></div></div><details class="job-details"><summary>${result ? 'View persisted deliverables' : 'View job details'}</summary><div class="job-metadata"><span>Job ID</span><code>${esc(job.id)}</code><span>Created</span><b>${esc(dateTime(job.created_at))}</b><span>Updated</span><b>${esc(dateTime(job.updated_at))}</b></div>${result ? `<pre>${esc(result)}</pre>` : '<p>No persisted result has been recorded yet.</p>'}</details></div>`; }).join('')}</div>`;
}

function renderResearch(findings) {
  if (!findings.length) { $('#research-content').innerHTML = empty('No current findings', 'Run a research command to populate the Intelligence Library.'); return; }
  $('#research-content').innerHTML = findings.map((finding) => { const credibility = percent(finding.credibility); const confidence = percent(finding.confidence); const source = finding.source_type && String(finding.source_type).toLowerCase() !== 'unknown' ? humanize(finding.source_type) : 'Unclassified source'; const expiresSoon = finding.expires_at && new Date(finding.expires_at).getTime() - Date.now() < 7 * 86400000; return `<article class="finding-card"><div class="card-top"><span class="source-tag">${esc(source)}</span>${expiresSoon ? pill('Expires soon', 'WAITING') : ''}</div><h3>${esc(finding.title || 'Research finding')}</h3><p>${esc(finding.summary || 'No summary supplied.')}</p><div class="confidence-grid"><div><span>Credibility</span><b>${Math.round(credibility)}%</b><div class="progress"><i style="width:${credibility}%"></i></div></div><div><span>Confidence</span><b>${Math.round(confidence)}%</b><div class="progress secondary"><i style="width:${confidence}%"></i></div></div></div><footer><span>Retrieved ${esc(relativeTime(finding.created_at || finding.freshness?.retrieved))}</span><span>${finding.corroboration?.length || 0} corroborating sources</span></footer></article>`; }).join('');
}

function renderAutomations(automations, watches, runs) {
  const records = [...automations.map((item) => ({ ...item, kind: 'Automation' })), ...watches.map((item) => ({ ...item, kind: 'Watch' }))];
  $('#automations-content').innerHTML = records.length ? records.map((item) => `<article class="operation-card"><div class="card-top"><span class="kicker">${esc(item.kind)}</span>${pill(item.status || 'ACTIVE')}</div><h3>${esc(item.name || item.subject || 'Automation')}</h3><p>${esc(item.objective || item.frequency || humanize(item.trigger?.type || 'Capability workflow'))}</p><footer><span>${item.steps?.length || item.actions?.length || 0} actions</span><span>${esc(relativeTime(item.updated_at || item.created_at))}</span></footer></article>`).join('') : empty('No automations configured', 'Create one from Command when a repeatable workflow is ready.');
  $('#automation-runs').innerHTML = runs.length ? `<div class="data-table"><div class="table-head"><span>Automation</span><span>Status</span><span>Started</span><span>Result</span></div>${runs.map((run) => `<div class="table-row"><div><strong>${esc(run.automation_id || 'Automation run')}</strong></div><div>${pill(run.status)}</div><div>${esc(relativeTime(run.started_at))}</div><div>${esc(run.error || (run.finished_at ? 'Completed' : 'In progress'))}</div></div>`).join('')}</div>` : empty('No automation runs yet');
}

function renderTikTokConnection() {
  const account = state.tiktokAccount || { status: 'ERROR', connected: false };
  const status = String(account.status || 'ERROR');
  const states = {
    NOT_CONNECTED: ['Not connected', 'Authorize the Infenergy TikTok account to enable approved video workflows.'],
    CONNECTED: ['Connected', account.display_name ? `Authorized as ${account.display_name}.` : 'TikTok authorization is active.'],
    REAUTHORIZATION_REQUIRED: ['Reauthorization required', 'The TikTok grant expired or can no longer be refreshed.'],
    ERROR: ['Connection error', 'TikTok connection status could not be verified.'],
  };
  const [title, detail] = states[status] || states.ERROR;
  const action = status === 'CONNECTED'
    ? '<button type="button" class="ghost" data-tiktok-disconnect>Disconnect</button>'
    : '<button type="button" data-tiktok-connect>Connect TikTok</button>';
  $('#tiktok-connection').innerHTML = `<article class="account-connection ${tone(status)}"><div class="account-mark">T</div><div><span class="kicker">Connected account</span><h3>TikTok · ${esc(title)}</h3><p>${esc(detail)}</p>${account.access_token_expires_at ? `<small>Authorization refreshes automatically · access valid through ${esc(dateTime(account.access_token_expires_at))}</small>` : ''}</div><div class="account-action">${pill(status)}${action}</div></article>`;
}

function renderSocial(today) {
  renderTikTokConnection();
  if (!today) { $('#social-content').innerHTML = empty('No social schedule loaded'); return; }
  const slots = Array.isArray(today.slots) ? today.slots : Object.entries(today.by_slot || {}).map(([slot, value]) => ({ slot, ...value }));
  const summary = [['Required', today.required || 0], ['Ready', today.ready || 0], ['Published', today.published || 0], ['Missing', today.missing || 0]];
  $('#social-content').innerHTML = `<div class="social-summary">${summary.map(([label, value]) => `<div><b>${esc(value)}</b><span>${esc(label)}</span></div>`).join('')}</div><div class="slot-grid">${['morning', 'midday', 'evening'].map((name) => { const slot = slots.find((item) => String(item.slot).toLowerCase() === name) || { slot: name, status: 'UNPLANNED' }; const platforms = slot.platform_policy?.platforms || Object.keys(slot.platform_results || {}); return `<article class="slot-card ${tone(slot.status)}"><div class="card-top"><span class="slot-time">${esc(humanize(name))}</span>${pill(slot.status || 'UNPLANNED')}</div><h3>${slot.content_id ? 'Content package ready' : 'No content assigned'}</h3><p>${slot.scheduled_at ? esc(dateTime(slot.scheduled_at)) : 'Schedule not available'}</p><div class="platforms">${platforms.length ? platforms.map((platform) => `<span title="${esc(humanize(platform))}">${esc(platform.slice(0, 1).toUpperCase())}</span>`).join('') : '<small>No channels assigned</small>'}</div>${slot.last_error ? `<div class="inline-alert">${esc(slot.last_error)}</div>` : ''}</article>`; }).join('')}</div>`;
}

function calendarIso(dateValue) {
  const year = dateValue.getFullYear();
  const month = String(dateValue.getMonth() + 1).padStart(2, '0');
  const day = String(dateValue.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function calendarPost(post) {
  const packageValue = post.package || {};
  const platformSchedule = packageValue.platform_schedule || {};
  const copies = packageValue.platform_posts || {};
  const slides = packageValue.carousel_slides || [];
  const assets = packageValue.carousel_assets || [];
  const title = packageValue.title || packageValue.objective || packageValue.post_id || 'Scheduled post';
  const platforms = post.platforms || [];
  const firstAsset = assets[0]?.local_path || assets[0]?.path || assets[0]?.url;
  const captionEntries = Object.entries(copies);
  const scheduledEntries = platforms.filter((platform) => platformSchedule[platform]).map((platform) => [platform, platformSchedule[platform]]);
  const timeLabel = (value) => new Date(value).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', timeZoneName: 'short' });
  return `<article class="calendar-post ${tone(post.status)}">${firstAsset ? `<img src="${esc(mediaUrl(firstAsset))}" alt="${esc(title)}" loading="lazy">` : ''}<div class="calendar-post-main"><div class="calendar-post-time"><strong>${esc(timeLabel(post.scheduled_at))}</strong>${pill(post.status)}</div><h3>${esc(title)}</h3>${scheduledEntries.length ? `<div class="calendar-platform-times">${scheduledEntries.map(([platform, value]) => `<span><b>${esc(humanize(platform))}</b>${esc(timeLabel(value))}</span>`).join('')}</div>` : `<div class="calendar-platforms">${platforms.map((platform) => `<span>${esc(humanize(platform))}</span>`).join('')}</div>`}<details><summary>View exact post</summary>${captionEntries.length ? `<div class="calendar-captions">${captionEntries.map(([platform, value]) => `<section><b>${esc(humanize(platform))}</b><p>${esc(value?.final_caption || value || '')}</p></section>`).join('')}</div>` : `<p>${esc(packageValue.fb_caption || packageValue.ig_caption || packageValue.li_text || 'No caption stored.')}</p>`}${slides.length ? `<div class="calendar-slides">${slides.map((slide, index) => `<span><b>${index + 1}</b>${esc(slide.on_image_headline || slide.headline || '')}<small>${esc(slide.on_image_subline || slide.supporting || '')}</small></span>`).join('')}</div>` : ''}<code>${esc(post.outbox_id)}</code></details></div></article>`;
}

function renderSocialCalendar(calendar) {
  const title = state.calendarDate.toLocaleDateString([], { month: 'long', year: 'numeric' });
  $('#calendar-title').textContent = `${title} · ${calendar.scheduled_count || 0} scheduled`;
  const today = calendarIso(new Date());
  $('#social-calendar').innerHTML = `<div class="calendar-weekdays">${['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((day) => `<span>${day}</span>`).join('')}</div><div class="calendar-days">${(calendar.days || []).map((day) => { const dateValue = new Date(`${day.date}T12:00:00`); const outsideMonth = dateValue.getMonth() !== state.calendarDate.getMonth(); return `<section class="calendar-day ${outsideMonth ? 'outside' : ''} ${day.date === today ? 'today' : ''}"><header><b>${dateValue.getDate()}</b><span>${dateValue.toLocaleDateString([], { weekday: 'short' })}</span></header>${day.posts.length ? day.posts.map(calendarPost).join('') : '<p class="calendar-empty">No post scheduled</p>'}</section>`; }).join('')}</div>`;
}

function planEntry(entry) {
  const product = entry.product || {};
  const dateValue = new Date(`${entry.date}T12:00:00`);
  const productLine = product.product_name ? `<span class="plan-product">${esc(product.product_name)} · ${esc(product.persona)}</span>` : '';
  const intervention = entry.series === 'Infenergy Intervention';
  const transformation = entry.transformation || {};
  const visibleText = entry.visible_text ? `<dt>Visible headline</dt><dd>${esc(entry.visible_text.headline)}</dd><dt>Infenergy dialogue</dt><dd>${esc(entry.visible_text.infenergy_line)}</dd><dt>Resolution text</dt><dd>${esc(entry.visible_text.resolution_line)}</dd>` : '';
  const storyDelivery = entry.layout === 'single_vertical_comic_strip' ? `<dt>Story delivery</dt><dd>${esc(entry.delivery_label)} · ${esc(entry.canvas_px.width)}×${esc(entry.canvas_px.height)} · ${esc(entry.panel_count)} panels on one canvas</dd><dt>Story product</dt><dd>${esc(entry.product_name)} · verified product reference required</dd>` : '';
  const companySource = entry.company_source || {};
  const quoteDelivery = entry.layout === 'single_frame_integrated_typography' ? `<dt>Quote delivery</dt><dd>${esc(entry.delivery_label)} · ${esc(entry.canvas_px.width)}×${esc(entry.canvas_px.height)} · exact text appears once</dd><dt>Exact super message</dt><dd>${esc(entry.exact_visible_text[0])}</dd><dt>Company source</dt><dd>${esc(companySource.knowledge_id)} · ${esc(companySource.message_id)} · verbatim</dd><dt>Caption support</dt><dd>${esc(companySource.support_thought_id)} · ${esc(entry.support_statement)}</dd><dt>Source audience</dt><dd>${esc(humanize(companySource.audience))} · ${esc(humanize(companySource.pillar))}</dd>` : '';
  return `<article class="plan-entry ${intervention ? 'intervention' : ''}"><div class="plan-date"><b>${esc(dateValue.toLocaleDateString([], { month: 'short', day: 'numeric' }))}</b><span>${esc(entry.weekday)} · ${esc(humanize(entry.slot))}</span></div><div class="plan-entry-main"><div class="plan-entry-meta"><span>${esc(entry.series)}</span><span>${esc(entry.post_type_label)}</span><span>${esc(entry.format_label)}</span>${pill(entry.state)}</div><div class="consumer-line"><b>${esc(entry.audience_name)}</b><span>${esc(entry.creative_territory)}</span><span>${esc(entry.funnel_stage)}</span></div><h3>${esc(entry.title)}</h3><p>${esc(entry.hook)}</p>${productLine}<details><summary>Consumer + creative brief</summary><dl><dt>Post type</dt><dd>${esc(entry.post_type_label)}</dd><dt>Visual post format</dt><dd>${esc(entry.format_label)}</dd>${storyDelivery}${quoteDelivery}${visibleText}<dt>Demographic lens</dt><dd>${esc(entry.demographic_lens)}</dd><dt>Psychographic</dt><dd>${esc(entry.psychographic)}</dd><dt>Consumer desire</dt><dd>${esc(entry.consumer_desire)}</dd><dt>Identity signal</dt><dd>${esc(entry.identity_signal)}</dd><dt>Transformation</dt><dd>${esc(humanize(transformation.from))} → ${esc(humanize(transformation.to))}</dd><dt>Culture</dt><dd>${esc(entry.cultural_register)}</dd><dt>Human reality</dt><dd>${esc(entry.human_reality)}</dd><dt>Thought shift</dt><dd>${esc(entry.brain_movement)} → ${esc(entry.heart_after)}</dd><dt>Platform</dt><dd>${esc(entry.platform_treatment)}</dd><dt>Story</dt><dd>${esc(entry.story)}</dd><dt>Takeaway</dt><dd>${esc(entry.takeaway)}</dd><dt>Natural response</dt><dd>${esc(entry.natural_response)}</dd><dt>Call to action</dt><dd>${esc(entry.cta)}</dd>${product.product_role ? `<dt>Product role</dt><dd>${esc(product.product_role)}</dd>` : ''}${product.proof_direction ? `<dt>Proof direction</dt><dd>${esc(product.proof_direction)}</dd>` : ''}</dl></details></div><div class="plan-production"><b>${intervention ? `#${entry.installment}` : `D${entry.day_number}`}</b><span>${esc(entry.image_status === 'NOT_GENERATED' ? 'No image' : entry.image_status)}</span></div></article>`;
}

function renderContentPlan() {
  const plan = state.contentPlan;
  if (!plan) { $('#plan-weeks').innerHTML = empty('Loading 120-day plan'); return; }
  const horizon = $('#plan-horizon').value;
  const audience = $('#plan-audience').value;
  const series = $('#plan-series').value;
  const query = $('#plan-search').value.trim().toLowerCase();
  const entries = (plan.entries || []).filter((entry) => {
    const product = entry.product || {};
    const searchable = [entry.title, entry.hook, entry.story, entry.weekly_arc, entry.series, entry.post_type, entry.post_type_label, entry.format_label, entry.audience_name, entry.demographic_lens, entry.psychographic, entry.consumer_desire, entry.creative_territory, product.product_name, product.persona].join(' ').toLowerCase();
    return (!horizon || entry.state === horizon) && (!audience || entry.audience_id === audience) && (!series || entry.series === series) && (!query || searchable.includes(query));
  });
  const weeks = new Map();
  entries.forEach((entry) => { if (!weeks.has(entry.week)) weeks.set(entry.week, []); weeks.get(entry.week).push(entry); });
  $('#plan-image-count').textContent = `${plan.image_count || 0} images`;
  $('#plan-metrics').innerHTML = [
    ['Day coverage', `${plan.date_coverage?.planned_days || plan.concept_count}/${plan.date_coverage?.expected_days || plan.days}`],
    ['Post types', `${Object.keys(plan.post_type_counts || {}).length}/${Object.keys(plan.post_type_taxonomy || {}).length}`],
    ['Product Story comics', plan.superhero_with_text_count || 0],
    ['Company quote visuals', plan.weekly_company_quote_count || 0],
    ['Super message bank', plan.company_super_message_bank_count || 0],
    ['Catalog coverage', `${plan.catalog_products_used}/${plan.catalog_size}`],
    ['Interventions', plan.series_counts?.['Infenergy Intervention'] || 0],
    ['Audience worlds', new Set((plan.entries || []).map((entry) => entry.audience_id)).size],
    ['Creative territories', new Set((plan.entries || []).map((entry) => entry.creative_territory)).size],
    ['Visible', entries.length],
  ].map(([label, value]) => `<div class="metric panel"><b>${esc(value)}</b><span>${esc(label)}</span></div>`).join('');
  $('#plan-weeks').innerHTML = weeks.size ? [...weeks.entries()].map(([week, weekEntries]) => { const lead = weekEntries[0]; return `<section class="plan-week"><header><div><span>Week ${week} · ${esc(lead.creative_territory)}</span><h2>${esc(lead.weekly_arc)}</h2><p>${esc(lead.audience_name)} · ${esc(lead.consumer_desire)}</p></div><b>${weekEntries.length} concepts</b></header><div>${weekEntries.map(planEntry).join('')}</div></section>`; }).join('') : empty('No concepts match these filters');
}

async function loadContentPlan() {
  const start = new Date();
  start.setDate(start.getDate() + 1);
  const result = await api('/api/os/content-plan', { method: 'POST', body: JSON.stringify({ start_date: calendarIso(start), days: 120 }) });
  state.contentPlan = result;
  const startLabel = new Date(`${result.start_date}T12:00:00`).toLocaleDateString([], { month: 'long', day: 'numeric' });
  const endLabel = new Date(`${result.end_date}T12:00:00`).toLocaleDateString([], { month: 'long', day: 'numeric', year: 'numeric' });
  $('#plan-date-range').textContent = `${startLabel} — ${endLabel}`;
  const horizonSelect = $('#plan-horizon');
  const audienceSelect = $('#plan-audience');
  const seriesSelect = $('#plan-series');
  const selectedHorizon = horizonSelect.value;
  const selectedAudience = audienceSelect.value;
  const selectedSeries = seriesSelect.value;
  horizonSelect.innerHTML = `<option value="">All horizons</option>${(result.horizons || []).map((item) => `<option value="${esc(item.state)}">${esc(humanize(item.state))} · through day ${item.through_day}</option>`).join('')}`;
  const audiences = [...new Map((result.entries || []).map((entry) => [entry.audience_id, entry.audience_name])).entries()].sort((left, right) => left[1].localeCompare(right[1]));
  audienceSelect.innerHTML = `<option value="">All audiences</option>${audiences.map(([id, name]) => `<option value="${esc(id)}">${esc(name)}</option>`).join('')}`;
  const series = [...new Set((result.entries || []).map((entry) => entry.series))].sort();
  seriesSelect.innerHTML = `<option value="">All series</option>${series.map((item) => `<option value="${esc(item)}">${esc(item)}</option>`).join('')}`;
  horizonSelect.value = selectedHorizon;
  audienceSelect.value = selectedAudience;
  seriesSelect.value = selectedSeries;
  renderContentPlan();
}

async function loadSocialCalendar() {
  const monthStart = new Date(state.calendarDate.getFullYear(), state.calendarDate.getMonth(), 1);
  const start = new Date(monthStart);
  start.setDate(start.getDate() - start.getDay());
  const result = await api('/api/os/calendar', { method: 'POST', body: JSON.stringify({ start_date: calendarIso(start), days: 42 }) });
  renderSocialCalendar(result);
}

function renderActivity(activity) {
  if (!activity.length) { $('#activity-table').innerHTML = empty('No audited activity'); return; }
  $('#activity-table').innerHTML = `<div class="data-table"><div class="table-head"><span>Action</span><span>Actor</span><span>Status</span><span>Time</span></div>${activity.map((item) => `<div class="table-row"><div><strong>${esc(humanize(item.action))}</strong><small>${esc(humanize(item.model_or_tool || 'system'))}</small></div><div>${esc(humanize(item.actor || 'system'))}</div><div>${pill(item.status)}</div><div><span>${esc(relativeTime(item.created_at))}</span><small>${esc(dateTime(item.created_at))}</small></div></div>`).join('')}</div>`;
}

function renderHealth(health) {
  const providers = Object.entries(health.providers || {}); const ready = providers.filter(([, item]) => item.configured || item.sdk_installed).length;
  $('#health-content').innerHTML = `<div class="health-hero"><div><span class="kicker">System status</span><h3>${esc(humanize(health.status || 'Unknown'))}</h3><p>${health.database?.exists ? 'Operational state is connected to durable storage.' : 'Durable storage is unavailable.'}</p></div>${pill(health.status || 'UNKNOWN')}</div><div class="provider-grid">${providers.map(([name, provider]) => { const configured = Boolean(provider.configured || provider.sdk_installed); return `<article class="provider-card ${configured ? 'ready' : 'missing'}"><div class="provider-icon">${configured ? '✓' : '!'}</div><div><h3>${esc(humanize(name))}</h3><p>${configured ? 'Connected and configured' : 'Configuration required'}</p>${provider.master_model ? `<small>Master model · ${esc(provider.master_model)}</small>` : ''}</div></article>`; }).join('')}</div><div class="health-footer"><span><b>${ready}/${providers.length}</b> providers ready</span><span>Database ${health.database?.exists ? 'connected' : 'unavailable'}</span><span>Safety mode ${health.dry_run ? 'on' : 'off'}</span><span>Checked ${esc(relativeTime(health.checked_at))}</span></div>`;
}

function renderPermissions(policies) {
  if (!policies.length) { $('#permissions-content').innerHTML = empty('Default deny is active', 'No explicit autonomy policies are currently granted.'); return; }
  $('#permissions-content').innerHTML = `<div class="permission-intro"><div><span class="kicker">Governance posture</span><h3>Default deny for production mutations</h3><p>Only the explicit capabilities below have delegated authority.</p></div><span class="shield">◆</span></div><div class="policy-list">${policies.map((policy) => `<article class="policy-card ${String(policy.approval_level || '').toLowerCase().replaceAll('_', '-')}"><div><span class="kicker">${esc(humanize(policy.capability))}</span><h3>${esc(policy.rule || 'Scoped operating authority')}</h3><p>Created by ${esc(humanize(policy.created_by || 'owner'))}${policy.valid_until ? ` · expires ${esc(relativeTime(policy.valid_until))}` : ' · no expiry'}</p></div>${pill(policy.approval_level || 'READ', policy.approval_level)}</article>`).join('')}</div>`;
}

function renderStrategy(policies) { const strategic = policies.filter((policy) => /goal|strateg|scenario|research|content/.test(String(policy.capability))); $('#strategy-content').innerHTML = strategic.length ? strategic.map((policy) => `<article class="operation-card"><div class="card-top"><span class="kicker">${esc(humanize(policy.capability))}</span>${pill(policy.status || 'ACTIVE')}</div><h3>${esc(policy.rule)}</h3><p>${esc(humanize(policy.approval_level))}</p></article>`).join('') : empty('No strategic directives recorded', 'Use Command to define goals, scenarios, or research missions.'); }

function render(data) {
  const attention = data.attention || [], approvals = data.approvals || [], jobs = data.jobs || [], policies = data.policies || [], health = data.health || {};
  const pendingApprovals = approvals.filter((item) => item.status === 'PENDING');
  const activeJobs = jobs.filter((job) => !['COMPLETED', 'CANCELED'].includes(job.status));
  const providerCount = Object.values(health.providers || {}).filter((provider) => provider.configured || provider.sdk_installed).length;
  $('#attention-count').textContent = attention.length + pendingApprovals.length; $('#job-count').textContent = jobs.length;
  const approvalCards = pendingApprovals.map((item) => `<div class="approval-card"><strong>${esc(humanize(item.capability))}</strong><small>${esc(approvalSummary(item))}</small><small>Requested ${esc(relativeTime(item.created_at))} · executes this exact request once</small><code>${esc(item.id)}</code><div class="approval-actions"><button data-approval="${esc(item.id)}" data-decision="approve">Approve & run once</button><button data-approval="${esc(item.id)}" data-decision="reject" class="secondary">Reject</button></div></div>`).join('');
  const attentionCards = attention.slice(0, 4).map((item) => `<div class="list-item"><strong>${esc(item.title)}</strong><small>Priority ${Number(item.score || 0).toFixed(1)}</small></div>`).join('');
  $('#attention-list').innerHTML = `${approvalCards}${attentionCards}` || 'Nothing material is waiting.';
  $('#job-list').innerHTML = jobs.slice(0, 4).map((job) => `<button class="list-item job-link" data-job-id="${esc(job.id)}"><strong>${esc(job.objective)}</strong><small>${esc(humanize(job.status))} · ${Math.round(percent(job.progress))}%</small><code>${esc(job.id)}</code></button>`).join('') || 'No jobs recorded.';
  $('#policy-summary').innerHTML = policies.slice(0, 4).map((policy) => `<div class="list-item"><strong>${esc(humanize(policy.capability))}</strong><small>${esc(humanize(policy.approval_level))}</small></div>`).join('') || 'Default deny for mutations.';
  $('#today-metrics').innerHTML = [['Attention', attention.length], ['Active jobs', activeJobs.length], ['Findings', (data.research_findings || []).length], ['Automations', (data.automations || []).length], ['Providers', providerCount]].map(([label, value]) => `<div class="metric panel"><b>${value}</b><span>${esc(label)}</span></div>`).join('');
  renderToday(attention, data.recent_events || []); renderJobs(jobs); renderResearch(data.research_findings || []); renderAutomations(data.automations || [], data.watches || [], data.automation_runs || []); renderSocial(health.social_today); renderStrategy(policies); renderActivity(data.recent_activity || []); renderHealth(health); renderPermissions(policies);
}

async function loadTikTokStatus() { try { state.tiktokAccount = await api('/api/auth/tiktok/status'); } catch { state.tiktokAccount = { status: 'ERROR', connected: false }; } }
async function load() { try { const [data] = await Promise.all([api('/api/os/state'), loadCreatives(), loadGenerationRequests(), loadMaster(), loadTikTokStatus(), loadSocialCalendar(), loadContentPlan()]); state.data = data; state.conversationId = data.conversation?.id; syncConversation(data.conversation); render(data); $('#system-dot').className = 'dot ok'; $('#system-label').textContent = 'Master OS connected'; } catch (error) { $('#system-dot').className = 'dot bad'; $('#system-label').textContent = 'Connection blocked'; toast(error.message); } }
function activateView(view) {
  const button = document.querySelector(`#nav button[data-view="${view}"]`);
  const target = $(`#${view}`);
  if (!button || !target) return;
  document.querySelectorAll('#nav button').forEach((item) => item.classList.toggle('active', item === button));
  document.querySelectorAll('.view').forEach((item) => item.classList.toggle('active', item === target));
  $('#view-title').textContent = button.textContent;
  $('#mobile-nav').value = view;
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
$('#nav').addEventListener('click', (event) => { const button = event.target.closest('button[data-view]'); if (button) activateView(button.dataset.view); });
$('#mobile-nav').addEventListener('change', (event) => activateView(event.target.value));
$('#job-search').addEventListener('input', (event) => { state.jobQuery = event.target.value.trim(); renderJobs(state.data?.jobs || []); });
['plan-horizon', 'plan-audience', 'plan-series', 'plan-search'].forEach((id) => $(`#${id}`).addEventListener(id === 'plan-search' ? 'input' : 'change', renderContentPlan));
$('#plan-reset').addEventListener('click', () => { $('#plan-horizon').value = ''; $('#plan-audience').value = ''; $('#plan-series').value = ''; $('#plan-search').value = ''; renderContentPlan(); });
document.addEventListener('click', (event) => { const link = event.target.closest('[data-job-id]'); if (!link) return; state.jobQuery = link.dataset.jobId; $('#job-search').value = state.jobQuery; renderJobs(state.data?.jobs || []); activateView('jobs'); });
$('#command-form').addEventListener('submit', async (event) => { event.preventDefault(); const input = $('#command-input'), text = input.value.trim(); if (!text) return; message('user', text); input.value = ''; message('assistant', 'Working… Complex operations can take several minutes while tools finish and results are verified.'); const pending = $('#messages .message:last-child'); try { const result = await api('/api/os/command', { method: 'POST', body: JSON.stringify({ message: text, conversation_id: state.conversationId }) }); pending.remove(); message('assistant', result.message, ['BLOCKED', 'TIMED_OUT', 'GENERATION_FAILED', 'VALIDATION_FAILED', 'ASSEMBLY_FAILED'].includes(result.status) ? 'blocked' : ''); if (result.status === 'DELIVERED') renderDeliverables(result); state.conversationId = result.conversation_id; await load(); } catch (error) { pending.remove(); message('assistant', 'The command could not finish: ' + error.message, 'blocked'); } });
$('#command-input').addEventListener('keydown', (event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); $('#command-form').requestSubmit(); } });
$('#login-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button');
  button.disabled = true;
  $('#login-error').textContent = '';
  try { await login($('#login-password').value); $('#login-password').value = ''; }
  catch (error) { showLogin(error.message); }
  finally { button.disabled = false; }
});
$('#logout').addEventListener('click', () => {
  state.token = '';
  sessionStorage.removeItem('infenergyToken');
  showLogin();
});
$('#refresh').addEventListener('click', load);
document.addEventListener('click', (event) => {
  const move = event.target.closest('[data-calendar-move]');
  const today = event.target.closest('[data-calendar-today]');
  if (!move && !today) return;
  state.calendarDate = today ? new Date(new Date().getFullYear(), new Date().getMonth(), 1) : new Date(state.calendarDate.getFullYear(), state.calendarDate.getMonth() + Number(move.dataset.calendarMove), 1);
  $('#social-calendar').innerHTML = empty('Loading calendar');
  loadSocialCalendar().catch((error) => { $('#social-calendar').innerHTML = `<div class="inline-alert">${esc(error.message)}</div>`; });
});
document.addEventListener('click', async (event) => {
  const connect = event.target.closest('[data-tiktok-connect]');
  const disconnect = event.target.closest('[data-tiktok-disconnect]');
  if (!connect && !disconnect) return;
  if (connect) {
    try {
      connect.disabled = true; connect.textContent = 'Opening TikTok…';
      const authorization = await api('/api/auth/tiktok/connect?format=json');
      window.location.assign(authorization.authorization_url);
    } catch (error) { connect.disabled = false; connect.textContent = 'Connect TikTok'; toast(error.message); }
    return;
  }
  if (!window.confirm('Disconnect TikTok and revoke the stored authorization?')) return;
  try { disconnect.disabled = true; await api('/api/auth/tiktok/disconnect', { method: 'POST', body: '{}' }); await loadTikTokStatus(); renderTikTokConnection(); toast('TikTok disconnected'); }
  catch (error) { disconnect.disabled = false; toast(error.message); }
});
$('#master-search').addEventListener('input', renderMasterCapabilities);
$('#master-domain').addEventListener('change', renderMasterCapabilities);
$('#master-capabilities').addEventListener('click', (event) => { const button = event.target.closest('[data-master-capability]'); if (button) selectMasterCapability(button.dataset.masterCapability); });
$('#master-refresh').addEventListener('click', () => loadMaster().catch((error) => toast(error.message)));
$('#master-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const capability = selectedCapability();
  if (!capability) return;
  const button = $('#master-execute');
  try {
    const argumentsValue = JSON.parse($('#master-arguments').value || '{}');
    if (!argumentsValue || Array.isArray(argumentsValue) || typeof argumentsValue !== 'object') throw new Error('Arguments must be a JSON object.');
    button.disabled = true; button.textContent = 'Executing…';
    const result = await api('/api/os/execute', { method: 'POST', body: JSON.stringify({ capability: capability.id, arguments: argumentsValue, dry_run: $('#master-dry-run').checked }) });
    renderMasterResult(result);
    await loadMaster();
    toast(result.status === 'WAITING_APPROVAL' ? 'Approval ready' : 'Capability completed');
  } catch (error) { $('#master-result').innerHTML = `<div class="inline-alert">${esc(error.message)}</div>`; }
  finally { button.disabled = false; button.textContent = 'Execute capability →'; }
});
document.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-master-approval]');
  if (!button) return;
  try {
    button.disabled = true; button.textContent = 'Approving and executing…';
    const result = await api(`/api/os/approvals/${button.dataset.masterApproval}`, { method: 'POST', body: JSON.stringify({ approved: true, execute: true, decided_by: 'owner' }) });
    renderMasterResult(result.execution || result);
    await load();
    toast('Approved and executed exactly once');
  } catch (error) { button.disabled = false; button.textContent = 'Approve & execute once'; toast(error.message); }
});
document.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-master-rollback]');
  if (!button) return;
  try {
    button.disabled = true; button.textContent = 'Rolling back…';
    const result = await api(`/api/os/transactions/${button.dataset.masterRollback}/rollback`, { method: 'POST', body: JSON.stringify({ actor: 'owner' }) });
    renderMasterResult(result);
    await load();
    toast('Operation rolled back');
  } catch (error) { button.disabled = false; button.textContent = 'Rollback'; toast(error.message); }
});
document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-view-deliverables]');
  if (!button) return;
  const transaction = state.transactions.find((item) => item.id === button.dataset.viewDeliverables);
  if (!transaction || !renderDeliverables(transaction)) return toast('No generated package is stored on this transaction.');
  activateView('command');
});
document.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-master-preset]');
  if (!button) return;
  const preset = button.dataset.masterPreset;
  if (preset === 'command' || preset === 'creative') { activateView(preset); return; }
  if (preset === 'plan') { activateView('content-plan'); return; }
  const presets = {
    health: ['system.health', {}, false],
    readiness: ['publication.operations.get', {}, false],
    dispatch: ['publication.dispatch', {}, true],
  };
  if (preset === 'undo') {
    try { button.disabled = true; const result = await api('/api/os/undo', { method: 'POST', body: JSON.stringify({ actor: 'owner' }) }); renderMasterResult(result); await load(); toast('Latest reversible operation undone'); }
    catch (error) { toast(error.message); }
    finally { button.disabled = false; }
    return;
  }
  const configuration = presets[preset];
  if (!configuration) return;
  selectMasterCapability(...configuration);
  $('.master-executor').scrollIntoView?.({ behavior: 'smooth', block: 'start' });
});
$('#new-creative').addEventListener('click', async () => {
  try {
    const result = await api('/api/os/creatives', { method: 'POST', body: JSON.stringify({ title: 'Untitled creative', slide_count: 6, platforms: ['facebook', 'instagram'] }) });
    state.creatives.unshift(result.creative);
    renderCreative(result.creative);
    $('#creative-title').select();
    toast('New idea saved');
  } catch (error) { toast(error.message); }
});
renderGenerationControls();
$('#generation-start').value = new Date().toISOString().slice(0, 10);
$('#generation-toggle').addEventListener('click', () => { $('#generation-form').hidden = !$('#generation-form').hidden; });
$('#generation-horizons').addEventListener('click', (event) => {
  const button = event.target.closest('[data-days]');
  if (!button) return;
  document.querySelectorAll('#generation-horizons [data-days]').forEach((item) => item.classList.toggle('active', item === button));
  const custom = button.dataset.days === 'custom';
  $('#generation-custom-days').hidden = !custom;
  state.generationDays = custom ? Number($('#generation-days').value || 30) : Number(button.dataset.days);
});
$('#generation-days').addEventListener('input', () => { state.generationDays = Math.max(1, Math.min(365, Number($('#generation-days').value || 1))); });
$('#generation-modes').addEventListener('click', (event) => {
  const button = event.target.closest('[data-mode]');
  if (!button) return;
  state.generationMode = button.dataset.mode;
  document.querySelectorAll('#generation-modes [data-mode]').forEach((item) => item.classList.toggle('active', item === button));
  if (state.generationMode === 'CUSTOMIZE') $('#generation-controls-panel').open = true;
});
document.addEventListener('change', (event) => {
  const select = event.target.closest('.delegated-control select');
  if (!select) return;
  const input = select.closest('.delegated-control').querySelector('input');
  input.disabled = select.value !== 'CUSTOM';
  if (!input.disabled) input.focus();
});
$('#generation-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = $('#generation-submit');
  try {
    button.disabled = true; button.textContent = 'Building strategy…';
    const result = await api('/api/os/generation-requests', { method: 'POST', body: JSON.stringify(generationRequestData()) });
    renderGenerationRequest(result.request);
    toast('Content program created');
  } catch (error) { toast(error.message); }
  finally { button.disabled = false; button.textContent = 'Build Content Program'; }
});
$('#generation-result').addEventListener('change', async (event) => {
  const frequency = event.target.closest('[data-day-frequency]');
  if (!frequency) return;
  try { frequency.disabled = true; await persistGenerationDay(frequency.closest('.generation-day')); toast('Day frequency saved'); }
  catch (error) { frequency.disabled = false; toast(error.message); }
});
$('#generation-result').addEventListener('click', async (event) => {
  const edit = event.target.closest('[data-edit-day]');
  if (edit) {
    const controls = edit.closest('.generation-day').querySelector('[data-day-controls]');
    controls.open = true;
    controls.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' });
    return;
  }
  const scopedRegeneration = event.target.closest('[data-regenerate-scope]');
  if (scopedRegeneration) {
    const card = scopedRegeneration.closest('.generation-day');
    const day = state.generationRequest.day_cards.find((item) => item.date === card.dataset.dayDate);
    const postId = scopedRegeneration.closest('[data-generation-post]').dataset.generationPost;
    const post = day.posts.find((item) => item.id === postId);
    try {
      scopedRegeneration.disabled = true;
      const scope = scopedRegeneration.dataset.regenerateScope;
      const command = `${generationCommand(day, post)} Regenerate ${scope} only. Preserve every unaffected component as a new version.`;
      const result = await api('/api/os/execute', { method: 'POST', body: JSON.stringify({ capability: 'creative.command.produce', arguments: { command } }) });
      if (operationOutput(result)) { renderDeliverables(result); activateView('command'); }
      await load();
      toast(result.status === 'WAITING_APPROVAL' ? 'Regeneration is waiting for owner approval' : `${scope} regenerated`);
    } catch (error) { scopedRegeneration.disabled = false; toast(error.message); }
    return;
  }
  const generate = event.target.closest('[data-generate-day]');
  if (generate) {
    try {
      generate.disabled = true; generate.textContent = 'Saving day controls…';
      const day = await persistGenerationDay(generate.closest('.generation-day'));
      if (!(day.posts || []).length) throw new Error('This day has no planned posts. Increase Posts this day first.');
      const results = [];
      for (const post of day.posts) {
        generate.textContent = `Producing ${results.length + 1} of ${day.posts.length}…`;
        results.push(await api('/api/os/execute', { method: 'POST', body: JSON.stringify({ capability: 'creative.command.produce', arguments: { command: generationCommand(day, post) } }) }));
      }
      const delivered = results.find((result) => operationOutput(result));
      if (delivered) { renderDeliverables(delivered); activateView('command'); }
      await load();
      toast(results.some((result) => result.status === 'WAITING_APPROVAL') ? 'Production is waiting for owner approval' : 'Day production completed');
    } catch (error) { generate.disabled = false; generate.textContent = 'Generate This Day'; toast(error.message); }
    return;
  }
  const button = event.target.closest('[data-regenerate]');
  if (!button) return;
  const actions = button.closest('.day-actions');
  const existing = actions.querySelector('.regenerate-menu');
  if (existing) { existing.remove(); return; }
  actions.insertAdjacentHTML('beforeend', '<div class="regenerate-menu"><button type="button" data-regenerate-scope="entire post">Entire Post</button><button type="button" data-regenerate-scope="concept">Concept Only</button><button type="button" data-regenerate-scope="visual">Visual Only</button><button type="button" data-regenerate-scope="caption">Caption Only</button><button type="button" data-regenerate-scope="copy">Copy Only</button><button type="button" data-regenerate-scope="one carousel card">One Carousel Card</button><button type="button" data-regenerate-scope="style">Style Only</button><button type="button" data-regenerate-scope="platform version">Platform Version Only</button></div>');
});
$('#creative-list').addEventListener('click', (event) => { const button = event.target.closest('[data-creative-id]'); if (button) renderCreative(state.creatives.find((item) => item.id === button.dataset.creativeId)); });
['creative-title', 'creative-idea', 'creative-slides', 'creative-platform'].forEach((id) => $(`#${id}`).addEventListener('input', queueCreativeSave));
document.querySelectorAll('.creative-channel').forEach((item) => item.addEventListener('change', queueCreativeSave));
$('#creative-run').addEventListener('click', async () => {
  const button = $('#creative-run');
  try {
    clearTimeout(state.creativeSaveTimer);
    const creative = await saveCreative({ quiet: true });
    if (!creative?.idea) throw new Error('Add the creative idea before scheduling.');
    if (!$('#creative-date').value) throw new Error('Choose a publication date.');
    if (!$('#creative-time').value) throw new Error('Choose a publication time.');
    button.disabled = true; button.textContent = 'Checking, approving, and scheduling…';
    const scheduledAt = `${$('#creative-date').value}T${$('#creative-time').value}:00`;
    const result = await api(`/api/os/creatives/${state.creativeId}/schedule`, { method: 'POST', body: JSON.stringify({ content_date: $('#creative-date').value, scheduled_at: scheduledAt, slot: $('#creative-slot').value }) });
    const index = state.creatives.findIndex((item) => item.id === result.creative.id);
    if (index >= 0) state.creatives[index] = result.creative;
    renderCreative(result.creative);
    toast('Creative checked, approved, and scheduled');
  } catch (error) { $('#creative-result').innerHTML = `<div class="inline-alert">${esc(error.message)}</div>`; }
  finally { button.disabled = false; button.textContent = 'Run checks, approve & schedule'; }
});
$('#new-chat').addEventListener('click', async () => {
  try {
    const result = await api('/api/os/conversations', { method: 'POST', body: JSON.stringify({ title: 'Infenergy Command' }) });
    state.conversationId = result.conversation.id;
    state.renderedConversationId = result.conversation.id;
    $('#messages').innerHTML = '';
    message('assistant', 'New command session started. Company knowledge remains available; this conversation now has a clean objective and plan.');
    toast('New session ready');
  } catch (error) { toast(error.message); }
});
document.addEventListener('click', (event) => { if (event.target.dataset.action === 'plan120') activateView('content-plan'); });
document.addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-approval]');
  if (!button) return;
  const approved = button.dataset.decision === 'approve';
  button.disabled = true; button.textContent = approved ? 'Executing…' : 'Rejecting…';
  const progressMessage = approved ? executionMessage() : null;
  let polling = Boolean(approved);
  const poll = approved ? window.setInterval(async () => {
    if (!polling) return;
    try {
      const response = await api('/api/os/transactions');
      const transaction = (response.transactions || []).find((item) => item.approval_id === button.dataset.approval);
      if (transaction) updateExecutionMessage(progressMessage, transaction);
    } catch { /* The approval request remains authoritative; the next poll can recover. */ }
  }, 1000) : null;
  try {
    const result = await api(`/api/os/approvals/${button.dataset.approval}`, { method: 'POST', body: JSON.stringify({ approved, execute: approved, decided_by: 'owner', conversation_id: state.conversationId }) });
    if (approved) {
      const execution = result.execution || {};
      const job = execution.result?.job;
      if (!renderDeliverables(result, progressMessage)) {
        progressMessage.remove();
        message('assistant', result.message || (job ? `Approval executed once. Durable job \`${job.id}\` is now **${job.status}** with ${job.steps?.length || 0} tracked steps. Transaction: \`${execution.transaction_id}\`.` : `Approval executed once. **${execution.capability || 'Operation'}** finished with status **${execution.status}**. Transaction: \`${execution.transaction_id}\`.`));
      }
    } else message('assistant', 'The pending operation was rejected and will not execute.');
    await load();
  } catch (error) { if (progressMessage) progressMessage.remove(); button.disabled = false; button.textContent = approved ? 'Approve & run once' : 'Reject'; message('assistant', 'Approval action failed: ' + error.message, 'blocked'); }
  finally { polling = false; if (poll) window.clearInterval(poll); }
});
const callbackResult = new URLSearchParams(window.location.search).get('tiktok');
if (state.token) { showApp(); load().then(() => { if (callbackResult) { activateView('social'); toast(callbackResult === 'connected' ? 'TikTok connected' : 'TikTok authorization was not completed'); history.replaceState({}, '', '/os'); } }); } else showLogin();
