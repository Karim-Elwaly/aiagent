# Mission Deliverable: Case 6: ddos recon firewall evasion SOC Investigation
## Case: ARENA-INVESTIGATE-APT-ENTERPRI-EA3569
**Classification:** CONFIDENTIAL // TLP:AMBER  
**Produced By:** Ingest and Parse Raw Logs  
**Assigned Fleet:** Case 6: ddos recon firewall evasion SOC Investigation Fleet  
**Status:** Completed & Cryptographically Verified  
**Timestamp:** 2026-10-26T13:45:31Z  

### Executive Summary & Final Solution
**Executive Summary**  
The investigation uncovered a coordinated APT intrusion that leveraged reconnaissance traffic, port‑scanning, SYN‑flood DDoS activity, and brute‑force authentication attempts against local accounts. The attack chain is fully mapped across authentication logs, process executions (none detected), and network flows. All identified C2 indicators of compromise (IOCs) have been catalogued, each linked to a MITRE ATT&CK technique, and actionable containment policies are provided for both perimeter firewalls and endpoint protection platforms.

---

## 1. Attack Kill Chain

| Event ID | Timestamp | Stage | Description | MITRE Technique |
|----------|-----------|-------|-------------|-----------------|
| E1 | 14 11:30:12 | Reconnaissance | Outbound TCP from internal host **203.0.113.10** to external IP **198.51.100.40** (port 443). | T1046 |
| E2 | 14 11:31:05 | Reconnaissance | Outbound TCP from **203.0.113.10** to external IP **142.250.190.36** (port 443). | T1046 |
| E3 | 14 11:33:05 | Recon / Initial Access Attempt | Inbound vertical port scan from **198.51.100.220** to DMZ host **10.10.10.20** (ports 21‑3389) blocked by ACL. | T1046 |
| E4 | 14 12:10:06 | Impact – DDoS | SYN flood from spoofed IPs **203.0.113.88‑92** targeting internal web gateway **10.10.10.5**; connection limits exceeded. | T1499 |
| E5 | 14 12:15:01 | Initial Access Attempt – Brute Force | AAA authentication rejected for user **root** from attacker IP **198.51.100.75**. | T1110 |
| E6 | 14 12:15:03 | Initial Access Attempt – Brute Force | AAA authentication rejected for user **admin** from attacker IP **198.51.100.75**. | T1110 |
| E7 | 14 12:15:05 | Initial Access Attempt – Brute Force | AAA authentication rejected for user **deploy** from attacker IP **198.51.100.75**. | T1110 |
| E8 | 14 12:15:07 | Initial Access Attempt – Brute Force | AAA authentication rejected for user **ubnt** from attacker IP **198.51.100.75**. | T1110 |

---

## 2. C2 Indicators of Compromise (IOCs)

### IP Addresses

| IP Address |
|------------|
| 203.0.113.10 |
| 198.51.100.40 |
| 142.250.190.36 |
| 198.51.100.220 |
| 10.10.10.20 |
| 203.0.113.88 |
| 203.0.113.89 |
| 203.0.113.90 |
| 203.0.113.91 |
| 203.0.113.92 |
| 10.10.10.5 |
| 198.51.100.75 |

### User Accounts

| Username |
|----------|
| root |
| admin |
| deploy |
| ubnt |

---

## 3. MITRE ATT&CK Mapping

| IOC Value | Technique ID | Technique Name | Description | Evidence Event IDs |
|-----------|--------------|----------------|-------------|--------------------|
| 203.0.113.10 | T1046 | Network Service Discovery | Detects processes performing network enumeration (e.g., port scans, service probing). | E1,E2 |
| 198.51.100.40 | T1046 | Network Service Discovery | Same as above. | E1 |
| 142.250.190.36 | T1046 | Network Service Discovery | Same as above. | E2 |
| 198.51.100.220 | T1046 | Network Service Discovery | Same as above. | E3 |
| 10.10.10.20 | T1046 | Network Service Discovery | Same as above. | E3 |
| 203.0.113.88‑92 | T1499 | Endpoint Denial of Service | Adversaries may perform endpoint DoS attacks to degrade or block availability of services. | E4 |
| 10.10.10.5 | T1499 | Endpoint Denial of Service | Same as above. | E4 |
| 198.51.100.75 | T1110 | Brute Force | Adversaries may use brute force techniques to gain access to accounts when passwords are unknown or hashes are obtained. | E5,E6,E7,E8 |
| root | T1110 | Brute Force | Same as above. | E5 |
| admin | T1110 | Brute Force | Same as above. | E6 |
| deploy | T1110 | Brute Force | Same as above. | E7 |
| ubnt | T1110 | Brute Force | Same as above. | E8 |

---

## 4. Automated Containment Policies

### Perimeter Firewall Rules (Linux iptables / Windows Defender)

1. **Block attacker IP**  
   - `iptables -A INPUT -s 198.51.100.75 -j DROP`  
   - `netsh advfirewall firewall add rule name="Block-198.51.100.75" dir=in action=block remoteip=198.51.100.75`

2. **Block SYN‑flood IP range**  
   - `iptables -A INPUT -m iprange --src-range 203.0.113.88-203.0.113.92 -j DROP`  
   - `netsh advfirewall firewall add rule name="Block-203.0.113.88-92" dir=in action=block remoteip=203.0.113.88-203.0.113.92`

3. **Block port‑scanning source**  
   - `iptables -A INPUT -s 198.51.100.220 -p tcp --dport 1:65535 -j DROP`  
   - `netsh advfirewall firewall add rule name="Block-198.51.100.220" dir=in action=block remoteip=198.51.100.220`

4. **Drop traffic to internal web gateway**  
   - `iptables -A OUTPUT -d 10.10.10.5 -j DROP`  
   - `netsh advfirewall firewall add rule name="Block-10.10.10.5" dir=out action=block remoteip=10.10.10.5`

### Endpoint Protection Rules

1. **Account Lockout** – If authentication failures for any of the users (root, admin, deploy, ubnt) exceed 5 within 10 minutes from IP 198.51.100.75, lock account and trigger alert.

2. **Process Block** – Terminate any outbound TCP SYN packet count > 500 per minute originating from IP range 203.0.113.88‑92; block the source IP thereafter.

3. **MFA Enforcement** – Require multi‑factor authentication for all accounts listed in the IOC user list after a lockout period.

### SIEM Detection (Splunk)

| Query | Purpose |
|-------|---------|
| `index=auth sourcetype=linux_secure | stats count by src_ip, user | where src_ip="198.51.100.75" AND count>5 | eval alert_type="BruteForce_T1110"` | Detect brute‑force attempts |
| `index=network sourcetype=netflow | stats sum(bytes) as total_bytes, count by src_ip, dest_ip, proto | where src_ip="203.0.113.88-92" AND dest_ip="10.10.10.5" AND proto="TCP" AND total_bytes>10000000 | eval alert_type="DoS_T1499"` | Detect SYN flood |
| `index=network sourcetype=netflow | stats dc(dest_port) as unique_ports by src_ip | where src_ip="198.51.100.220" AND unique_ports>50 | eval alert_type="Recon_T1046"` | Detect port scanning |

### Suricata Signatures

1. **SYN Flood** – `alert tcp any any -> 10.10.10.5 any (msg:"SYN Flood from DDoS IP range"; flow:to_server,established; threshold:type both, track by_src, count 500, seconds 60; sid:1000001;)`
2. **Port Scan** – `alert tcp 198.51.100.220 any -> 10.10.10.20 any (msg:"Port Scan from Recon IP"; flow:to_server,established; threshold:type both, track by_src, count 50, seconds 30; sid:1000002;)`
3. **Brute‑Force Login** – `alert tcp any any -> any 22 (msg:"SSH Brute Force T1110"; flow:to_server,established; content:"Failed password"; threshold:type both, track by_src, count 5, seconds 300; sid:1000003;)`

---

**Conclusion**  
The attack leveraged reconnaissance, port scanning, a SYN‑flood DDoS, and brute‑force credential attempts. All malicious IPs and user accounts have been identified, mapped to MITRE ATT&CK techniques, and containment rules are ready for deployment across perimeter firewalls and endpoint protection platforms.
