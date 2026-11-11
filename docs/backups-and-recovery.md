# GovMap backups and recovery

Production is backed up once a day by
[`scripts/backup-coolify-daily.sh`](../scripts/backup-coolify-daily.sh), run by a
systemd timer on the Coolify server. Duplicati copies the result off-site.
This page covers how it works, how to check it, and how to recover.

**Verified on 2026-11-10.** The dev and production bundles each passed their
checksums and restored into scratch databases. The restored copies matched
the source exactly: production showed revision `0013`, 539 members, 19,512
bills, 289 votes and 46,012 ZIP rows. The nightly timer was then enabled, and
Duplicati copied the bundle to both off-site destinations.

## How it works

1. **02:30 server time** (up to 10 minutes of random delay), the
   `govmap-daily-backup.timer` runs the backup service as root.
2. The script finds exactly one running `postgres-` and one `backend-`
   container for the configured Coolify resource ID. It stops if it finds
   none or more than one.
3. It builds a new bundle in a private scratch folder:
   - `database.dump`: a consistent custom-format `pg_dump` of database
     `govmap`, checked with `pg_restore --list`
   - `logs.tar`: the backend's `/app/logs` (application and bug-report logs)
   - `coolify-config/`: the Coolify deployment folder, including `.env`
     **secrets** and `docker-compose.yaml`
   - `MANIFEST.txt`: time, containers, Postgres image, Alembic revision
   - `SHA256SUMS` and `RESTORE.txt`
4. Only after every step succeeds does it replace yesterday's
   `/srv/govmap-backup/govmap-backup.tar.gz`. Any failure keeps yesterday's file
   and marks the systemd service failed.
5. If `GOVMAP_HEARTBEAT_URL` is set, it pings that URL. A monitor alerts when
   the ping does not arrive, covering both failed runs and a stopped timer.
6. **Later each night** Duplicati backs up `/srv/govmap-backup` to its two
   off-site destinations, encrypting the copies and keeping version history.

Only one bundle is kept on the server; history lives in Duplicati.

The bundle is **not encrypted** on the server. It is protected by being
root-only: the folder is `root:root 700` and the file is `600`. The script
refuses to write to a folder that the group or others can access. The
Duplicati job **must** have encryption enabled, and its passphrase must be
stored separately (in the vault).

Not covered: the operating system, Coolify itself, Duplicati's own
configuration, the Cloudflare dashboard configuration (tunnel routes, Access
policies), and PostgreSQL cluster-wide roles. The bundle does not record the
deployed git commit; take that from Coolify's deployment history. Never back
up or restore the live `postgres-data` volume as files; it is not a
consistent copy.

## Server setup

Install from a reviewed checkout of a CI-green commit. Run as root:

```bash
install -m 755 -o root -g root scripts/backup-coolify-daily.sh /usr/local/sbin/govmap-daily-backup
install -m 644 -o root -g root scripts/systemd/govmap-daily-backup.service scripts/systemd/govmap-daily-backup.timer /etc/systemd/system/
install -d -m 700 -o root -g root /srv/govmap-backup /etc/govmap-backup
```

`/etc/govmap-backup/daily.env` (root, mode `600`):

```text
GOVMAP_RESOURCE_ID=<production Coolify resource ID>
GOVMAP_BACKUP_DIR=/srv/govmap-backup
GOVMAP_CONFIG_DIR=/data/coolify/applications/<production Coolify resource ID>
GOVMAP_HEARTBEAT_URL=<https ping URL from the monitor>
```

`GOVMAP_CONFIG_DIR` and `GOVMAP_HEARTBEAT_URL` are optional. The heartbeat URL
contains a token: keep it only in this file. The script passes it to `curl` on
stdin so it never appears in the process list, and it refuses non-`https`
URLs. Then:

```bash
systemctl daemon-reload
systemctl start govmap-daily-backup.service      # one supervised run first
systemctl enable --now govmap-daily-backup.timer
```

To update the script later, reinstall it from a newer CI-green checkout the
same way, then run the service once.

### Heartbeat monitor

Use a dead-man's-switch check, such as a Healthchecks.io check or an Uptime
Kuma **Push** monitor. Set the expected period to 1 day and the grace period to
a few hours. Put its ping URL in `daily.env`, run the service once, and confirm
the monitor turns green. Also confirm that its alerts reach you, for example
with the monitor's test notification.

## Day-to-day checks

```bash
systemctl list-timers govmap-daily-backup.timer --no-pager
systemctl status govmap-daily-backup.service --no-pager
journalctl -u govmap-daily-backup.service --since -2d --no-pager
sudo tar -xzOf /srv/govmap-backup/govmap-backup.tar.gz govmap-backup/MANIFEST.txt
```

## Verifying a bundle (monthly, and after changes)

This restores into a **scratch database in the dev Postgres container** and
only reads from production. Replace the container names with the current
ones from `docker ps`.

```bash
# 1. Checksums
sudo bash -c 'set -euo pipefail; w=$(mktemp -d /srv/govmap-backup/verify-XXXXXX); trap "rm -rf -- \"$w\"" EXIT; tar -xzf /srv/govmap-backup/govmap-backup.tar.gz -C "$w"; cd "$w/govmap-backup"; sha256sum --quiet -c SHA256SUMS && echo CHECKSUMS_OK'
# 2. Restore into a new scratch database (createdb fails if it already exists)
sudo bash -c 'set -euo pipefail; c=DEV_POSTGRES_CONTAINER; docker exec "$c" createdb -U govmap govmap_restore_check; tar -xzOf /srv/govmap-backup/govmap-backup.tar.gz govmap-backup/database.dump | docker exec -i "$c" pg_restore -U govmap --no-owner --no-privileges --exit-on-error -d govmap_restore_check; echo RESTORE_OK'
# 3. Compare with production (revision, members, bills, votes, ZIP rows)
q="SELECT (SELECT version_num FROM alembic_version), (SELECT count(*) FROM members), (SELECT count(*) FROM bills), (SELECT count(*) FROM votes), (SELECT count(*) FROM zip_districts)"
sudo docker exec PROD_POSTGRES_CONTAINER psql -U govmap -d govmap -At -c "$q"
sudo docker exec DEV_POSTGRES_CONTAINER psql -U govmap -d govmap_restore_check -At -c "$q"
# 4. Remove the scratch database
sudo docker exec DEV_POSTGRES_CONTAINER dropdb -U govmap govmap_restore_check
```

Production refreshes run continuously, so bills and votes may be slightly
higher on live production than in the bundle. A different revision or a large
gap means something is wrong.

At least once, restore a bundle **from a Duplicati copy** rather than the local
file, and run step 1 on it. This proves the off-site copies are usable.

## Recovering production on a new server

The database restore is the only step that has been rehearsed. Treat the rest
of this as a checklist and record what happens.

1. Restore `govmap-backup.tar.gz` from Duplicati into a private, root-only
   folder on the new server. Unpack it and run `sha256sum -c SHA256SUMS`.
2. Install Coolify and create the GovMap resource from this repository, at
   the commit last deployed (from Coolify's deployment history), using
   `docker-compose.coolify.yml`. Copy the environment variables from
   `coolify-config/.env`. **If the old production could still be running,**
   leave `CLOUDFLARE_TUNNEL_TOKEN` pointed at a separate test tunnel and set
   `SCHEDULER_ENABLED=false` until the cutover.
3. Deploy. The backend creates an empty schema on first start, so stop the
   backend before restoring. Then, in the new Postgres container, drop and
   recreate database `govmap`. Restore with
   `pg_restore -U govmap --no-owner --no-privileges --exit-on-error --single-transaction -d govmap`
   from `database.dump`.
4. Start the backend. Compare the Alembic revision and the counts in
   `MANIFEST.txt` and step 3 above with what you expect. Test the site.
5. If needed, extract `logs.tar` into the new backend's `/app/logs`.
6. Switch the tunnel token and scheduler to production values, then redeploy.
   Then install the backup timer on the new server.

## Other backups that still exist

- **One age-encrypted production dump**,
  `/home/cradmin/govmap-backups/production/govmap-ojfuvwkiigcbdxrhdgtjzvdy-20261110T020733Z-*.dump.age`,
  was created with
  [`scripts/backup-coolify-database.sh`](../scripts/backup-coolify-database.sh).
  It decrypts only with the production age identity in the vault. That
  identity is itself passphrase-protected. The command is
  `age --decrypt --identity govmap-prod-identity.age FILE | pg_restore ...`.
  The utility remains available for an ad-hoc encrypted export.
- **The 2026-11-09 old-VM migration backups** (`old-vm-final.dump.age`,
  `govmap-prod-20261109T130147Z.dump.age` and their log archives) are
  passphrase-encrypted. Decrypt them with `age --decrypt` and that passphrase
  only. Do **not** use `--identity`.

The old VM's Compose backup and restore scripts were removed on 2026-11-10,
along with this page's procedures for them. Both are in git history before
that commit.
