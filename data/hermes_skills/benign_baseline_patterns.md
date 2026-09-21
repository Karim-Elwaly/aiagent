---
name: benign_baseline_patterns
description: Methodology for recognising and excluding benign activity that resembles an attack - cloud address rotation, maintenance traffic, carrier roaming, scheduled automation and service accounts - before it becomes a false positive in a report.
author: UAOS Security Methodology
version: 1.0.0
license: MIT
metadata:
  category: security
  skills: [benign_baseline_patterns, baseline_analysis, false_positive_analysis, triage, quality_assurance]
  risk_level: low
parameters:
  candidate_finding:
    type: string
    description: The candidate finding you want to test against benign baselines before reporting.
    required: false
---

# Benign Baseline Patterns

Reference methodology for false-positive suppression. In a security report a false
positive is not a harmless extra - it consumes response capacity, can trigger
containment of an innocent user or production system, and destroys the reader's
trust in the true positives sitting next to it.

## 1. The discipline

Every candidate finding must survive an explicit challenge before it is reported:

1. State the benign explanation that best fits the same evidence. There is almost
   always one; if you cannot construct it, you have not understood the activity.
2. Identify the **discriminator** - the specific observable that separates the
   malicious reading from the benign one.
3. Check whether the evidence actually contains that discriminator.
4. If it does, report with the discriminator cited. If it does not, either downgrade
   to a hypothesis requiring more data, or drop it.

"I could not rule out the benign explanation" is a legitimate and honest outcome.

## 2. Recurring benign shapes

These are described by *shape*, not by specific addresses, hostnames or accounts -
concrete values differ per environment and memorising them produces brittle, wrong
analysis.

### Cloud and content-delivery address rotation
A destination inside a large provider's shared range, contacted by many internal
hosts, whose address changes between connections for the same logical service.
Looks like: fast-flux or infrastructure rotation.
Discriminators that would make it malicious: contacted by exactly one host; first
seen inside the incident window; accompanied by process-level anomalies on the
initiating host; strongly periodic beaconing with no corresponding application.

### Operating system and vendor maintenance traffic
Regular outbound connections to platform update, telemetry, revocation or time
services, present across the fleet, predating the incident.
Looks like: command-and-control beaconing.
Discriminators: single-host exclusivity, start time coinciding with the intrusion,
unusual initiating process, payload asymmetry inconsistent with an update check.

### Credential typo, self-corrected
One or two authentication failures immediately followed by success, same principal,
same source, same device, within a short window.
Looks like: successful brute force.
Discriminators: many failures rather than a couple; a *different* source or device
for the success than for the failures; anomalous actions after the success;
the same source failing against other principals too.

### Mobile carrier address rotation
A user's source address changing, sometimes across wide apparent geography, with no
change in device, client or behaviour, on a consumer mobile network.
Looks like: impossible travel or session hijack.
Discriminators: a different device or client accompanying the new address; both
endpoints outside the same provider; failure bursts or post-login anomalies;
concurrent sessions from genuinely unrelated networks.

### Scheduled automation periodicity
Machine-regular activity at a fixed cadence, stable source, stable target, predating
the window, often under a non-interactive identity.
Looks like: beaconing or automated attack tooling.
Discriminators: cadence or target changed at the incident time; the schedule was
created inside the window; the activity reaches destinations outside its normal set.

### Administrative tooling in expected context
Remote execution, management utilities or scripting run by an administrative
identity, from an administrative host, during a change window, with readable
arguments.
Looks like: lateral movement or living-off-the-land abuse.
Discriminators: a non-administrative or newly-privileged identity; encoded or
obfuscated arguments; an implausible parent process; activity outside change hours;
targets outside the administrator's normal scope.

### Service account behaviour within its own baseline
High volume, perfectly regular, unchanging source and client.
Looks like: automated attack or mass enumeration.
Discriminators: comparison against **its own history**, not against human patterns -
a new source, a new target set, interactive logon types, or a change in cadence.

## 3. What invalidates a benign explanation

Any of the following should flip a benign classification back to suspicious,
regardless of how well the shape matched:

- The activity has no history before the incident window.
- The identity or host involved is already implicated by an independent finding.
- The behaviour changed at the moment of a known compromise event.
- The benign shape is present *and* an unambiguous malicious artefact accompanies it
  (log clearing, credential dumping, encoded execution, privilege change).

Benign classification is provisional. Re-examine every suppressed item after the
timeline is assembled, because context arriving later can invalidate an earlier
dismissal.

## 4. Baselines you do not have

If the ingested window is short, you have no baseline. Saying "this destination is
new" requires historical data you may not possess.

- Distinguish "not seen earlier in the ingested window" from "never seen before".
- If baseline data is absent, say the novelty could not be established and treat it
  as a collection requirement.
- Do not manufacture a baseline from intuition about what is normal in an
  environment you have not observed.

## 5. Before reporting

For each finding that survives, include a one-line "benign explanation considered and
excluded" note with its discriminator. For each candidate you suppressed, keep a short
suppressed-items list with the reason. That list is evidence of rigour, and it lets a
reviewer overturn your call if they know something you do not.
