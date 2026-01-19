# Generated manually for ADR-0010: Replace encrypted database fields with environment variables

from django.db import migrations


class Migration(migrations.Migration):
    """Remove credential fields from PiholeConfig.

    Pi-hole credentials (URL, password, verify_ssl) are now read from
    environment variables:
    - PIHOLE_URL
    - PIHOLE_PASSWORD
    - PIHOLE_VERIFY_SSL
    """

    dependencies = [
        ("backup", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="piholeconfig",
            name="pihole_url",
        ),
        migrations.RemoveField(
            model_name="piholeconfig",
            name="password",
        ),
        migrations.RemoveField(
            model_name="piholeconfig",
            name="verify_ssl",
        ),
    ]
