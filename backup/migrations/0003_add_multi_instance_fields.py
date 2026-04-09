# ADR-0014: Add multi-instance support fields

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add env_prefix field to PiholeConfig for multi-instance credential support.

    The env_prefix field determines which environment variables to read:
    PIHOLE_{PREFIX}_URL, PIHOLE_{PREFIX}_PASSWORD, PIHOLE_{PREFIX}_VERIFY_SSL.

    Credentials are never stored in the database — only the prefix is stored.
    The AddField default="PRIMARY" automatically populates existing rows.
    """

    dependencies = [
        ("backup", "0002_remove_credential_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="piholeconfig",
            name="env_prefix",
            field=models.CharField(
                default="PRIMARY",
                help_text="Environment variable prefix (e.g., PRIMARY reads PIHOLE_PRIMARY_URL)",
                max_length=50,
            ),
        ),
    ]
