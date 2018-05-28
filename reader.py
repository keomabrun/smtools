# =========================== imports =========================================

import json

# =========================== define ==========================================

LOG_FILE  = "sm.log"

SLOFRAME_LENGTH = 256
SLOT_DURATION_s = 7.25

# === battery
CHARGE_Idle_uC                              = 6.4
CHARGE_TxDataRxAck_uC                       = 54.5
CHARGE_TxData_uC                            = 49.5
CHARGE_TxDataRxAckNone_uC                   = 54.5
CHARGE_RxDataTxAck_uC                       = 32.6
CHARGE_RxData_uC                            = 22.6
BATTERY_AA_CAPACITY_mAh                     = 2200

# =========================== main ============================================

def main():

    # init
    snapshots = []
    hrs = []
    motes = {}

    # read file
    with open(LOG_FILE, 'r') as f:
        for line in f.readlines():
            line = json.loads(line)

            if line['name'] == "snapshot":
                snapshots.append(line['snapshot'])

            if line['name'] == "hr":
                hrs.append(line)

    # extract mote info
    for snap in snapshots:
        for mac, paths in snap["getPathInfo"].iteritems():
            up_links = sum(
                [path['numLinks'] for path in paths.itervalues() if path['direction'] == 2]
            )
            down_links = sum(
                [path['numLinks'] for path in paths.itervalues() if path['direction'] == 3]
            )
            # ave_current_uA = motestats['charge'] / float(
            #     (time_delta) * SLOT_DURATION_s)
            # lifetime = (BATTERY_AA_CAPACITY_mAh * 1000 / float(motestats['ave_current_uA'])) / (24.0 * 365)
            # motes[mac] = {
            #     'up_links': up_links,
            #     'down_links': down_links,
            #     'ave_current_uA': ave_current_uA,
            #     'lifetime_AA_years':,
            #
            # }

    print json.dumps(motes, indent=4)


if __name__ == "__main__":
    main()