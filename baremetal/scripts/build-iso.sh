#!/bin/bash
# build-iso.sh — Build a custom Ubuntu autoinstall ISO
#
# A standalone, reusable utility for creating per-node Ubuntu autoinstall ISOs
# with embedded user-data and network-config. Can be used independently of
# the baremetal K8s provisioner.
#
# Usage:
#   build-iso.sh --base-iso <path> --output <path> --user-data <path> [options]
#
# Required:
#   --base-iso     Path to the stock Ubuntu live server ISO
#   --output       Path for the output ISO
#   --user-data    Path to autoinstall user-data YAML file
#
# Optional:
#   --network-config   Path to network-config YAML file
#   --label            ISO volume label (default: UBUNTU-AUTOINSTALL)
#   --help             Show this help message
#
# Dependencies: xorriso, 7z (p7zip-full)
#
# Examples:
#   # Build a single node ISO
#   ./build-iso.sh \
#       --base-iso /opt/iso/ubuntu-22.04.4-live-server-amd64.iso \
#       --output /opt/iso/node1.iso \
#       --user-data /opt/configs/autoinstall-node1.yaml \
#       --network-config /opt/configs/network-config-node1.yaml
#
#   # Minimal (no network config)
#   ./build-iso.sh \
#       --base-iso ubuntu-22.04.iso \
#       --output custom.iso \
#       --user-data my-autoinstall.yaml

set -euo pipefail

# --- Argument parsing ---
BASE_ISO=""
OUTPUT_ISO=""
USER_DATA=""
NETWORK_CONFIG=""
LABEL="UBUNTU-AUTOINSTALL"

usage() {
    sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
    exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --base-iso)     BASE_ISO="$2";        shift 2 ;;
        --output)       OUTPUT_ISO="$2";       shift 2 ;;
        --user-data)    USER_DATA="$2";        shift 2 ;;
        --network-config) NETWORK_CONFIG="$2"; shift 2 ;;
        --label)        LABEL="$2";            shift 2 ;;
        --help|-h)      usage 0 ;;
        *)
            echo "Unknown option: $1" >&2
            usage 1
            ;;
    esac
done

# --- Validate required arguments ---
if [[ -z "$BASE_ISO" ]]; then
    echo "ERROR: --base-iso is required" >&2
    usage 1
fi
if [[ -z "$OUTPUT_ISO" ]]; then
    echo "ERROR: --output is required" >&2
    usage 1
fi
if [[ -z "$USER_DATA" ]]; then
    echo "ERROR: --user-data is required" >&2
    usage 1
fi

# --- Validate files exist ---
if [[ ! -f "$BASE_ISO" ]]; then
    echo "ERROR: Base ISO not found: $BASE_ISO" >&2
    exit 1
fi
if [[ ! -f "$USER_DATA" ]]; then
    echo "ERROR: User-data file not found: $USER_DATA" >&2
    exit 1
fi
if [[ -n "$NETWORK_CONFIG" && ! -f "$NETWORK_CONFIG" ]]; then
    echo "ERROR: Network-config file not found: $NETWORK_CONFIG" >&2
    exit 1
fi

# --- Check dependencies ---
for cmd in xorriso 7z; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: Required command '$cmd' not found." >&2
        echo "Install with: sudo apt install xorriso p7zip-full" >&2
        exit 1
    fi
done

# --- Setup ---
WORK_DIR=$(mktemp -d "/tmp/iso-build-XXXXXX")
trap "rm -rf ${WORK_DIR}" EXIT

echo "=== Building autoinstall ISO ==="
echo "  Base ISO:       $BASE_ISO"
echo "  Output:         $OUTPUT_ISO"
echo "  User-data:      $USER_DATA"
if [[ -n "$NETWORK_CONFIG" ]]; then
    echo "  Network-config: $NETWORK_CONFIG"
fi
echo "  Label:          $LABEL"
echo ""

# --- Step 1: Extract base ISO ---
echo "Step 1: Extracting base ISO..."
7z x -o"${WORK_DIR}/iso" "${BASE_ISO}" > /dev/null

# --- Step 2: Inject autoinstall config ---
echo "Step 2: Injecting autoinstall configuration..."
mkdir -p "${WORK_DIR}/iso/autoinstall"
cp "$USER_DATA" "${WORK_DIR}/iso/autoinstall/user-data"
touch "${WORK_DIR}/iso/autoinstall/meta-data"

if [[ -n "$NETWORK_CONFIG" ]]; then
    cp "$NETWORK_CONFIG" "${WORK_DIR}/iso/autoinstall/network-config"
fi

# --- Step 3: Patch GRUB for autoinstall ---
echo "Step 3: Patching GRUB config for autoinstall..."

for grub_cfg in \
    "${WORK_DIR}/iso/boot/grub/grub.cfg" \
    "${WORK_DIR}/iso/boot/grub/loopback.cfg"; do
    if [[ -f "$grub_cfg" ]]; then
        sed -i 's|---| autoinstall ds=nocloud ---|g' "$grub_cfg"
    fi
done

# --- Step 4: Repack ISO ---
echo "Step 4: Repacking ISO with xorriso..."

OUTPUT_DIR=$(dirname "$OUTPUT_ISO")
mkdir -p "$OUTPUT_DIR"

xorriso -as mkisofs \
    -r -V "$LABEL" \
    -o "$OUTPUT_ISO" \
    --grub2-mbr --interval:local_fs:0s-15s:zero_mbrpt:"${BASE_ISO}" \
    -partition_cyl_align off \
    -partition_offset 16 \
    --mbr-force-bootable \
    -append_partition 2 28732ac11ff8d211ba4b00a0c93ec93b \
    -appended_part_as_gpt \
    -iso_mbr_part_type a2a0d0ebe5b9334487c068b6b72699c7 \
    -c '/boot.catalog' \
    -b '/boot/grub/i386-pc/eltorito.img' \
    -no-emul-boot -boot-load-size 4 -boot-info-table --grub2-boot-info \
    -eltorito-alt-boot \
    -e '--interval:appended_partition_2_start_595856s_size_10080d:all::' \
    -no-emul-boot \
    "${WORK_DIR}/iso" 2>/dev/null

echo ""
echo "=== ISO built successfully: $OUTPUT_ISO ==="
echo "  Size: $(du -h "$OUTPUT_ISO" | cut -f1)"
