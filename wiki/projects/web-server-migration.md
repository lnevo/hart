# Web server migration

Status: done (2026-11-23)

- **Owner:** lnevo
- **Status:** 2026-11-23. Done. Every site moved and checked, the static IP moved to `www-2026` the same day, and the old instance was deleted after a final snapshot. Left: see the end of this page.
- **Server before the move:** www.easte.net, the host of www.hartrailroad.com ([`www/README.md`](../../www/README.md), server notes). It is an Amazon Lightsail instance (512 MB RAM, 20 GB disk) running Ubuntu 18.04, VestaCP 0.9.8, nginx 1.25.0 from nginx.org, PHP 7.2 and MySQL 5.7 from Ubuntu, and Exim and Dovecot for mail. Besides hartrailroad.com it hosts the owner's easte.net sites and WordPress sites for other users (WordPress 6.9.12, auto-update on).

## Why

Ubuntu 18.04 gets security updates only through Ubuntu Pro ESM, which ends in April 2028. nginx.org stopped building for 18.04 at 1.25.0, so nginx gets no more fixes. VestaCP has had no release since 2019 and does not run on Ubuntu 22.04 or 24.04.

## Done on 2026-11-19

- PHP 7.2 updated from `+esm14` to `+esm15` (16 CVEs, among them the FPM status page XSS and the corrupted-session RCE). PHP-FPM restarted; the sites answer.
- The expired nginx.org signing key (`ABF5BD827BD9BF62`) replaced with the current key from nginx.org, fingerprints checked. The repository loads again but has nothing newer than 1.25.0.
- The Grafana repository moved to `https://apt.grafana.com` with Grafana's new key (`963FA27710458545`); the old list is kept as `grafana.list.bak-20261119`. Grafana 9.2.3 is installed but not running and was not upgraded.
- Unattended upgrades already take the ESM security channels, so later PHP fixes arrive within a day without a watcher.

## Decisions

- **Stay on Lightsail.** Disk, IPv4 and transfer are included in the plan price; the same size on EC2 costs more before transfer.
- **1 GB, not 2 GB (owner, 2026-11-23).** The bill stays near today's $7 a month: `micro_3_0` (1 GB RAM, 40 GB disk) is $7, with a 1 GB swap file. The old server's two manual snapshots from 2020 were deleted the same day.
- **New server, not an in-place upgrade.** Three `do-release-upgrade` steps (18.04 to 24.04) would leave VestaCP broken, move MySQL 5.7 to 8.0 (one way) and PHP 7.2 to 8.3 at once, and could run out of memory on 512 MB, with no way back if one fails.
- **Target:** instance `www-2026`, 1 GB, Ubuntu 24.04 and HestiaCP, the maintained fork of VestaCP (same layout and `v-*` commands).
- **What moves (owner, 2026-11-23):** every site. The aquarium pages move with their cron jobs commented out; pequott.easte.net moves but is suspended. No mail server: HestiaCP is installed without Exim, Dovecot, ClamAV, SpamAssassin, DNS or FTP.
- **The owner approves** the other users' sites, the instance creation and the cut-over.

## Steps

1. **Done 2026-11-23.** The owner made IAM user `lnevo-agent` with Lightsail rights only (`lightsail:*`) and `SignInLocalDevelopmentAccess`; the Mac's `default` AWS profile signs in with `aws login`, so there is no stored access key. Original step: create an IAM user with Lightsail permissions only and an access key, and store it on the Mac with `aws configure --profile lightsail`, never in chat or the repo. Optional: an AWS Budget alarm at $20 a month.
2. **Done 2026-11-23** ([survey](../../docs/website/old-server-survey.md)). A read-only survey of the old server: web domains, databases, mail accounts in use, cron jobs, Grafana, WordPress plugins and themes that may not run on PHP 8.3. Written up in `docs/` for the owner's approval.
3. **Done 2026-11-23.** Instance `www-2026` (`micro_3_0`, us-east-1a, Lightsail SSH key `web-2026`, private key `~/.ssh/lightsail_web` on the Mac, log in as `ubuntu`). Firewall 22, 80, 443 and 8083. 1 GB swap. HestiaCP 1.10.9 with nginx and PHP-FPM (PHP 8.5; older versions are added per site as needed), MariaDB, fail2ban, no API; panel user `hstadmin`, password in `~/.ssh/hestia-www-2026-admin.txt` on the Mac. Unattended security updates on. Original step: create the instance, SSH key and firewall; install HestiaCP; turn on unattended security updates.
4. **Agent:** move one Vesta user at a time (Vesta backup, Hestia restore) and check each site on the new server before any switch (`curl --resolve`, screenshots). The owner checks the other users' sites.
5. **Agent:** rebuild the hartrailroad.com setup: the rsync-only deploy key (`Host hart-deploy`), the `static-revalidate` nginx template with its 404 and header lines, and the panel and phpMyAdmin restrictions. Update the server notes in `www/README.md` and, if a path changes, `www/scripts/deploy_hartrailroad.sh`.
6. **Owner and agent:** move the Lightsail static IP to the new instance (no DNS change), then issue the Let's Encrypt certificates there. Take a final snapshot of the old instance and delete it (a stopped instance is still billed in full); the snapshot is the fallback for a few weeks. Then delete the snapshot and the IAM user.

## Move done on 2026-11-23

- **Checks.** Before the move, the old server's answers were recorded for all 90 hartrailroad.com sitemap pages, the other sites' main pages and every published WordPress post and page. After the restore and again after the switch, the new server gave the same status codes and redirects. All 90 hartrailroad.com pages and its file list (1,352 files) were byte-identical, with the same security headers and `no-cache`. On the WordPress sites, 18 of 22 pages were byte-identical; the other four differ only in a random "related products" box.
- **Accounts.** `lnevo`, `dnevo` and `br2fi` were restored from fresh Vesta backups with `v-restore-user`. Vesta's `admin` account could not be restored, because Ubuntu 24.04 has a system group `admin`. Its one site, dashboard.easte.net, was rebuilt by hand under `lnevo`, with its database renamed to `lnevo_wp90`.
- **Templates.** `static-revalidate` was rebuilt for HestiaCP, including the hand edit of 2026-11-09 that serves the site's own `404.html`. `force-https` is a copy of HestiaCP's default, and HTTPS is forced with HestiaCP's own setting.
- **PHP.** The WordPress sites run on PHP 8.5. easte.net runs on PHP 7.4 for its old aquarium pages. WPBakery on debbies.kitchen logs a deprecation warning on 8.5.
- **easte.net pages.** These fetch `www.easte.net` from the server itself, so `/etc/hosts` maps that name to the private address 172.26.2.161, where nginx listens (backup `/etc/hosts.bak-20261123`).
- **Cron and pequott.** The six aquarium and MRTG jobs are in HestiaCP but suspended. pequott.easte.net is suspended.
- **SSH and deploy.** The old server's SSH host keys were copied over, so neither logins nor the hartrailroad.com deploy see a new host. rrsync is linked at `/usr/local/bin/rrsync` for the deploy key, and a dry run with the deploy key passed.
- **Switch.** The static IP was moved, HestiaCP's NAT address set to it, and Let's Encrypt certificates reissued for the five HTTPS sites. They are valid to 2027-02-21 and HestiaCP renews them.
- **Lightsail.** Daily automatic snapshots are on for `www-2026`. The old instance's final snapshot is `Ubuntu-1-final-2026-11-23`.

## Left

- Delete the snapshot `Ubuntu-1-final-2026-11-23` once nothing more is needed from the old server (about $1 a month while kept).
- The panel at `https://www.easte.net:8083` uses HestiaCP's own certificate: HestiaCP issues a hostname certificate only when `www.easte.net` is its own web domain, and here it is an alias of easte.net.
- easte.net without `www` points in DNS to another host (66.96.149.32), as it did before the move.
- debbies.kitchen cannot send email (no mail server, no SMTP plugin), as before the move.
- Optional: an AWS Budget alarm (needs billing rights the `lnevo-agent` user does not have).

## Open questions (2026-11-19, answered by the survey)

- The five questions at the end of the [survey](../../docs/website/old-server-survey.md): the aquarium jobs, pequott.easte.net, MainWP, a server without mail, and the other users' checks.
