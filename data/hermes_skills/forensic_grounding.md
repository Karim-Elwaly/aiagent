---
name: forensic_grounding
description: Methodology for keeping every investigative claim traceable to a concrete evidence record - citation discipline, uncertainty language, and the rules that prevent fabricated hashes, counts, hostnames and addresses.
author: UAOS Security Methodology
version: 1.0.0
license: MIT
metadata:
  category: security
  skills: [forensic_grounding, evidence_analysis, report_verification, quality_assurance, citation_discipline]
  risk_level: low
parameters:
  claim_or_section:
    type: string
    description: The draft claim, paragraph or report section you want to ground before delivery.
    required: false
---

# Forensic Grounding

Reference methodology. Retrieve this before writing any finding, timeline entry or
remediation step. It describes *how to state things*, not what to conclude.

## 1. The three-part claim

Every investigative sentence should be decomposable into:

| Part | Question it answers | Where it comes from |
|---|---|---|
| Observation | What is literally in the record? | An evidence record, quoted or summarised |
| Citation | Which record? | `[EV:<evidence_id>]` returned by the evidence tooling |
| Inference | What does it mean? | Your reasoning, explicitly labelled as reasoning |

If you cannot separate the observation from the inference, the sentence is not ready.
Write the observation first, then the inference in a separate clause introduced by a
hedge ("this is consistent with", "this suggests", "the most likely explanation is").

## 2. Citation rules

- Cite the *narrowest* record that supports the claim, not a whole file.
- One claim, one or more citations. A paragraph with a single trailing citation is
  under-cited if it makes several independent factual assertions.
- Never invent a citation identifier. Identifiers are produced by the evidence store
  and can be re-fetched; a reader who fetches an id you made up will find nothing,
  and the whole report loses credibility.
- If a claim is genuinely uncited, mark it `[UNVERIFIED]` in place of the citation.
  An acknowledged gap is a valid deliverable. A silent gap is not.

## 3. Numbers are claims

Counts, durations, byte volumes, percentages and confidence scores are claims and
require the same grounding as prose.

- Do not state a record count you did not obtain by counting.
- Do not state a data volume unless the telemetry carries byte fields. Netflow and
  proxy logs usually do; firewall accept/deny lines and authentication logs usually
  do not. Absence of byte fields means "volume not observable", not "no data moved".
- Do not round a derived statistic into a rhetorically stronger one.
- Prefer "at least N observed in the ingested window" over a bare N; ingestion windows
  are partial by default.

## 4. Identifiers are claims

Hashes, IP addresses, hostnames, usernames, process paths, ports and domains must
appear in your output **only if they appear in an evidence record**.

- A file hash that you did not read out of a record is fabrication, even if the
  malware family it supposedly identifies is real.
- A hostname that "would plausibly be the domain controller" is fabrication.
- An internal address invented to make a network diagram look complete is fabrication,
  and it is the most dangerous kind because it looks operational.

When an identifier is needed but unknown, use an explicit placeholder that cannot be
mistaken for data: `<UNKNOWN_HOST>`, `<NOT_IN_TELEMETRY>`. Never a realistic-looking value.

## 5. Remediation must name only real systems

Containment and eradication steps are executed by humans, sometimes by copy-paste.
A fabricated target in a remediation block is an operational incident of its own.

- Every host, account, address, session id or rule target inside a remediation
  instruction must trace to an evidence record.
- If the target is unknown, write the step as a parameterised instruction with an
  explicit lookup action: "identify the session id via <query>, then revoke it" —
  not a concrete value.
- Scripts and command blocks are held to a stricter standard than prose, because
  prose is read and scripts are run.

## 6. Reputation, attribution and intelligence

- Internal telemetry establishes *behaviour*. It does not establish *who*.
- Do not assign an actor name, campaign name, malware family or tool name unless a
  record contains it or an external lookup you actually performed returned it.
- Do not assert that an address is "known malicious" without a source. Say instead
  what the behaviour was and label the reputation `UNVERIFIED - requires external
  threat intelligence lookup`.
- Naming a well-known offensive tool because the behaviour "looks like" it is a
  guess wearing a uniform. Describe the behaviour; let the reader map it.

## 7. Temporal discipline

- Preserve the timestamp format and timezone of the source. If sources disagree on
  timezone, normalise explicitly and say that you did.
- A timeline entry must not precede the earliest ingested record or follow the latest.
  Check your first and last entries against the ingestion window.
- Ordering claims ("X then Y", "immediately after") require both timestamps present.
  If one is missing, say the order is undetermined.

## 8. Absence of evidence

Distinguish three states and never collapse them:

1. **Observed** - a record shows it.
2. **Not observed, but observable** - the telemetry type would have recorded it and
   did not. This is meaningful and can be reported as a negative finding.
3. **Not observable** - no ingested source carries that field or event type. This is
   a coverage gap, not a negative finding.

Reporting (3) as (2) manufactures false reassurance. State coverage gaps explicitly
in their own section so the reader knows what the investigation could not see.

## 9. Pre-delivery checklist

Run this before the report leaves your hands:

- [ ] Every number traces to something counted or read.
- [ ] Every identifier appears in at least one evidence record.
- [ ] Every citation identifier is one the evidence store actually issued.
- [ ] Remediation blocks contain no value you cannot point at in evidence.
- [ ] Attribution and reputation claims are sourced or labelled unverified.
- [ ] First and last timeline entries lie inside the ingestion window.
- [ ] Coverage gaps have their own section.
- [ ] Anything still unsupported is marked `[UNVERIFIED]` rather than deleted or softened.

A report that says "I could not determine X" is more useful than a report that
quietly fills X with something plausible.
