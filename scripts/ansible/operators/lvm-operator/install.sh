#!/bin/bash
# Install TopoLVM — LVM-based CSI storage for Kubernetes
# This is the vanilla K8s equivalent of OpenShift's LVMS operator.
#
# Prerequisites: each worker node needs an LVM volume group named "topolvm-vg".
# Create it with: sudo pvcreate /dev/vdb && sudo vgcreate topolvm-vg /dev/vdb

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Installing TopoLVM (LVM CSI driver) ==="

# Install via helm
if ! command -v helm &>/dev/null; then
    echo "Installing helm..."
    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

# Add TopoLVM helm repo
helm repo add topolvm https://topolvm.github.io/topolvm
helm repo update

# Install TopoLVM
if helm status topolvm -n topolvm-system &>/dev/null; then
    echo "TopoLVM already installed. Upgrading..."
    helm upgrade topolvm topolvm/topolvm -n topolvm-system
else
    echo "Installing TopoLVM..."
    kubectl create namespace topolvm-system --dry-run=client -o yaml | kubectl apply -f -
    helm install topolvm topolvm/topolvm -n topolvm-system
fi

# Wait for TopoLVM controller to be ready
echo "Waiting for TopoLVM controller..."
kubectl wait --for=condition=Available deployment/topolvm-controller \
    -n topolvm-system --timeout=120s

# Apply custom StorageClass
echo "Applying StorageClass..."
kubectl apply -f "$SCRIPT_DIR/storageclass.yaml"

echo "=== TopoLVM installation complete ==="
echo ""
echo "NOTE: Each worker node needs an LVM volume group named 'topolvm-vg'."
echo "Create it with: sudo pvcreate /dev/vdb && sudo vgcreate topolvm-vg /dev/vdb"
echo ""
echo "Verify with: kubectl get sc"
