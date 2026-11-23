# Web server migration

Status: active

- **Owner:** lnevo
- **Status:** 2026-11-23. Steps 1 and 2 done; the survey waits on the owner's answers ([`docs/website/old-server-survey.md`](../../docs/website/old-server-survey.md)).
- **Server today:** www.easte.net, the host of www.hartrailroad.com ([`www/README.md`](../../www/README.md), server notes). It is an Amazon Lightsail instance (512 MB RAM, 20 GB disk) running Ubuntu 18.04, VestaCP 0.9.8, nginx 1.25.0 from nginx.org, PHP 7.2 and MySQL 5.7 from Ubuntu, and Exim and Dovecot for mail. Besides hartrailroad.com it hosts the owner's easte.net sites and WordPress sites for other users (WordPress 6.9.12, auto-update on).

## Why

Ubuntu 18.04 gets security updates only through Ubuntu Pro ESM, which ends in April 2028. nginx.org stopped building for 18.04 at 1.25.0, so nginx gets no more fixes. VestaCP has had no release since 2019 and does not run on Ubuntu 22.04 or 24.04.

## Done on 2026-11-19

- PHP 7.2 updated from `+esm14` to `+esm15` (16 CVEs, among them the FPM status page XSS and the corrupted-session RCE). PHP-FPM restarted; the sites answer.
- The expired nginx.org signing key (`ABF5BD827BD9BF62`) replaced with the current key from nginx.org, fingerprints checked. The repository loads again but has nothing newer than 1.25.0.
- The Grafana repository moved to `https://apt.grafana.com` with Grafana's new key (`963FA27710458545`); the old list is kept as `grafana.list.bak-20261119`. Grafana 9.2.3 is installed but not running and was not upgraded.
- Unattended upgrades already take the ESM security channels, so later PHP fixes arrive within a day without a watcher.

## Decisions

- **Stay on Lightsail.** A 2 GB Lightsail plan is $12 a month with disk, IPv4 and transfer included; the same size on EC2 is about $21 before transfer.
- **New server, not an in-place upgrade.** Three `do-release-upgrade` steps (18.04 to 24.04) would leave VestaCP broken, move MySQL 5.7 to 8.0 (one way) and PHP 7.2 to 8.3 at once, and could run out of memory on 512 MB, with no way back if one fails.
- **Target:** a 2 GB Lightsail instance with Ubuntu 24.04 and HestiaCP, the maintained fork of VestaCP (same layout and `v-*` commands).
- **The owner approves** the other users' sites, the instance creation and the cut-over.

## Steps

1. **Done 2026-11-23.** The owner made IAM user `lnevo-agent` with Lightsail rights only (`lightsail:*`) and `SignInLocalDevelopmentAccess`; the Mac's `default` AWS profile signs in with `aws login`, so there is no stored access key. Original step: create an IAM user with Lightsail permissions only and an access key, and store it on the Mac with `aws configure --profile lightsail`, never in chat or the repo. Optional: an AWS Budget alarm at $20 a month.
2. **Done 2026-11-23** ([survey](../../docs/website/old-server-survey.md)). A read-only survey of the old server: web domains, databases, mail accounts in use, cron jobs, Grafana, WordPress plugins and themes that may not run on PHP 8.3. Written up in `docs/` for the owner's approval.
3. **Agent, after the owner's yes:** create the instance, SSH key and firewall; install HestiaCP; turn on unattended security updates.
4. **Agent:** move one Vesta user at a time (Vesta backup, Hestia restore) and check each site on the new server before any switch (`curl --resolve`, screenshots). The owner checks the other users' sites.
5. **Agent:** rebuild the hartrailroad.com setup: the rsync-only deploy key (`Host hart-deploy`), the `static-revalidate` nginx template with its 404 and header lines, and the panel and phpMyAdmin restrictions. Update the server notes in `www/README.md` and, if a path changes, `www/scripts/deploy_hartrailroad.sh`.
6. **Owner and agent:** move the Lightsail static IP to the new instance (no DNS change), then issue the Let's Encrypt certificates there. Keep the old instance stopped for a few weeks as the fallback, then delete it and the IAM user.

## Open questions

- The five questions at the end of the [survey](../../docs/website/old-server-survey.md): the aquarium jobs, pequott.easte.net, MainWP, a server without mail, and the other users' checks.
