#!/bin/bash
# Install LVMS operator via OLM (Operator Lifecycle Manager)
#
# This installs the OpenShift LVMS operator on vanilla K8s using OLM,
# the same operator management framework used by OpenShift.
#
# OLM handles:
#   - Operator installation from a CatalogSource
#   - Dependency resolution (e.g., cert-manager if needed)
#   - Operator upgrades via Subscription channels
#
# Prerequisites:
#   - Each worker node needs an available block device (e.g., /dev/vdb)
#     The LVMCluster CR will create the VG automatically.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OLM_VERSION="v0.31.0"
NAMESPACE="openshift-storage"

# ---------------------------------------------------------------
# Step 1: Install OLM
# ---------------------------------------------------------------
echo "=== Step 1: Installing OLM ${OLM_VERSION} ==="

if kubectl get deployment olm-operator -n olm &>/dev/null; then
    echo "OLM already installed, skipping."
else
    curl -fsSL "https://github.com/operator-framework/operator-lifecycle-manager/releases/download/${OLM_VERSION}/install.sh" \
        | bash -s "${OLM_VERSION}"
fi

echo "Waiting for OLM to be ready..."
kubectl wait --for=condition=Available deployment/olm-operator -n olm --timeout=120s
kubectl wait --for=condition=Available deployment/catalog-operator -n olm --timeout=120s

# Verify the community catalog is available (installed by OLM by default)
echo "Waiting for OperatorHub community catalog..."
kubectl wait --for=jsonpath='{.status.connectionState.lastObservedState}'=READY \
    catalogsource/operatorhubio-catalog -n olm --timeout=300s

# ---------------------------------------------------------------
# Step 2: Create namespace and OperatorGroup
# ---------------------------------------------------------------
echo ""
echo "=== Step 2: Creating namespace and OperatorGroup ==="

kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "$SCRIPT_DIR/operatorgroup.yaml"

# ---------------------------------------------------------------
# Step 3: Subscribe to LVMS operator
# ---------------------------------------------------------------
echo ""
echo "=== Step 3: Subscribing to lvms-operator ==="

kubectl apply -f "$SCRIPT_DIR/subscription.yaml"

# Wait for the operator CSV to be installed
echo "Waiting for LVMS operator to install (this may take a few minutes)..."
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
    echo "Debug: kubectl get subscription lvms-operator -n ${NAMESPACE} -o yaml"
    exit 1
fi

# Wait for the CSV to succeed
echo "Waiting for CSV ${CSV} to reach Succeeded phase..."
kubectl wait --for=jsonpath='{.status.phase}'=Succeeded \
    csv/"${CSV}" -n "${NAMESPACE}" --timeout=300s

echo "LVMS operator installed successfully!"

# ---------------------------------------------------------------
# Step 4: Create LVMCluster
# ---------------------------------------------------------------
echo ""
echo "=== Step 4: Creating LVMCluster ==="

kubectl apply -f "$SCRIPT_DIR/lvmcluster.yaml"

echo ""
echo "=== LVMS operator installation complete ==="
echo ""
echo "The LVMCluster CR will auto-discover available block devices on worker nodes"
echo "and create a default StorageClass."
echo ""
echo "Verify with:"
echo "  kubectl get lvmcluster -n ${NAMESPACE}"
echo "  kubectl get sc"
echo "  kubectl get pods -n ${NAMESPACE}"
