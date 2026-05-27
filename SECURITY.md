# Security Policy

We take the security of FIVUCSAS and all Rollingcat-Software projects seriously.

## Reporting a vulnerability

**Do not open a public issue for security problems.** Report privately to
**info@app.fivucsas.com** with the subject prefix `[SECURITY]` and the affected
repository name. Where available, you may also use GitHub's private
**"Report a vulnerability"** (Security advisories) on the affected repo.

Please include: affected repo/version, a description and impact assessment, and
reproduction steps or a proof of concept.

## Our commitment

- **Acknowledgement** within 3 business days.
- **Initial assessment** within 10 business days.
- Coordinated disclosure once a fix is available; we credit reporters who wish to be named.

## Scope

In scope: authentication/authorization bypass, tenant isolation breaks, liveness/PAD
bypass (print, replay, screen, mask, deepfake), token/credential handling, injection,
and exposure of biometric data, embeddings, or PII.

Out of scope: findings requiring physical device access, social engineering, volumetric
DoS, and automated-scanner output without a demonstrated impact.

## Safe harbor

Good-faith research that respects user privacy, does not degrade service, and follows
this process is welcome. We will not pursue legal action against researchers who follow
this policy.
