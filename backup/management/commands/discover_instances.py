"""Discover Pi-hole instances from PIHOLE_* environment variables."""

from django.core.management.base import BaseCommand

from backup.services.discovery_service import discover_instances_from_env


class Command(BaseCommand):
    help = "Discover Pi-hole instances from PIHOLE_* environment variables"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-apply env var values to existing instances (except credentials)",
        )

    def handle(self, *args, **options):
        result = discover_instances_from_env(force=options["force"])

        if result["created"]:
            self.stdout.write(f"Created instances: {', '.join(result['created'])}")
        if result["updated"]:
            self.stdout.write(f"Updated instances: {', '.join(result['updated'])}")
        if result["skipped"]:
            self.stdout.write(f"Skipped (already exist): {', '.join(result['skipped'])}")

        if not any(result.values()):
            self.stdout.write("No PIHOLE_* environment variables found")
