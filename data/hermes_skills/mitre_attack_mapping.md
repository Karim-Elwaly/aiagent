---
name: mitre_attack_mapping
description: Methodology for mapping observed telemetry to MITRE ATT&CK tactics and techniques with defensible evidence, including sub-technique selection, confidence bands, and avoiding speculative or over-broad mappings.
author: UAOS Security Methodology
version: 1.0.0
license: MIT
metadata:
  category: security
  skills: [mitre_attack_mapping, attack_mapping, technique_classification, kill_chain_analysis, threat_analysis]
  risk_level: low
parameters:
  observation:
    type: string
    description: The behaviour or set of evidence records you want to map to ATT&CK.
    required: false
---

# MITRE ATT&CK Mapping

Reference methodology for turning raw observations into defensible technique mappings.
ATT&CK is a shared vocabulary, not a verdict generator - a mapping is a claim and
carries the same grounding burden as any other claim.

## 1. Map behaviour, not tooling

The unit of mapping is *what happened*, not *what you think did it*.

- "A signed system binary retrieved a remote file" is a behaviour. Map it.
- "Cobalt Strike was used" is an attribution. It is not a technique and it usually
  is not supported by internal telemetry alone.

Start from a single evidence record or a tight cluster of records, describe the
behaviour in one plain sentence, then find the technique that describes that sentence.

## 2. Work tactic-first, then technique, then sub-technique

1. **Tactic** - what was the adversary trying to accomplish at that moment?
   (initial access, execution, persistence, privilege escalation, defense evasion,
   credential access, discovery, lateral movement, collection, command and control,
   exfiltration, impact, reconnaissance, resource development)
2. **Technique** - how, in general terms?
3. **Sub-technique** - only if the evidence distinguishes it.

Claiming a sub-technique the evidence cannot distinguish is over-precision. A correct
parent technique beats a confidently wrong sub-technique. If two sub-techniques are
both consistent, cite the parent and list both as candidates.

## 3. Evidence sufficiency per mapping

For each mapping, record:

- **Basis** - the evidence identifiers that support it.
- **Discriminator** - what in those records rules out the benign explanation.
- **Confidence** - see banding below.

If you cannot state a discriminator, you have a *possible* mapping, not a confirmed one.

| Confidence | Criteria |
|---|---|
| High | Direct record of the behaviour, plus a discriminator that excludes routine activity, plus corroboration from a second source or a second event in sequence. |
| Medium | Direct record of the behaviour, but single-source, or the benign explanation is unlikely rather than excluded. |
| Low | Behaviour inferred from a side effect, or consistent with the technique but also consistent with normal operations. |

Report low-confidence mappings as hypotheses to test, in a separate list from
confirmed mappings. Do not silently promote them.

## 4. Coverage is part of the answer

A mapping exercise produces two outputs:

- Tactics **evidenced** by the telemetry.
- Tactics **not evidenced**, split into "telemetry exists and shows nothing" versus
  "no telemetry of that kind was ingested".

The second list is what drives the next collection request. An investigation that
maps five tactics and says nothing about the other nine has not finished.

Common blind spots to check deliberately, because they are frequently missed:

- **Persistence** - is the access durable, or did it end with the session?
- **Defense evasion** - were logs cleared, tooling disabled, or signed binaries abused?
- **Collection** - was data staged or archived before any transfer?
- **Exfiltration** - did anything leave? Outbound volume, destination, timing.
- **Impact** - was anything encrypted, deleted, disabled or altered?

Exfiltration and impact are the tactics that determine regulatory and business
consequence. Explicitly state their status even when the answer is "not observable".

### Work the event inventory to completion

The evidence store's coverage report lists every distinct action/event-code
present in the ingested data, with counts and example citation ids. Treat that
inventory as a checklist: the mapping exercise is not finished until every row
has either been mapped, examined and ruled benign with a citation, or explicitly
deferred with a reason.

Rank rows rarest-first. In any log corpus the bulk of records are routine
operations; the rare, state-changing rows - an account created, a group
membership changed, a service installed, a privilege assigned, credentials used
explicitly for another identity - are precisely where persistence, privilege
escalation and lateral movement live. A row with three occurrences deserves more
scrutiny than a row with three thousand.

The most common investigation failure is not misreading an event - it is never
reading it. Data that was ingested, counted, and displayed in the coverage table
but analysed by nobody produces a report that is faithful to what it examined
and still wrong about the incident.

## 5. Chain the mappings

Individual mappings are weak; a sequence is strong. After mapping, order the
techniques by timestamp and ask:

- Does the sequence follow a coherent progression?
- Is there an unexplained jump - e.g. privileged action with no preceding credential
  access or escalation? That gap is either a missing log source or a wrong mapping.
- Does any single entity (account, host, address, process) bridge two tactics? Those
  bridges are the strongest findings in the report.

A gap in the chain is a finding. Do not paper over it with an assumed step.

## 6. Anti-patterns

- **Shotgun mapping** - listing a dozen techniques so something is right. Each
  unsupported entry dilutes the supported ones.
- **Tool-name mapping** - deriving the technique from an assumed tool rather than
  from the record.
- **Title matching** - picking a technique because its name contains a word that
  appears in the log line.
- **Retrofitting** - choosing the technique first because it makes a better story,
  then hunting for support.
- **Ignoring the benign path** - most techniques have a legitimate twin. Administrative
  use of remote execution, backup software reading many files, and patching agents
  fetching remote content all look like techniques. State why this instance is not that.

## 7. Presenting mappings

For each technique include: identifier, name, tactic, one-sentence behavioural
description grounded in the evidence, supporting evidence identifiers, discriminator,
confidence, and any candidate sub-techniques not distinguished. Keep confirmed and
hypothesised mappings in separate sections.
