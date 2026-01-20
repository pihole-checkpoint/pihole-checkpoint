# ADR-0013: Reliability and Security Fixes

**Status:** Implemented
**Date:** 2026-01-19
**Deciders:** Project Owner

---

## Context

A follow-up review identified additional reliability and security concerns not covered in ADR-0011. These issues range from high-impact design flaws to minor robustness improvements.

---

## Findings

### Critical Issues

---

#### Issue 1: Scheduler Redundancy Bug (N Jobs × N Configs)

| | |
|---|---|
| **Location** | `backup/management/commands/runapscheduler.py:36, 73-119` |
| **Status** | [x] Complete |
| **Priority** | Critical |

**Description:**
`schedule_backup_jobs()` creates one scheduled job per config (line 109), but each job calls `run_backup_job()` which iterates over **all** active configs (line 40-42). With N configs, this results in N jobs each backing up N configs = N² backup attempts.

**Current Code:**
```python
# Line 109: Creates job per config
scheduler.add_job(
    run_backup_job,  # But this function backs up ALL configs
    trigger=trigger,
    id=job_id,
    ...
)

# Line 36-42: Backs up all configs
def run_backup_job():
    configs = PiholeConfig.objects.filter(is_active=True)
    for config in configs:
        # backs up each config
```

**Impact:**
- With 3 configs: 3 jobs × 3 configs = 9 backup attempts per schedule interval
- Per-config locks prevent concurrent execution but not the redundant "run all configs" behavior
- Wasted resources, excessive Pi-hole API calls, storage bloat

**Fix Options:**

**Option A: Single job backs up all configs (simpler)**
```python
def schedule_backup_jobs(scheduler):
    """Schedule a single backup job that handles all configs."""
    # Remove any old per-config jobs
    for job in scheduler.get_jobs():
        if job.id.startswith("backup_"):
            scheduler.remove_job(job.id)

    # Get the earliest/most frequent schedule from all configs
    configs = PiholeConfig.objects.filter(is_active=True)
    if not configs:
        return

    # Use the most frequent backup schedule
    # (or implement per-config scheduling with config_id parameter)
    scheduler.add_job(
        run_backup_job,
        trigger=CronTrigger(hour=4, minute=0),  # Example: daily at 4am
        id="backup_all_configs",
        name="Backup all Pi-hole configs",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
```

**Option B: Per-config jobs with config_id parameter (preserves per-config schedules)**
```python
def run_backup_job_for_config(config_id: int):
    """Execute backup for a specific config."""
    try:
        config = PiholeConfig.objects.get(id=config_id, is_active=True)
    except PiholeConfig.DoesNotExist:
        logger.warning(f"Config {config_id} not found or inactive, skipping")
        return

    lock = _get_config_lock(config_id)
    if not lock.acquire(blocking=False):
        logger.warning(f"Backup already in progress for {config.name}, skipping")
        return

    try:
        logger.info(f"Creating backup for: {config.name}")
        service = BackupService(config)
        record = service.create_backup(is_manual=False)
        logger.info(f"Backup created: {record.filename}")
    except Exception as e:
        logger.error(f"Backup failed for {config.name}: {e}")
    finally:
        lock.release()


def schedule_backup_jobs(scheduler):
    """Schedule backup jobs based on current config."""
    configs = PiholeConfig.objects.filter(is_active=True)

    for config in configs:
        job_id = f"backup_{config.id}"

        # ... trigger setup code ...

        # Use functools.partial or lambda to pass config_id
        from functools import partial
        scheduler.add_job(
            partial(run_backup_job_for_config, config.id),
            trigger=trigger,
            id=job_id,
            name=f"Backup {config.name}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
```

**Recommendation:** Option B preserves the per-config scheduling feature.

---

#### Issue 2: Notification Failures Can Fail Operations

| | |
|---|---|
| **Location** | `backup/services/backup_service.py:114`, `backup/services/restore_service.py:80` |
| **Status** | [x] Complete |
| **Priority** | Critical |

**Description:**
`_notify()` is called inside the main try block after the operation succeeds. If notification fails with an exception, it propagates up and the successful operation appears to have failed.

**Current Code (backup_service.py):**
```python
try:
    # ... backup logic ...
    record = BackupRecord.objects.create(...)

    # Send success notification - if this throws, backup appears to fail!
    self._notify(
        NotificationEvent.BACKUP_SUCCESS,
        "Backup Completed",
        ...
    )

    return record

except Exception as e:
    # This catches notification errors too!
    logger.error(f"Backup failed for {self.config.name}: {e}")
```

**Impact:**
- Successful backups reported as failures
- Confusing error messages (notification errors mixed with backup errors)
- Users may retry backups unnecessarily

**Fix Implementation:**

```python
def create_backup(self, is_manual: bool = False) -> BackupRecord:
    """Create a new backup from Pi-hole."""
    logger.info(f"Creating backup for {self.config.name} (manual={is_manual})")

    filename = self._generate_filename()
    filepath = self.backup_dir / filename

    try:
        # Download backup from Pi-hole
        client = self._get_client()
        backup_data = client.download_teleporter_backup()

        # Save to file
        with open(filepath, "wb") as f:
            f.write(backup_data)

        # Calculate checksum
        checksum = self._calculate_checksum(filepath)

        # Create record
        record = BackupRecord.objects.create(
            config=self.config,
            filename=filename,
            file_path=str(filepath),
            file_size=len(backup_data),
            checksum=checksum,
            status="success",
            is_manual=is_manual,
        )

        # Update config status
        self.config.last_successful_backup = timezone.now()
        self.config.last_backup_error = ""
        self.config.save(update_fields=["last_successful_backup", "last_backup_error"])

        logger.info(f"Backup created successfully: {filename}")

        # Send success notification (isolated from backup success)
        self._safe_notify(
            NotificationEvent.BACKUP_SUCCESS,
            "Backup Completed",
            f"Successfully created backup: {record.filename}",
            details={"File size": f"{record.file_size:,} bytes"},
        )

        return record

    except Exception as e:
        logger.error(f"Backup failed for {self.config.name}: {e}")

        # Clean up partial file if it exists
        self._safe_cleanup(filepath)

        # Create failed record
        record = BackupRecord.objects.create(...)

        # Send failure notification (isolated)
        self._safe_notify(
            NotificationEvent.BACKUP_FAILED,
            "Backup Failed",
            f"Failed to create backup: {e}",
            details={"Error": str(e)},
        )

        raise


def _safe_notify(
    self,
    event: NotificationEvent,
    title: str,
    message: str,
    details: dict | None = None,
) -> None:
    """Send notification, catching any errors to prevent operation failure."""
    try:
        payload = NotificationPayload(
            event=event,
            title=title,
            message=message,
            pihole_name=self.config.name,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            details=details,
        )
        self.notification_service.send_notification(payload)
    except Exception as e:
        logger.warning(f"Failed to send notification: {e}")


def _safe_cleanup(self, filepath: Path) -> None:
    """Clean up partial file, catching any errors."""
    try:
        if filepath.exists():
            filepath.unlink()
    except OSError as e:
        logger.warning(f"Failed to clean up partial file {filepath}: {e}")
```

**Apply same pattern to restore_service.py.**

---

#### Issue 3: Error Masking During Cleanup

| | |
|---|---|
| **Location** | `backup/services/backup_service.py:127-128` |
| **Status** | [x] Complete |
| **Priority** | High |

**Description:**
In the exception handler, `filepath.unlink()` can raise and replace the original exception in the traceback.

**Current Code:**
```python
except Exception as e:
    logger.error(f"Backup failed for {self.config.name}: {e}")

    # This can raise and mask the original error!
    if filepath.exists():
        filepath.unlink()
```

**Impact:**
- Original error is hidden
- Debugging becomes difficult
- Users see "permission denied" instead of the actual backup failure reason

**Fix Implementation:**
```python
except Exception as e:
    logger.error(f"Backup failed for {self.config.name}: {e}")

    # Clean up partial file - don't let cleanup errors mask original
    try:
        if filepath.exists():
            filepath.unlink()
    except OSError as cleanup_error:
        logger.warning(f"Failed to clean up partial file {filepath}: {cleanup_error}")

    # ... rest of error handling ...
    raise
```

---

### Warning-Level Issues

---

#### Issue 4: Telegram Unescaped Markdown

| | |
|---|---|
| **Location** | `backup/services/notifications/telegram.py:25-32` |
| **Status** | [x] Complete |
| **Priority** | Warning |

**Description:**
User-provided content (Pi-hole name, messages, error details) is interpolated directly into Markdown without escaping.

**Current Code:**
```python
text = f"{icon} *{payload.title}*\n\n{payload.message}\n\n"
text += f"📍 Pi-hole: {payload.pihole_name}\n"
```

**Impact:**
- Names containing `*`, `_`, `[`, or `` ` `` break Markdown formatting
- Notification may fail to send or display incorrectly
- Potential for markup injection (low risk but poor hygiene)

**Fix Implementation:**
```python
def _escape_markdown(text: str) -> str:
    """Escape Telegram Markdown special characters."""
    # Characters that need escaping in Telegram Markdown
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def send(self, payload: NotificationPayload) -> bool:
    """Send notification via Telegram bot."""
    icon = "❌" if "failed" in payload.event.value else "✅"

    # Escape user-provided content
    safe_title = _escape_markdown(payload.title)
    safe_message = _escape_markdown(payload.message)
    safe_name = _escape_markdown(payload.pihole_name)
    safe_timestamp = _escape_markdown(payload.timestamp)

    text = f"{icon} *{safe_title}*\n\n{safe_message}\n\n"
    text += f"📍 Pi-hole: {safe_name}\n"
    text += f"🕒 Time: {safe_timestamp}"

    if payload.details:
        text += "\n\n"
        for key, value in payload.details.items():
            safe_key = _escape_markdown(str(key))
            safe_value = _escape_markdown(str(value))
            text += f"*{safe_key}:* {safe_value}\n"
```

**Alternative: Use MarkdownV2 or HTML parse mode with proper escaping.**

---

#### Issue 5: Secret Key File Race Condition

| | |
|---|---|
| **Location** | `config/settings.py:26-32` |
| **Status** | [x] Complete |
| **Priority** | Warning |

**Description:**
TOCTOU race condition: two processes checking `key_file.exists()` simultaneously could both see False, then both generate and write different keys.

**Current Code:**
```python
if key_file.exists():
    return key_file.read_text().strip()

# Generate new key
key = secrets.token_urlsafe(50)
key_file.parent.mkdir(parents=True, exist_ok=True)
key_file.write_text(key)
```

**Impact:**
- Different Gunicorn workers could have different SECRET_KEYs
- Session cookies signed by one worker invalid for another
- Rare in practice but possible during first startup with multiple workers

**Fix Implementation:**
```python
import os
import fcntl  # Unix only; use msvcrt on Windows

def get_or_create_secret_key() -> str:
    """Get secret key from env or generate and persist one (atomic)."""
    key = os.environ.get("SECRET_KEY")
    if key:
        return key

    key_file = BASE_DIR / "data" / ".secret_key"
    key_file.parent.mkdir(parents=True, exist_ok=True)

    # Use exclusive create to ensure atomicity
    try:
        # O_CREAT | O_EXCL fails if file exists - atomic check-and-create
        fd = os.open(key_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            key = secrets.token_urlsafe(50)
            os.write(fd, key.encode())
            return key
        finally:
            os.close(fd)
    except FileExistsError:
        # Another process created it first, read their key
        return key_file.read_text().strip()
```

---

#### Issue 6: Health Check Depends on pgrep

| | |
|---|---|
| **Location** | `backup/views.py:264` |
| **Status** | [x] Complete |
| **Priority** | Warning |

**Description:**
Health check shells out to `pgrep` which may not exist in minimal Docker images.

**Current Code:**
```python
result = subprocess.run(
    ["pgrep", "-f", "runapscheduler"],
    capture_output=True,
    timeout=5,
)
scheduler_running = result.returncode == 0
```

**Impact:**
- Health checks fail on images without procps package
- False negatives cause unnecessary container restarts

**Fix Options:**

**Option A: Use /proc filesystem directly (Linux)**
```python
import os

def _is_scheduler_running() -> bool:
    """Check if scheduler is running by scanning /proc."""
    try:
        for pid in os.listdir('/proc'):
            if not pid.isdigit():
                continue
            try:
                cmdline_path = f'/proc/{pid}/cmdline'
                with open(cmdline_path, 'rb') as f:
                    cmdline = f.read().decode('utf-8', errors='ignore')
                    if 'runapscheduler' in cmdline:
                        return True
            except (FileNotFoundError, PermissionError):
                continue
        return False
    except Exception:
        return False
```

**Option B: Use a heartbeat file/database record**
```python
# In runapscheduler.py - update heartbeat periodically
from django.core.cache import cache

def run_backup_job():
    cache.set('scheduler_heartbeat', timezone.now().isoformat(), timeout=120)
    # ... rest of job

# In health check
def health_check(request):
    heartbeat = cache.get('scheduler_heartbeat')
    if heartbeat:
        last_beat = datetime.fromisoformat(heartbeat)
        scheduler_running = (timezone.now() - last_beat).seconds < 120
    else:
        scheduler_running = False
```

**Option C: Ensure procps is installed in Dockerfile**
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends procps && rm -rf /var/lib/apt/lists/*
```

---

#### Issue 7: UI Assumes Single Config

| | |
|---|---|
| **Location** | `backup/views.py:21` |
| **Status** | [x] Complete |
| **Priority** | Low |

**Description:**
Dashboard uses `.first()` and UI is designed for single Pi-hole instance.

**Current Code:**
```python
def dashboard(request):
    config = PiholeConfig.objects.first()
    backups = BackupRecord.objects.filter(config=config) if config else BackupRecord.objects.none()
```

**Impact:**
- Multi-instance support broken despite model supporting it
- Confusing if user creates multiple configs

**Recommendation:**
- Document this as a known limitation
- Either remove multi-config capability from model or implement multi-config UI
- For now, add a migration/check that ensures only one config exists

---

### Minor Issues (Tech Debt)

---

#### Issue 8: testConnection() Global Event Pattern

| | |
|---|---|
| **Location** | `backup/templates/backup/settings.html:55, 173` |
| **Status** | [x] Complete |
| **Priority** | Low |

**Description:**
JavaScript uses global event dispatching for test connection results.

**Impact:**
- Tight coupling between components
- Harder to test and maintain

**Recommendation:** Refactor to use proper callback pattern or Alpine.js reactivity in future UI improvements.

---

#### Issue 9: Test Staticfiles Warning

| | |
|---|---|
| **Location** | `backup/tests/conftest.py` |
| **Status** | [x] Complete |
| **Priority** | Low |

**Description:**
Tests emit warnings about missing staticfiles configuration.

**Fix Implementation:**
```python
# In conftest.py or test settings
@pytest.fixture(autouse=True)
def configure_static_files(settings, tmp_path):
    settings.STATIC_ROOT = str(tmp_path / "static")
    settings.STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
```

---

## Decision

Implement fixes in the following priority order:

### Phase 1: Critical Reliability (Immediate)
1. **Issue 1**: Scheduler redundancy - fix N×N backup problem
2. **Issue 2**: Notification failure isolation
3. **Issue 3**: Error masking in cleanup

### Phase 2: Security Hardening
4. **Issue 4**: Telegram Markdown escaping
5. **Issue 5**: Atomic secret key creation

### Phase 3: Robustness
6. **Issue 6**: Health check pgrep dependency
7. **Issue 7**: Document single-config limitation

### Phase 4: Tech Debt (Optional)
8. **Issue 8**: JS global event pattern
9. **Issue 9**: Test staticfiles warning

---

## Consequences

### Positive
- Scheduled backups work correctly with multiple configs
- Notification failures don't affect backup/restore success
- Better error messages for debugging
- More secure secret key handling
- More portable health checks

### Negative
- Development effort required
- Scheduler behavior change may surprise users expecting current (buggy) behavior

### Mitigations
- Add tests for each fix
- Document behavior changes in release notes
- Phase rollout to catch regressions

---

## Progress Tracking

| Issue | Priority | Status | Fixed In |
|-------|----------|--------|----------|
| 1 | Critical | Complete | feature/adr-0013-reliability-security-fixes |
| 2 | Critical | Complete | feature/adr-0013-reliability-security-fixes |
| 3 | High | Complete | feature/adr-0013-reliability-security-fixes |
| 4 | Warning | Complete | feature/adr-0013-reliability-security-fixes |
| 5 | Warning | Complete | feature/adr-0013-reliability-security-fixes |
| 6 | Warning | Complete | feature/adr-0013-reliability-security-fixes |
| 7 | Low | Complete | feature/adr-0013-reliability-security-fixes |
| 8 | Low | Complete | feature/adr-0013-reliability-security-fixes |
| 9 | Low | Complete | feature/adr-0013-reliability-security-fixes |

---

## References

- [ADR-0011: Bug Review Findings](0011-bug-review-findings.md) - Previous bug review
- [APScheduler Documentation](https://apscheduler.readthedocs.io/)
- [Telegram Bot API - Markdown](https://core.telegram.org/bots/api#markdownv2-style)
