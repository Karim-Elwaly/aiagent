---
name: network_anomaly_analysis
description: Methodology for finding command-and-control beaconing, staging and exfiltration in network telemetry using periodicity, volume asymmetry, and destination analysis while excluding benign automation.
author: UAOS Security Methodology
version: 1.0.0
license: MIT
metadata:
  category: security
  skills: [network_anomaly_analysis, network_analysis, beacon_detection, exfiltration_analysis, c2_analysis, traffic_analysis]
  risk_level: low
parameters:
  traffic_observation:
    type: string
    description: The flows, connections or destinations under analysis.
    required: false
---

# Network Anomaly Analysis

Reference methodology for connection, flow, proxy and firewall telemetry. Network
evidence answers three questions in order: *is something talking regularly*,
*is something taking data out*, and *can this telemetry even tell me*.

## 1. Know what your telemetry can answer

Before analysing, establish which fields exist:

| Question | Requires |
|---|---|
| Who talked to whom, when | source, destination, timestamp |
| How often / periodicity | repeated records for the same pair |
| How much data moved | byte or packet counters |
| Direction of the volume | separate sent/received counters |
| What protocol or service | port, protocol, or application field |
| Whether it was allowed | action / disposition field |

Firewall accept-deny lines often lack byte counters. Flow and proxy records usually
have them. **If byte counters are absent, data volume is not observable** - say so.
Never estimate a transfer size from connection counts.

## 2. Beaconing: periodicity over volume

Command-and-control is usually low-volume and regular. Ranking destinations by bytes
will hide it; rank by *regularity* instead.

For each internal-to-external pair with enough connections:

1. Build the sorted list of intervals between consecutive connections.
2. Compute a dispersion measure (standard deviation relative to the mean interval).
3. Low relative dispersion means machine-driven timing. Human browsing is bursty and
   irregular; beacons are metronomic even when jitter is applied.

Supporting indicators, none sufficient alone:

- Long total duration - it persists across hours or days rather than a single session.
- Consistent, small, similar-sized payloads.
- Connections continuing outside working hours or while the host is otherwise idle.
- A destination contacted by exactly one internal host, repeatedly.
- Use of a common encrypted port for a destination with no legitimate business role -
  attackers favour ports that blend into permitted egress. Note that the port itself
  is not evidence; the combination of port, regularity and destination is.

**Benign periodic traffic exists and is common.** Before reporting a beacon, exclude:
operating-system update and telemetry endpoints, endpoint-security agents checking in,
monitoring and heartbeat agents, certificate revocation and time synchronisation,
software licence checks, and scheduled internal automation. The discriminators are:
Does the destination serve many internal hosts or exactly one? Does the destination
belong to a provider the organisation already relies on? Did the traffic exist before
the suspected intrusion window, or start with it?

That last question is the strongest one available. Compare the first-seen time of the
destination against the incident timeline.

## 3. Exfiltration: asymmetry and novelty

Exfiltration is outbound-heavy. Look for:

- **Volume asymmetry** - outbound bytes substantially exceeding inbound for a pair,
  inverting the normal client pattern.
- **Statistical outliers** - a pair whose outbound volume is many standard deviations
  above that host's own baseline, or above the population of pairs in the window.
- **Novel destination** - first contact within the incident window.
- **Timing** - transfer immediately following collection, staging or archive activity
  on the same host. This correlation is far stronger than volume alone.
- **Channel choice** - transfer over a protocol or service the host does not normally
  use for bulk transfer, or a legitimate file-sharing service used for the first time
  by that host.

Benign causes to exclude: backup and replication jobs, log shipping, cloud storage
synchronisation, software distribution, media uploads by the user's normal role, and
virtual meeting traffic. The discriminators are periodicity (backups are scheduled),
destination ownership, and whether the host has done it before.

**Always report exfiltration status explicitly, including when the answer is negative
or unobservable.** An investigation that does not address whether data left the
environment is incomplete regardless of how well it describes the intrusion.

## 4. Destination analysis

For every external destination that appears in a finding, record what the telemetry
actually says: which internal hosts contacted it, first and last seen, connection
count, port and protocol, disposition, and byte totals if present.

Do not assign reputation, ownership, geolocation or malware family from memory.
Large shared address ranges belong to cloud and content-delivery providers and will
be reached by ordinary software; a rotating set of addresses within one provider's
range contacted by many hosts is a service, not an adversary. If enrichment was not
actually performed, label reputation `UNVERIFIED` and describe only the behaviour.

## 5. Internal movement

For internal-to-internal traffic, look for:

- A host initiating connections to administrative or file-sharing services it has not
  previously used.
- One source touching an unusually large number of internal destinations in a short
  window - scanning or enumeration.
- Sequential connections across hosts that trace a path, especially when each hop is
  preceded by an authentication event for the same principal.

Correlating a network hop with an authentication event for the same account at the
same moment is the strongest lateral-movement evidence available. Neither alone
establishes it.

## 6. Reporting

For each network finding state: the pair, the observed statistic (interval dispersion,
byte totals, connection count) with its supporting evidence identifiers, the benign
explanation excluded and the discriminator used, and the mapped tactic. Distinguish
"no exfiltration observed" from "exfiltration not observable in the ingested telemetry",
and put the latter in the coverage-gap section.
