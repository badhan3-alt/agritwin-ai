"""Verify the external NASA connection using the same client as the website."""
from django.core.management.base import BaseCommand, CommandError

from climate.services import NASADataUnavailable, get_climate


class Command(BaseCommand):
    help = "Retrieve and validate real NASA POWER data, then print its provenance. No sample data is used."

    def add_arguments(self, parser):
        parser.add_argument("--latitude", type=float, default=24.3745, help="Latitude; defaults to the public Rajshahi example.")
        parser.add_argument("--longitude", type=float, default=88.6042, help="Longitude; defaults to the public Rajshahi example.")

    def handle(self, *args, **options):
        try:
            climate = get_climate(options["latitude"], options["longitude"], refresh=True)
        except (NASADataUnavailable, ValueError) as error:
            raise CommandError(str(error)) from error
        provenance = climate["provenance"]
        self.stdout.write(self.style.SUCCESS("Verified real NASA POWER data."))
        self.stdout.write(f"Source: {climate['source']}")
        self.stdout.write(f"Period: {provenance['period']}")
        self.stdout.write(f"Retrieved: {provenance['retrieved_at']}")
        self.stdout.write(f"Months: {len(climate['monthly_data'])}")
        self.stdout.write(f"Annual climatological precipitation: {climate['annual_summary']['total_precip_mm']} mm")
        self.stdout.write(f"Original response preserved: {bool(climate['raw_response'])}")
        self.stdout.write(f"Request: {provenance['url']}")
