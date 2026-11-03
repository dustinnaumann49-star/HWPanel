# Security

**Languages:** English · [Deutsch](SECURITY.de.md)

Please report security problems privately by e-mail to dustinnaumann49@gmail.com, not through public issues. If GitHub's private vulnerability reporting is enabled for the repository, you can use that instead (Security tab, "Report a vulnerability"). I will get back to you as soon as I can.

## What counts

The daemon `hwpaneld` runs as root and offers a Unix socket (`/run/hwpanel/hwpanel.sock`) to the members of one group. Relevant reports are, for example: ways to write outside the whitelist of sysfs paths, ways around the limits (values above the driver defaults, the fan protection rules), access to the socket for users outside the group, and privilege escalation through the daemon, the installer or the systemd unit.

## What to include

The version (`hwpanelctl --json info`, field `version`), your system and kernel, a description of the problem and, if possible, steps to reproduce it.

## Supported versions

Fixes go into the latest version.
