---
name: deploy-openshift-mcp
description: Deploy the OpenShift MCP server inside a cluster and, when requested, register it with the OpenShift AI Gen AI Playground. Use for MCP server installation, secure in-cluster access, Playground discovery, and deployment troubleshooting.
---

# Deploy the OpenShift MCP Server

Use this skill to deploy the upstream Kubernetes/OpenShift MCP server as an in-cluster service and optionally make it discoverable from OpenShift AI's Gen AI Playground. Keep the server deployment separate from OpenShift AI configuration. Registering the server changes only the platform MCP-server ConfigMap.

## Choose the requested scope

- **Server only:** deploy and verify the MCP service in its own namespace.
- **Server plus Playground:** also add one uniquely named entry to `gen-ai-aa-mcp-servers` in `redhat-ods-applications` so users can select it from their Playground project.

Do not change `DataScienceCluster`, `DSCInitialization`, `OdhDashboardConfig`, or other OpenShift AI settings as part of this workflow. Check whether the Playground prerequisites are already met; get the user's direction before changing them if they are not.

## Before changing the cluster

1. Read the current repository's deployment scripts and manifests first. Reuse existing conventions when they fit this MCP deployment.
2. Confirm the target context with `oc whoami --show-server` and `oc whoami`. Stop if the active server does not match the cluster the user named.
3. Never copy an OpenShift password, login token, MaaS API key, or kubeconfig into this skill, a ConfigMap, a manifest, shell history, or Git. The MCP pod uses its projected ServiceAccount identity to query the in-cluster Kubernetes API; this is separate from client authentication to the MCP HTTP endpoint.
4. Check the target namespace, chart release, image, and current service before installing or upgrading. Pin a reviewed Helm chart version and server image digest; do not deploy `latest` in a repeatable environment. Render the chart and inspect its output before applying it.

## Deploy an internal service

Use the upstream OCI Helm chart when its pinned version supports the required OpenShift settings. Review that version's values before using them:

```bash
helm show chart oci://ghcr.io/containers/charts/kubernetes-mcp-server --version "$MCP_CHART_VERSION"
helm show values oci://ghcr.io/containers/charts/kubernetes-mcp-server --version "$MCP_CHART_VERSION"
```

For a Playground-only in-cluster endpoint, keep the service private:

- Set the Service type to `ClusterIP`.
- Disable Ingress, OpenShift Route, Gateway API `HTTPRoute`, and any other external exposure unless the user explicitly requests external access.
- Do not enable chart settings that create a Route implicitly. Inspect rendered objects to confirm no Route, Ingress, or HTTPRoute is created.
- Use a dedicated namespace and ServiceAccount. Grant only the read permissions needed for the enabled tools. Use namespace-scoped RoleBindings when access to a limited set of namespaces is sufficient; use a cluster-wide `view` binding only when the requested discovery scope requires it.
- Keep the MCP tools read-only. Deny access to Secrets, ConfigMaps, and RBAC objects unless the user explicitly needs one of those resource types and accepts the access.
- Disable pod log tools if log access is not part of the requested use case.
- Keep the container non-root, drop Linux capabilities, and use the chart's restricted pod/container security defaults where available.

The MCP server must run in HTTP mode in a pod. Its TOML configuration needs a non-empty `port` such as `"8080"`; empty `port` selects stdio mode, which is for a locally launched process. A safe baseline configuration is:

```toml
port = "8080"
read_only = true
toolsets = ["core"]
disabled_tools = ["pods_log"]

[[denied_resources]]
group = ""
version = "v1"
kind = "Secret"

[[denied_resources]]
group = ""
version = "v1"
kind = "ConfigMap"

[[denied_resources]]
group = "rbac.authorization.k8s.io"
version = "v1"
kind = "Role"

[[denied_resources]]
group = "rbac.authorization.k8s.io"
version = "v1"
kind = "RoleBinding"

[[denied_resources]]
group = "rbac.authorization.k8s.io"
version = "v1"
kind = "ClusterRole"

[[denied_resources]]
group = "rbac.authorization.k8s.io"
version = "v1"
kind = "ClusterRoleBinding"
```

Use the pinned chart's supported config values or mount this TOML from a ConfigMap. Do not assume a chart version accepts arbitrary config keys: inspect its values schema and rendered ConfigMap. If the rendered config omits a required setting, stop and use a supported ConfigMap mount or versioned Deployment manifest rather than deploying a weaker configuration by accident.

The server's MCP HTTP endpoint is `/mcp`. Discover its actual Service name and construct the internal URL as:

```text
http://<service>.<namespace>.svc.cluster.local:<port>/mcp
```

## Make it available to the Gen AI Playground (only when requested)

OpenShift AI 3.5 discovers platform MCP servers from the `gen-ai-aa-mcp-servers` ConfigMap in `redhat-ods-applications`. The ConfigMap contains case-sensitive, unique keys whose values are JSON objects with a `url` and `description`.

Before editing it:

1. Read the existing ConfigMap and inspect its owner labels/annotations and current data keys.
2. Preserve every existing key and metadata field. If a Helm release or GitOps controller owns it, update the owning source and reconcile from there instead of creating an unmanaged edit.
3. Add only a new unique key for this MCP service. Do not replace the ConfigMap or alter unrelated entries. Use the internal Service URL and omit `accessToken` for the no-client-token Playground setup the user requested.
4. Keep in mind that omitting `accessToken` means the MCP HTTP endpoint does not authenticate individual clients. A `ClusterIP` prevents ordinary access from outside the cluster, but any in-cluster workload allowed by network policy may still be able to reach it. If caller identity or tenant isolation is required, configure supported HTTP authentication or network controls before exposing it to those callers.

Example data entry (replace the service DNS name and description with the deployed values):

```yaml
data:
  OpenShift-MCP-Server: |
    {"url":"http://<service>.<namespace>.svc.cluster.local:8080/mcp","description":"Read-only tools for inspecting the OpenShift cluster."}
```

When the ConfigMap already exists, use a merge operation on the one new `data` key or update its owner-managed source. Do not apply a new full ConfigMap manifest over existing data.

## Verify the deployment

Confirm both Kubernetes readiness and MCP protocol behavior:

1. Check the Deployment is available and the Service has ready endpoints.
2. Confirm the MCP namespace has no Route, Ingress, or HTTPRoute unless external exposure was explicitly requested.
3. Confirm the ServiceAccount can perform only the expected read operations, and cannot read Secrets or perform writes. Use `oc auth can-i` with the ServiceAccount identity for the relevant resources and namespaces.
4. Connect with an MCP client through an in-cluster test pod or a temporary `oc port-forward`. Send an MCP `initialize`, then list tools and call a harmless read-only tool. Do not send an OpenShift bearer token as an MCP client credential for the no-token Playground setup.
5. If Playground registration was requested, verify the ConfigMap's unique key and parse its value as JSON. Open the Gen AI Playground in the requested project and confirm the server appears and completes a connection check.
6. Check server logs for configuration or API errors, without printing credentials.

Do not delete the namespace, ServiceAccount, RBAC, or Playground ConfigMap entry as routine cleanup. Remove these only when the user asks, and remove only resources owned by this MCP deployment.

## References

- [OpenShift MCP server Kubernetes deployment guide](https://github.com/openshift/openshift-mcp-server/blob/main/docs/getting-started-kubernetes.md)
- [MCP server configuration reference](https://github.com/openshift/openshift-mcp-server/blob/main/docs/configuration.md)
- [MCP server Helm chart reference](https://github.com/openshift/openshift-mcp-server/blob/main/charts/kubernetes-mcp-server/README.md)
- [OpenShift AI 3.5 Gen AI Playground prerequisites and MCP configuration](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/experimenting_with_models_in_the_gen_ai_playground/playground-prerequisites_rhoai-user)
