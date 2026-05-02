# Pre-Customer Deployment Legal Checklist

This checklist is for internal review before any commercial installation or customer handover.
It is a practical aide-mémoire and does not constitute legal advice.

---

## 1. Intellectual Property

- [ ] Confirm that all source code was authored by the named author(s) or by parties who have assigned rights to MACD Adaptive Ltd.
- [ ] Confirm no third-party code has been copied into the repository without a compatible licence.
- [ ] Verify no client or employer IP has been included without written permission.

---

## 2. Licence Wording

- [ ] `LICENSE` file exists in the repository root.
- [ ] Licence clearly states **"licensed, not sold"** — the customer receives a right to use the software, not ownership of it.
- [ ] Licence uses "LICENSED USE ONLY" (or equivalent proprietary wording) rather than any open-source template.
- [ ] Permitted uses, restrictions, and termination conditions are explicitly stated.
- [ ] Licence references the correct legal entity (e.g. MACD Adaptive Ltd) as licensor.

---

## 3. Supporting Notices

- [ ] `NOTICE.md` exists and identifies the project as proprietary / confidential.
- [ ] `THIRD_PARTY_NOTICES.md` lists all runtime dependencies, their versions, and their licences.
- [ ] PyQt5 / Qt commercial-use obligations have been reviewed and are satisfied (GPL vs commercial licence).
- [ ] Any other dependencies with GPL, LGPL, or copyleft licences have been assessed for compatibility with commercial distribution.

---

## 4. Privacy and Data Handling

- [ ] `docs/PRIVACY_NOTES.md` exists and documents what personal data the application stores (seat names, speaker names, backup files).
- [ ] Data retention policy for customer backups is defined and communicated.
- [ ] Customer is made aware of where data is stored (`~/.config/dublinisl/` by default).
- [ ] Responsibilities for GDPR or local data-protection compliance have been allocated between licensor and customer.

---

## 5. Public Documentation Review

- [ ] Personal phone numbers, personal email addresses, and home addresses have been removed from all public-facing documentation (README, config examples, etc.).
- [ ] Contact information in README refers only to the business entity or a dedicated support address.
- [ ] No customer-specific credentials, IP addresses, or network details are committed to the repository.

---

## 6. Contractual Alignment

- [ ] The customer contract (or order form) references this software by name and version.
- [ ] Licence model in the contract matches the `LICENSE` file (e.g. per-site licence, perpetual licence with annual support).
- [ ] Support scope, SLA, and response times are defined in writing before handover.
- [ ] Hardware responsibilities (who supplies, configures, and maintains cameras, network, Raspberry Pi) are clearly allocated in the contract.
- [ ] Backup and disaster-recovery responsibilities are allocated between licensor and customer.

---

## 7. Pre-Handover Technical Checks

- [ ] Version number in `VERSION` file matches the release being delivered.
- [ ] `CHANGELOG.md` is up to date for the delivered version.
- [ ] Default password has been changed; `password.enc` is not pre-seeded with a known value.
- [ ] No development or test credentials are present in the deployed configuration.
- [ ] Simulation mode is disabled for production deployment.
- [ ] Camera IP addresses and ATEM address are configured for the customer's network (not left as placeholders).

---

## Sign-Off

| Item | Checked by | Date |
|------|-----------|------|
| IP ownership confirmed | | |
| Licence wording reviewed | | |
| Third-party licences verified | | |
| Privacy notes prepared | | |
| Public docs sanitised | | |
| Contract aligned | | |
| Technical pre-checks passed | | |

---

*This document does not constitute legal advice. Seek qualified legal counsel for jurisdiction-specific requirements.*
