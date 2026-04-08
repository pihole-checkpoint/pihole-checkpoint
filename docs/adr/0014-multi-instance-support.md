# ADR-0014: Multi-Instance Pi-hole Support

**Status:** Proposed
**Date:** 2026-04-07

---

## Context

Pi-hole Checkpoint currently backs up a single Pi-hole v6 instance. While the data model was designed with multi-instance in mind (ADR-0001, Section 5), the UI and credential system are hardcoded to single-instance:

- `PiholeConfig` has a `name` field and `BackupRecord` has a foreign key to it
- The scheduler creates per-config jobs via `run_backup_job_for_config(config_id)` (ADR-0013, Issue 1)
- `RetentionService.enforce_all()` iterates all active configs
- `BackupService`, `RestoreService` accept a `config` parameter

**But these layers are single-instance:**

- **Credentials**: `CredentialService` reads from single env vars `PIHOLE_URL`/`PIHOLE_PASSWORD`/`PIHOLE_VERIFY_SSL`
- **Views**: `dashboard()`, `settings_view()`, `create_backup()` all use `PiholeConfig.objects.first()`
- **Templates**: Dashboard shows one config, settings edits one config, no instance navigation
- **URLs**: No config selector in URL patterns

ADR-0013, Issue 7 documents this as a known limitation. Users running primary + secondary Pi-hole instances (a common HA setup) must deploy separate Checkpoint containers.

### Reference Implementation

The `nodered-backup` project in this repo family solves the same problem using an **environment variable prefix pattern**: each instance stores an `env_prefix` in the DB, and credentials are read from `FLOWHISTORY_{PREFIX}_USER`/`FLOWHISTORY_{PREFIX}_PASS` at runtime. Credentials never touch the database.

---

## Decision

**Add full multi-instance support using the environment variable prefix pattern for credentials, instance-scoped URL routing, and a card-based instance overview UI.**

---

## Options Considered

### Credential Storage

| Option | Pros | Cons |
|--------|------|------|
| **1. Env prefix pattern** | No DB encryption needed, Docker-friendly, proven pattern | Requires container restart to add credentials |
| 2. Encrypted DB fields (Fernet) | UI-only config, no restart | Adds `cryptography` dependency, partially reverts ADR-0010 |
| 3. Django Signer obfuscation | No new dependency, UI-only config | Not real encryption, passwords recoverable |
| 4. Plaintext DB fields | Simplest | Passwords visible in SQLite file |

**Recommendation: Option 1** — Matches the established pattern from nodered-backup, keeps credentials out of the database entirely (aligned with ADR-0010's philosophy), and avoids any encryption dependency.

### URL Structure

| Option | Pros | Cons |
|--------|------|------|
| **1. `/instances/<id>/` prefix** | RESTful, bookmarkable, clean | More URL patterns to maintain |
| 2. Query param `?config=<id>` | Simple | Not RESTful, messy with POST |
| 3. Session-based active instance | Fewer URL changes | Breaks multi-tab, confusing state |

**Recommendation: Option 1** — Clean REST semantics, works naturally with Django's URL routing.

### UI Approach

| Option | Pros | Cons |
|--------|------|------|
| **1. Instance card grid + detail pages** | Clear overview, scales to N instances | Two template layers |
| 2. Navbar dropdown switcher | Compact | Hides instance overview, doesn't scale |
| 3. Tabs on single page | Everything visible | Long page, doesn't scale |

**Recommendation: Option 1** — Provides both an at-a-glance overview and detailed per-instance views.

---

## Implementation Plan

### Phase 1: Model Layer

**File:** `backup/models.py`

Add fields and a credential method to `PiholeConfig`:

```python
class PiholeConfig(models.Model):
    # ... existing fields ...

    # Multi-instance credential support
    env_prefix = models.CharField(
        max_length=50, blank=True, default="",
        help_text="Environment variable prefix (e.g., PRIMARY reads PIHOLE_PRIMARY_URL)"
    )
    pihole_url = models.URLField(
        blank=True, default="",
        help_text="Pi-hole URL (read from env if prefix is set)"
    )
    verify_ssl = models.BooleanField(
        default=False,
        help_text="Enable SSL certificate verification"
    )

    def get_pihole_credentials(self):
        """Read Pi-hole credentials from environment variables using configured prefix.

        Env var pattern: PIHOLE_{PREFIX}_URL, PIHOLE_{PREFIX}_PASSWORD, PIHOLE_{PREFIX}_VERIFY_SSL
        Legacy fallback: PIHOLE_URL, PIHOLE_PASSWORD, PIHOLE_VERIFY_SSL (deprecated)
        """
        if self.env_prefix:
            prefix = self.env_prefix.upper()
            url = os.environ.get(f"PIHOLE_{prefix}_URL", "")
            password = os.environ.get(f"PIHOLE_{prefix}_PASSWORD", "")
            verify_ssl = os.environ.get(f"PIHOLE_{prefix}_VERIFY_SSL", "false").lower() == "true"
        else:
            # Legacy single-instance fallback (deprecated)
            url = getattr(settings, "PIHOLE_URL", "") or ""
            password = getattr(settings, "PIHOLE_PASSWORD", "") or ""
            verify_ssl = getattr(settings, "PIHOLE_VERIFY_SSL", False)
        return {
            "url": url,
            "password": password,
            "verify_ssl": verify_ssl,
        }

    def is_credentials_configured(self):
        """Check if Pi-hole credentials are available in the environment."""
        creds = self.get_pihole_credentials()
        return bool(creds["url"] and creds["password"])
```

**Migration:** `0003_add_multi_instance_fields.py`
- Add `env_prefix`, `pihole_url`, `verify_ssl` fields
- Data migration: if existing `PiholeConfig` rows have no `env_prefix`, set it to `"PRIMARY"` for the first active config (so existing `PIHOLE_URL` env var users can rename to `PIHOLE_PRIMARY_URL`)

### Phase 2: Credential Service Refactor

**File:** `backup/services/credential_service.py`

Refactor to delegate to the config's credential method:

```python
class CredentialService:
    @staticmethod
    def get_credentials(config: PiholeConfig) -> dict:
        """Get Pi-hole credentials for a specific config instance."""
        creds = config.get_pihole_credentials()
        if not creds["url"]:
            raise ValueError(
                f"PIHOLE_{config.env_prefix.upper()}_URL environment variable is required"
                if config.env_prefix
                else "PIHOLE_URL environment variable is required (deprecated: use env_prefix)"
            )
        if not creds["password"]:
            raise ValueError(
                f"PIHOLE_{config.env_prefix.upper()}_PASSWORD environment variable is required"
                if config.env_prefix
                else "PIHOLE_PASSWORD environment variable is required (deprecated: use env_prefix)"
            )
        return creds

    @staticmethod
    def is_configured(config: PiholeConfig) -> bool:
        """Check if Pi-hole credentials are configured for this instance."""
        return config.is_credentials_configured()

    @staticmethod
    def get_status(config: PiholeConfig) -> dict:
        """Get configuration status for display in UI."""
        creds = config.get_pihole_credentials()
        return {
            "url": creds["url"] or None,
            "has_password": bool(creds["password"]),
            "verify_ssl": creds["verify_ssl"],
            "env_prefix": config.env_prefix,
        }
```

### Phase 3: Service Layer Updates

**Files:** `backup/services/backup_service.py`, `backup/services/restore_service.py`

Both services already accept `config: PiholeConfig` in their constructors. Update the internal `_get_client()` calls from:
```python
creds = CredentialService.get_credentials()
```
to:
```python
creds = CredentialService.get_credentials(self.config)
```

No structural changes needed — just pass `self.config` through.

### Phase 4: URL Routing

**File:** `backup/urls.py`

```python
urlpatterns = [
    # Overview / instance list
    path("", views.dashboard, name="dashboard"),

    # Instance management
    path("instances/add/", views.add_instance, name="add_instance"),
    path("instances/<int:config_id>/", views.instance_dashboard, name="instance_dashboard"),
    path("instances/<int:config_id>/settings/", views.instance_settings, name="instance_settings"),
    path("instances/<int:config_id>/delete/", views.delete_instance, name="delete_instance"),

    # Per-instance API endpoints
    path("instances/<int:config_id>/backup/", views.create_backup, name="create_backup"),
    path("instances/<int:config_id>/test-connection/", views.test_connection, name="test_connection"),

    # Backup-level operations (unchanged — resolve config via backup.config FK)
    path("backup/<int:backup_id>/delete/", views.delete_backup, name="delete_backup"),
    path("backup/<int:backup_id>/download/", views.download_backup, name="download_backup"),
    path("api/restore/<int:backup_id>/", views.restore_backup, name="restore_backup"),

    # Legacy redirects
    path("settings/", views.settings_redirect, name="settings"),

    # Auth (unchanged)
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("health/", views.health_check, name="health_check"),
]
```

### Phase 5: View Layer

**File:** `backup/views.py`

**Refactored `dashboard()`** — smart routing based on config count:
```python
def dashboard(request):
    configs = PiholeConfig.objects.all()
    if configs.count() == 1:
        # Single-instance: show full dashboard directly (backward compat)
        config = configs.first()
        backups = BackupRecord.objects.filter(config=config)
        return render(request, "backup/instance_dashboard.html", {
            "config": config, "backups": backups, "single_instance": True,
        })
    # Multi-instance: show overview grid
    return render(request, "backup/instance_list.html", {"configs": configs})
```

**New `instance_dashboard(config_id)`:**
```python
def instance_dashboard(request, config_id):
    config = get_object_or_404(PiholeConfig, id=config_id)
    backups = BackupRecord.objects.filter(config=config)
    return render(request, "backup/instance_dashboard.html", {
        "config": config, "backups": backups, "single_instance": False,
    })
```

**New `instance_settings(config_id)`:**
```python
def instance_settings(request, config_id):
    config = get_object_or_404(PiholeConfig, id=config_id)
    # Form handling with PiholeConfigForm(instance=config)
    # ...
```

**New `add_instance()`** — renders blank form, creates new config on POST.

**New `delete_instance(config_id)`** — POST-only, deletes config + all backup records/files. Confirmation required.

**Refactored `create_backup(config_id)`** — use `get_object_or_404` instead of `.first()`.

**Refactored `test_connection(config_id)`** — load config by ID, call `CredentialService.get_credentials(config)`.

**`settings_redirect()`** — redirects `/settings/` to first config's settings page or add-instance page.

### Phase 6: Templates

**New `backup/templates/backup/instance_list.html`:**
- Card grid layout, one card per `PiholeConfig`
- Each card shows: name, Pi-hole URL (from env), last backup timestamp, schedule, status badge
- Quick actions: "Backup Now" button, "View" link, "Settings" link
- "Add Instance" button

**New/refactored `backup/templates/backup/instance_dashboard.html`:**
- Extracted from current `dashboard.html`
- Scoped to one config
- "Back to Overview" link when `single_instance` is False
- AJAX URLs point to `/instances/<id>/...`

**Modified `backup/templates/backup/settings.html`:**
- Add `env_prefix` field (with help text explaining the env var pattern)
- Show resolved env var status (URL detected, password detected)
- Per-instance scoping via `/instances/<id>/settings/`
- "Delete Instance" danger zone at bottom

**Modified `backup/templates/backup/base.html`:**
- Add breadcrumb navigation below navbar when on instance pages
- "Dashboard > Instance Name > Settings" pattern

### Phase 7: Form Updates

**File:** `backup/forms.py`

Add `env_prefix`, `pihole_url`, `verify_ssl` to `PiholeConfigForm.Meta.fields`. The `pihole_url` field serves as a display/reference field — the actual URL used at runtime comes from the environment variable.

### Phase 8: Testing

**Test scenarios:**

| Scenario | Expected |
|----------|----------|
| Single config exists | Root `/` shows full dashboard (backward compat) |
| Zero configs exist | Root `/` shows empty state with "Add Instance" |
| 2+ configs exist | Root `/` shows instance card grid |
| Env prefix `PRIMARY` set | Reads `PIHOLE_PRIMARY_URL`, `PIHOLE_PRIMARY_PASSWORD` |
| No prefix (legacy) | Falls back to `PIHOLE_URL`, `PIHOLE_PASSWORD` with deprecation |
| Per-instance backup | Creates backup using that config's env credentials |
| Per-instance test connection | Tests with that config's env credentials |
| Delete instance | Removes config + all backup records + backup files |
| Instance with missing env vars | Shows clear error about which env var is missing |

**Files to update:**
- `backup/tests/conftest.py` — multi-config fixtures with `env_prefix`
- `backup/tests/unit/test_credential_service.py` — test prefix-based credential resolution
- `backup/tests/views/test_dashboard.py` — test single vs multi-config routing
- `backup/tests/views/test_instance_management.py` — new: add/delete instance flows

---

## Files to Modify

| File | Changes |
|------|---------|
| `backup/models.py` | Add `env_prefix`, `pihole_url`, `verify_ssl` fields + `get_pihole_credentials()` method |
| `backup/migrations/0003_*.py` | **New** — add fields, data migration for existing configs |
| `backup/services/credential_service.py` | Refactor to accept `config` parameter, delegate to model method |
| `backup/services/backup_service.py` | Pass `self.config` to `CredentialService.get_credentials()` |
| `backup/services/restore_service.py` | Pass `self.config` to `CredentialService.get_credentials()` |
| `backup/views.py` | Add instance CRUD views, refactor existing views for config_id |
| `backup/urls.py` | Add instance-prefixed URL patterns |
| `backup/forms.py` | Add credential-related fields to form |
| `backup/templates/backup/instance_list.html` | **New** — instance card grid overview |
| `backup/templates/backup/instance_dashboard.html` | **New** — per-instance dashboard (extracted from dashboard.html) |
| `backup/templates/backup/settings.html` | Add env_prefix field, per-instance scoping |
| `backup/templates/backup/base.html` | Add breadcrumb navigation |
| `.env.example` | Update with prefix pattern, deprecation note for old vars |
| `docs/adr/0000-index.md` | Add ADR-0014 entry |

---

## Migration Path for Existing Users

1. User pulls new Docker image, runs `docker compose up`
2. Migration `0003` runs automatically:
   - Existing `PiholeConfig` gets `env_prefix = "PRIMARY"`
   - All existing backup records stay linked (FK unchanged)
3. User updates `.env` file to rename env vars:
   - `PIHOLE_URL` → `PIHOLE_PRIMARY_URL`
   - `PIHOLE_PASSWORD` → `PIHOLE_PRIMARY_PASSWORD`
   - `PIHOLE_VERIFY_SSL` → `PIHOLE_PRIMARY_VERIFY_SSL`
4. **Legacy env vars continue working** as fallback (with deprecation log warning) if user doesn't rename immediately
5. To add a second Pi-hole, user adds env vars with a new prefix (e.g., `PIHOLE_SECONDARY_URL`) and creates a new instance via the UI with `env_prefix = "SECONDARY"`
6. Container restart required after adding new env vars (standard Docker behavior)

---

## Consequences

### Positive

- Users can back up multiple Pi-hole instances from a single deployment
- No breaking changes — single-instance users see identical UI until they add a second instance
- No new dependencies — credentials stay in environment, no encryption library needed
- Consistent pattern with nodered-backup project in this repo family
- Scheduler, retention, and services require minimal changes (already multi-instance ready)
- Foundation for future features: bulk backup, cross-instance restore, instance health monitoring

### Negative

- Adding a new Pi-hole instance requires both a container restart (for env vars) and a UI action (to create the config) — two-step process
- More URL patterns and views to maintain
- Template count increases (instance_list, instance_dashboard)

### Risks

- **Env var misconfiguration**: User sets wrong prefix in UI vs env vars → backup silently fails. Mitigation: show resolved env var status on settings page, validate on test connection.
- **Legacy env var deprecation**: Users who don't update `.env` still work via fallback, but may be confused by deprecation warnings. Mitigation: clear migration docs, log warning only once per startup.
- **SQLite concurrency**: Multiple instances backing up simultaneously could increase write contention. Mitigation: existing per-config locking in scheduler serializes per-config; SQLite WAL mode handles moderate concurrency.

---

## Future Considerations

- **Bulk "Backup All" button** on the overview page
- **Cross-instance restore** — restore a backup from one Pi-hole to another
- **Instance health monitoring** — periodic connectivity checks with status indicators
- **Per-instance notification settings** — different notification channels per Pi-hole
- **Instance groups/tags** — organize instances (e.g., "Primary DNS", "Secondary DNS")

---

## References

- [ADR-0001](0001-pihole-backup-architecture.md) — Original architecture, Section 5: multi-instance model design
- [ADR-0010](0010-env-var-credentials.md) — Env var credential decision (philosophy preserved here)
- [ADR-0013](0013-reliability-security-fixes.md) — Issue 1 (per-config scheduler) and Issue 7 (single-config UI limitation)
- nodered-backup `env_prefix` pattern — Reference implementation
