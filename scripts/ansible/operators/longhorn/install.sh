#!/bin/bash
# Install Longhorn distributed block storage via kubectl
#
# This applies the official Longhorn manifest and waits for all
# components to become ready in the longhorn-system namespace.
#
# Prerequisites:
#   - Worker nodes must have iscsi-initiator-utils, nfs-utils installed
#   - iscsid service must be running on worker nodes
#   - iscsi_tcp kernel module must be loaded

set -euo pipefail

LONGHORN_VERSION="${LONGHORN_VERSION:-v1.11.0}"
NAMESPACE="longhorn-system"

# ---------------------------------------------------------------
# Step 1: Install Longhorn
# ---------------------------------------------------------------
echo "=== Installing Longhorn ${LONGHORN_VERSION} ==="

kubectl apply -f "https://raw.githubusercontent.com/longhorn/longhorn/${LONGHORN_VERSION}/deploy/longhorn.yaml"

# ---------------------------------------------------------------
# Step 2: Wait for Longhorn components to be ready
# ---------------------------------------------------------------
echo ""
echo "=== Waiting for Longhorn pods to be ready ==="

echo "Waiting for longhorn-manager daemonset..."
kubectl -n "${NAMESPACE}" rollout status daemonset/longhorn-manager --timeout=300s

echo "Waiting for longhorn deployments..."
for deploy in longhorn-driver-deployer longhorn-ui; do
    kubectl -n "${NAMESPACE}" rollout status deployment/"${deploy}" --timeout=300s 2>/dev/null || true
done

echo ""
echo "=== Longhorn ${LONGHORN_VERSION} installation complete ==="
echo ""
echo "Verify with:"
echo "  kubectl -n ${NAMESPACE} get pod"
echo "  kubectl get sc"
