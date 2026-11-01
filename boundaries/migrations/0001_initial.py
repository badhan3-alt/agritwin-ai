import boundaries.geometry
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [("farms", "0005_farm_owner")]
    operations = [migrations.CreateModel(
        name="FarmBoundary",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("geometry", models.JSONField(validators=[boundaries.geometry.validate_geometry])),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("farm", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="boundary", to="farms.farm")),
        ],
    )]
