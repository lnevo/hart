# Old web server survey (2026-11-23)

A read-only survey of www.easte.net before the move to a new Lightsail server, with what to move, what to drop and the questions for the owner.

Plan and decisions: [`wiki/projects/web-server-migration.md`](../../wiki/projects/web-server-migration.md). The survey changed nothing on the server or in AWS. Account names, database names, addresses and the port list are kept off this page because the repo is public.

## The instance

- Lightsail `nano_2_0` (512 MB RAM, 20 GB disk) in us-east-1a, created 2020-12-21. 11 GB of the disk is used.
- One static IP, attached to this instance. Moving it to the new instance moves every site without a DNS change.
- Automatic daily snapshots are on (seven kept). Two manual snapshots from December 2020 are still stored.
- The Lightsail firewall opens more ports than anything listens on: five of the open ports have no service behind them. The new instance opens only 22, 80 and 443, plus the panel port.

## Sites

Seven web domains in four panel accounts. Sizes are the docroot.

| Site | Kind | Size | Requests, last 7 days | Moves? |
|------|------|------|----------------------|--------|
| hartrailroad.com | Static, `static-revalidate` template, rsync-only deploy key | 112 MB | 29,000 | Yes |
| easte.net | Static files plus the aquarium data pages (`radb`, `radb_data`, `mrtg`) | 80 MB | 495,000, nearly all from the server itself (see cron) | Owner decides |
| familytree.easte.net | Static family tree | 44 MB | 9,700 | Yes |
| pequott.easte.net | Static files (CSV, Word, HTML exports) | 3 MB | 1 | Owner decides |
| dashboard.easte.net | WordPress with MainWP, which manages the other WordPress sites | 105 MB | 4,000 | Yes, if MainWP is still used |
| debbies.kitchen | WordPress with WooCommerce, another user's site | 371 MB, database 10 MB | 65,500 | Yes, the user checks it |
| bankrupt2fi.com | WordPress, another user's site | 139 MB | 104,000 | Yes, the user checks it |

All three WordPress sites run 6.9.12. Let's Encrypt covers every site except easte.net and pequott.easte.net, which are plain HTTP.

### PHP 8.3 risks

The new server runs PHP 8.3; the old one runs 7.2. HestiaCP can run an older PHP per site, so a plugin that fails on 8.3 does not block the move.

- **debbies.kitchen** is the one to test hardest. It runs a commercial ThemeForest theme (`bakery` with a child theme), WPBakery (`js_composer`) and Slider Revolution (`revslider`). These update outside WordPress.org, so their versions need checking. It also runs WooCommerce with currency switcher, Square and ShipStation (`woocommerce-stampscomendicia`) add-ons, and `wp-migrate-db`.
- **bankrupt2fi.com** has three old third-party themes (`diagnoseo`, `lolipop`, `nucleare`) and two hand-written PHP pages in the docroot (`calc.php`, `calc2.php`).
- **dashboard.easte.net** has only MainWP and stock themes.

## Mail

The mail stack (Exim, Dovecot, SpamAssassin, Roundcube) runs but no account has a mail domain and the Exim logs show no message sent or received. The new server can be installed without mail, which also removes the port 25 question from the plan.

One thing follows from this: WordPress mail does not leave the server today. debbies.kitchen has no SMTP plugin, so any WooCommerce order or password-reset email from that site is not delivered now. That is the same after the move unless the site gets an SMTP plugin.

## Cron jobs

The panel's own jobs (backups, Let's Encrypt renewal, stats) come back with HestiaCP. The six jobs in the owner's account all belong to the aquarium controller pages on easte.net:

| Job | Runs | What it does | State |
|-----|------|--------------|-------|
| `update_ra.sh` | Every minute | Fetches the controller status from a home address on port 2000, writes `radb_data/` | Fails: the connection times out. The status file is from 2023-02-02 |
| `update_alk.sh` | Every 5 minutes | Reads the alkalinity tester at the same home address, writes `radb/alk.html` | Fails since 2023-02-02 |
| `push_alk.sh` | Hourly | Logs an alkalinity dose from the last tester reading | Has nothing new to read since 2023 |
| `send_alk.sh` | Daily | Posts the last reading to AquaticLog | AquaticLog answers with an error page |
| `send_ml.sh` | Daily | Posts the dosing volume to AquaticLog | AquaticLog answers with an error page |
| `mrtg.sh` | Every 5 minutes | Draws MRTG graphs into `easte.net/mrtg` | Runs; what it graphs is not checked |

The 495,000 weekly requests on easte.net are these jobs calling the server's own PHP pages once a minute.

## Also on the server, not moving

- Grafana 9.2.3: installed, disabled.
- Docker: installed, no containers.
- Softaculous, ProFTPD (no FTP accounts in use) and phpPgAdmin config.
- The Vesta backups in `/backup` (one tar a day per account). The move uses fresh ones.

## Questions for the owner

1. Drop the aquarium jobs and the `radb`, `radb_data` and `mrtg` pages, or keep them on the new server?
2. Keep pequott.easte.net (one request a week)?
3. Is MainWP on dashboard.easte.net still used to manage the other WordPress sites?
4. Install the new server without mail? WordPress mail is not delivered today either.
5. Ask the owners of debbies.kitchen and bankrupt2fi.com to check their sites on the new server before the switch, as the plan says. Is the debbies.kitchen shop still taking orders?
