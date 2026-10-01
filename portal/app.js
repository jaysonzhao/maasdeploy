const docs = {
  catalog: 'https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/manage_and_govern_model_catalog_sources/manage-model-catalog-sources-in-dashboard_manage-govern-model-catalog-sources',
  maas: 'https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/govern_llm_access_with_models-as-a-service/deploy-and-manage-models-as-a-service',
  llmd: 'https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/deploy_models_using_distributed_inference_with_llm-d/deploying-models-topology-selector_topology-selector',
};

const steps = [
  {
    id: 'catalog', title: 'Model catalog', short: 'Model catalog', number: '01', icon: '◈', label: 'DISCOVER', badge: 'START HERE',
    lead: 'Choose which model sources users can discover, then find a model that fits the intended serving hardware and use case.',
    summaryTitle: 'A curated entry point for models',
    summary: 'OpenShift AI administrators manage catalog sources to control which models appear in the dashboard. A source can expose models from Hugging Face or a YAML catalog, with include and exclude patterns to shape what users see. Enabling a source validates its connection.',
    checklist: [
      'Open the OpenShift AI dashboard and go to Settings → Model resources and operations → Model catalog settings (catalog source management requires administrator access).',
      'Add or preview a source, set include/exclude patterns, and enable it after checking connectivity.',
      'Hugging Face sources expose public, non-gated models. The cluster needs network access to Hugging Face; upstream model quality and deployment compatibility are not validated by Red Hat.',
    ],
    links: [
      ['Open the OpenShift AI dashboard', 'dashboard'],
      ['Browse the repository model manifests', 'https://github.com/jaysonzhao/maasdeploy/tree/main/manifests/05-maas-models'],
      ['Read: manage model catalog sources', docs.catalog],
    ],
    commandTitle: 'Repository starting point', command: 'ls manifests/05-maas-models', commandNote: 'Use catalog browsing for discovery; these repo examples are ready-made deployment configurations.',
    source: ['Model catalog sources', docs.catalog], next: 'deployment',
  },
  {
    id: 'deployment', title: 'Deploy a model', short: 'Model deployment', number: '02', icon: '⬡', label: 'SERVE', badge: 'MODEL SERVING',
    lead: 'Deploy a model into a data science project, choose the serving method, then register the serving endpoint for MaaS governance.',
    summaryTitle: 'Select an inference topology that matches the model',
    summary: 'The RHOAI 3.5 deployment wizard can use distributed inference with llm-d. Its topology selector includes single-node, multi-node data-parallel, single-node prefill/decode, and multi-node prefill/decode patterns. Single-node is the default; other topologies require an administrator-provided LLMInferenceServiceConfig and supported hardware.',
    checklist: [
      'Create or select a data science project and verify model storage and serving prerequisites.',
      'From Models, choose Deploy model and select the generative AI deployment flow. Select llm-d only where the model and cluster support it.',
      'Choose a topology based on model size, accelerator capacity, and traffic pattern; wait for the inference endpoint to become ready.',
      'Register or verify the MaaSModelRef and its authorization policy/subscription resources for the endpoint.',
    ],
    links: [
      ['Open the OpenShift AI dashboard', 'dashboard'],
      ['Open repository deployment script', 'https://github.com/jaysonzhao/maasdeploy/blob/main/scripts/deploy-model.sh'],
      ['Browse deployment manifests', 'https://github.com/jaysonzhao/maasdeploy/tree/main/manifests/05-maas-models'],
      ['Read: distributed inference with llm-d', docs.llmd],
    ],
    commandTitle: 'Deploy this repository’s model configuration', command: './scripts/deploy-model.sh --help\n./scripts/deploy-model.sh --model simulator', commandNote: 'Replace simulator with a GPU model when the target cluster has supported accelerators.',
    callout: 'The llm-d topology selector is a Technology Preview feature in RHOAI 3.5. Check the official support scope before using it for production workloads.',
    source: ['Distributed inference with llm-d', docs.llmd], next: 'policy',
  },
  {
    id: 'policy', title: 'Authorization policy', short: 'Authorization policy', number: '03', icon: '⌑', label: 'GOVERN', badge: 'ACCESS CONTROL',
    lead: 'Define which identity groups can call a MaaS model. The policy and a matching subscription work together to authorize and limit requests.',
    summaryTitle: 'Policies authorize groups at the gateway',
    summary: 'A MaaS authorization policy associates an identity group with a model. Without an allowing policy, requests are rejected with 403. A subscription supplies the model quota and rate limits; a policy without a matching subscription can receive 429 responses.',
    checklist: [
      'Open Settings → MaaS governance → Authorization policies in the OpenShift AI dashboard, or inspect MaaSAuthPolicy resources in the cluster.',
      'Choose the model and identity group(s) that should be allowed to use it.',
      'Check that the same group and model are covered by a subscription; authorization without subscription/quota can be rate-limited.',
    ],
    links: [
      ['Open the OpenShift AI dashboard', 'dashboard'],
      ['Inspect policy examples', 'https://github.com/jaysonzhao/maasdeploy/tree/main/rhoai-maas-guide/manifests/05-maas-models'],
      ['Read: govern LLM access with MaaS', docs.maas],
    ],
    commandTitle: 'Inspect authorization policy resources', command: 'oc get maasauthpolicy -A', commandNote: 'The exact policy name and group values depend on the identity provider and model.',
    source: ['MaaS governance', docs.maas], next: 'subscription',
  },
  {
    id: 'subscription', title: 'MaaS subscription', short: 'Subscription', number: '04', icon: '≋', label: 'SET LIMITS', badge: 'QUOTA + RATE LIMITS',
    lead: 'Create a subscription that binds an approved group to a model with request or token limits and a priority for subscription selection.',
    summaryTitle: 'Subscriptions attach quotas to model access',
    summary: 'A MaaS subscription defines the model, authorized group, token quota and rate limits. If the console creates a matching authorization policy along with a subscription, later edits to either resource need to stay aligned. Subscription priority can select the default when a key is created without an explicit subscription.',
    checklist: [
      'Open Settings → MaaS governance → Subscriptions and select the model and target group.',
      'Set limits and priority for the intended access tier. Confirm that the authorization policy authorizes the same group/model pair.',
      'If you use the option to create a matching authorization policy, verify both resources after creation; synchronize later edits manually.',
    ],
    links: [
      ['Open the OpenShift AI dashboard', 'dashboard'],
      ['Inspect subscription examples', 'https://github.com/jaysonzhao/maasdeploy/tree/main/rhoai-maas-guide/manifests/05-maas-models'],
      ['Read: MaaS subscriptions and access governance', docs.maas],
    ],
    commandTitle: 'Inspect subscriptions', command: 'oc get maassubscription -n models-as-a-service', commandNote: 'Check the model, groups, priority, token limits, and rate-limit settings before issuing keys.',
    source: ['MaaS governance', docs.maas], next: 'apikey',
  },
  {
    id: 'apikey', title: 'Generate an API key', short: 'API key', number: '05', icon: '⌘', label: 'CONNECT', badge: 'SECRET SHOWN ONCE',
    lead: 'Create a key scoped to the right subscription, then store it in an approved secret manager and use it only from a trusted client.',
    summaryTitle: 'API keys are subscription-scoped credentials',
    summary: 'A MaaS API key grants the access of its associated subscription. The key value is displayed only when it is created, so copy it directly to approved secure storage. Administrators can create keys for users; the default maximum expiry is 90 days and administrators can configure that limit. Users can also create a temporary one-hour key from a model endpoint.',
    checklist: [
      'Open Settings → MaaS governance → API keys and create a key for the intended user and subscription, or use the endpoint details for a short-lived test key.',
      'Copy the plaintext key once to a secret manager. Never paste it into this portal, a terminal transcript, Git, a screenshot, or a public notebook.',
      'For this repository’s scheduled demo, scripts/run-maas-loadtest.sh creates regular free/premium demo keys and stores them in an OpenShift Secret; it does not print them.',
    ],
    links: [
      ['Open the OpenShift AI dashboard', 'dashboard'],
      ['Read: create and manage MaaS API keys', docs.maas],
      ['Review the load-test key lifecycle script', 'https://github.com/jaysonzhao/maasdeploy/blob/main/scripts/run-maas-loadtest.sh'],
    ],
    commandTitle: 'For an approved local client', command: 'export MAAS_API_KEY="<read-from-your-secret-manager>"', commandNote: 'This guide does not read, submit, or save the key. Avoid putting it in shell history.',
    callout: 'The MaaS key value is shown once. If it is lost, revoke it and create a replacement.',
    source: ['MaaS API keys', docs.maas], next: 'loadtest',
  },
  {
    id: 'loadtest', title: 'Run the load test', short: 'Load test', number: '06', icon: '↗', label: 'EXERCISE', badge: 'BOUNDED DEMO',
    lead: 'Generate parallel free- and premium-tier inference requests to make quota behavior visible in request logs and the MaaS usage dashboard.',
    summaryTitle: 'A repository demo workload, scheduled every 20 minutes',
    summary: 'The repository CronJob runs separate free and premium clients, using subscription-scoped keys stored in a Kubernetes Secret. It is a bounded demonstration workload, not a built-in MaaS feature. Free-tier 429 responses and premium-tier successful responses can illustrate different limits when the model and tier quotas are configured accordingly.',
    checklist: [
      'Confirm the MaaSModelRef is Ready and the matching free and premium subscriptions exist.',
      'From the repo root, run the setup script once to create/rotate keys, store them in a Secret, and apply the CronJob.',
      'The CronJob runs every 20 minutes and keeps free/premium credentials out of Git. Review status codes and request summaries in the two container logs.',
      'When the demonstration is over, run the cleanup script to revoke keys and remove the namespace.',
    ],
    links: [
      ['Open the OpenShift console', 'console'],
      ['Open the load-test runbook', 'https://github.com/jaysonzhao/maasdeploy/blob/main/content/modules/ROOT/pages/09-load-test.adoc'],
      ['Inspect CronJob manifest', 'https://github.com/jaysonzhao/maasdeploy/blob/main/manifests/09-load-test/cronjob.yaml'],
    ],
    commandTitle: 'Install or refresh the demo workload', command: './scripts/run-maas-loadtest.sh\noc get cronjob,job,pod -n maas-load-test\noc logs -n maas-load-test -l app.kubernetes.io/name=maas-rate-limit-demo -c free-tier\noc logs -n maas-load-test -l app.kubernetes.io/name=maas-rate-limit-demo -c premium-tier', commandNote: 'Each run is bounded. For teardown: ./scripts/cleanup-maas-loadtest.sh',
    source: ['MaaS access and rate limits', docs.maas], next: 'monitoring',
  },
  {
    id: 'monitoring', title: 'Monitor usage', short: 'Monitoring', number: '07', icon: '⌁', label: 'OBSERVE', badge: 'USAGE + REQUESTS',
    lead: 'Compare subscription usage and request counts while the workload is active, then inspect gateway and workload signals when results differ from expectations.',
    summaryTitle: 'MaaS usage metrics help operators understand access',
    summary: 'The OpenShift AI MaaS usage dashboard presents subscription-level token usage, request counts, and rate-limit violations. Its underlying metrics include authorized_hits_total (tokens), authorized_calls_total (authorized requests), and limited_calls_total (HTTP 429s). It is available to cluster administrators and relies on the Cluster Observability Operator, Kuadrant observability, Prometheus collection, and tenant telemetry configuration. In RHOAI 3.5 it is a Technology Preview: use it for visibility and showback, not billing-grade accounting or a production SLA.',
    checklist: [
      'Open OpenShift AI → Observe & monitor → Dashboard → Usage. The dashboard requires the appropriate cluster permissions.',
      'Enable the supported cluster observability and MaaS tenant telemetry configuration; generate requests and allow time for metrics scraping.',
      'Compare subscription usage, request counts, and rate-limit violations with the free/premium client logs. Export dashboard data when a CSV is useful.',
      'If there is no dashboard or usage, check the observability dashboard feature flag, tenant telemetry, Kuadrant gateway metrics, and Prometheus scraping.',
    ],
    links: [
      ['Open the OpenShift AI dashboard', 'dashboard'],
      ['Open the repository observability runbook', 'https://github.com/jaysonzhao/maasdeploy/blob/main/content/modules/ROOT/pages/07-observability.adoc'],
      ['Read: MaaS usage dashboard and telemetry', docs.maas],
    ],
    commandTitle: 'Quick checks for telemetry and workload', command: 'oc get maastenantconfig -n models-as-a-service\noc get telemetrypolicy -A\noc get jobs,pods -n maas-load-test', commandNote: 'RHOAI 3.4 uses Tenant instead of MaasTenantConfig; follow the version-specific repository runbook.',
    callout: 'The RHOAI 3.5 MaaS usage dashboard is a Technology Preview and is not intended as billing-grade accounting.',
    source: ['MaaS usage dashboard', docs.maas], next: null,
  },
];

let current = 0;
let config = { dashboardUrl: '', consoleUrl: '', clusterName: 'OpenShift cluster' };
const completeKey = 'maas-guide-complete-v1';
let completed = new Set();
try { completed = new Set(JSON.parse(localStorage.getItem(completeKey) || '[]')); } catch { completed = new Set(); }
completed = new Set([...completed].filter((id) => steps.some((step) => step.id === id)));

function safeUrl(value) {
  try { const parsed = new URL(value, window.location.origin); return ['https:', 'http:'].includes(parsed.protocol) ? parsed.href : '#'; }
  catch { return '#'; }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);
}

function routeFor(value) {
  if (value === 'dashboard') return config.dashboardUrl;
  if (value === 'console') return config.consoleUrl;
  return value;
}

function renderNav() {
  const nav = document.getElementById('step-nav');
  nav.replaceChildren(...steps.map((step, index) => {
    const button = document.createElement('button');
    button.className = `step-link${completed.has(step.id) ? ' is-complete' : ''}`;
    button.type = 'button';
    if (index === current) button.setAttribute('aria-current', 'step');
    button.setAttribute('aria-label', `Step ${index + 1}: ${step.title}${completed.has(step.id) ? ', complete' : ''}`);
    button.innerHTML = `<span class="step-number">${completed.has(step.id) ? '✓' : step.number.slice(1)}</span><span class="step-name"></span><span class="step-check">${completed.has(step.id) ? '✓' : ''}</span>`;
    button.querySelector('.step-name').textContent = step.short;
    button.addEventListener('click', () => { current = index; render(); });
    return button;
  }));
}

function render() {
  const step = steps[current];
  renderNav();
  document.getElementById('breadcrumb-step').textContent = step.title.toUpperCase();
  const count = steps.filter((step) => completed.has(step.id)).length;
  const percent = Math.round((count / steps.length) * 100);
  document.getElementById('progress-count').textContent = `${count} of ${steps.length} complete`;
  document.getElementById('progress-percent').textContent = `${percent}%`;
  const progress = document.getElementById('progress-bar');
  for (let stepCount = 0; stepCount <= steps.length; stepCount += 1) progress.classList.remove(`progress-${stepCount}`);
  progress.classList.add(`progress-${count}`);
  progress.setAttribute('aria-valuenow', String(count));
  const content = document.getElementById('step-content');
  const items = step.checklist.map((line) => `<li>${line}</li>`).join('');
  const links = step.links.map(([label, href]) => {
    const url = routeFor(href);
    const missing = !url;
    if (missing) return `<div class="action-link action-link-disabled" aria-disabled="true"><span>${escapeHtml(label)}</span><span>Not configured</span></div>`;
    return `<a class="action-link" href="${safeUrl(url)}" target="_blank" rel="noreferrer"><span>${escapeHtml(label)}</span><span aria-hidden="true">↗</span></a>`;
  }).join('');
  const callout = step.callout ? `<div class="callout"><span aria-hidden="true">ⓘ</span><span>${step.callout}</span></div>` : '';
  content.innerHTML = `
    <div class="step-header"><div><div class="eyebrow">STEP ${step.number} &nbsp;·&nbsp; ${step.label}</div><h1>${step.title}</h1><p class="lead">${step.lead}</p></div><div class="step-badge"><strong>${step.number}</strong> &nbsp; ${step.badge}</div></div>
    <article class="summary-card"><div class="summary-icon" aria-hidden="true">${step.icon}</div><div><h2>${step.summaryTitle}</h2><p>${step.summary}</p></div></article>
    <div class="section-grid"><section class="info-card"><h2>What to do</h2><ul class="check-list">${items}</ul></section><section class="info-card"><h2>Open a workspace</h2><div class="action-list">${links}</div><p class="sr-only">External links open in a new tab.</p></section></div>
    <section class="command-card" aria-label="Repository command"><div class="command-heading"><strong>${escapeHtml(step.commandTitle)}</strong><span>${escapeHtml(step.commandNote)}</span></div><div class="command-body"><pre><code>${escapeHtml(step.command)}</code></pre><button class="copy-button" type="button">Copy</button></div></section>
    ${callout}
    <div class="step-controls"><div class="step-controls-left"><label class="complete-toggle"><input type="checkbox" ${completed.has(step.id) ? 'checked' : ''}><span>Mark this step complete</span></label></div><div class="step-controls-right"><button class="control-button previous" type="button" ${current === 0 ? 'disabled' : ''}>← Previous</button><button class="control-button primary next" type="button">${current === steps.length - 1 ? 'Back to start' : 'Next step'} →</button></div></div>
    <p class="sr-only source-note">Official reference: ${step.source[0]}</p>`;
  content.querySelector('.copy-button').addEventListener('click', async (event) => {
    const button = event.currentTarget;
    try { await navigator.clipboard.writeText(step.command); button.textContent = 'Copied'; }
    catch { button.textContent = 'Select command'; }
    window.setTimeout(() => { button.textContent = 'Copy'; }, 1600);
  });
  content.querySelector('input[type="checkbox"]').addEventListener('change', (event) => {
    if (event.currentTarget.checked) completed.add(step.id); else completed.delete(step.id);
    try { localStorage.setItem(completeKey, JSON.stringify([...completed])); } catch { /* Progress remains available for this page session. */ }
    render();
  });
  content.querySelector('.previous').addEventListener('click', () => { current = Math.max(0, current - 1); render(); });
  content.querySelector('.next').addEventListener('click', () => { current = (current + 1) % steps.length; render(); });
}

async function start() {
  try {
    const response = await fetch('/config.json', { cache: 'no-store' });
    if (response.ok) config = { ...config, ...await response.json() };
  } catch { /* The guide remains usable when cluster links are not configured. */ }
  document.getElementById('cluster-name').textContent = config.clusterName || 'OpenShift cluster';
  const dashboardLink = document.getElementById('dashboard-link');
  if (config.dashboardUrl) dashboardLink.href = safeUrl(config.dashboardUrl);
  else {
    dashboardLink.href = '#';
    dashboardLink.setAttribute('aria-disabled', 'true');
    dashboardLink.addEventListener('click', (event) => event.preventDefault());
  }
  render();
}
start();
