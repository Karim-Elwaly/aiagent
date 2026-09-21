---
name: identity_attack_patterns
description: Methodology for distinguishing password spray, credential stuffing, brute force, MFA fatigue, token or session replay, and consent abuse from their benign twins using authentication log signatures.
author: UAOS Security Methodology
version: 1.0.0
license: MIT
metadata:
  category: security
  skills: [identity_attack_patterns, identity_analysis, authentication_analysis, account_compromise, mfa_analysis, threat_analysis]
  risk_level: low
parameters:
  auth_observation:
    type: string
    description: The authentication behaviour or set of sign-in records under analysis.
    required: false
---

# Identity Attack Patterns

Reference methodology for authentication telemetry. Identity attacks are distinguished
by the *shape* of the attempt sequence - the ratio of accounts to attempts, the timing,
and above all what happened immediately after the noise stopped.

## 0. The rule that matters most

**Find the success.** A burst of failures is the noise. The single authentication that
succeeded at the end of the burst, or shortly after it, is the compromise. It is
frequently the lowest-volume event in the dataset and the easiest to miss precisely
because analysis tends to rank by count.

For every failure cluster, explicitly answer: did any attempt against the same
principal succeed within the surrounding window? If yes, that event is the pivot
point of the entire incident and everything after it is post-compromise activity.

## 1. Shape table

| Pattern | Accounts | Attempts per account | Source | Distinguishing signature |
|---|---|---|---|---|
| Password spray | Many | Few (1-3) | Usually few sources | Wide account fan-out, low per-account count, often one common password, paced to stay under lockout |
| Credential stuffing | Many | Usually 1 | Often many sources | Account list looks externally sourced; unrelated accounts; high source diversity |
| Brute force | One or few | Many | Few sources | Deep per-account count, rapid, often hits lockout |
| MFA fatigue / push bombing | One | Many pushes | One source | Repeated MFA challenges after a *valid* primary credential; ends in an approval |
| Token / session replay | One | One or few | New source | Authentication succeeds without a fresh credential or MFA interaction; session or token artefact reused from a different context |
| Consent / app abuse | One | One | Legitimate | A grant or delegation event, not a password event; persistence without credentials |

Do not classify from volume alone. The account-to-attempt ratio is the discriminator
between spray and brute force, and it inverts between them.

## 2. Password spray

- Look for a failure count per account that is *deliberately low* - the attacker is
  pacing under the lockout threshold.
- Breadth matters more than depth: count distinct principals targeted in a window.
- Check whether targeted accounts share an attribute (naming convention, department,
  a published list). Enumeration preceded the spray if so.
- The spray is rarely the finding. The one account that succeeded is.

## 3. MFA fatigue

- Precondition: the primary credential was already valid. Push bombing does not work
  without a correct password, so a fatigue sequence implies a prior credential
  compromise that may not appear in this dataset.
- Signature: repeated challenge/deny events for one principal from one source in a
  short window, then an approval.
- The approval is the compromise moment. Record its timestamp precisely - it is the
  boundary between "attempted" and "successful" for the whole incident.
- Denials followed by silence is a *survived* attempt. Denials followed by an approval
  is a *breach*. Never summarise the two the same way.

## 4. Token and session replay

- Signature: a successful authentication that shows no fresh credential entry and no
  interactive MFA, appearing from a context inconsistent with the issuing context
  (different network, different device identifier, different client).
- Contrast with normal single sign-on, which is also credential-free. The discriminator
  is the *inconsistency* between issuance context and use context, not the absence of
  a password prompt.
- Do not label an event "replay" solely because MFA is absent. Many legitimate flows
  satisfy MFA once and reuse the result. State the contextual mismatch you observed,
  or classify it as undetermined.
- Replay also tends to preserve artefacts across the boundary - a session, device or
  token identifier that appears in both a legitimate and an anomalous authentication.
  That shared identifier is the evidence, and it is what you should cite.

## 5. Impossible travel and velocity

- Compute required velocity between consecutive successful authentications for the
  same principal. Flag only when the implied speed is physically implausible.
- Suppress, or at minimum annotate, these benign causes before reporting:
  - Corporate VPN or proxy egress, which relocates the apparent source.
  - Mobile carrier address assignment, which can place a stationary device far from
    its physical location and rotates frequently.
  - Cloud or CDN front-ends that terminate the connection.
  - Missing or coarse geolocation, which yields spurious distance.
- If the two endpoints belong to the same provider or network owner, treat the
  distance as unreliable rather than as a finding.
- Velocity is a *lead*, never a conclusion. Corroborate with a second signal -
  an unfamiliar device, an unusual client, a failure burst, or a post-login action
  inconsistent with the user's baseline - before calling it compromise.

## 6. Benign twins to exclude explicitly

For each candidate finding, state which benign explanation you excluded and how:

- **Typo** - one or two failures immediately followed by success from the same source
  and same device. This is a user mistyping, not a compromise. Check this *before*
  applying any success-after-failure rule.
- **Expired credential** - failures across multiple services for one principal at the
  same moment, resolving after a change event.
- **Stale cached credential** - a device repeatedly failing with an old secret,
  unattended, at machine-like regular intervals.
- **Service account** - high volume, perfectly periodic, unchanging source and client.
  Compare against its own history, not against human behaviour.
- **Misconfigured client** - a single source failing against one endpoint in a tight
  loop with an identical error code.
- **Roaming** - source address changes with no other behavioural change, on a
  consumer-mobile network.

## 7. Post-compromise questions

Once the compromise moment is fixed, the investigation is only half done. For the
principal involved, examine the window *after* that timestamp for:

- Authentication method or MFA registration changes.
- Delegation, forwarding, or consent grants.
- Role, group or permission changes.
- Authentication to systems the principal does not normally touch.
- Onward authentication to additional principals from the same source or device -
  this is how a single compromise becomes an incident, and it is routinely missed
  because analysis stops at the first victim.

Always check whether a *second* account was compromised from the same source. Report
the full set of affected principals, not just the first one found.

## 8. Reporting

State, for each identity finding: the principal, the pattern name, the compromise
moment timestamp if one exists, the attempt shape that justifies the pattern, the
benign twin excluded and how, the source context, and the post-compromise actions
observed. Anything not observable from the ingested authentication telemetry belongs
in the coverage-gap section rather than being inferred.
