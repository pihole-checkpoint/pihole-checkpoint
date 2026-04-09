# ADR-0014: Add multi-instance support fields

from django.db import migrations, models


def set_primary_prefix(apps, schema_editor):
    """Set env_prefix='PRIMARY' on the first existing PiholeConfig if blank."""
    PiholeConfig = apps.get_model("backup", "PiholeConfig")
    first_config = PiholeConfig.objects.order_by("pk").first()
    if first_config and not first_config.env_prefix:
        first_config.env_prefix = "PRIMARY"
        first_config.save(update_fields=["env_prefix"])


def clear_primary_prefix(apps, schema_editor):
    """Reverse: clear env_prefix on configs that were set to PRIMARY."""
    PiholeConfig = apps.get_model("backup", "PiholeConfig")
    PiholeConfig.objects.filter(env_prefix="PRIMARY").update(env_prefix="")


class Migration(migrations.Migration):
    """Add env_prefix field to PiholeConfig for multi-instance credential support.

    The env_prefix field determines which environment variables to read:
    PIHOLE_{PREFIX}_URL, PIHOLE_{PREFIX}_PASSWORD, PIHOLE_{PREFIX}_VERIFY_SSL.

    Credentials are never stored in the database — only the prefix is stored.
    """

    dependencies = [
        ("backup", "0002_remove_credential_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="piholeconfig",
            name="env_prefix",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Environment variable prefix (e.g., PRIMARY reads PIHOLE_PRIMARY_URL)",
                max_length=50,
            ),
        ),
        migrations.RunPython(set_primary_prefix, clear_primary_prefix),
    ]
