---
name: lolbin_detection
description: Methodology for detecting living-off-the-land abuse of signed system binaries and scripting hosts by analysing argument idioms, parent-child lineage, and execution context rather than binary names.
author: UAOS Security Methodology
version: 1.0.0
license: MIT
metadata:
  category: security
  skills: [lolbin_detection, process_analysis, execution_analysis, defense_evasion_analysis, threat_analysis]
  risk_level: low
parameters:
  process_observation:
    type: string
    description: The process execution record or command line under analysis.
    required: false
---

# Living-off-the-Land Binary Detection

Reference methodology for process-execution telemetry. Adversaries prefer signed,
pre-installed binaries because they are trusted, ubiquitous and rarely blocked. The
binary name is therefore *never* the finding - the combination of binary, arguments,
parent, and context is.

## 1. The four-factor test

A system binary execution is suspicious when several of these hold at once:

1. **Capability** - does this binary have a capability an adversary wants?
   (remote download, arbitrary execution, credential access, proxied execution of
   code, archiving, scheduled persistence, log manipulation)
2. **Argument idiom** - are the arguments exercising that capability rather than the
   binary's routine purpose?
3. **Lineage** - is the parent process plausible? A system utility spawned by a
   document editor, a browser, a mail client, a web server process or a script host
   is far more interesting than the same utility spawned by an administrative shell
   or a management agent.
4. **Context** - user, host role, and time. An administrator running a management tool
   on a server during change hours is different from the same command on a workstation
   at an unusual hour under a standard user.

One factor alone is weak. Three together is a finding.

## 2. Capability categories to reason about

Rather than memorising a list of binary names, classify by what the invocation is
*doing*:

- **Remote content retrieval** - any signed utility that can fetch a URL to disk.
  Certificate, transfer, scripting and package utilities all have this.
- **Proxied execution** - a trusted binary asked to execute code held elsewhere
  (a script, a library, a registered component, a compiled payload).
- **Encoding and obfuscation** - base64 or hex payloads, string concatenation,
  character arithmetic, or escape-heavy command lines. Encoded arguments in an
  interactive shell invocation are close to self-evidently suspicious; legitimate
  automation rarely needs to hide its own command from its own logs.
- **Execution-policy and protection bypass** - flags that disable a security control,
  suppress prompts, or hide a window.
- **Credential access** - reading credential stores, dumping process memory of an
  authentication process, or exporting secrets.
- **Persistence** - registering scheduled work, services, startup entries, or
  component handlers.
- **Defense evasion via log manipulation** - clearing, disabling or reconfiguring
  audit and event logging. Treat any such event as high severity on its own, since
  it degrades the very evidence you are analysing.
- **Collection and staging** - archiving many files into one, especially into a
  temporary or public-writable path, shortly before outbound traffic.

## 3. Argument idioms worth flagging

Generic, vendor-neutral signals:

- A remote URL or UNC path as an argument to a utility whose normal use is local.
- An output path in a temporary, public, user-profile or recycle-bin-adjacent
  location combined with an executable or script extension.
- Encoded command payloads.
- Flags that suppress interaction, hide windows, or bypass policy.
- Execution of a file whose extension does not match its apparent use, or a
  double extension.
- A file written by one process and executed by another within seconds.

Record the *full* command line as evidence. A truncated command line frequently
removes exactly the argument that constitutes the finding.

## 4. Lineage analysis

Build the parent-child chain around any flagged execution, in both directions:

- What spawned it, and what spawned that?
- What did it spawn afterwards?
- Did anything write a file that later executed?

Chains that cross a trust boundary - from a document or browser process into a script
host into a system utility - are the classic initial-access-into-execution pattern and
are worth reporting even when each individual step looks ordinary.

Also look for the same chain on multiple hosts. Repetition across hosts turns a
single ambiguous execution into a campaign.

## 5. Benign explanations to exclude

System binaries are used legitimately far more often than maliciously. Before
reporting, exclude and say how:

- **Software deployment and patching** - management agents spawn installers and
  scripts constantly, usually under a service account, on a schedule, on many hosts
  simultaneously.
- **Administrative scripting** - an administrator account, from an administrative
  host or session, during a change window, with readable non-encoded arguments.
- **Vendor tooling** - endpoint agents, inventory tools and backup software invoke
  system utilities as part of normal operation.
- **Developer activity** - build and packaging tools on an engineering workstation.

The strongest discriminators are: who ran it, what spawned it, whether it is
encoded, and whether the same invocation appears routinely in the host's history.
If the host has no history in the ingested window, say the baseline is unknown
rather than assuming novelty.

## 6. Reporting

For each flagged execution state: host, user, full command line, parent chain,
timestamp, the capability being exercised, the specific idiom that triggered the
flag, the benign explanation excluded and its discriminator, supporting evidence
identifiers, and the mapped technique. Where process telemetry is absent for a host,
record it as a coverage gap - the absence of flagged executions on an unmonitored
host is not a clean result.
