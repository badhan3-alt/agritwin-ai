"""Validate a single field ring and measure its WGS84 geodesic area."""
import math

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from geographiclib.geodesic import Geodesic

SQUARE_METRES_PER_ACRE = 4046.8564224


def _orientation(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _intersects(a, b, c, d):
    def on_segment(p, q, r):
        return min(p[0], r[0]) <= q[0] <= max(p[0], r[0]) and min(p[1], r[1]) <= q[1] <= max(p[1], r[1])

    abc, abd, cda, cdb = _orientation(a, b, c), _orientation(a, b, d), _orientation(c, d, a), _orientation(c, d, b)
    if ((abc > 0 > abd) or (abd > 0 > abc)) and ((cda > 0 > cdb) or (cdb > 0 > cda)):
        return True
    return any(abs(v) < 1e-14 and on_segment(p, q, r) for v, p, q, r in [
        (abc, a, c, b), (abd, a, d, b), (cda, c, a, d), (cdb, c, b, d),
    ])


def validate_geometry(value):
    if not isinstance(value, dict) or value.get("type") != "Polygon":
        raise ValidationError(_("Enter a GeoJSON Polygon with one closed ring."))
    rings = value.get("coordinates")
    if not isinstance(rings, list) or len(rings) != 1 or not isinstance(rings[0], list):
        raise ValidationError(_("Draw one field boundary without holes."))
    ring = rings[0]
    if not 4 <= len(ring) <= 501:
        raise ValidationError(_("Use between 3 and 500 boundary corners, then close the ring."))
    for point in ring:
        # JSON integers may be larger than float can represent. Bounds below
        # safely reject those integers without overflowing math.isfinite().
        if not isinstance(point, list) or len(point) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or (isinstance(v, float) and not math.isfinite(v)) for v in point):
            raise ValidationError(_("Each corner must contain a finite longitude and latitude."))
        if not (88 <= point[0] <= 92.8 and 20.5 <= point[1] <= 26.7):
            raise ValidationError(_("Boundary corners must be within the Bangladesh planning area."))
    if ring[0] != ring[-1]:
        raise ValidationError(_("Close the boundary by repeating the first corner at the end."))
    vertices = ring[:-1]
    if len(set(map(tuple, vertices))) != len(vertices):
        raise ValidationError(_("Boundary corners must be distinct."))
    for i, b in enumerate(vertices):
        a, c = vertices[i - 1], vertices[(i + 1) % len(vertices)]
        # Consecutive edges may share their corner, but may not double back
        # over the same line. Non-adjacent intersections are checked below.
        if abs(_orientation(a, b, c)) < 1e-14 and (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1]) < 0:
            raise ValidationError(_("Boundary edges must not cross or touch each other."))
    for i, (a, b) in enumerate(zip(ring, ring[1:])):
        for j in range(i + 1, len(vertices)):
            if j == i + 1 or (i == 0 and j == len(vertices) - 1):
                continue
            if _intersects(a, b, ring[j], ring[j + 1]):
                raise ValidationError(_("Boundary edges must not cross or touch each other."))
    area = measure(value)[0]
    if not 1 <= area <= 100000 * SQUARE_METRES_PER_ACRE:
        raise ValidationError(_("Boundary area must be between 1 square metre and 100,000 acres."))


def measure(geometry):
    polygon = Geodesic.WGS84.Polygon()
    for lon, lat in geometry["coordinates"][0][:-1]:
        polygon.AddPoint(lat, lon)
    _, perimeter, area = polygon.Compute()
    return abs(area), perimeter


def schematic_points(geometry, width=600, height=260, margin=28):
    """North-up local projection for an offline SVG/PDF boundary schematic."""
    ring = geometry["coordinates"][0]
    lat0 = sum(p[1] for p in ring[:-1]) / (len(ring) - 1)
    projected = [(lon * math.cos(math.radians(lat0)), lat) for lon, lat in ring]
    min_x, max_x = min(p[0] for p in projected), max(p[0] for p in projected)
    min_y, max_y = min(p[1] for p in projected), max(p[1] for p in projected)
    scale = min((width - 2 * margin) / max(max_x - min_x, 1e-10), (height - 2 * margin) / max(max_y - min_y, 1e-10))
    return [(width / 2 + (x - (max_x + min_x) / 2) * scale, height / 2 - (y - (max_y + min_y) / 2) * scale) for x, y in projected]
