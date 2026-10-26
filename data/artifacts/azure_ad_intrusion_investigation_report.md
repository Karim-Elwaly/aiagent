# Incident Investigation Report: Azure AD Identity Takeover & Impossible Travel
## Case: CASE-3-IDENTITY-TAKEOVER-IMPOSSIBLE-TRAVEL
**Classification:** CONFIDENTIAL // TLP:AMBER  
**Target Tenant:** Contoso Global Enterprise (Tenant ID: `0f81d942-8821-4f1a-b62e-9d2a4e819b11`)  
**Target Identity:** `alex.vance@contoso-global.com` (Director of Strategic Finance)  
**Assigned Fleet:** Azure AD & Cloud Identity Defense Fleet  
**Status:** Kill Chain Reconstructed · Autonomous Containment Formulated · Sign-Off Completed  

---

### 1. Executive Summary & Incident Timeline
A sophisticated credential compromise and identity takeover incident was detected within the Azure AD tenant. The adversary leveraged compromised primary credentials coupled with an **Impossible Travel** anomaly—authenticating from **London, UK (corporate office)** and subsequently from **Amsterdam, NL (Tor Exit Node)** within an 8-minute window (geographic displacement velocity exceeding 3,400 km/h). 

Following the initial sign-in, the attacker bypassed MFA via session token replay (Primary Refresh Token theft), added a rogue credential to an existing Enterprise Application registration with `Directory.ReadWrite.All` privileges, and initiated bulk data exfiltration from OneDrive/SharePoint.

---

### 2. Multi-Stage Attack Kill Chain Reconstruction (MITRE ATT&CK)

1. **Initial Access & Credential Abuse (T1078.004 - Cloud Accounts / T1110.003 - Password Spraying):**
   - **08:14:22 UTC**: Successful login from legitimate user IP `194.26.29.112` (London, UK) via Edge on Windows 11.
   - **08:22:05 UTC**: Concurrent authentication attempt from IP `185.220.101.45` (Amsterdam, NL) using user agent `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36`.
   - **Anomaly Detected**: Azure AD Identity Protection flagged `riskEventType: impossibleTravel` with Risk Level `HIGH`.

2. **Defense Evasion & Session Hijacking (T1539 - Steal Web Session Cookie / T1556 - Modify Authentication Process):**
   - Attacker replayed captured `ESTSAUTH` cookie and Primary Refresh Token (PRT), evading the standard conditional access prompt.
   - Session continuity validated without generating an additional interactive MFA prompt.

3. **Persistence & Privilege Escalation (T1098.001 - Additional Cloud Credentials):**
   - **08:27:40 UTC**: Attacker navigated to Microsoft Entra App Registrations.
   - Created a new client secret (name: `DiagnosticSyncKey-2026`) under pre-approved multi-tenant application `Financial-Reporting-Sync-App` (AppID: `7a14e912-88f1-4b19-9133-e9821a4f01bc`).
   - Granted elevated permissions: `RoleManagement.ReadWrite.Directory` and `Mail.Read`.

4. **Collection & Exfiltration (T1114.002 - Remote Email Collection / T1567 - Exfiltration Over Web Service):**
   - **08:31:15 UTC**: Scripted API queries executed via PowerShell `Microsoft.Graph` module.
   - Exported 4,218 confidential emails and 18 internal Excel financial audit records to external endpoint `https://sync-telemetry-cache.net/upload`.

---

### 3. Neutralized Indicators of Compromise (IOCs)

| IOC Type | Indicator Value | Attribution / Context | Status |
| :--- | :--- | :--- | :--- |
| **Adversary IP (Tor)** | `185.220.101.45` | Known Tor Exit Node (Amsterdam, NL) used for session replay | **BLOCKED** |
| **Secondary C2 IP** | `194.135.31.88` | Bulletproof hosting proxy used for Graph API extraction | **BLOCKED** |
| **Exfiltration Domain** | `sync-telemetry-cache.net` | Malicious webhook receiver (ASN 61124) | **SINKHOLED** |
| **Compromised Account** | `alex.vance@contoso-global.com` | User ID: `usr-9941-avance` | **REVOKED / LOCKED** |
| **Rogue App Credential** | `DiagnosticSyncKey-2026` | AppID: `7a14e912-88f1-4b19-9133-e9821a4f01bc` | **REVOKED & PURGED** |
| **User Agent** | `Python-urllib/3.10` / `Go-http-client/1.1` | Used during automated Graph API mass extraction | **SIGNATURE APPLIED** |

---

### 4. Autonomous Containment & Remediation Actions

1. **Immediate Session Termination (Graph API):**
   - Invoked `POST /v1.0/users/alex.vance@contoso-global.com/revokeSignInSessions` invalidating all active refresh tokens and browser sessions across all devices.
2. **Account Quarantine & Password Reset:**
   - Account status set to `AccountEnabled: false`. Forced password reset flag enabled upon operator release.
3. **App Secret Deletion:**
   - Key identifier `0x9a8f21bc` removed from App `Financial-Reporting-Sync-App`.
4. **Conditional Access Hardening:**
   - Enforced Conditional Access Policy `CAP-IDENTITY-HARDEN-09`: Requires compliant device + FIDO2 hardware token for all directory role assignments and sensitive SaaS apps.
   - Blocked all incoming authentications originating from known anonymizer/Tor networks.

---

### 5. SOC Sign-Off & Attestation
- **Investigating Lead:** Cloud Identity Incident Commander (Azure AD Specialist Agent)  
- **Assurance Record:** `Assurance Review: Generate Automated Containment Policies`  
- **Audit Verification:** Signed under SHA-256 hash `d4e5f6a1b2c39874561230abcdef0123456789abcdef0123456789abcdef0123`  
- **Status:** **ALL 4 GOVERNANCE ROOMS APPROVED AND COMMITTED TO ESTATE AUDIT LEDGER**
