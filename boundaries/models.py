from django.db import models
from .geometry import SQUARE_METRES_PER_ACRE, measure, schematic_points, validate_geometry


class FarmBoundary(models.Model):
    farm = models.OneToOneField("farms.Farm", on_delete=models.CASCADE, related_name="boundary")
    geometry = models.JSONField(validators=[validate_geometry])
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def area_square_metres(self):
        return measure(self.geometry)[0]

    @property
    def area_acres(self):
        return self.area_square_metres / SQUARE_METRES_PER_ACRE

    @property
    def perimeter_metres(self):
        return measure(self.geometry)[1]

    @property
    def svg_points(self):
        return " ".join(f"{x:.2f},{y:.2f}" for x, y in schematic_points(self.geometry))

    def __str__(self):
        return f"Boundary: {self.farm.name}"
