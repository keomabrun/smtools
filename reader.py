# =========================== imports =========================================

import os
import json
from datetime import datetime, timedelta
import argparse
import networkx as nx
import matplotlib.pyplot as plt

# =========================== define ==========================================

SLOFRAME_LENGTH = 256.0                     # has to be float
SLOT_DURATION_s = 0.00725

PATH_DIR_UP = 0x02

LINK_FLAG_RX = 0x02
LINK_FLAG_ADVERTISEMENT = 0x20

# === battery
CHARGE_Idle_mC                              = 6.4  / 1000.0
CHARGE_TxDataRxAck_mC                       = 54.5 / 1000.0
CHARGE_TxData_mC                            = 49.5 / 1000.0
CHARGE_TxDataRxAckNone_mC                   = 54.5 / 1000.0
CHARGE_RxDataTxAck_mC                       = 32.6 / 1000.0
#CHARGE_RxData_mC                            = 22.6 / 1000.0
BATTERY_AA_CAPACITY_mAh                     = 2200

# =========================== main ============================================

def main(options):

    # init
    snapshots = []
    hrs = []
    create_events = []
    join_events = []
    oper_events = []
    motes = {}
    manager = None

    # read file
    with open(options.inputfile, 'r') as f:
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
        # ignore manager
        if event['fields']['moteId'] == 1:
            continue
        motes[event['fields']['macAddress']] = {
            'total_TxData': 0,
            'total_RxIdle': 0,
            'total_RxDataTxAck': 0,
            'total_TxDataRxAckNone': 0,
            'total_TxDataAdv': 0,
            'total_charge_mC': 0,
            'num_rx_links': 0,
            'create_datetime': event['datetime'],
            'macAddress': event['fields']['macAddress'],
            'moteId': event['fields']['moteId'],
        }
    #print "Found {} motes".format(len(motes))

    # save join time
    for event in join_events:
        mac = event['fields']['macAddress']
        join_time = datetime.strptime(event['datetime'], "%Y-%m-%d %H:%M:%S") - \
                    datetime.strptime(motes[mac]['create_datetime'],
                                      "%Y-%m-%d %H:%M:%S")
        motes[mac].update({
            'join_time_s': join_time.total_seconds(),
            'join_datetime': event['datetime']
        })

    # save sync time
    for event in oper_events:
        mac = event['fields']['macAddress']
        if 'join_datetime' in motes[mac]:
            sync_time = (
                    datetime.strptime(event['datetime'], "%Y-%m-%d %H:%M:%S") -
                    datetime.strptime(motes[mac]['join_datetime'], "%Y-%m-%d %H:%M:%S")
            ).total_seconds()
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
        time_delta_asn = time_delta.total_seconds() / float(SLOT_DURATION_s)

        # calculate the number of slotframes passed
        slotframe_count = time_delta_asn / SLOFRAME_LENGTH

        for mac, links in snap['snapshot']["getMoteLinks"].iteritems():
            # ignore manager
            if mac == manager['macAddress']:
                continue

            # --- RX
            # calculate the number of rx cells without reception
            motes[mac]['num_rx_links'] += slotframe_count * len(
                [link for link in links['links'] if link['flags'] & LINK_FLAG_RX]
            )

            # --- Advertisement
            # calculate the number of advertisement cells (one adv per slotframe)
            motes[mac]['total_TxDataAdv'] += slotframe_count

        prev_datetime = snap['datetime']

    for mac, mote in motes.iteritems():
        motes[mac]['total_RxIdle'] += motes[mac]['num_rx_links'] - motes[mac]['total_RxDataTxAck']

    # calculate charge consumed
    for mac, mote in motes.iteritems():

        if 'total_RxDataTxAck' not in mote:
            print "Didn't receive HR Neighbor for mote {0}".format(mac)
            exit(1)
        mote['estimated_charge_mC'] =  mote['total_RxDataTxAck'] * CHARGE_RxDataTxAck_mC
        mote['estimated_charge_mC'] += (mote['total_TxData'] - mote['total_TxDataRxAckNone']) * CHARGE_TxDataRxAck_mC
        mote['estimated_charge_mC'] += mote['total_TxDataRxAckNone'] * CHARGE_TxDataRxAckNone_mC
        mote['estimated_charge_mC'] += mote['total_TxDataAdv'] * CHARGE_TxData_mC
        mote['estimated_charge_mC'] += mote['total_RxIdle'] * CHARGE_Idle_mC

    # calculate lifetime
    for mac, mote in motes.iteritems():
        time_delta = datetime.strptime(motes[mac]['last_datetime'], "%Y-%m-%d %H:%M:%S") - \
                     datetime.strptime(motes[mac]['sync_datetime'], "%Y-%m-%d %H:%M:%S")

        if mote['estimated_charge_mC'] > 0:
            ave_current_mA = mote['estimated_charge_mC'] / float(time_delta.total_seconds())
            lifetime = (BATTERY_AA_CAPACITY_mAh / float(ave_current_mA)) / (24.0 * 365)

            mote.update({
                'ave_current_mA': ave_current_mA,
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
            # if hr['mac'] == "00-17-0d-00-00-31-c9-da":
            #     print json.dumps(hr, indent=4)
    for mac, mote in motes.iteritems():
        if abs(mote['total_charge_mC'] - mote['estimated_charge_mC']) > 2000:
            print 'Huge charge difference smip={0} and calculated={1} (mC) for {2}'.format(
                mote['total_charge_mC'],
                int(mote['estimated_charge_mC']),
                mote['macAddress']
            )

    # calculate lifetime
    for mac, mote in motes.iteritems():
        time_delta = datetime.strptime(motes[mac]['last_datetime'], "%Y-%m-%d %H:%M:%S") - \
                     datetime.strptime(motes[mac]['sync_datetime'], "%Y-%m-%d %H:%M:%S")

        if mote['total_charge_mC'] > 0:
            ave_current_mA = mote['total_charge_mC'] / float(time_delta.total_seconds())
            lifetime = (BATTERY_AA_CAPACITY_mAh / float(ave_current_mA)) / (24.0 * 365)

            mote.update({
                'ave_current_mA_hr': ave_current_mA,
                'lifetime_AA_years_hr': lifetime,
            })

    # ===== LATENCY

    """
    Calculate the latency for each packet
    The relation between relative time and absolute time is updated using getTime notifications
    """
    faults = []
    sec = []
    ids = []
    with open(options.inputfile, 'r') as f:
        time_offset = None
        for line in f.readlines():
            line = json.loads(line)

            if line['name'] == 'oap':
                if time_offset is None: # skip if time offset not known message
                    continue
                secs, usec = line["fields"]["packet_timestamp"]
                relative_time = datetime.fromtimestamp(secs) + timedelta(microseconds=usec)
                tx_time = relative_time + time_offset
                rx_time = datetime.strptime(line["fields"]['received_timestamp'], "%Y-%m-%d %H:%M:%S.%f")
                latency = rx_time - tx_time
                #print (tx_time-datetime(1970,1,1)).total_seconds()
                #print (rx_time-datetime(1970,1,1)).total_seconds()#-5.036e8
                faults.append((tx_time-datetime(1970,1,1)).total_seconds())
                sec.append((rx_time-datetime(1970,1,1)).total_seconds())
                ids.append(datetime.strptime(line['datetime'], "%Y-%m-%d %H:%M:%S"))
                if latency.total_seconds() > 20:
                    print "Huge latency {0}s for mac {1} at {2}".format(
                        latency.total_seconds(),
                        line['mac'],
                        line["fields"]['received_timestamp']
                    )
                    #print tx_time, rx_time, relative_time, time_offset
                else:
                    motes[line['mac']].setdefault('latencies', []).append(latency.total_seconds())
            elif line['name'] == 'getTime':
                absolute_time = datetime.strptime(line["datetime"], "%Y-%m-%d %H:%M:%S")
                relative_time = datetime.fromtimestamp(line["utcSecs"]) + timedelta(microseconds=line["utcUsecs"])
                time_offset    = absolute_time - relative_time
                #print "getTime. abs={0}, rel={1}, offset={2}".format(absolute_time, relative_time, time_offset)

    import matplotlib.pyplot as plt
    plt.plot(ids, faults, label='tx')
    plt.plot(ids, sec, label='rx')
    plt.legend()
    plt.show()

    # calculate min/max/ave
    for mac, mote in motes.iteritems():
        mote['latency_min_s'] = min(mote['latencies'])
        mote['latency_avg_s'] = sum(mote['latencies']) / float(len(mote['latencies']))
        mote['latency_max_s'] = max(mote['latencies'])
    # compare with mote config info
    for snap in snapshots:
        for mac, info in snap['snapshot']["getMoteInfo"].iteritems():
            if mac == manager['macAddress']:
                continue
            motes[mac]['avgLatency'] = info['avgLatency']
        #break
    for mote in motes.itervalues():
        if abs(mote['avgLatency'] - (mote['latency_avg_s'] * 1000.0)) > 1000:
            print 'Huge latency difference smip={0} and calculated={1} (ms) for {2}'.format(
                mote['avgLatency'],
                mote['latency_avg_s'] * 1000.0,
                mote['macAddress']
            )
            #exit(1)

    # ===== TOPOLOGY

    # create mac mapping to replace mac by ids
    mac_map = {mote['macAddress']: mote['moteId'] - 1 for mote in motes.itervalues()}
    mac_map.update({manager['macAddress']: 0})

    first_datetime = None
    with open(os.path.join(os.path.dirname(options.inputfile), "topology.json"), 'w') as f:
        for snap in snapshots:
            # save first datetime
            if first_datetime is None:
                first_datetime = datetime.strptime(snap['datetime'], "%Y-%m-%d %H:%M:%S")
            time_delta = datetime.strptime(snap['datetime'], "%Y-%m-%d %H:%M:%S") - first_datetime

            # create topology
            path_dict = {}
            for mac, paths in snap['snapshot']["getPathInfo"].iteritems():
                mote_id = mac_map[mac]
                for path in paths.values():
                    if path['direction'] == PATH_DIR_UP:
                        path['dest'] = mac_map[path['dest']]
                        # save parent with highest quality
                        if mote_id not in path_dict or path_dict[mote_id]['quality'] < path['quality']:
                            path_dict[mote_id] = path
            topology = json.dumps({
                'paths': path_dict,
                'asn': int(time_delta.total_seconds() / SLOT_DURATION_s)
            })

            f.write(topology + '\n')

    # =========================================================================

    kpis = {
        '0': {mac_map[mac]: mote for mac, mote in motes.iteritems()}
    }
    #print json.dumps(kpis, indent=4)
    with open(os.path.join(os.path.dirname(options.inputfile), "result.kpi"), 'w') as f:
        f.write(json.dumps(kpis, indent=4))

    with open(os.path.join(os.path.dirname(options.inputfile), 'last_snap.json'), 'w') as f:
        f.write(json.dumps(snapshots[-1], indent=4))

    draw_topology()

def draw_topology():
    with open(os.path.join(os.path.dirname(options.inputfile), "topology.json"), 'r') as f:
        for line in f:
            line = json.loads(line)
            topology = line['paths']
            break

    G = nx.Graph()
    for source, path in topology.iteritems():
        G.add_edge(int(source), int(path['dest']))
    nx.draw(G, with_labels=True)
    plt.savefig(os.path.join(os.path.dirname(options.inputfile), "topology.png"))

def parse_args():
    # parse options
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-i', '--inputfile',
        help       = 'The simulation result folder.',
        default    = 'sm.log',
    )
    return parser.parse_args()

if __name__ == '__main__':

    options = parse_args()

    main(options)
