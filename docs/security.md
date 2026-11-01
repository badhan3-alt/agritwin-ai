# Secrets and private farm data

AgriTwin currently uses Django, server-rendered templates, and SQLite. It has no
Supabase client, Supabase project connection, browser database API, or Supabase
service-role key. There are therefore no Supabase Row Level Security policies
to enable in this checkout. SQLite does not provide Postgres RLS. The present
data boundary is Django's server-side ownership checks; database-level RLS is
an additional protection that would need a real Postgres deployment.

## Server-owned credentials

Create the local server environment before starting Django:

```powershell
.venv\Scripts\python.exe scripts\setup_env.py
.venv\Scripts\python.exe manage.py migrate
```

The setup script generates a private `DJANGO_SECRET_KEY` when missing or still
a placeholder, preserves an existing strong key and unrelated settings, and
does not print its value. Django rejects missing, placeholder, or weak signing
keys instead of sharing a source-code fallback. Keep `.env` out of version
control and outside the public web root. Use the hosting platform's server-side
secret storage for deployment.

Debug mode defaults to off. Local setup explicitly adds `DJANGO_DEBUG=True`
when no debug choice exists; it preserves an existing choice. Use
`DJANGO_DEBUG=False` for a hosted server. Production also enables secure
cookies, HTTPS redirects, and a one-hour HSTS policy, and refuses wildcard
allowed hosts. HSTS subdomains and preloading are left off because ownership
and HTTPS support of every subdomain must be verified before enabling them.

Never put signing keys, database credentials, Supabase secret/service-role keys,
or admin tokens in templates, `static/`, client JavaScript, source maps, public
JSON endpoints, or browser storage. Names beginning with `VITE_`, `NEXT_PUBLIC_`,
`PUBLIC_`, `REACT_APP_`, `NUXT_PUBLIC_`, or `EXPO_PUBLIC_` are intended for public
client configuration. Startup checks reject privileged credentials assigned to
these prefixes, including recognizable Supabase secret keys and legacy
service-role JWTs. This guard supplements review; arbitrary credentials cannot
be identified reliably from their spelling alone.

Django's signing key must remain private and production debugging must be off.
With debugging enabled, exception pages can disclose source, local variables,
and settings. Follow the [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).

## Ownership and authentication

Account farms are selected using the authenticated user's identity on the
server. A farm ID supplied in a URL, form, or query string does not confer
access. The ownership check runs before farm reads or mutations, analysis,
weather requests, photo delivery, and report downloads. Related calendar,
ledger, diary, soil, and boundary records are scoped to that authorized farm.
Creation assigns the owner on the server rather than trusting an owner ID
submitted by the browser.

Guest farms continue to use a private Django session. They are accessible only
to that session until registration or login claims its unowned farms. Existing
account-owned farms cannot be claimed through a reused session identifier.
Cross-device access to account farms requires signing into the same account.
Staff administration uses Django's separate staff and model permissions.

Mutations use POST and Django CSRF protection. Private and authenticated
responses use cache controls so shared intermediaries do not cache them.
Downloaded reports contain private information and should be shared deliberately.

These are application-level controls. A server database credential or process
with direct access to the SQLite file can read the stored rows. Protect the
host, backups, and database file with filesystem and hosting access controls.

## Public files and deployment

Serve only collected public assets from `STATIC_ROOT`. Never point a static
server at the repository root, `.env`, the SQLite database, `templates/`,
`frontend/`, or application source directories. The ignored `frontend/dist`
directory is a legacy build and is not part of the current Django application.

Diary uploads live under the separate `MEDIA_ROOT`. They are delivered by an
ownership-checked Django endpoint. Do not add an unrestricted `/media/` alias
or upload that directory to a public bucket. An unguessable filename alone is
not an authorization check.

Before deployment, configure a strong private key, `DJANGO_DEBUG=False`, exact
allowed hosts and trusted origins, HTTPS, and a production WSGI/ASGI server.
Run `python manage.py check --deploy` against that production configuration.
The development server is for local development.

## If a privileged key was previously published

Removing a key from a bundle cannot revoke copies that have already reached a
browser, CDN, repository, log, or source map. Revoke or rotate it at its provider,
update only server-side secret storage, rebuild affected assets, and invalidate
cached deployments. Review access logs and affected data. The local code audit
does not rotate external credentials and does not establish what an earlier
deployment exposed.

Supabase secret keys and legacy `service_role` keys bypass its RLS and belong
only in trusted server code that performs its own authorization. A browser
integration would use a publishable key plus authenticated user tokens,
restricted grants, and tested RLS policies for every exposed table. See
[Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys) and
[Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security).

## Verification

```powershell
python manage.py test tests.test_security_config tests.test_secret_exposure tests.test_security_access tests.test_security_cache tests.test_accounts
```

Exposure tests inject test-only backend secrets and verify actual rendered
pages, JSON responses, browser assets, and production error responses. They
also check that environment files, source, database files, and private media
are not publicly routed and that static-file traversal is rejected. Separate
ownership tests check user/session boundaries and mutations. These checks are
regressions for the current architecture, not a claim of an external security
audit or database RLS enforcement.
