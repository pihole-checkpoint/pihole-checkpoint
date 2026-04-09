"""Management command to auto-discover Pi-hole instances from environment variables."""

import logging

from django.core.management.base import BaseCommand

from backup.models import PiholeConfig
from backup.services.credential_service import CredentialService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Discover Pi-hole instances from PIHOLE_{PREFIX}_URL environment variables"

    def handle(self, *args, **options):
        prefixes = CredentialService.discover_prefixes()

        if not prefixes:
            self.stdout.write(self.style.WARNING("No Pi-hole instances found in environment variables."))
            return

        created_count = 0
        for entry in prefixes:
            prefix = entry["prefix"]
            _, created = PiholeConfig.objects.get_or_create(
                env_prefix=prefix,
                defaults={"name": prefix.replace("_", " ").title()},
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created instance: {prefix}"))
            else:
                self.stdout.write(f"Instance already exists: {prefix}")

        self.stdout.write(
            self.style.SUCCESS(f"Discovery complete: {created_count} new, {len(prefixes) - created_count} existing")
        )
