from django.core.management.base import BaseCommand, CommandError
from climate.services import NASADataUnavailable
from farms.models import Farm
from farms.services import ensure_analysis

class Command(BaseCommand):
    help = "Prepare a Rajshahi example using actual NASA POWER data. An Internet connection to NASA is required."

    def handle(self, *args, **options):
        farm, _ = Farm.objects.update_or_create(owner_session="__example__", name="Rajshahi example farm", defaults={k: v for k, v in Farm.example_defaults().items() if k != "name"})
        try:
            analysis = ensure_analysis(farm, refresh=True)
        except NASADataUnavailable as error:
            raise CommandError(f"Example farm saved, but no NASA analysis was generated: {error}") from error
        self.stdout.write(self.style.SUCCESS(f"NASA example prepared: {analysis.climate['provenance']['period']}. Open http://127.0.0.1:8000/ and choose Explore NASA example farm."))
