let adminKey = "";
document.addEventListener('click', event => {
  if (event.target.id === 'edit-selected-plan') {
    document.querySelector(`[data-edit-campaign="${el('plan-campaign').value}"]`)?.click();
  }
  if (event.target.id === 'cancel-schedule-edit') el('schedule-edit-form').hidden = true;
  if (event.target.id === 'edit-meta-dates') {
    const d = savedCampaignPlans.find(p => p.campaign_id === el('plan-campaign').value);
    const form = el('schedule-edit-form');
    form.dataset.campaign = d.campaign_id;
    form.elements.start_date.value = d.plan.start_date;
    form.elements.end_date.value = d.plan.end_date;
    el('schedule-edit-message').textContent = '';
    form.hidden = false;
    form.elements.start_date.focus();
  }
});
document.addEventListener('submit', async event => {
  if (event.target.id !== 'schedule-edit-form') return;
  event.preventDefault();
  const form = event.target;
  const payload = {start_date:form.elements.start_date.value, end_date:form.elements.end_date.value};
  if (!window.confirm(`Save dates ${payload.start_date} through ${payload.end_date} to this paused Meta Ad Set? Budget stays unchanged; final launch approval will be required again.`)) return;
  const button = form.querySelector('button');
  button.disabled = true;
  try {
    await request(`/integrations/campaigns/${encodeURIComponent(form.dataset.campaign)}/schedule`, {method:'PUT', body:JSON.stringify(payload)});
    await loadDashboard();
    el('plan-campaign').dispatchEvent(new Event('change'));
    el('plan-message').textContent = 'Dates saved and verified in Meta. Delivery remains paused. Review billing and give final launch approval when ready.';
  } catch (error) { el('schedule-edit-message').textContent = error.message; }
  finally { button.disabled = false; }
});
let workflowApprovals = [];
let savedCampaignPlans = [];
let campaignChoices = [];
let draftRequestKey = null, draftRequestPayload = null;
let workflowData = null;
// MCP probe cannot execute tools or change campaigns.
let selectedLocations = [], locationResults = [], liveWritesEnabled = false, pausedPreparationEnabled = false;
const headers = () => ({ "Content-Type": "application/json", "X-Admin-Key": adminKey });
const el = (id) => document.getElementById(id);
function budgetLabel(plan) {
  return plan.budget_mode === 'DYNAMIC' ? `Dynamic: INR ${plan.daily_budget_min_inr}–${plan.daily_budget_inr}/day; INR ${plan.weekly_budget_inr} total maximum` : `Fixed: INR ${plan.daily_budget_inr}/day; INR ${plan.weekly_budget_inr} total maximum`;
}
function showBudgetMode() {
  const dynamic = el('budget-mode-form').elements.mode.value === 'DYNAMIC';
  el('budget-fixed-fields').hidden = dynamic;
  el('budget-range-fields').hidden = !dynamic;
  el('budget-fixed').disabled = dynamic;
  el('budget-min').disabled = el('budget-max').disabled = !dynamic;
  el('budget-fixed').required = !dynamic;
  el('budget-min').required = el('budget-max').required = dynamic;
}
el('budget-mode-form').addEventListener('change', showBudgetMode);
showBudgetMode();
el('budget-mode-form').addEventListener('submit', async event => {
  event.preventDefault();
  const id = el('plan-campaign').value;
  if (!id) { el('budget-mode-message').textContent = 'Create or select a draft first.'; return; }
  const dynamic = event.target.elements.mode.value === 'DYNAMIC';
  const payload = {budget_mode:dynamic ? 'DYNAMIC' : 'FIXED', daily_budget_inr:Number(el(dynamic ? 'budget-max' : 'budget-fixed').value), weekly_budget_limit_inr:Number(el('budget-weekly').value)};
  if (dynamic) { payload.daily_budget_min_inr = Number(el('budget-min').value); payload.daily_budget_max_inr = Number(el('budget-max').value); }
  const button = event.target.querySelector('button'); button.disabled = true;
  try {
    await request(`/campaigns/${encodeURIComponent(id)}/budget`, {method:'PUT', body:JSON.stringify(payload)});
    await loadDashboard();
    el('budget-mode-message').textContent = 'Budget settings saved to this draft. Review and approve the updated plan before creating Meta ads.';
  } catch (error) { el('budget-mode-message').textContent = error.message; }
  finally { button.disabled = false; }
});
document.querySelectorAll('input[name="daily_budget_inr"]').forEach(input => { input.max = "150"; });
document.querySelectorAll('input[name="weekly_budget_limit_inr"]').forEach(input => { input.max = "1050"; });
const campaignPicker = el("plan-campaign").closest("label");
campaignPicker.firstChild.textContent = "Selected campaign — used for details, approval and Meta actions";
el("app").prepend(campaignPicker);
el("plan-form").querySelector("button").textContent = "Save and review campaign";
el("review-section").querySelector("h2").textContent = "2. Review your campaign and approve";
el("review-section").querySelector("p").textContent = "Check the product, dates, locations and budget below. Click Approve this plan and product, then Confirm approval. No ad spends money at this step.";
const manageLink = document.createElement("a");
manageLink.href = "#manage-campaigns";
manageLink.textContent = "Manage / delete campaigns";
el("app").prepend(manageLink);
const escapeHtml = (value) => String(value ?? "—").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"})[char]);

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 60000);
  try {
    const response = await fetch(path, { ...options, signal: controller.signal, headers: { ...headers(), ...(options.headers || {}) } });
    if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(Array.isArray(body.detail) ? body.detail.map(item => item.msg).join("; ") : body.detail || "Request failed"); }
    return await response.json();
  } catch (error) {
    if (error.name === "AbortError") throw new Error("The server did not respond within 60 seconds. Refresh to check the result before repeating the action; it may still be processing.");
    throw error;
  } finally { clearTimeout(timeout); }
}
function rows(items, render, empty) { return items.length ? items.map(render).join("") : `<p class="muted">${empty}</p>`; }
function campaignIdentity(c) {
  const d = savedCampaignPlans.find(p => p.campaign_id === c.id);
  return `${c.name} · ${d?.remote_campaign_id ? 'Meta ' + d.remote_campaign_id : 'Local only · ' + c.id.slice(0, 8)} · ${c.status}`;
}
function canDeleteLocal(c) {
  const d = savedCampaignPlans.find(p => p.campaign_id === c.id);
  return ['DRAFT', 'PENDING_APPROVAL', 'READY', 'FAILED'].includes(c.status) && !c.meta_campaign_id &&
    ![d?.remote_campaign_id, d?.remote_adset_id, d?.remote_creative_id, d?.remote_ad_id, d?.operation, d?.automation_enabled].some(Boolean);
}
function fillSelect(id, items, label, empty) {
  const select = el(id), previous = select.value;
  select.innerHTML = `<option value="">${empty}</option>` + items.map(item => `<option value="${escapeHtml(item.id)}">${escapeHtml(label(item))}</option>`).join("");
  if (items.some(item => item.id === previous)) select.value = previous;
  select.disabled = !items.length;
}
async function loadWorkflow(campaigns, cached = null) {
  const [products, allApprovals, allPlans] = cached || await Promise.all([request("/catalog?available_only=true"), request("/approvals"), request("/integrations/campaigns")]);
  workflowData = [products, allApprovals, allPlans];
  const activeIds = new Set(campaigns.map(c => c.id));
  const approvals = allApprovals.filter(a => activeIds.has(a.campaign_id));
  const allActivePlans = allPlans.filter(p => activeIds.has(p.campaign_id));
  workflowApprovals = approvals;
  savedCampaignPlans = allActivePlans;
  campaignChoices = campaigns;
  const campaignName = id => campaigns.find(c => c.id === id)?.name || id;
  fillSelect("plan-campaign", campaigns, campaignIdentity, "Select a campaign");
  if (!el("plan-campaign").value && campaigns.length) {
    const remembered = sessionStorage.getItem('selectedCampaign');
    el("plan-campaign").value = campaigns.find(c => c.id === remembered)?.id || allActivePlans.find(p => p.prepared)?.campaign_id || campaigns[0].id;
  }
  sessionStorage.setItem('selectedCampaign', el('plan-campaign').value);
  const plans = allActivePlans.filter(p => p.campaign_id === el("plan-campaign").value);
  fillSelect("plan-product", products.map(p => ({...p, id:p.product_code})), p => `${p.product_code} — ${p.name}`, products.length ? "Select a product" : "Import or add products first");
  const editable = campaigns.find(c => c.id === el("plan-campaign").value)?.status === "DRAFT";
  const selectedCampaign = campaigns.find(c => c.id === el('plan-campaign').value);
  const selectedPlan = plans[0];
  el('schedule-edit-form').hidden = true;
  el('edit-plan-controls').innerHTML = editable ? '<p>Draft: edit the fields below, then save and review.</p>' : selectedPlan?.remote_adset_id
    ? '<p>This plan is saved in Meta. Edit its dates here. For product, caption, audience or budget changes, use Campaign history to prepare a revised copy.</p><button type="button" id="edit-meta-dates">Edit schedule</button>'
    : selectedCampaign && canDeleteLocal(selectedCampaign) ? '<p>This saved plan is locked after review.</p><button type="button" id="edit-selected-plan">Edit campaign details</button>' : '<p>Select an editable campaign to change its details.</p>';
  for (const field of el("plan-form").elements) field.disabled = !editable;
  if (!products.length) el("plan-product").disabled = true;
  el("plan-list").innerHTML = rows(plans, d => {
    const p = d.plan;
    return `<div class="row"><div><strong>${escapeHtml(campaignName(d.campaign_id))}</strong><p>${escapeHtml(p.caption)}</p><small>Product: ${escapeHtml(p.product_code)} · INR ${p.daily_budget_inr}/day · INR ${p.weekly_budget_inr} maximum<br>${escapeHtml(p.start_date)} to ${escapeHtml(p.end_date)} · Ages ${p.age_min}–${p.age_max}<br>${escapeHtml(p.locations.map(l => l.name).join(", "))}<br>${escapeHtml(p.windows.map(w => `${w.start}–${w.end}`).join(", "))} (${escapeHtml(p.timezone)})<br>Destination: ${escapeHtml(p.destination)}<br>Platforms: ${p.instagram_actor_id ? "Facebook + Instagram" : "Facebook"}</small></div></div>`;
  }, "No campaign plans saved yet.");
  el("live-campaigns").innerHTML = rows(plans, d => {
    const c = campaigns.find(c => c.id === d.campaign_id);
    const action = (name, label) => {
      const reason = d.operation ? "A previous Meta operation is unresolved. Check Ads Manager before retrying to avoid duplicate ads." : !(name === "prepare" ? (pausedPreparationEnabled || liveWritesEnabled) : liveWritesEnabled) ? "This action is disabled in the local application configuration." : "";
      return `<div><button data-live-action="${name}" data-id="${escapeHtml(d.campaign_id)}" ${reason ? `disabled title="${escapeHtml(reason)}"` : ""}>${label}</button>${reason ? `<p class="muted">${escapeHtml(reason)}</p>` : ""}</div>`;
    };
    return `<div class="row"><div><strong>${escapeHtml(c?.name)}</strong><small>${escapeHtml(c?.status)} · ${d.prepared ? "Prepared on Meta" : "Not prepared"} · Scheduling ${d.automation_enabled ? "enabled" : "off"}</small>${d.last_error ? `<p class="error">${escapeHtml(d.last_error)}</p>` : ""}${d.operation ? `<p>Pending operation: ${escapeHtml(d.operation)}. Reconcile in Ads Manager before retrying.</p>` : ""}</div><div class="actions">${["READY", "FAILED"].includes(c?.status) && !d.prepared ? action("prepare", "Prepare paused ads") : ""}${d.prepared && d.owner_status === "APPROVED" && ["READY", "PAUSED"].includes(c?.status) ? action("activate", "Activate approved campaign") : ""}${d.remote_campaign_id && c?.status !== "ENDED" ? action("pause", "Pause") + action("end", "End campaign") : ""}</div></div>`;
  }, "Save and approve a campaign plan first.");
  for (const d of plans) {
    const panel = document.createElement("div");
    panel.className = "meta-diagnostics";
    panel.classList.add(d.connection_ok ? "meta-ok" : "meta-error");
    const values = {"Selected campaign":campaignIdentity(campaigns.find(c => c.id === d.campaign_id)), "Meta connection":d.connection_ok ? "GREEN — last check succeeded" : "RED — unverified or failed", "Ad account":d.ad_account_id || "Not bound yet", "Campaign ID":d.remote_campaign_id, "Ad Set ID":d.remote_adset_id, "Creative ID":d.remote_creative_id, "Ad ID":d.remote_ad_id, "Creation status":d.creation_status, "Campaign status on Meta":d.meta_campaign_status, "Ad status on Meta":d.meta_ad_status, "Payment status":d.payment_status, "Launch approval":d.owner_status, "Last successful Meta sync":d.last_meta_sync};
    panel.innerHTML = `<h3>Meta diagnostics</h3><dl>${Object.entries(values).map(([k,v]) => `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v || "Not verified")}</dd>`).join("")}</dl><p>${escapeHtml(d.billing_note)}</p><div class="actions"><button type="button" data-meta-step="health" data-id="${escapeHtml(d.campaign_id)}">Re-check Meta status</button>${d.prepared ? `<button type="button" data-meta-step="billing" data-id="${escapeHtml(d.campaign_id)}">Verify and open Meta payment</button>` : ""}</div>${d.prepared && ["PAYMENT_PENDING", "OWNER_REVIEWED_IN_META"].includes(d.payment_status) ? `<label class="confirmation"><input type="checkbox" class="billing-reviewed">I reviewed billing in Meta and approve launching with the displayed budget.</label><button type="button" data-meta-step="launch-approval" data-id="${escapeHtml(d.campaign_id)}">Confirm owner launch approval</button>` : ""}<p class="meta-step-result" role="status"></p>`;
    el("live-campaigns").append(panel);
    if (d.budget_diagnosis) {
      const diagnosis = d.budget_diagnosis;
      const explanation = document.createElement('div');
      explanation.className = 'notice';
      const title = document.createElement('h3'); title.textContent = 'Budget needs owner review';
      const message = document.createElement('p'); message.textContent = diagnosis.message;
      const options = document.createElement('ul');
      for (const text of diagnosis.options) { const li = document.createElement('li'); li.textContent = text; options.append(li); }
      const note = document.createElement('p'); note.textContent = diagnosis.note;
      explanation.append(title, message, options, note);
      panel.append(explanation);
    }
  }
  el("catalog-empty-help").hidden = products.length > 0;
  el("approval-list").innerHTML = rows(plans, d => {
    const p = d.plan, c = campaigns.find(c => c.id === d.campaign_id);
    const a = approvals.find(a => a.id === d.approval_id);
    let photo = "";
    try { const url = new URL(p.image_url); if (["https:", "http:"].includes(url.protocol)) photo = `<a href="${escapeHtml(url.href)}" target="_blank" rel="noopener noreferrer"><img class="review-photo" src="${escapeHtml(url.href)}" alt="${escapeHtml(p.product_name)}" loading="lazy" referrerpolicy="no-referrer"><br>View full product photo</a>`; } catch {}
    const editable = ["DRAFT", "PENDING_APPROVAL"].includes(c.status) && !d.operation && !d.remote_campaign_id;
    const controls = a?.status === "APPROVED" ? `<strong>Plan approved</strong><p>${d.prepared ? "Meta objects verified. Continue below to review billing and approve launch." : "Next: create and verify the Meta objects. Payment stays unavailable until this succeeds."}</p><a href="#launch-section">Continue to Meta setup</a>` : editable ? `<button type="button" data-review-action="approve" data-campaign="${escapeHtml(c.id)}">Approve this plan and product</button>${a?.status === "PENDING" ? `<button type="button" class="secondary" data-decision="reject" data-id="${escapeHtml(a.id)}">Reject / edit</button>` : ""}` : `<span>${escapeHtml(c.status)}</span>`;
    return `<article class="review-card"><h3>${escapeHtml(c.name)}</h3><div class="review-layout">${photo}<div><strong>${escapeHtml(p.product_name)}</strong><p>${escapeHtml(p.caption)}</p><p>INR ${p.daily_budget_inr}/day · INR ${p.weekly_budget_inr} total limit<br>${escapeHtml(p.start_date)} to ${escapeHtml(p.end_date)}<br>Locations: ${escapeHtml(p.locations.map(l => l.name).join(", "))}<br>Ages ${p.age_min}–${p.age_max}<br>${escapeHtml(p.windows.map(w => `${w.start}–${w.end}`).join(", "))} (${escapeHtml(p.timezone)})<br>Customer enquiries on WhatsApp: ${escapeHtml(p.whatsapp_number)}<br>Placements: ${p.instagram_actor_id ? "Facebook and Instagram" : "Facebook"}</p><div class="actions">${controls}</div></div></div></article>`;
  }, "Save a campaign plan above. Its product and approval actions will appear here automatically.");
  const incomplete = approvals.filter(a => a.status === "PENDING" && !plans.some(d => d.approval_id === a.id));
  el('approval-list').querySelectorAll('article').forEach((card, index) => {
    const label = document.createElement('p');
    label.textContent = budgetLabel(plans[index].plan);
    card.querySelector('h3').after(label);
  });
  el("approval-list").innerHTML += incomplete.map(a => `<div class="row"><p>${escapeHtml(campaignName(a.campaign_id))}: incomplete plan. Reject to edit.</p><button type="button" data-decision="reject" data-id="${escapeHtml(a.id)}">Reject / edit</button></div>`).join("");
}
async function submitWorkflow(form, messageId, path, payload) {
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    await request(path, {method:"POST", body:JSON.stringify(payload)});
    el(messageId).textContent = "Saved successfully.";
    form.reset();
    try { await loadDashboard(); } catch { el(messageId).textContent = "Saved, but refresh failed. Use Refresh to reload the records."; }
  } catch(error) { el(messageId).textContent = error.message; }
  finally { button.disabled = false; }
}
async function loadDashboard() {
  const reusable = await request("/campaigns/reusable");
  el("reuse-history").innerHTML = rows(reusable, c => `<div class="row"><div><strong>${escapeHtml(c.name)}</strong><small>${c.previously_run ? "Previously run" : "Saved plan — not verified as run"} · ${escapeHtml(c.status)}</small></div><button type="button" class="secondary" data-reuse-id="${escapeHtml(c.id)}" data-reuse-name="${escapeHtml(c.name)}">Use this campaign</button></div>`, "No saved campaign history yet. Save your first campaign plan to reuse it here.");
  if (!reusable.some(c => c.id === el("reuse-campaign").value)) {
    el("reuse-campaign").value = "";
    el("reuse-selected").textContent = "Select a campaign from history above.";
  }
  const [overview, campaigns, setup] = await Promise.all([request("/dashboard/overview"), request("/campaigns"), request("/setup/status")]);
  el("campaign-count").textContent = overview.counts.campaigns; el("ready-count").textContent = overview.counts.ready_campaigns;
  el("product-count").textContent = overview.counts.catalog_products; el("lead-count").textContent = overview.counts.leads;
  liveWritesEnabled = setup.live_operations_enabled;

  pausedPreparationEnabled = setup.paused_preparation_enabled;
  await loadWorkflow(campaigns);
  el("setup-status").innerHTML = `<p><strong>${liveWritesEnabled ? "Live writes enabled — verify the account before use" : "Live writes disabled"}</strong></p><p class="muted">Still needed: ${escapeHtml(setup.missing_live_configuration.filter(name => !name.startsWith('WHATSAPP_') && !['OWNER_WHATSAPP_NUMBER', 'PUBLIC_DASHBOARD_URL'].includes(name)).join(", ") || "Run the account check")}</p>`;
  el("campaigns").innerHTML = rows(campaigns, c => `<div class="row"><div><strong>${escapeHtml(c.name)}</strong><small>₹${c.daily_budget_inr}/day · ₹${c.weekly_budget_limit_inr} total limit</small></div><div class="actions"><button type="button" data-open-campaign="${escapeHtml(c.id)}">Open campaign</button><span class="badge">${escapeHtml(c.status === "PENDING_APPROVAL" && workflowApprovals.some(a => a.campaign_id === c.id && a.status === "APPROVED") ? "Approved — ready to prepare" : c.status)}</span>${canDeleteLocal(c) ? `<button type="button" data-edit-campaign="${escapeHtml(c.id)}">Edit saved campaign</button><button type="button" class="secondary" data-delete-campaign="${escapeHtml(c.id)}" data-name="${escapeHtml(campaignIdentity(c))}">Delete local campaign</button>` : ""}</div></div>`, "No campaigns yet.");
  el("leads").innerHTML = rows(overview.recent_leads, lead => `<div class="row"><div><strong>${escapeHtml(lead.customer_name || "New lead")}</strong><small>${escapeHtml(lead.product_interest)} · ${escapeHtml(lead.city)}</small></div><span class="badge">${escapeHtml(lead.status)} · ${lead.score}</span></div>`, "No leads received yet.");
  for (const row of el("campaigns").children) {
    const button = row.querySelector("[data-delete-campaign]");
    if (button) button.className = "danger";
    else if (row.classList.contains("row")) {
      const note = document.createElement("p");
      note.textContent = "This campaign has Meta activity or a protected status. To revise its plan, use Campaign history above to create an editable copy. The original ad remains unchanged.";
      row.append(note);
    }
  }

}
el("key-form").addEventListener("submit", async (event) => { event.preventDefault(); adminKey = el("admin-key").value; try { await loadDashboard(); el("admin-key").value = ""; el("key-panel").hidden = true; el("app").hidden = false; el("logout").hidden = false; el("plan-campaign").dispatchEvent(new Event("change")); } catch (error) { el("key-error").textContent = error.message; } });
el("logout").addEventListener("click", () => { adminKey = ""; window.location.reload(); });
el("refresh").addEventListener("click", async () => {
  if (!adminKey) { el("session-message").textContent = "Unlock the dashboard to refresh campaign data."; el("admin-key").focus(); return; }
  el("refresh").disabled = true;
  el("session-message").textContent = "Refreshing…";
  try { await loadDashboard(); el("session-message").textContent = "Dashboard refreshed. Unsaved form entries have been kept."; }
  catch (error) { el("session-message").textContent = error.message; }
  finally { el("refresh").disabled = false; }
});
el("reuse-form").addEventListener("submit", async event => {
  event.preventDefault();
  const source = el("reuse-campaign").value;
  if (!source) { el("reuse-message").textContent = "Choose Use this campaign from history first."; return; }
  const data = Object.fromEntries(new FormData(event.target));
  data.daily_budget_inr = Number(data.daily_budget_inr);
  data.weekly_budget_limit_inr = Number(data.weekly_budget_limit_inr);
  const button = event.target.querySelector("button"); button.disabled = true;
  try {
    const result = await request(`/campaigns/${encodeURIComponent(source)}/reuse`, {method:"POST", body:JSON.stringify(data)});
    event.target.reset();
    await loadDashboard();
    el("plan-campaign").value = result.id;
    el("plan-campaign").dispatchEvent(new Event("change"));
    el("reuse-message").textContent = "New draft created. Review its saved plan below and request fresh approval. No ads launched.";
  } catch (error) { el("reuse-message").textContent = error.message; }
  finally { button.disabled = false; }
});
el("reuse-history").addEventListener("click", event => {
  const button = event.target.closest("button[data-reuse-id]");
  if (!button) return;
  const form = el("reuse-form");
  form.reset();
  el("reuse-campaign").value = button.dataset.reuseId;
  el("reuse-selected").textContent = `Selected: ${button.dataset.reuseName}`;
  form.elements.namedItem("name").value = `${button.dataset.reuseName} — new run`.slice(0, 255);
  el("reuse-message").textContent = "Enter the new budget and dates below. This creates a draft, not a live ad.";
  form.scrollIntoView({behavior:"smooth", block:"center"});
  form.elements.namedItem("daily_budget_inr").focus({preventScroll:true});
});
el("mcp-check").addEventListener("click", async () => {
  el("mcp-check").disabled = true;
  el("mcp-message").textContent = "Checking server availability…";
  try {
    const result = await request("/integrations/meta/mcp/check", {method:"POST"});
    el("mcp-message").textContent = `${result.status}: ${result.note}`;
  } catch (error) { el("mcp-message").textContent = error.message; }
  finally { el("mcp-check").disabled = false; }
});
el("campaigns").addEventListener("click", async event => {
  const button = event.target.closest("button[data-delete-campaign]");
  if (!button) return;
  const row = button.closest(".row");
  let panel = row.querySelector(".delete-confirmation");
  if (!panel) {
    panel = document.createElement("div");
    panel.className = "delete-confirmation";
    panel.innerHTML = `<p>Permanently delete <strong>${escapeHtml(button.dataset.name)}</strong> and its saved plan? This cannot be undone. Archive keeps the records and hides the campaign instead.</p><div class="actions"><button type="button" class="danger" data-confirm-delete>Yes, delete</button><button type="button" class="secondary" data-confirm-archive>Archive instead</button><button type="button" class="secondary" data-cancel-delete>Cancel</button></div><p role="status"></p>`;
    row.append(panel);
    panel.querySelector("[data-cancel-delete]").onclick = () => panel.remove();
    for (const archive of [false, true]) {
      panel.querySelector(archive ? "[data-confirm-archive]" : "[data-confirm-delete]").onclick = async () => {
        const buttons = row.querySelectorAll("button");
        buttons.forEach(b => b.disabled = true);
        const message = panel.querySelector('[role="status"]');
        message.textContent = archive ? "Archiving…" : "Deleting…";
        try {
          await request(`/campaigns/${encodeURIComponent(button.dataset.deleteCampaign)}${archive ? "/archive" : ""}`, {method:archive ? "POST" : "DELETE"});
          el("manage-message").textContent = archive ? "Campaign archived; records preserved." : "Campaign deleted.";
          await loadDashboard();
        } catch (error) { message.textContent = error.message; }
        finally { buttons.forEach(b => b.disabled = false); }
      };
    }
  }
  panel.scrollIntoView({behavior:"smooth", block:"center"});
});
for (const [id, path] of [["meta-check", "/integrations/meta/check"], ["meta-import", "/integrations/meta/catalog/import"], ["meta-collect", "/integrations/meta/collect"]]) {
  el(id).addEventListener("click", async () => {
    el(id).disabled = true; el("meta-message").textContent = "Working…";
    try {
      const result = await request(path, {method:"POST"});
      el("meta-message").textContent = result.account ? `Connected: ${result.account.name} (${result.account.currency}). ${result.note}` : result.imported !== undefined ? `Imported ${result.imported} products; skipped ${result.skipped}. ${result.note}` : JSON.stringify(result);
      await loadDashboard();
    } catch(error) { el("meta-message").textContent = error.message; }
    finally { el(id).disabled = false; }
  });
}
el("location-search-form").addEventListener("submit", async event => {
  event.preventDefault();
  const button = event.target.querySelector("button");
  button.disabled = true;
  el("location-message").textContent = "Searching Meta locations…";
  locationResults = [];
  el("location-results").textContent = "Searching…";
  try {
    locationResults = await request(`/integrations/meta/locations?q=${encodeURIComponent(el("location-query").value.trim())}`);
    el("location-results").innerHTML = locationResults.map((l, i) => `<label class="location-option"><input type="checkbox" value="${i}">${escapeHtml(l.name)} (${escapeHtml(l.type)})</label>`).join("");
    el("location-message").textContent = locationResults.length ? "Tick one or more results and click Add selected locations. Search again to add other places." : "No matches. Try another city or state name.";
  } catch(error) {
    el("location-results").textContent = "Search unavailable";
    el("location-message").textContent = error.message;
  } finally { button.disabled = false; }
});
el("add-location").addEventListener("click", () => {
  const checked = [...el("location-results").querySelectorAll("input:checked")];
  if (!checked.length) { el("location-message").textContent = "Tick at least one location first."; return; }
  const next = [...selectedLocations];
  for (const item of checked) {
    const location = locationResults[Number(item.value)];
    if (location && !next.some(l => l.key === location.key && l.type === location.type)) next.push(location);
  }
  if (next.length > 10) { el("location-message").textContent = "Select at most 10 locations. Remove a selected location before adding more."; return; }
  selectedLocations = next;
  checked.forEach(item => { item.checked = false; });
  renderSelectedLocations();
  el("location-message").textContent = `${selectedLocations.length} locations selected. Save the campaign plan to apply changes.`;
});
function renderSelectedLocations() {
  el("selected-locations").innerHTML = selectedLocations.length ? selectedLocations.map((l, i) => `<button type="button" class="secondary" data-remove-location="${i}" aria-label="Remove ${escapeHtml(l.name)}">${escapeHtml(l.name)} ×</button>`).join("") : "No locations selected.";
}
el("selected-locations").addEventListener("click", event => {
  const button = event.target.closest("button[data-remove-location]");
  if (!button) return;
  selectedLocations.splice(Number(button.dataset.removeLocation), 1);
  renderSelectedLocations();
  el("location-message").textContent = "Location removed from this form. Save the campaign plan to apply changes.";
});
el("clear-locations").addEventListener("click", () => { selectedLocations = []; renderSelectedLocations(); });
el("plan-campaign").addEventListener("change", () => {
  const selectedBudget = campaignChoices.find(c => c.id === el('plan-campaign').value);
  if (selectedBudget) {
    el('budget-mode-form').elements.mode.value = selectedBudget.budget_mode || 'FIXED';
    el('budget-fixed').value = Math.min(150, selectedBudget.daily_budget_inr);
    el('budget-min').value = selectedBudget.budget_mode === 'DYNAMIC' ? selectedBudget.daily_budget_min_inr : 150;
    el('budget-max').value = selectedBudget.budget_mode === 'DYNAMIC' ? selectedBudget.daily_budget_max_inr : 200;
    el('budget-weekly').value = selectedBudget.weekly_budget_limit_inr;
    el('budget-mode-message').textContent = '';
    showBudgetMode();
  }
  if (workflowData) loadWorkflow(campaignChoices, workflowData).catch(error => { el("session-message").textContent = error.message; });
  const plan = savedCampaignPlans.find(p => p.campaign_id === el("plan-campaign").value)?.plan;
  selectedLocations = plan ? plan.locations.map(l => ({...l})) : [];
  renderSelectedLocations();
  el("location-message").textContent = "Add or clear locations, then save the campaign plan.";
  const form = el("plan-form");
  el("plan-product").value = plan?.product_code || "";
  for (const name of ["caption", "start_date", "end_date", "age_min", "age_max"]) {
    form.elements.namedItem(name).value = plan?.[name] ?? (name === "age_min" ? 20 : name === "age_max" ? 60 : "");
  }
  for (const [field, key] of [["window_start", "start"], ["window_end", "end"]]) {
    form.elements.namedItem(field).value = plan?.windows?.[0]?.[key] || "";
  }
});
el("plan-form").addEventListener("submit", async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  if (!selectedLocations.length || !el("plan-campaign").value || !el("plan-product").value) { el("plan-message").textContent = "Select a draft, product and at least one location."; return; }
  const button = event.target.querySelector("button"); button.disabled = true;
  try {
    await request(`/integrations/campaigns/${encodeURIComponent(el("plan-campaign").value)}/plan`, {method:"PUT", body:JSON.stringify({product_code:el("plan-product").value, caption:data.caption, start_date:data.start_date, end_date:data.end_date, age_min:Number(data.age_min), age_max:Number(data.age_max), locations:selectedLocations, windows:[{start:data.window_start, end:data.window_end}]})});
    await loadDashboard();
    el("plan-message").textContent = "Plan saved. View its product and click Approve on the review card below.";
    const card = el("approval-list").querySelector(`[data-campaign="${el("plan-campaign").value}"]`)?.closest("article");
    (card || el("review-section")).scrollIntoView({behavior:"smooth", block:"start"});
  } catch(error) { el("plan-message").textContent = error.message; }
  finally { button.disabled = false; }
});
el("live-campaigns").addEventListener("click", async event => {
  const button = event.target.closest("button[data-meta-step]");
  if (!button) return;
  const panel = button.closest(".meta-diagnostics"), message = panel.querySelector(".meta-step-result");
  const step = button.dataset.metaStep;
  if (step === "launch-approval" && !panel.querySelector(".billing-reviewed")?.checked) { message.textContent = "Review Meta billing and tick the owner approval checkbox first."; return; }
  button.disabled = true;
  message.textContent = "Checking Meta…";
  try {
    const result = await request(`/integrations/campaigns/${encodeURIComponent(button.dataset.id)}/${step}`, {method:"POST", ...(step === "launch-approval" ? {body:JSON.stringify({billing_reviewed_in_meta:true})} : {})});
    await loadDashboard();
    if (step === "billing") {
      const url = new URL(result.url);
      if (url.origin !== "https://adsmanager.facebook.com") throw new Error("Unexpected billing destination.");
      const link = document.createElement("a");
      link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer";
      link.className = "payment-link"; link.textContent = "Open verified Meta billing account";
      el("live-message").replaceChildren("Meta objects verified. Complete billing in Meta, then return and re-check status. ", link);
    } else el("live-message").textContent = step === "health" ? "Meta objects verified; payment still requires review in Meta." : "Owner launch approval recorded. Activation is a separate action.";
  } catch (error) { message.textContent = error.message; el("live-message").textContent = error.message; }
  finally { button.disabled = false; }
});
el("live-campaigns").addEventListener("click", async event => {
  const button = event.target.closest("button[data-live-action]");
  if (!button) return;
  const action = button.dataset.liveAction;
  if (action === "activate" && !confirm("Activate this approved campaign on Meta? It can spend the budget shown in its saved plan.")) return;
  button.disabled = true;
  try {
    await request(`/integrations/campaigns/${encodeURIComponent(button.dataset.id)}/${action}`, {method:"POST"});
    el("live-message").textContent = `${action === "prepare" ? "Paused ads prepared" : "Campaign action confirmed"}.`;
  } catch(error) { el("live-message").textContent = error.message; }
  finally { await loadDashboard().catch(() => {}); button.disabled = false; }
});
el("approval-list").addEventListener("click", async event => {
  const button = event.target.closest("button[data-review-action]");
  if (!button) return;
  const d = savedCampaignPlans.find(d => d.campaign_id === button.dataset.campaign);
  if (!d) return;
  if (button.dataset.reviewAction === "cancel-approval") {
    button.closest(".approval-confirmation").remove();
    return;
  }
  if (button.dataset.reviewAction === "approve") {
    const card = button.closest("article");
    let confirmation = card.querySelector(".approval-confirmation");
    if (!confirmation) {
      confirmation = document.createElement("div");
      confirmation.className = "approval-confirmation notice";
      confirmation.innerHTML = `<p>Confirm approval of this product, caption, locations and schedule: <strong>INR ${escapeHtml(d.plan.daily_budget_inr)}/day, INR ${escapeHtml(d.plan.weekly_budget_inr)} total limit</strong>. This does not launch ads.</p><div class="actions"><button type="button" data-review-action="confirm-approval" data-campaign="${escapeHtml(d.campaign_id)}">Confirm approval</button><button type="button" class="secondary" data-review-action="cancel-approval" data-campaign="${escapeHtml(d.campaign_id)}">Cancel</button></div><p class="approval-result" role="status"></p>`;
      card.append(confirmation);
      const range = document.createElement('p');
      range.textContent = budgetLabel(d.plan);
      confirmation.prepend(range);
    }
    confirmation.scrollIntoView({behavior:"smooth", block:"center"});
    confirmation.querySelector("button").focus({preventScroll:true});
    return;
  }
  if (button.dataset.reviewAction !== "confirm-approval") return;
  const resultMessage = button.closest(".approval-confirmation").querySelector(".approval-result");
  resultMessage.textContent = "Saving your approval…";
  let approved = false;
  button.disabled = true;
  try {
    let a = workflowApprovals.find(a => a.id === d.approval_id && a.status === "PENDING");
    if (!a) {
      const result = await request("/approvals/request", {method:"POST", body:JSON.stringify({campaign_id:d.campaign_id, product_code:d.plan.product_code})});
      a = {id:result.approval_id};
    }
    await request(`/approvals/${encodeURIComponent(a.id)}/decision`, {method:"POST", body:JSON.stringify({message:`APPROVE ${d.plan.product_code}`})});
    approved = true;
    el("approval-message").textContent = "Plan approved. Next: Prepare paused ads. Activation remains a separate action.";
  } catch (error) { resultMessage.textContent = error.message; el("approval-message").textContent = error.message; }
  finally {
    if (approved) await loadDashboard().catch(() => { resultMessage.textContent = "Approval saved, but refresh failed. Click Refresh to see the updated status."; });
    button.disabled = false;
  }
});

el("approval-list").addEventListener("click", async event => {
  const button = event.target.closest("button[data-decision]");
  if (!button) return;
  const approval = workflowApprovals.find(a => a.id === button.dataset.id);
  if (!approval) return;
  const buttons = button.parentElement.querySelectorAll("button");
  buttons.forEach(b => b.disabled = true);
  try {

    await request(`/approvals/${encodeURIComponent(approval.id)}/decision`, {method:"POST", body:JSON.stringify({message:button.dataset.decision === "approve" ? `APPROVE ${approval.product_code}` : "REJECT"})});
    el("approval-message").textContent = "Creative decision saved.";
    try { await loadDashboard(); } catch { el("approval-message").textContent = "Decision saved. Use Refresh to reload the records."; }
  } catch(error) { el("approval-message").textContent = error.message; }
  finally { buttons.forEach(b => b.disabled = false); }
});
el("campaign-form").addEventListener("submit", async event => {
  event.preventDefault();
  const button = event.target.querySelector("button");
  button.disabled = true;
  try {
    const data = new FormData(event.target);
    const payload = JSON.stringify({name:data.get("name"), daily_budget_inr:Number(data.get("daily_budget_inr")), weekly_budget_limit_inr:Number(data.get("weekly_budget_limit_inr"))});
    if (payload !== draftRequestPayload) { draftRequestPayload = payload; draftRequestKey = crypto.randomUUID(); }
    const result = await request("/campaigns", {method:"POST", headers:{"Idempotency-Key":draftRequestKey}, body:payload});
    event.target.reset();
    await loadDashboard();
    el("plan-campaign").value = result.id;
    el("plan-campaign").dispatchEvent(new Event("change"));
    el("campaign-message").textContent = `Draft “${result.name}” created. Complete its campaign details next.`;
    el("plan-form").closest("section").scrollIntoView({behavior:"smooth", block:"start"});
    el("plan-product").focus({preventScroll:true});
  } catch (error) { el("campaign-message").textContent = error.message; }
  finally { button.disabled = false; }
});
el("product-form").addEventListener("submit", async (event) => { event.preventDefault(); const data=Object.fromEntries(new FormData(event.target)); data.price_inr=Number(data.price_inr); try { const result = await request("/catalog", { method:"POST", body:JSON.stringify(data) }); el("product-message").textContent = `${result.product_code} added to catalog.`; event.target.reset(); await loadDashboard(); } catch(error) { el("product-message").textContent = error.message; } });

// One selection controls review, diagnostics and billing.
el("campaigns").addEventListener("click", event => {
  const button = event.target.closest("[data-open-campaign]");
  if (!button) return;
  el("plan-campaign").value = button.dataset.openCampaign;
  el("plan-campaign").dispatchEvent(new Event("change"));
  el("plan-campaign").scrollIntoView({behavior:"smooth", block:"center"});
});

el("campaigns").addEventListener("click", async event => {
  const button = event.target.closest("[data-edit-campaign]");
  if (!button) return;
  const id = button.dataset.editCampaign;
  if (!window.confirm("Edit this saved campaign? Its previous approval will be withdrawn. Review and approve the updated plan before preparing ads.")) return;
  button.disabled = true;
  try {
    await request(`/campaigns/${encodeURIComponent(id)}/edit`, {method:"POST"});
    await loadDashboard();
    el("plan-campaign").value = id;
    el("plan-campaign").dispatchEvent(new Event("change"));
    el("plan-message").textContent = "Editing saved campaign. Update product, caption, dates, locations or budget, then save and approve the revised plan.";
    el("plan-form").scrollIntoView({behavior:"smooth", block:"start"});
  } catch (error) { el("manage-message").textContent = error.message; }
  finally { button.disabled = false; }
});
