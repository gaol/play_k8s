#!/bin/bash
# Install LVMS operator via OLM Subscription
#
# Requires: OLM must be installed (handled by the olm Ansible role)
#
# This creates:
#   - Namespace (openshift-storage)
#   - OperatorGroup (scopes the operator)
#   - Subscription (triggers OLM to install the operator)
#   - LVMCluster CR (configures LVM storage on worker nodes)
#
# Prerequisites:
#   - Each worker node needs an available block device (e.g., /dev/vdb)
#     The LVMCluster CR will auto-discover and use it.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

NAMESPACE="openshift-storage"

# ---------------------------------------------------------------
# Step 1: Verify OLM is available
# ---------------------------------------------------------------
echo "=== Verifying OLM is installed ==="
if ! kubectl get deployment olm-operator -n olm &>/dev/null; then
    echo "ERROR: OLM is not installed. Run the olm Ansible role first."
    exit 1
fi
echo "OLM is available."

# ---------------------------------------------------------------
# Step 2: Create namespace, OperatorGroup, and Subscription
# ---------------------------------------------------------------
echo ""
echo "=== Creating namespace and subscribing to lvms-operator ==="

kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "$SCRIPT_DIR/operatorgroup.yaml"
kubectl apply -f "$SCRIPT_DIR/subscription.yaml"

# ---------------------------------------------------------------
# Step 3: Wait for operator to be installed
# ---------------------------------------------------------------
echo ""
echo "=== Waiting for LVMS operator to install ==="

CSV=""
for i in $(seq 1 60); do
    CSV=$(kubectl get subscription lvms-operator -n "${NAMESPACE}" \
        -o jsonpath='{.status.installedCSV}' 2>/dev/null || true)
    if [[ -n "$CSV" ]]; then
        echo "CSV found: $CSV"
        break
    fi
    echo "  Waiting for CSV... ($i/60)"
    sleep 10
done

if [[ -z "$CSV" ]]; then
    echo "ERROR: Timed out waiting for LVMS operator CSV"
    echo "Debug with:"
    echo "  kubectl get subscription lvms-operator -n ${NAMESPACE} -o yaml"
    echo "  kubectl get installplan -n ${NAMESPACE}"
    exit 1
fi

echo "Waiting for CSV ${CSV} to reach Succeeded phase..."
kubectl wait --for=jsonpath='{.status.phase}'=Succeeded \
    csv/"${CSV}" -n "${NAMESPACE}" --timeout=300s

echo "LVMS operator installed successfully!"

# ---------------------------------------------------------------
# Step 4: Create LVMCluster
# ---------------------------------------------------------------
echo ""
echo "=== Creating LVMCluster ==="

kubectl apply -f "$SCRIPT_DIR/lvmcluster.yaml"

echo ""
echo "=== LVMS operator installation complete ==="
echo ""
echo "The LVMCluster CR will auto-discover available block devices"
echo "on worker nodes and create a default StorageClass."
echo ""
echo "Verify with:"
echo "  kubectl get lvmcluster -n ${NAMESPACE}"
echo "  kubectl get sc"
echo "  kubectl get pods -n ${NAMESPACE}"
