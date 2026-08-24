const state = { data: null, conversationId: null };
const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char]));

async function api(path, options = {}) {
  const token = localStorage.getItem('infenergyToken') || prompt('Enter the Infenergy owner token');
  if (token) localStorage.setItem('infenergyToken', token);
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(path, { ...options, headers });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
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
function empty(title, detail = '') { return `<div class="empty-state"><span>✓</span><strong>${esc(title)}</strong>${detail ? `<p>${esc(detail)}</p>` : ''}</div>`; }
function humanize(value) { return String(value || 'Unknown').replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase()); }
function relativeTime(value) { if (!value) return 'Not recorded'; const date = new Date(value); if (Number.isNaN(date.getTime())) return String(value); const seconds = Math.round((date.getTime() - Date.now()) / 1000); for (const [size, unit] of [[31536000, 'year'], [2592000, 'month'], [86400, 'day'], [3600, 'hour'], [60, 'minute']]) { if (Math.abs(seconds) >= size) return new Intl.RelativeTimeFormat('en', { numeric: 'auto' }).format(Math.round(seconds / size), unit); } return 'just now'; }
function dateTime(value) { if (!value) return '—'; const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }); }
function tone(status) { const value = String(status || '').toUpperCase(); if (['OPERATIONAL', 'ACTIVE', 'COMPLETED', 'PUBLISHED', 'READY', 'SUCCESS', 'HEALTHY'].some((word) => value.includes(word))) return 'good'; if (['FAILED', 'BLOCKED', 'DENIED', 'CANCELED', 'ERROR', 'MISSING', 'DEGRADED'].some((word) => value.includes(word))) return 'bad'; if (['WAITING', 'PAUSED', 'PLANNING', 'DRY_RUN', 'UNPLANNED', 'PENDING'].some((word) => value.includes(word))) return 'warn'; return 'neutral'; }
function pill(label, status = label) { return `<span class="pill ${tone(status)}"><i></i>${esc(humanize(label))}</span>`; }
function percent(value) { const number = Number(value || 0); return Math.max(0, Math.min(100, number <= 1 ? number * 100 : number)); }

function renderToday(attention, events) {
  const signals = attention.map((item) => { const score = Number(item.score || item.materiality || 0); return `<article class="signal-card"><div class="card-top"><span class="kicker">Executive attention</span><strong class="score">${score.toFixed(1)}</strong></div><h3>${esc(item.title || item.subject || 'Material signal')}</h3><p>${esc(item.summary || item.description || 'Requires owner review.')}</p><div class="meta-line">${pill(item.status || 'OPEN')}<span>${esc(relativeTime(item.created_at))}</span></div></article>`; }).join('');
  const recent = events.slice(0, 8).map((event) => { const payload = event.payload || {}; const detail = [payload.capability && humanize(payload.capability), payload.status && humanize(payload.status)].filter(Boolean).join(' · '); return `<article class="event-card"><div class="event-icon ${tone(payload.status || event.type)}">${tone(payload.status || event.type) === 'good' ? '✓' : '•'}</div><div><h3>${esc(humanize(event.type || 'System event'))}</h3><p>${esc(detail || `${humanize(event.subject_type || 'system')} update recorded`)}</p><small>${esc(relativeTime(event.recorded_at || event.occurred_at))}</small></div></article>`; }).join('');
  $('#today-content').innerHTML = signals || recent ? `${signals ? `<div class="section-label">Priority signals</div><div class="dashboard-grid">${signals}</div>` : ''}${recent ? `<div class="section-label ${signals ? 'spaced' : ''}">Recent operations</div><div class="event-list">${recent}</div>` : ''}` : empty('Everything is clear', 'No material signals or recent events require attention.');
}

function renderJobs(jobs) {
  if (!jobs.length) { $('#jobs-table').innerHTML = empty('No jobs in the execution fabric', 'Create a research mission or preview the rolling 120-day plan.'); return; }
  $('#jobs-table').innerHTML = `<div class="data-table"><div class="table-head"><span>Job</span><span>Status</span><span>Progress</span><span>Updated</span></div>${jobs.map((job) => { const progress = percent(job.progress); return `<div class="table-row"><div><strong>${esc(job.objective || humanize(job.job_type))}</strong><small>${esc(humanize(job.job_type))}${job.current_step ? ` · ${esc(humanize(job.current_step))}` : ''}</small></div><div>${pill(job.status)}</div><div class="progress-cell"><div class="progress"><i style="width:${progress}%"></i></div><small>${Math.round(progress)}%</small></div><div><span>${esc(relativeTime(job.updated_at))}</span><small>${job.steps?.length || 0} steps</small></div></div>`; }).join('')}</div>`;
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

function renderSocial(today) {
  if (!today) { $('#social-content').innerHTML = empty('No social schedule loaded'); return; }
  const slots = Array.isArray(today.slots) ? today.slots : Object.entries(today.by_slot || {}).map(([slot, value]) => ({ slot, ...value }));
  const summary = [['Required', today.required || 0], ['Ready', today.ready || 0], ['Published', today.published || 0], ['Missing', today.missing || 0]];
  $('#social-content').innerHTML = `<div class="social-summary">${summary.map(([label, value]) => `<div><b>${esc(value)}</b><span>${esc(label)}</span></div>`).join('')}</div><div class="slot-grid">${['morning', 'midday', 'evening'].map((name) => { const slot = slots.find((item) => String(item.slot).toLowerCase() === name) || { slot: name, status: 'UNPLANNED' }; const platforms = slot.platform_policy?.platforms || Object.keys(slot.platform_results || {}); return `<article class="slot-card ${tone(slot.status)}"><div class="card-top"><span class="slot-time">${esc(humanize(name))}</span>${pill(slot.status || 'UNPLANNED')}</div><h3>${slot.content_id ? 'Content package ready' : 'No content assigned'}</h3><p>${slot.scheduled_at ? esc(dateTime(slot.scheduled_at)) : 'Schedule not available'}</p><div class="platforms">${platforms.length ? platforms.map((platform) => `<span title="${esc(humanize(platform))}">${esc(platform.slice(0, 1).toUpperCase())}</span>`).join('') : '<small>No channels assigned</small>'}</div>${slot.last_error ? `<div class="inline-alert">${esc(slot.last_error)}</div>` : ''}</article>`; }).join('')}</div>`;
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
  const attention = data.attention || [], jobs = data.jobs || [], policies = data.policies || [], health = data.health || {};
  const activeJobs = jobs.filter((job) => !['COMPLETED', 'CANCELED'].includes(job.status));
  const providerCount = Object.values(health.providers || {}).filter((provider) => provider.configured || provider.sdk_installed).length;
  $('#attention-count').textContent = attention.length; $('#job-count').textContent = activeJobs.length;
  $('#attention-list').innerHTML = attention.slice(0, 4).map((item) => `<div class="list-item"><strong>${esc(item.title)}</strong><small>Priority ${Number(item.score || 0).toFixed(1)}</small></div>`).join('') || 'Nothing material is waiting.';
  $('#job-list').innerHTML = activeJobs.slice(0, 4).map((job) => `<div class="list-item"><strong>${esc(job.objective)}</strong><small>${esc(humanize(job.status))} · ${Math.round(percent(job.progress))}%</small></div>`).join('') || 'No active jobs.';
  $('#policy-summary').innerHTML = policies.slice(0, 4).map((policy) => `<div class="list-item"><strong>${esc(humanize(policy.capability))}</strong><small>${esc(humanize(policy.approval_level))}</small></div>`).join('') || 'Default deny for mutations.';
  $('#today-metrics').innerHTML = [['Attention', attention.length], ['Active jobs', activeJobs.length], ['Findings', (data.research_findings || []).length], ['Automations', (data.automations || []).length], ['Providers', providerCount]].map(([label, value]) => `<div class="metric panel"><b>${value}</b><span>${esc(label)}</span></div>`).join('');
  renderToday(attention, data.recent_events || []); renderJobs(jobs); renderResearch(data.research_findings || []); renderAutomations(data.automations || [], data.watches || [], data.automation_runs || []); renderSocial(health.social_today); renderStrategy(policies); renderActivity(data.recent_activity || []); renderHealth(health); renderPermissions(policies);
}

async function load() { try { const data = await api('/api/os/state'); state.data = data; state.conversationId = data.conversation?.id; render(data); $('#system-dot').className = 'dot ok'; $('#system-label').textContent = 'OS connected'; } catch (error) { $('#system-dot').className = 'dot bad'; $('#system-label').textContent = 'Connection blocked'; toast(error.message); } }
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
$('#command-form').addEventListener('submit', async (event) => { event.preventDefault(); const input = $('#command-input'), text = input.value.trim(); if (!text) return; message('user', text); input.value = ''; message('assistant', 'Working… Complex operations can take several minutes while tools finish and results are verified.'); const pending = $('#messages .message:last-child'); try { const result = await api('/api/os/command', { method: 'POST', body: JSON.stringify({ message: text, conversation_id: state.conversationId }) }); pending.remove(); message('assistant', result.message, ['BLOCKED', 'TIMED_OUT'].includes(result.status) ? 'blocked' : ''); state.conversationId = result.conversation_id; await load(); } catch (error) { pending.remove(); message('assistant', 'The command could not finish: ' + error.message, 'blocked'); } });
$('#command-input').addEventListener('keydown', (event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); $('#command-form').requestSubmit(); } });
$('#refresh').addEventListener('click', load);
$('#new-chat').addEventListener('click', async () => {
  try {
    const result = await api('/api/os/conversations', { method: 'POST', body: JSON.stringify({ title: 'Infenergy Command' }) });
    state.conversationId = result.conversation.id;
    $('#messages').innerHTML = '';
    message('assistant', 'New command session started. Company knowledge remains available; this conversation now has a clean objective and plan.');
    toast('New session ready');
  } catch (error) { toast(error.message); }
});
document.addEventListener('click', async (event) => { if (event.target.dataset.action !== 'plan120') return; try { const result = await api('/api/os/execute', { method: 'POST', body: JSON.stringify({ capability: 'content.plan_120_days', arguments: { objective: 'Build the next 120 days. Entertainment first. Keep the future adaptive.' }, dry_run: true }) }); toast(result.status); await load(); } catch (error) { toast(error.message); } });
load();
