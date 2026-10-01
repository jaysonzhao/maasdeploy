---
name: build-maas-portal
description: Build, update, deploy, or verify a guided OpenShift AI Models-as-a-Service portal. Use for portal content, dashboard and CRD links, OAuth-protected OpenShift deployment, or portal troubleshooting in this repository.
---

# Build the MaaS Guided Portal

Use this skill to change the guided portal in this repository or adapt its workflow to another OpenShift AI cluster. Keep cluster-specific hostnames out of source files; the deploy script supplies them at runtime.

## Source files

Work from the repository root. Read these files before making portal changes:

| Purpose | Files |
|---|---|
| Step content, dashboard destinations, and CRD/resource links | `portal/app.js` |
| Portal layout and footer | `portal/index.html` |
| Styling | `portal/styles.css` |
| Static server and runtime configuration | `portal/server.py` |
| OpenShift OAuth, Service, Deployment, Route, and RBAC | `manifests/11-maas-portal/` |
| Cluster discovery, ConfigMaps, and rollout | `scripts/deploy-maas-portal.sh` |
| Human-facing deployment notes | `content/modules/ROOT/pages/11-maas-portal.adoc` |

The portal is a static HTML/CSS/JavaScript application served by the Python standard library. `/config.json` supplies `dashboardUrl`, `consoleUrl`, and `clusterName`; do not put cluster addresses in `app.js`.

## Build or update the journey

1. Inspect the existing portal and the RHOAI version in scope. Keep the journey focused on the user's requested features. The current seven-step path is model catalog, model deployment, authorization policy, subscription, API key, load test, and usage monitoring.
2. For each step, write a short feature description, operator checklist, command snippet when useful, and an official Red Hat documentation link for the installed version.
3. Add a direct OpenShift AI dashboard destination and the most relevant OpenShift CRD or resource destination for each step. Use live dashboard navigation to discover dashboard paths. Do not guess URL patterns or reuse a path from a different cluster version without checking it.
4. Keep link targets cluster-independent in `portal/app.js`:

   - `dashboard:<path>` appends an observed path to the configured dashboard Route.
   - `console:<path>` appends an observed path to the configured OpenShift console URL.
   - `crd:<plural>.<group>` opens the console CRD definition page.
   - Full URLs are for official documentation, not cluster addresses.

5. Verify each CRD name with `oc get crd` before linking. Label Kubernetes resources accurately when a feature has no feature-specific CRD. In particular, catalog sources are configured through a ConfigMap, a load-test workload is a CronJob, and MaaS API keys are managed by MaaS; use the applicable Tenant or MaaSTenantConfig CRD only for key or telemetry settings.
6. Do not put GitHub/source-repository URLs in the portal journey. Keep source commands local and use official product documentation for reference links.
7. Keep the portal informational: it must not request, display, transmit, or persist MaaS API keys. Keep the Python server independent of the Kubernetes API.

Observed RHOAI 3.5 dashboard paths currently used by the portal are:

| Feature | Dashboard path |
|---|---|
| Model catalog settings | `/settings/model-resources-operations/model-catalog` |
| Find and deploy models | `/ai-hub/models` |
| Authorization policies | `/maas/maas-governance/auth-policies` |
| Subscriptions | `/maas/maas-governance` |
| API keys | `/maas/tokens` |
| Usage dashboard | `/observe-and-monitor/dashboard` |

Re-discover and confirm these paths in the target dashboard before reusing them. Confirm the selected dashboard page and any tabs or filters the user needs.

## Keep the OpenShift deployment protected

- Preserve the OAuth proxy, TLS Route, service account, delegated authorization checks, and least-privilege RBAC in `manifests/11-maas-portal/`.
- Preserve the generated cookie secret in the `maas-portal` namespace across updates. Do not print or commit its value.
- Keep static files, environment configuration, and OAuth credentials in their existing separate ConfigMaps and Secrets.
- Serve `/`, `/index.html`, `/app.js`, and `/styles.css` with `Cache-Control: no-store`, and keep `/config.json` uncached. This prevents a browser from mixing a newly deployed page with an old JavaScript bundle or cluster configuration.
- The portal service account does not need general Kubernetes API access. Do not add it to the portal server.

## Deploy and verify

Deploy only when the user requests deployment or the current task clearly includes publishing the portal. Before changing cluster state, check the selected project and cluster:

```bash
pwd
oc whoami --show-server
oc whoami
```

Stop if the active API server differs from the cluster named by the user. Deploy from the repository root:

```bash
./scripts/deploy-maas-portal.sh
```

The script discovers the ingress domain and OpenShift AI dashboard Route, sets runtime URLs, applies the portal resources, preserves the cookie Secret, restarts the Deployment, waits for rollout, and prints the portal Route. The console host must handle both ingress domains that already begin with `apps.` and domains that do not.

After deployment:

1. Confirm `oc rollout status deployment/maas-guided-journey -n maas-portal` succeeds and read the Route printed by the script.
2. Open the portal and inspect every journey card's rendered link target. Confirm dashboard links open the right feature, CRD links open the matching CRD definition, and non-CRD links open the actual resource page.
3. Confirm the portal UI contains no source-repository URLs and no credentials. Check `portal/app.js` link definitions and the rendered page.
4. Run lightweight source checks:

   ```bash
   node --check portal/app.js
   python3 -c 'import ast, pathlib; ast.parse(pathlib.Path("portal/server.py").read_text())'
   bash -n scripts/deploy-maas-portal.sh
   git diff --check
   ```

5. Update `content/modules/ROOT/pages/11-maas-portal.adoc` or `README.md` if the documented workflow changes. Commit and push only when requested or already authorized in the conversation.

## Remove the portal

Only remove it when the user asks. Its cleanup includes a namespace and a cluster-scoped OAuth delegation binding:

```bash
oc delete namespace maas-portal
oc delete clusterrolebinding maas-guided-journey-auth-delegator
```

Do not run cleanup as part of a normal portal update.

## Product references

Use documentation matching the installed RHOAI release. For the current RHOAI 3.5 journey:

- [Manage and govern model catalog sources](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/manage_and_govern_model_catalog_sources/index)
- [Govern LLM access with Models-as-a-Service](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/govern_llm_access_with_models-as-a-service/index)
- [Deploy models using distributed inference with llm-d](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/deploy_models_using_distributed_inference_with_llm-d/index)
