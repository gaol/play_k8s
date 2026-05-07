#!/bin/bash
# Redfish BMC helper — power, boot, virtual media operations
# Usage: redfish.sh <action> <bmc_address> <username> <password> [args...]
#
# Actions:
#   power-status  — Get power state
#   power-on      — Power on
#   power-off     — Graceful shutdown
#   power-cycle   — Force restart
#   mount-iso     — Mount ISO via VirtualMedia
#   eject-iso     — Eject VirtualMedia
#   set-boot-cd   — Set one-time boot to CD/VirtualMedia
#   boot          — Full sequence: eject → mount → set-boot → power-on/restart

set -euo pipefail

ACTION="${1:?Usage: redfish.sh <action> <bmc_address> <username> <password> ...}"
BMC_ADDRESS="${2:?Missing BMC address}"
BMC_USER="${3:?Missing BMC username}"
BMC_PASS="${4:?Missing BMC password}"

SCHEME="${5:-https}"
BASE_URI="${6:-/redfish/v1/Systems/1}"

CURL_OPTS=(-s -k -u "${BMC_USER}:${BMC_PASS}" -H "Content-Type: application/json")
BASE_URL="${SCHEME}://${BMC_ADDRESS}"

redfish_get() {
    curl "${CURL_OPTS[@]}" "${BASE_URL}${1}"
}

redfish_post() {
    curl "${CURL_OPTS[@]}" -X POST "${BASE_URL}${1}" -d "${2}"
}

redfish_patch() {
    curl "${CURL_OPTS[@]}" -X PATCH "${BASE_URL}${1}" -d "${2}"
}

case "$ACTION" in
    power-status)
        state=$(redfish_get "${BASE_URI}" | python3 -c "import sys,json; print(json.load(sys.stdin)['PowerState'])")
        echo "$state"
        ;;

    power-on)
        echo "Powering on ${BMC_ADDRESS}..."
        redfish_post "${BASE_URI}/Actions/ComputerSystem.Reset" '{"ResetType": "On"}' > /dev/null
        echo "Power on command sent."
        ;;

    power-off)
        echo "Powering off ${BMC_ADDRESS}..."
        redfish_post "${BASE_URI}/Actions/ComputerSystem.Reset" '{"ResetType": "GracefulShutdown"}' > /dev/null
        echo "Power off command sent."
        ;;

    power-cycle)
        echo "Power cycling ${BMC_ADDRESS}..."
        redfish_post "${BASE_URI}/Actions/ComputerSystem.Reset" '{"ResetType": "ForceRestart"}' > /dev/null
        echo "Power cycle command sent."
        ;;

    mount-iso)
        MANAGER_URI="${7:?Missing manager_uri}"
        SLOT="${8:?Missing virtual_media_slot}"
        ISO_URL="${9:?Missing ISO URL}"
        echo "Mounting ISO: ${ISO_URL}"
        redfish_post "${MANAGER_URI}/VirtualMedia/${SLOT}/Actions/VirtualMedia.InsertMedia" \
            "{\"Image\": \"${ISO_URL}\", \"TransferProtocolType\": \"HTTP\"}" > /dev/null
        echo "ISO mounted."
        ;;

    eject-iso)
        MANAGER_URI="${7:?Missing manager_uri}"
        SLOT="${8:?Missing virtual_media_slot}"
        echo "Ejecting VirtualMedia..."
        redfish_post "${MANAGER_URI}/VirtualMedia/${SLOT}/Actions/VirtualMedia.EjectMedia" '{}' > /dev/null 2>&1 || true
        echo "VirtualMedia ejected."
        ;;

    set-boot-cd)
        echo "Setting one-time boot to VirtualMedia CD..."
        redfish_patch "${BASE_URI}" \
            '{"Boot": {"BootSourceOverrideTarget": "Cd", "BootSourceOverrideEnabled": "Once"}}' > /dev/null
        echo "Boot override set."
        ;;

    boot)
        MANAGER_URI="${7:?Missing manager_uri}"
        SLOT="${8:?Missing virtual_media_slot}"
        ISO_URL="${9:?Missing ISO URL}"

        echo "=== Booting ${BMC_ADDRESS} from ISO ==="

        echo "Step 1: Ejecting existing VirtualMedia..."
        redfish_post "${MANAGER_URI}/VirtualMedia/${SLOT}/Actions/VirtualMedia.EjectMedia" '{}' > /dev/null 2>&1 || true

        echo "Step 2: Mounting ISO: ${ISO_URL}"
        redfish_post "${MANAGER_URI}/VirtualMedia/${SLOT}/Actions/VirtualMedia.InsertMedia" \
            "{\"Image\": \"${ISO_URL}\", \"TransferProtocolType\": \"HTTP\"}" > /dev/null

        echo "Step 3: Setting boot override to CD (once)..."
        redfish_patch "${BASE_URI}" \
            '{"Boot": {"BootSourceOverrideTarget": "Cd", "BootSourceOverrideEnabled": "Once"}}' > /dev/null

        POWER_STATE=$(redfish_get "${BASE_URI}" | python3 -c "import sys,json; print(json.load(sys.stdin)['PowerState'])")
        if [ "$POWER_STATE" = "On" ]; then
            echo "Step 4: System is On — forcing restart..."
            redfish_post "${BASE_URI}/Actions/ComputerSystem.Reset" '{"ResetType": "ForceRestart"}' > /dev/null
        else
            echo "Step 4: System is Off — powering on..."
            redfish_post "${BASE_URI}/Actions/ComputerSystem.Reset" '{"ResetType": "On"}' > /dev/null
        fi

        echo "=== Boot sequence complete for ${BMC_ADDRESS} ==="
        ;;

    *)
        echo "Unknown action: $ACTION" >&2
        echo "Valid actions: power-status, power-on, power-off, power-cycle, mount-iso, eject-iso, set-boot-cd, boot" >&2
        exit 1
        ;;
esac
