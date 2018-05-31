# =========================== imports =========================================

import json
from datetime import datetime

# =========================== define ==========================================

LOG_FILE  = "sm.log"

SLOFRAME_LENGTH = 256.0                     # has to be float
SLOT_DURATION_s = 0.00725

PATH_DIR_UP = 0x02

LINK_FLAG_RX = 0x02
LINK_FLAG_ADVERTISEMENT = 0x20

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
    create_events = []
    join_events = []
    oper_events = []
    motes = {}
    manager = None

    # read file
    with open(LOG_FILE, 'r') as f:
        for line in f.readlines():
            line = json.loads(line)

            if line['name'] == "snapshot":
                snapshots.append(line)

            if line['name'] == "hr":
                hrs.append(line)

            if line['name'] == "eventMoteCreate":
                create_events.append(line)

            if line['name'] == "eventMoteJoin":
                join_events.append(line)

            if line['name'] == "eventMoteOperational":
                oper_events.append(line)

    if len(snapshots) < 2:
        print "Not enough snapshots"
        exit(1)

    # create mote dict
    for event in create_events:
        motes[event['fields']['macAddress']] = {
            'total_TxData': 0,
            'total_RxIdle': 0,
            'total_RxDataTxAck': 0,
            'total_TxDataRxAckNone': 0,
            'total_TxDataAdv': 0,
            'create_datetime': event['datetime']
        }

    # save join time
    for event in join_events:
        mac = event['fields']['macAddress']
        join_time = datetime.strptime(event['datetime'], "%Y-%m-%d %H:%M:%S") - \
                    datetime.strptime(motes[mac]['create_datetime'],
                                      "%Y-%m-%d %H:%M:%S")
        motes[mac].update({
            'join_time_s': join_time.seconds,
            'join_datetime': event['datetime']
        })

    # save sync time
    for event in oper_events:
        mac = event['fields']['macAddress']
        if 'join_datetime' in motes[mac]:
            sync_time = (
                    datetime.strptime(event['datetime'], "%Y-%m-%d %H:%M:%S") -
                    datetime.strptime(motes[mac]['join_datetime'], "%Y-%m-%d %H:%M:%S")
            ).seconds
            motes[mac]['sync_time_s'] = sync_time

        motes[event['fields']['macAddress']].update({
            'sync_datetime': event['datetime']
        })

    # save manager and last snapshot datetime
    for snap in snapshots:
        for mac, mote in snap['snapshot']["getMoteConfig"].iteritems():
            # ignore manager
            if mote['isAP'] is True:
                manager = mote
                continue
            motes[mac]['last_datetime'] = snap['datetime']

    # =========================================================================

    # ===== LIFETIME

    """
    Calculate the lifetime of each mote given a AA battery.
    The mote charge takes into account:
      * Tx Cells (Fail or Success)
      * Rx Cells (with or without data)
      * Advertisement Cells (considered Tx)
    """
    # count TxData, RxDataTxAck and TxDataRxAckNone
    for hr in hrs:
        if "Neighbors" in hr['hr']:
            # increment counters
            for ngbr in hr['hr']["Neighbors"]["neighbors"]:
                motes[hr['mac']]['total_TxData'] += ngbr['numTxPackets']
                motes[hr['mac']]['total_RxDataTxAck'] += ngbr['numRxPackets']
                motes[hr['mac']]['total_TxDataRxAckNone'] += ngbr['numTxFailures']

    # --- RxData and Advertisements
    prev_datetime = None
    for snap in snapshots:
        if prev_datetime is None:
            prev_datetime = snap['datetime']
            continue

        # calculate time delta with previous hr neighbors
        time_delta = datetime.strptime(snap['datetime'], "%Y-%m-%d %H:%M:%S") - \
                     datetime.strptime(prev_datetime, "%Y-%m-%d %H:%M:%S")
        time_delta_asn = time_delta.seconds / float(SLOT_DURATION_s)

        # calculate the number of slotframes passed
        slotframe_count = time_delta_asn / SLOFRAME_LENGTH

        for mac, links in snap['snapshot']["getMoteLinks"].iteritems():
            # ignore manager
            if mac == manager['macAddress']:
                continue

            # --- RX
            # calculate the number of rx cells without reception
            motes[mac]['total_RxIdle'] += slotframe_count * len(
                [link for link in links['links'] if link['flags'] & LINK_FLAG_RX]
            ) - motes[mac]['total_RxDataTxAck']

            # --- Advertisement
            # calculate the number of advertisement cells
            motes[mac]['total_TxDataAdv'] += slotframe_count * len(
                [link for link in links['links'] if link['flags'] & LINK_FLAG_ADVERTISEMENT]
            )

    # calculate charge consumed
    for mac, mote in motes.iteritems():

        if 'total_RxDataTxAck' not in mote:
            print "Didn't receive HR Neighbor for mote {0}".format(mac)
            exit(1)
        mote['charge'] =  mote['total_RxDataTxAck'] * CHARGE_RxDataTxAck_uC
        mote['charge'] += mote['total_TxData'] - mote['total_TxDataRxAckNone'] * CHARGE_TxDataRxAck_uC
        mote['charge'] += mote['total_TxDataRxAckNone'] * CHARGE_TxDataRxAckNone_uC
        mote['charge'] += mote['total_TxDataAdv'] * CHARGE_TxData_uC
        mote['charge'] += mote['total_RxIdle'] * CHARGE_Idle_uC

    # calculate lifetime
    for mac, mote in motes.iteritems():
        time_delta = datetime.strptime(motes[mac]['last_datetime'], "%Y-%m-%d %H:%M:%S") - \
                     datetime.strptime(motes[mac]['sync_datetime'], "%Y-%m-%d %H:%M:%S")

        if mote['charge'] > 0:
            ave_current_uA = mote['charge'] / float(time_delta.seconds)
            lifetime = (BATTERY_AA_CAPACITY_mAh * 1000 / float(ave_current_uA)) / (24.0 * 365)

            mote.update({
                'ave_current_uA': ave_current_uA,
                'lifetime_AA_years': lifetime,

            })
        else:
            mote['WARNING'] = "The mote did not send messages"

    # compare with HRDevice charge
    prev_datetime = None
    for hr in hrs:
        if prev_datetime is None:
            prev_datetime = hr['datetime']
            continue

        if "Device" in hr['hr']:
            # increment counters
            motes[hr['mac']]['total_charge_mC'] = hr['hr']["Device"]['charge']
    # calculate lifetime
    for mac, mote in motes.iteritems():
        time_delta = datetime.strptime(motes[mac]['last_datetime'], "%Y-%m-%d %H:%M:%S") - \
                     datetime.strptime(motes[mac]['sync_datetime'], "%Y-%m-%d %H:%M:%S")

        if mote['total_charge_mC'] > 0:
            ave_current_mA = mote['total_charge_mC'] / float(time_delta.seconds)
            lifetime = (BATTERY_AA_CAPACITY_mAh / float(ave_current_mA)) / (24.0 * 365)

            mote.update({
                'ave_current_uA_hr': ave_current_mA * 1000,
                'lifetime_AA_years_hr': lifetime,

            })

    # ===== LATENCY

    """
    Calculate the latency for each packet
    The relation between relative time and absolute time is updating using getTime notifications
    """
    with open(LOG_FILE, 'r') as f:
        time_delta = None
        for line in f.readlines():
            line = json.loads(line)

            if line['name'] == 'oap':
                secs, usec = line["fields"]["packet_timestamp"]
                relative_time = datetime.fromtimestamp(secs)
                tx_time = relative_time + time_delta
                rx_time = datetime.strptime(line["fields"]['received_timestamp'][:-3], "%Y-%m-%d %H:%M:%S.%f")
                latency = rx_time - tx_time
                motes[line['mac']].setdefault('latencies', []).append(latency.seconds)
            elif line['name'] == 'getTime':
                absolute_time = datetime.strptime(line["datetime"], "%Y-%m-%d %H:%M:%S")
                relative_time = datetime.fromtimestamp(line["utcSecs"])
                time_delta    = absolute_time - relative_time
    # calculate min/max/ave
    for mac, mote in motes.iteritems():
        mote['latency_min_s'] = min(mote['latencies'])
        mote['latency_avg_s'] = sum(mote['latencies']) / float(len(mote['latencies']))
        mote['latency_max_s'] = max(mote['latencies'])
        del mote['latencies']

    # ===== TOPOLOGY
    first_datetime = None
    with open("topology.json", 'w') as f:
        for snap in snapshots:
            # save first datetime
            if first_datetime is None:
                first_datetime = datetime.strptime(snap['datetime'], "%Y-%m-%d %H:%M:%S")
            time_delta = datetime.strptime(snap['datetime'], "%Y-%m-%d %H:%M:%S") - first_datetime

            # create mac mapping to replace mac by ids
            mac_map = {mac: i for i, mac in enumerate(motes)}
            mac_map.update({manager['macAddress']: 0})

            # create topology
            path_dict = {}
            for mac, paths in snap['snapshot']["getPathInfo"].iteritems():
                mote_id = mac_map[mac]
                for path in paths.values():
                    if path['direction'] == PATH_DIR_UP:
                        path['dest'] = mac_map[path['dest']]
                        # save parent with highest quality
                        if mote_id not in path_dict or path_dict[mote_id]['quality'] > path['quality']:
                            path_dict[mote_id] = path
            topology = json.dumps({
                'paths': path_dict,
                'asn': int(time_delta.seconds / SLOT_DURATION_s)
            })

            f.write(topology + '\n')

    # =========================================================================

    print json.dumps(motes, indent=4)
    with open("result.kpi", 'w') as f:
        f.write(json.dumps({'0': motes}, indent=4))


if __name__ == "__main__":
    main()