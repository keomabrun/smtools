# Objective

What do we want to obtain ?
- E2E latency for each mote
- estimated network lifetime
- a topology we can use in the 6TiSCH simulator

### E2E Latency

State: TODO

We calculate each packet e2e latency and get the min/max/avg values per mote and for the entire network.

Fields to use:

* `fields.packet_timestamp` and `fields.received_timestamp` from `oap`
* `getMoteInfo.mote.avgLatency` in `snapshot`

### Network Lifetime

State: ongoing

1. record the number of cells that are used in transmission and in reception.
  1. use `hr_neighbor` to get `numTx` `numTxFailure` and `numRx`
  1. use `getPathInfo` to get the number of "idle listen"
1. calculate the charge spent by each mote
1. estimate the lifetime of each mote given the charge of a AA battery
1. network-lifetime is the min mote-lifetime

Fields to use:

* `getPathInfo.mac.numLinks` and `getPathInfo.mac.direction` in `snapshot`
* `neighbor_id.numTxPackets` and `neighbor_id.numRxPackets` in `hr_neighbors`
* `getMoteConfig.mac` and `getMoteConfig.moteId` in `snaphost`

### Topology

State: TODO

We generate a k7 file ?

Fields to use:

* `getPathInfo` in `snapshot`

# Misc

What info we don't have:

