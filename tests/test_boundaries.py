"""Offline boundary geometry, ownership and area-estimate workflow checks."""
from copy import deepcopy
import json
import math
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from boundaries.forms import BoundaryForm
from boundaries.geometry import SQUARE_METRES_PER_ACRE, measure, schematic_points, validate_geometry
from boundaries.models import FarmBoundary
from farms.models import Analysis, Farm


def polygon(points):
    return {"type": "Polygon", "coordinates": [points + [points[0]]]}


# Roughly 100 by 100 metres near 24 degrees north. The independent expected
# area is one hectare to within 0.5%, rather than another call to measure().
HECTARE = polygon([[89.0, 24.0], [89.000983, 24.0], [89.000983, 24.000903], [89.0, 24.000903]])
TINY = polygon([[89.0, 24.0], [89.00002, 24.0], [89.00002, 24.00002], [89.0, 24.00002]])


class BoundaryGeometryTests(SimpleTestCase):
    def test_geodesic_area_and_perimeter_are_close_to_one_hectare_square(self):
        validate_geometry(HECTARE)
        area, perimeter = measure(HECTARE)
        self.assertAlmostEqual(area, 10000, delta=50)
        self.assertAlmostEqual(perimeter, 400, delta=2)

    def test_area_is_invariant_to_corner_order_and_starting_corner(self):
        expected_area, expected_perimeter = measure(HECTARE)
        vertices = HECTARE["coordinates"][0][:-1]
        for start in range(len(vertices)):
            rotated = vertices[start:] + vertices[:start]
            for points in [rotated, list(reversed(rotated))]:
                with self.subTest(start=start, points=points):
                    geometry = polygon(points)
                    validate_geometry(geometry)
                    area, perimeter = measure(geometry)
                    self.assertAlmostEqual(area, expected_area, places=5)
                    self.assertAlmostEqual(perimeter, expected_perimeter, places=5)

    def test_rejects_invalid_geojson_structures_without_crashing(self):
        invalid = [None, False, 1, "Polygon", [], {}, {"type": "Feature", "geometry": HECTARE}, {"type": ["Polygon"], "coordinates": []}, {"type": "Point", "coordinates": [89, 24]}, {"type": "Polygon", "coordinates": None}, {"type": "Polygon", "coordinates": []}, {"type": "Polygon", "coordinates": [HECTARE["coordinates"][0], HECTARE["coordinates"][0]]}, {"type": "Polygon", "coordinates": [[[]]]}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_geometry(value)

    def test_rejects_nonfinite_boolean_nonnumeric_and_huge_integer_coordinates(self):
        for bad in [float("nan"), float("inf"), -float("inf"), True, False, "89", None, [], {}, 10 ** 1000]:
            for coordinate in [0, 1]:
                geometry = deepcopy(HECTARE)
                geometry["coordinates"][0][1][coordinate] = bad
                with self.subTest(bad=str(bad)[:30], coordinate=coordinate), self.assertRaises(ValidationError):
                    validate_geometry(geometry)
        geometry = deepcopy(HECTARE)
        geometry["coordinates"][0][1].append(0)
        with self.assertRaises(ValidationError):
            validate_geometry(geometry)

    def test_rejects_outside_unclosed_duplicate_and_degenerate_rings(self):
        cases = [
            polygon([[87.9, 24], [88.1, 24], [88.1, 24.01]]),
            polygon([[89, 20.4], [89.01, 20.6], [89, 20.6]]),
            polygon([[89, 26.8], [89.01, 26.6], [89, 26.6]]),
            polygon([[92.9, 24], [92.7, 24], [92.7, 24.01]]),
            {"type": "Polygon", "coordinates": [HECTARE["coordinates"][0][:-1]]},
            polygon([[89, 24], [89.001, 24], [89.001, 24], [89, 24.001]]),
            polygon([[89, 24], [89.001, 24], [89, 24.001], [89.001, 24], [89.001, 24.001]]),
            polygon([[89, 24], [89.001, 24], [89.002, 24]]),
            polygon([[89, 24], [89.000001, 24], [89.000001, 24.000001], [89, 24.000001]]),
            polygon([[88, 20.5], [92.8, 20.5], [92.8, 26.7], [88, 26.7]]),
        ]
        for geometry in cases:
            with self.subTest(geometry=geometry), self.assertRaises(ValidationError):
                validate_geometry(geometry)

    def test_rejects_crossings_touches_overlaps_and_adjacent_reversals(self):
        # Work in degrees but use small offsets wholly within the planning area.
        cases = [
            [[0, 0], [2, 2], [0, 2], [2, 0]],
            [[0, 0], [4, 0], [4, 4], [2, 0], [0, 4]],
            [[0, 0], [4, 0], [4, 4], [1, 4], [1, 0], [3, 0], [3, 3], [0, 3]],
            [[0, 0], [4, 0], [2, 0], [2, 2], [0, 2]],
            [[0, 0], [4, 0], [4, 4], [0, 4], [0, -1]],
        ]
        for points in cases:
            geometry = polygon([[89 + x / 1000, 24 + y / 1000] for x, y in points])
            with self.subTest(points=points), self.assertRaises(ValidationError):
                validate_geometry(geometry)

    def test_allows_a_redundant_corner_that_continues_along_an_edge(self):
        geometry = deepcopy(HECTARE)
        geometry["coordinates"][0].insert(1, [89.0004915, 24.0])
        validate_geometry(geometry)
        self.assertAlmostEqual(measure(geometry)[0], 10000, delta=50)

    def test_limits_ring_to_five_hundred_corners(self):
        for count in [500, 501]:
            geometry = polygon([[89 + .001 * math.cos(2 * math.pi * i / count), 24 + .001 * math.sin(2 * math.pi * i / count)] for i in range(count)])
            if count == 500:
                validate_geometry(geometry)
            else:
                with self.assertRaises(ValidationError):
                    validate_geometry(geometry)

    def test_offline_schematic_stays_inside_canvas_and_points_north_up(self):
        points = schematic_points(HECTARE)
        self.assertEqual(points[0], points[-1])
        self.assertTrue(all(28 <= x <= 572 and 28 <= y <= 232 for x, y in points))
        self.assertLess(points[2][1], points[1][1])

    def test_form_rejects_unknown_json_types_and_nonfinite_values(self):
        for value in [None, True, [], "text", {"type": "Other", "coordinates": []}, polygon([[89, 24], [float("nan"), 24], [89, 24.001]])]:
            form = BoundaryForm({"geometry": json.dumps(value)})
            self.assertFalse(form.is_valid())
            self.assertIn("geometry", form.errors)


class BoundaryWorkflowTests(TestCase):
    def setUp(self):
        session = self.client.session
        session["language"] = "en"
        session.save()
        self.farm = Farm.objects.create(owner_session=session.session_key, **Farm.example_defaults())
        self.editor = reverse("boundaries:editor", args=[self.farm.pk])
        self.download = reverse("boundaries:download", args=[self.farm.pk])
        self.delete = reverse("boundaries:delete", args=[self.farm.pk])
        self.network = patch("requests.get", side_effect=AssertionError("Boundary editing must not fetch NASA or another service"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def save_boundary(self, geometry=HECTARE, **extra):
        return self.client.post(self.editor, {"geometry": json.dumps(geometry), **extra})

    def test_editor_saves_estimate_and_leaves_farm_size_and_analysis_unchanged(self):
        analysis = Analysis.objects.create(farm=self.farm, climate={"test_marker": "preserved"})
        self.assertEqual(self.client.get(self.editor).status_code, 200)
        self.assertEqual(self.save_boundary().status_code, 302)
        boundary = FarmBoundary.objects.get(farm=self.farm)
        self.assertAlmostEqual(boundary.area_square_metres, 10000, delta=50)
        self.assertAlmostEqual(boundary.area_acres, boundary.area_square_metres / SQUARE_METRES_PER_ACRE)
        self.assertAlmostEqual(boundary.perimeter_metres, 400, delta=2)
        self.farm.refresh_from_db()
        self.assertEqual(self.farm.farm_size_acres, 3)
        analysis.refresh_from_db()
        self.assertEqual(analysis.climate, {"test_marker": "preserved"})

    def test_only_explicit_checkbox_updates_farm_size(self):
        self.assertEqual(self.save_boundary(use_estimated_area="on").status_code, 302)
        boundary = FarmBoundary.objects.get(farm=self.farm)
        self.farm.refresh_from_db()
        self.assertAlmostEqual(self.farm.farm_size_acres, boundary.area_acres, delta=.00005)
        self.assertEqual(self.save_boundary(TINY).status_code, 302)
        self.farm.refresh_from_db()
        self.assertAlmostEqual(self.farm.farm_size_acres, boundary.area_acres, delta=.00005)
        self.assertEqual(FarmBoundary.objects.filter(farm=self.farm).count(), 1)

    def test_tiny_boundary_can_be_saved_but_cannot_silently_clamp_farm_area(self):
        response = self.save_boundary(TINY, use_estimated_area="on")
        self.assertEqual(response.status_code, 200)
        self.assertIn("use_estimated_area", response.context["form"].errors)
        self.assertFalse(FarmBoundary.objects.filter(farm=self.farm).exists())
        self.farm.refresh_from_db()
        self.assertEqual(self.farm.farm_size_acres, 3)
        self.assertEqual(self.save_boundary(TINY).status_code, 302)

    def test_invalid_edit_preserves_saved_preview_and_database(self):
        self.save_boundary()
        for geometry, extra in [({"type": "Polygon", "coordinates": "invalid"}, {}), (TINY, {"use_estimated_area": "on"})]:
            with self.subTest(geometry=geometry):
                response = self.save_boundary(geometry, **extra)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.assertEqual(response.context["boundary"].geometry, HECTARE)
                self.assertEqual(FarmBoundary.objects.get(farm=self.farm).geometry, HECTARE)

    def test_geojson_download_is_private_and_contains_only_supported_geometry(self):
        geometry = {**HECTARE, "unrelated": {"metadata": "discard"}}
        self.save_boundary(geometry)
        response = self.client.get(self.download)
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(".geojson", response["Content-Disposition"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response.json()["type"], "Feature")
        self.assertEqual(response.json()["geometry"], HECTARE)
        self.assertEqual(response.json()["properties"]["farm"], self.farm.name)
        self.assertNotIn("owner_session", response.json()["properties"])
        self.assertEqual(self.client.post(self.download).status_code, 405)

    def test_download_requires_a_saved_boundary(self):
        self.assertEqual(self.client.get(self.download).status_code, 404)

    def test_other_guest_and_account_cannot_access_any_boundary_route(self):
        self.save_boundary()
        stranger = Client()
        account = get_user_model().objects.create_user(username="outsider", password="Boundary!Pass2026")
        authenticated = Client()
        authenticated.force_login(account)
        for browser in [stranger, authenticated]:
            for method, route, data in [("get", self.editor, {}), ("post", self.editor, {"geometry": json.dumps(HECTARE)}), ("get", self.download, {}), ("post", self.delete, {})]:
                with self.subTest(method=method, route=route):
                    self.assertEqual(getattr(browser, method)(route, data).status_code, 404)
        self.assertTrue(FarmBoundary.objects.filter(farm=self.farm).exists())

    def test_authenticated_owner_can_access_from_another_session(self):
        user = get_user_model().objects.create_user(username="owner", password="Boundary!Pass2026")
        self.farm.owner = user
        self.farm.save()
        other_device = Client()
        other_device.force_login(user)
        self.assertEqual(other_device.get(self.editor).status_code, 200)
        self.assertEqual(other_device.post(self.editor, {"geometry": json.dumps(HECTARE)}).status_code, 302)
        self.assertEqual(other_device.get(self.download).status_code, 200)
        self.assertEqual(other_device.post(self.delete).status_code, 302)

    def test_delete_requires_post_and_preserves_farm_size(self):
        self.save_boundary(use_estimated_area="on")
        self.farm.refresh_from_db()
        saved_area = self.farm.farm_size_acres
        self.assertEqual(self.client.get(self.delete).status_code, 405)
        self.assertTrue(FarmBoundary.objects.filter(farm=self.farm).exists())
        self.assertEqual(self.client.post(self.delete).status_code, 302)
        self.assertFalse(FarmBoundary.objects.filter(farm=self.farm).exists())
        self.farm.refresh_from_db()
        self.assertEqual(self.farm.farm_size_acres, saved_area)

    def test_mutations_require_csrf_token(self):
        protected = Client(enforce_csrf_checks=True)
        session = protected.session
        session.save()
        self.farm.owner_session = session.session_key
        self.farm.save()
        self.assertEqual(protected.post(self.editor, {"geometry": json.dumps(HECTARE)}).status_code, 403)
        self.assertFalse(FarmBoundary.objects.filter(farm=self.farm).exists())
        FarmBoundary.objects.create(farm=self.farm, geometry=HECTARE)
        self.assertEqual(protected.post(self.delete).status_code, 403)
        self.assertTrue(FarmBoundary.objects.filter(farm=self.farm).exists())

    def test_model_full_clean_validates_geometry(self):
        boundary = FarmBoundary(farm=self.farm, geometry=HECTARE)
        boundary.full_clean()
        boundary.geometry = {"type": "Polygon", "coordinates": [[[89, 24], [89, 24], [89, 24], [89, 24]]]}
        with self.assertRaises(ValidationError) as result:
            boundary.full_clean()
        self.assertIn("geometry", result.exception.message_dict)
