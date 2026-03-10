#!/bin/bash
# Install TopoLVM — LVM-based CSI storage for Kubernetes
# This is the vanilla K8s equivalent of OpenShift's LVMS operator.
#
# Prerequisites:
#   - cert-manager (installed automatically by this script)
#   - Each worker node needs an LVM volume group named "topolvm-vg".
#     Create it with: sudo pvcreate /dev/vdb && sudo vgcreate topolvm-vg /dev/vdb

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Install helm if not present
if ! command -v helm &>/dev/null; then
    echo "Installing helm..."
    curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

# --- cert-manager (required by TopoLVM for webhook TLS) ---
echo "=== Installing cert-manager ==="
if kubectl get namespace cert-manager &>/dev/null; then
    echo "cert-manager namespace exists, skipping install."
else
    kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.17.2/cert-manager.yaml
fi

echo "Waiting for cert-manager..."
kubectl wait --for=condition=Available deployment/cert-manager -n cert-manager --timeout=120s
kubectl wait --for=condition=Available deployment/cert-manager-webhook -n cert-manager --timeout=120s
kubectl wait --for=condition=Available deployment/cert-manager-cainjector -n cert-manager --timeout=120s

# --- TopoLVM ---
echo ""
echo "=== Installing TopoLVM (LVM CSI driver) ==="

helm repo add topolvm https://topolvm.github.io/topolvm
helm repo update

if helm status topolvm -n topolvm-system &>/dev/null; then
    echo "TopoLVM already installed. Upgrading..."
    helm upgrade topolvm topolvm/topolvm -n topolvm-system
else
    echo "Installing TopoLVM..."
    kubectl create namespace topolvm-system --dry-run=client -o yaml | kubectl apply -f -
    helm install topolvm topolvm/topolvm -n topolvm-system
fi

echo "Waiting for TopoLVM controller..."
kubectl wait --for=condition=Available deployment/topolvm-controller \
    -n topolvm-system --timeout=120s

# Apply custom StorageClass
echo "Applying StorageClass..."
kubectl apply -f "$SCRIPT_DIR/storageclass.yaml"

echo ""
echo "=== TopoLVM installation complete ==="
echo ""
echo "NOTE: Each worker node needs an LVM volume group named 'topolvm-vg'."
echo "Create it with: sudo pvcreate /dev/vdb && sudo vgcreate topolvm-vg /dev/vdb"
echo ""
echo "Verify with: kubectl get sc"
