# Moving the database from Supabase to Aiven (free plan)

Why: the Supabase free tier allows about 5 GB of egress a month and the project went over it.
Aiven's free PostgreSQL has no such cap that we have found, but it only allows **15 connections
(3 reserved)**, so the app talks to it through a local PgBouncer.

Rehearsed on 2026-10-06: a restore of the `public` schema matched Supabase on all 29 tables
and 57 indexes. Heavy queries ran about twice as fast on Aiven when run one at a time.

## One-time Aiven setup (already done for the test copy)

The service must be PostgreSQL 17 or newer. As `avnadmin`:

```sql
ALTER ROLE avnadmin SET timezone = 'Europe/Skopje';
ALTER ROLE avnadmin SET statement_timeout = 120000;
ALTER ROLE avnadmin SET idle_in_transaction_session_timeout = 60000;
```

These replace the `DB_SESSION_OPTIONS` connection options (`core/database.py`), which PgBouncer
does not pass through.

## Run PgBouncer on the host that runs the API (the Shield)

```bash
apt install pgbouncer
cp deploy/pgbouncer.ini.example /etc/pgbouncer/pgbouncer.ini   # fill in host, port, password
printf '"avnadmin" ""\n' > /etc/pgbouncer/userlist.txt         # trust auth, 127.0.0.1 only
chmod 600 /etc/pgbouncer/pgbouncer.ini
# PgBouncer refuses to run as root, even with -u root. Use an unprivileged user:
mkdir -p /var/log/pgbouncer /var/run/pgbouncer
chown -R postgres:postgres /var/log/pgbouncer /var/run/pgbouncer /etc/pgbouncer
runuser -u postgres -- pgbouncer -d /etc/pgbouncer/pgbouncer.ini
```

The example config already points `auth_file` at that file. Check:
`psql "postgresql://avnadmin@127.0.0.1:6543/presek" -c "select 1"`.

Start PgBouncer from the watchdog so it comes back after a reboot.

## Cutover (about 5 minutes of downtime)

1. **Stop the writers** on every host: Celery workers and beat, and the API (or at least ingestion).
   Check nothing is writing: `select count(*) from pg_stat_activity where state = 'active'`.
2. **Final copy** from any host with both URLs in its `.env`:
   `bash deploy/migrate_to_aiven.sh --yes`. It replaces Aiven's `public` schema, restores,
   and compares row counts. Do not continue unless it prints `OK`.
3. **Switch the app.** In `/root/presek/.env` on the Shield:
   - keep `DATABASE_URL` for Supabase as `SOURCE_DATABASE_URL` (the fallback),
   - set `DATABASE_URL=postgresql://avnadmin@127.0.0.1:6543/presek?sslmode=disable`,
   - set `BACKUP_DATABASE_URL` to the direct Aiven URL (`pg_dump` cannot run through the pooler).
   Port 6543 makes `core/database.py` turn off server-side prepared statements.
4. **Start** the API, Celery and the web server through the watchdog. Check `/api/health`, the
   homepage, a story page, and the logs for `couldn't get a connection`.
5. **Rollback** if anything is wrong: put the Supabase `DATABASE_URL` back and restart. Supabase
   is untouched, but it has missed any writes since step 2, so roll back before new data lands.

## After the cutover

- Rotate the Aiven password (it was shared in chat) and update both `.env` and `pgbouncer.ini`.
- Keep Supabase for a week as a fallback, then pause or delete the project.
- `free_tier_guard.sh` and its `DATABASE_URL/6543 -> 5432` rewrite are Supabase-specific; its size
  check still works through the pooler. Backups use `BACKUP_DATABASE_URL`.

## Known unknowns

- Aiven's free plan may power the service off after inactivity. The site makes constant requests,
  so this should not trigger.
- I found no egress figure for Aiven's free plan.
- A cold `/api/home` took 35 to 55 seconds in a CPU-starved test on the phone, with and without
  PgBouncer and on Supabase too, while the same queries took 40 to 250 ms standalone. Production has
  Redis and a fast host; verify the real homepage after the cutover.
