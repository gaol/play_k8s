#!/bin/bash
# Install NGINX Ingress Controller and patch it to use fixed NodePorts.
#
# The infra node's HAProxy forwards :80/:443 to these NodePorts on workers,
# so they must be deterministic (not randomly assigned by Kubernetes).
#
# Environment variables (set by Ansible):
#   INGRESS_HTTP_NODEPORT  — NodePort for HTTP  (default: 30080)
#   INGRESS_HTTPS_NODEPORT — NodePort for HTTPS (default: 30443)

set -euo pipefail

INGRESS_HTTP_NODEPORT="${INGRESS_HTTP_NODEPORT:-30080}"
INGRESS_HTTPS_NODEPORT="${INGRESS_HTTPS_NODEPORT:-30443}"
NAMESPACE="ingress-nginx"

# ---------------------------------------------------------------
# Step 1: Apply the official NGINX Ingress manifest
# ---------------------------------------------------------------
echo "=== Installing NGINX Ingress Controller ==="

MANIFEST_URL="https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.2/deploy/static/provider/baremetal/deploy.yaml"
kubectl apply -f "${MANIFEST_URL}"

# ---------------------------------------------------------------
# Step 2: Patch the Service to use fixed NodePorts
# ---------------------------------------------------------------
echo ""
echo "=== Patching ingress-nginx-controller Service with fixed NodePorts ==="
echo "  HTTP  NodePort: ${INGRESS_HTTP_NODEPORT}"
echo "  HTTPS NodePort: ${INGRESS_HTTPS_NODEPORT}"

kubectl -n "${NAMESPACE}" patch svc ingress-nginx-controller --type='json' -p="[
  {\"op\": \"replace\", \"path\": \"/spec/ports/0/nodePort\", \"value\": ${INGRESS_HTTP_NODEPORT}},
  {\"op\": \"replace\", \"path\": \"/spec/ports/1/nodePort\", \"value\": ${INGRESS_HTTPS_NODEPORT}}
]"

# ---------------------------------------------------------------
# Step 3: Wait for the controller to be ready
# ---------------------------------------------------------------
echo ""
echo "=== Waiting for NGINX Ingress Controller to be ready ==="

kubectl -n "${NAMESPACE}" rollout status deployment/ingress-nginx-controller --timeout=300s

echo ""
echo "=== NGINX Ingress Controller installation complete ==="
echo ""
echo "Verify with:"
echo "  kubectl -n ${NAMESPACE} get pods"
echo "  kubectl -n ${NAMESPACE} get svc"
echo ""
echo "Traffic flow:"
echo "  Client :80/:443 → infra HAProxy → workers:${INGRESS_HTTP_NODEPORT}/${INGRESS_HTTPS_NODEPORT} → NGINX → App"
