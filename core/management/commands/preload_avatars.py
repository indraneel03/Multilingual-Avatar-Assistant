import json

from django.core.management.base import BaseCommand

from core.services.lipsync import musetalk_preload_status_payload, preload_musetalk_workers_sync


class Command(BaseCommand):
    help = "Preload MuseTalk avatar workers and inspect preload status."

    def add_arguments(self, parser):
        parser.add_argument("--status", action="store_true", help="Show current preload status and exit.")
        parser.add_argument("--sync", action="store_true", help="Kept for compatibility; preload already blocks by default.")

    def handle(self, *args, **options):
        if options["status"]:
            self.stdout.write(json.dumps(musetalk_preload_status_payload(), indent=2))
            return

        if options["sync"]:
            preload_musetalk_workers_sync()
            self.stdout.write(json.dumps(musetalk_preload_status_payload(), indent=2))
            return

        preload_musetalk_workers_sync()
        self.stdout.write(json.dumps(musetalk_preload_status_payload(), indent=2))
