"""Discover Pi-hole instances from PIHOLE_* environment variables."""

from django.core.management.base import BaseCommand

from backup.services.discovery_service import check_connections, discover_instances_from_env


class Command(BaseCommand):
    help = "Discover Pi-hole instances from PIHOLE_* environment variables"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-apply env var values to existing instances (except credentials)",
        )
        parser.add_argument(
            "--skip-check",
            action="store_true",
            help="Skip connection checks after discovery (faster startup)",
        )

    def handle(self, *args, **options):
        result = discover_instances_from_env(force=options["force"])

        if result["removed"]:
            self.stdout.write(f"Removed instances: {', '.join(result['removed'])}")
        if result["created"]:
            self.stdout.write(f"Created instances: {', '.join(result['created'])}")
        if result["updated"]:
            self.stdout.write(f"Updated instances: {', '.join(result['updated'])}")
        if result["skipped"]:
            self.stdout.write(f"Skipped (already exist): {', '.join(result['skipped'])}")

        if not any(result.values()):
            self.stdout.write("No PIHOLE_* environment variables found")

        if options["skip_check"]:
            return

        # Check connections for all instances
        statuses = check_connections()
        if statuses:
            for prefix, status in statuses.items():
                icon = "OK" if status == "ok" else status.upper()
                self.stdout.write(f"  {prefix}: {icon}")
