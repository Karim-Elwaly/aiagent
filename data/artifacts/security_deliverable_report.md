# Mission Deliverable: Security
## Case: ARENA-MAKING-ANALYTICAL-PROCES-6D7328
**Classification:** CONFIDENTIAL // TLP:AMBER  
**Produced By:** Ingest Alert and Initial Contextualization  
**Assigned Fleet:** Security Fleet  
**Status:** Completed & Cryptographically Verified  
**Timestamp:** 2026-10-27T21:53:06Z  

### Executive Summary & Final Solution
## Executive Summary  

- **Alert Validity** – The alert is confirmed as a real attack; all key indicators of compromise (shadow file read, kernel module load, privileged pod creation, cluster‑admin binding, secret enumeration) are present in the supplied logs.  
- **Attack Chain** – A single service account (`webapp-sa`) performed discovery → created a privileged pod with host‑PID/host‑Network/host‑IPC, escaped to the node via `nsenter`, loaded an out‑of‑tree kernel module (`diamorphine`), obtained a root shell and read `/etc/shadow`, then escalated its Kubernetes privileges by creating a ClusterRoleBinding that granted it cluster‑admin rights. With those rights it listed all secrets in the cluster.  
- **MITRE ATT&CK Mapping** – T1003.008, T1014/T1547.006, T1611, T1078.004, T1552.007.  
- **Impact** – Full host compromise (root shell + kernel rootkit), full control plane takeover (cluster‑admin), credential dumping of password hashes and Kubernetes secrets. No exfiltration detected but the attacker now has the capability to exfiltrate data.  
- **Containment Actions** – Quarantine `k8s-worker-node-01`, delete malicious pod and ClusterRoleBinding, reboot/unload `diamorphine`, audit and revoke excessive RBAC bindings, reset compromised credentials, deploy host‑based IDS (Falco) with rules for LKM loading, privileged pod creation, and root shell escalation.  

---

## Detailed Findings

| IOC | Log Source | Evidence |
|-----|------------|----------|
| `/etc/shadow` read | `linux_audit.log` – lines 17‑18 | `type=SYSCALL … comm="cat" exe="/usr/bin/cat" auid=1001 uid=0 key="shadow_access"` |
| Kernel module load (`diamorphine.ko`) | `linux_audit.log` – line 27 | `type=SYSCALL … comm="insmod" exe="/usr/bin/kmod" key="kernel_module_load"` |
| Privileged pod creation (hostPID/hostNetwork/hostIPC) | `k8s_api_audit.json` – event 5 | `verb":"create", "spec":{"hostPID":true,"hostNetwork":true,"hostIPC":true,…}` |
| ClusterRoleBinding granting cluster‑admin to `webapp-sa` | `k8s_api_audit.json` – event 6 | `verb":"create", "roleRef":{"kind":"ClusterRole","name":"cluster-admin"}, "subjects":[{"kind":"ServiceAccount","name":"webapp-sa"}]` |
| Secret enumeration by `webapp‑sa` | `k8s_api_audit.json` – event 7 | `verb":"list", "resource":"secrets"` |

---

## Attack Chain Narrative

1. **Discovery** – 08:48 12: Service account *webapp‑sa* lists pods in `kube-system`.  
2. **Privileged Pod Creation** – 08:50 04: Creates `system-health-diagnostics-pod` with hostPID/hostNetwork/hostIPC; container runs `nsenter … /bin/sh`, gaining a shell in the node’s PID namespace (T1611).  
3. **Kernel Compromise** – 08:45 30: Inside the host, attacker loads `diamorphine.ko` via `insmod`; hooks sys_call_table (T1014/T1547.006).  
4. **Credential Dumping** – 08:42 15: Reads `/etc/shadow` with root privileges (`cat /etc/shadow`) – credential dumping (T1003.008).  
5. **Control‑Plane Takeover** – 08:52 18: Creates ClusterRoleBinding `system-cluster-admin-binding`, granting `webapp‑sa` cluster‑admin rights (T1078.004).  
6. **Secret Dumping** – 08:53 40: Lists all secrets in the cluster with new privileges (T1552.007).  

No exfiltration was observed; the chain ends at privilege escalation and credential theft.

---

## MITRE ATT&CK Mapping

| Technique ID | Name | Log Evidence |
|--------------|------|--------------|
| T1003.008 | Credential Dumping – Shadow File Access | `linux_audit.log` line 17‑18 |
| T1014 / T1547.006 | Loadable Kernel Module – Kernel Module Loading | `linux_audit.log` line 27 |
| T1611 | Container Escape via Privileged Pod | Event 5 (`create pod`, hostPID/hostNetwork/hostIPC) |
| T1078.004 | Cloud Account Management – RBAC Escalation | Event 6 (ClusterRoleBinding to cluster‑admin) |
| T1552.007 | Secret Store Credential Dumping – Kubernetes | Event 7 (list secrets) |

---

## Impact Assessment

- **Host** – Root shell, kernel rootkit (`diamorphine`) loaded → persistence and stealth.  
- **Control Plane** – Cluster‑admin binding grants unrestricted API access; attacker can create/delete resources, modify RBAC, and read all secrets.  
- **Data Exposure** – `/etc/shadow` read exposes password hashes; secret enumeration may reveal service credentials, tokens, certificates.  
- **Operational Disruption** – Malicious pod and kernel module could degrade node performance or cause instability if left unchecked.  

---

## Containment & Remediation

| Step | Action | Rationale |
|------|--------|-----------|
| 1 | **Isolate `k8s-worker-node-01`** (drop all inbound/outbound except established) | Prevent further lateral movement and stop the rootkit from communicating. |
| 2 | **Delete malicious pod** (`system-health-diagnostics-pod`) and any hostPath mounts. | Removes breakout vector. |
| 3 | **Revoke `system-cluster-admin-binding`** (delete ClusterRoleBinding). | Removes cluster‑admin privileges granted to attacker’s service account. |
| 4 | **Unload or reboot node** to unload `diamorphine`. | Kernel module removal requires a reboot; ensures persistence mechanism is removed. |
| 5 | **Reset credentials** for user `deploy` and any other accounts that may have been compromised. | Stops reuse of stolen password hashes. |
| 6 | **Audit RBAC** – list all ClusterRoleBindings, RoleBindings, and ServiceAccounts; enforce least‑privilege policies. | Prevents future privilege escalation via service accounts. |
| 7 | **Deploy host‑based IDS (Falco, Sysdig)** with rules for: <br>• LKM loading (`insmod`, `kmod`) <br>• Privileged pod creation (`hostPID`, `hostNetwork`, `hostIPC`) <br>• Root shell via sudo by non‑admin users | Provides early detection of similar attacks. |
| 8 | **Review audit logs** for any other suspicious activity on the node or in the cluster; consider a full forensic disk image. | Ensures no additional backdoors remain. |

---

## Lessons Learned

- Enforce least‑privilege for service accounts; never grant `cluster-admin` unless absolutely necessary.  
- Restrict `hostPID`, `hostNetwork`, and `hostIPC` via PodSecurityPolicies or OPA Gatekeeper.  
- Disable or whitelist kernel module loading; enforce signed modules and module‑signing enforcement.  
- Configure auditd to capture privileged actions with distinct keys (`shadow_access`, `kernel_module_load`).  
- Implement real‑time alerts for LKM loads, privileged pod creation, and shadow file access.

---

**Conclusion:** The logs confirm a full compromise of the worker node and Kubernetes control plane through container escape, kernel rootkit injection, credential dumping, and RBAC escalation. Immediate isolation, removal of malicious artifacts, revocation of elevated privileges, and deployment of host‑based detection are mandatory to contain the incident and prevent further damage.
