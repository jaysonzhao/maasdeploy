# Phase 7: Observability (Optional)

Cluster Observability Operator, DSCI monitoring, the OpenShift AI dashboard
feature flag, and MaaS tenant telemetry for usage metrics. `setup-maas.sh`
supports both RHOAI 3.5+ (`MaasTenantConfig`) and 3.4 (`Tenant`). The RHOAI
operator normally creates the gateway telemetry resources after tenant
telemetry is enabled; the YAML in `telemetry/` is retained as a reference and
fallback.

Full documentation: https://rh-aiservices-bu.github.io/rhoai-maas-guide/modules/main/07-observability.html
