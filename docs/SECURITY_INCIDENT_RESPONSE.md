# Presek Security Incident Response Plan

This document outlines the operational procedures for responding to security incidents (e.g. key exposures, unauthorized administrative access, or injection attacks) on the Presek platform.

---

## 🚨 Phase 1: Identification & Escalation

### 1. Indicators of Compromise (IoC)
- Failed admin token authentications spiking in logs:
  ```bash
  journalctl -u presek-fastapi-unified --since "1 hour ago" | grep "admin_token_validation_failed"
  ```
- Unauthorized POST requests to `/newsletter/subscribe` or `/sources/{name}/control` bypassing CSRF verification.
- Alerts from `scripts/security_monitoring.py` indicating altered file permissions or unexpected secrets in files.

### 2. Immediate Contact
In case of a verified exploit or secret exposure, notify the system owner immediately and escalate to emergency containment.

---

## 🛡️ Phase 2: Containment & Immediate Mitigation

### 1. Token Exposure
If `PRESEK_ADMIN_TOKEN` or `CSRF_TOKEN_SECRET` is compromised or leaked:
1. Open the production shared environment file:
   ```bash
   nano /home/emiloffingen/presek-runtime/shared/.env
   ```
2. Revoke and rotate the compromised secrets:
   - Generate a cryptographically secure key: `openssl rand -hex 32`
   - Replace the values of `PRESEK_ADMIN_TOKEN` and `CSRF_TOKEN_SECRET`.
3. Force a restart of the serving stack:
   ```bash
   sudo systemctl restart presek-fastapi-unified.service
   ```

### 2. Host-Level Intrusions
If the server has been compromised:
1. Shut down the application immediately to prevent lateral data movement:
   ```bash
   sudo systemctl stop presek.target
   ```
2. Disable external access via Nginx or UFW firewall:
   ```bash
   sudo ufw deny proto tcp from any to any port 80,443
   ```

---

## 🧹 Phase 3: Eradication & Recovery

1. **Verify Integrity**: Run the hygiene checks to verify that no untracked configuration or executables are left behind:
   ```bash
   make hygiene
   ```
2. **Re-audit the System**: Run a full security scan:
   ```bash
   python3 scripts/security_audit.py
   ```
3. **Restore & Upgrade**: Re-enable external traffic only after all tests pass successfully.
