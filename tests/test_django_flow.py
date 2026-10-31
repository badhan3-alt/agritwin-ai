"""Offline integration checks for the Django farm-to-report journey."""
import csv
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from unittest.mock import patch

import requests
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from farms.models import Analysis, Farm
from farms.services import ensure_analysis


class FarmJourneyTests(TestCase):
    def setUp(self):
        # An original NASA response is replayed offline; application code still
        # performs its normal request, parsing, validation and score generation.
        cache.clear()
        self.addCleanup(cache.clear)
        self.nasa_payload = json.loads((Path(__file__).parent / "fixtures" / "nasa_power_climatology.json").read_text(encoding="utf-8"))
        self.network = patch("climate.services.requests.get")
        self.network_mock = self.network.start()
        self.addCleanup(self.network.stop)
        self.network_mock.return_value.url = "https://power.larc.nasa.gov/api/temporal/climatology/point?latitude=24.3745&longitude=88.6042&community=AG&format=JSON"
        self.network_mock.return_value.raise_for_status.return_value = None
        self.network_mock.return_value.json.side_effect = lambda: deepcopy(self.nasa_payload)
        session = self.client.session
        session["language"] = "en"
        session.save()
        self.farm = Farm.objects.create(owner_session=session.session_key, **Farm.example_defaults())

    def form_data(self, **overrides):
        data = {
            "name": "North field", "location_name": "Rajshahi, Bangladesh",
            "latitude": "24.3745", "longitude": "88.6042", "farm_size_acres": "3",
            "current_crops": ["aman_rice", "boro_rice"], "first_crop": "aman_rice",
            "soil_type": "clay_loam", "soil_ph": "", "drainage": "well_drained",
            "irrigation_availability": "limited", "farming_priority": "water_conservation",
            "budget": "medium",
        }
        data.update(overrides)
        return data

    def test_create_farm_keeps_unknown_ph_and_saves_analysis(self):
        response = self.client.post(reverse("farms:create"), self.form_data())
        self.assertEqual(response.status_code, 302)
        farm = Farm.objects.get(name="North field")
        self.assertEqual(farm.owner_session, self.client.session.session_key)
        self.assertIsNone(farm.soil_ph)
        self.assertEqual(farm.analysis.climate["status"], "live")
        self.assertEqual(farm.analysis.climate["raw_response"], self.nasa_payload)
        self.assertEqual(len(farm.analysis.strategies), 3)
        self.network_mock.assert_called_once()
        request_parameters = self.network_mock.call_args.kwargs["params"]
        self.assertEqual(request_parameters["latitude"], farm.latitude)
        self.assertEqual(request_parameters["longitude"], farm.longitude)
        self.assertIn("PRECTOTCORR", request_parameters["parameters"])
        self.assertIn("T2M", request_parameters["parameters"])

    def test_new_farm_defaults_can_be_submitted_unchanged(self):
        response = self.client.get(reverse("farms:create"))
        form = response.context["form"]
        self.assertEqual(form["current_crops"].value(), ["aman_rice", "boro_rice"])
        self.assertIn('checked', str(form["current_crops"]))
        data = {name: form[name].value() for name in form.fields}
        data = {name: value for name, value in data.items() if value is not None}
        response = self.client.post(reverse("farms:create"), data)
        self.assertEqual(response.status_code, 302, response.context and response.context["form"].errors)
        farm = Farm.objects.exclude(pk=self.farm.pk).get()
        self.assertRedirects(response, reverse("farms:detail", args=[farm.pk]))
        self.assertEqual(farm.current_crops, ["aman_rice", "boro_rice"])

    def test_invalid_new_farm_shows_linked_error_summary(self):
        before = Farm.objects.count()
        response = self.client.post(reverse("farms:create"), self.form_data(current_crops=[]))
        self.assertEqual(Farm.objects.count(), before)
        self.assertContains(response, 'href="#id_current_crops"')
        self.assertContains(response, 'id="farm-form-errors"')

    def test_first_crop_changes_saved_baseline_sequence(self):
        self.client.post(reverse("farms:create"), self.form_data(first_crop="boro_rice"))
        farm = Farm.objects.get(name="North field")
        self.assertEqual(farm.current_crops, ["boro_rice", "aman_rice"])
        current = next(s for s in farm.analysis.strategies if s["type"] == "existing")
        self.assertEqual([crop["id"] for crop in current["sequence"]], farm.current_crops)

    def test_invalid_location_and_area_do_not_create_farm(self):
        initial_count = Farm.objects.count()
        response = self.client.post(reverse("farms:create"), self.form_data(latitude="91", farm_size_acres="-1"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("latitude", response.context["form"].errors)
        self.assertIn("farm_size_acres", response.context["form"].errors)
        self.assertEqual(Farm.objects.count(), initial_count)

    def test_unknown_crop_is_rejected(self):
        response = self.client.post(reverse("farms:create"), self.form_data(current_crops=["invented_crop"], first_crop=""))
        self.assertEqual(response.status_code, 200)
        self.assertIn("current_crops", response.context["form"].errors)
        self.assertFalse(Farm.objects.filter(name="North field").exists())

    def test_empty_post_displays_required_field_errors(self):
        response = self.client.post(reverse("farms:create"), {})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].is_bound)
        self.assertIn("name", response.context["form"].errors)

    def test_region_preset_works_without_javascript_and_keeps_soil_unknown(self):
        response = self.client.post(reverse("farms:create"), self.form_data(region="rangpur", soil_type="unknown"))
        self.assertEqual(response.status_code, 302)
        farm = Farm.objects.get(name="North field")
        self.assertAlmostEqual(farm.latitude, 25.7439)
        self.assertAlmostEqual(farm.longitude, 89.2752)
        self.assertEqual(farm.soil_type, "unknown")

    def test_no_recommendation_when_all_candidates_are_blocked(self):
        self.farm.drainage = "poor"
        self.farm.save()
        response = self.client.get(reverse("rotations:explorer", kwargs={"pk": self.farm.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["recommended"])
        self.assertContains(response, "None passes all selected constraints")

    def test_other_browser_cannot_read_or_change_farm(self):
        outsider = Client()
        routes = ["farms:detail", "farms:edit", "climate:dashboard", "rotations:explorer", "simulator:workbench", "reports:detail"]
        for route in routes:
            with self.subTest(route=route):
                response = outsider.get(reverse(route, kwargs={"pk": self.farm.pk}))
                self.assertEqual(response.status_code, 404)
        for route in ["farms:edit", "farms:delete", "climate:refresh", "simulator:workbench"]:
            with self.subTest(write_route=route):
                response = outsider.post(reverse(route, kwargs={"pk": self.farm.pk}), self.form_data())
                self.assertEqual(response.status_code, 404)
        self.assertTrue(Farm.objects.filter(pk=self.farm.pk).exists())

    def test_farm_cards_map_each_owned_location_with_machine_readable_coordinates(self):
        another = Farm.objects.create(owner_session=self.farm.owner_session, **{
            **Farm.example_defaults(), "name": "South field", "latitude": 22.35, "longitude": 91.8,
        })
        Farm.objects.create(owner_session="other-owner", **{**Farm.example_defaults(), "name": "Private field", "latitude": 25.1})
        response = self.client.get(reverse("farms:list"))
        self.assertContains(response, 'data-farm-map', count=2)
        self.assertContains(response, 'data-lat="24.3745"')
        self.assertContains(response, 'data-lat="22.35"')
        self.assertContains(response, 'data-lon="91.8"')
        self.assertContains(response, reverse("farms:detail", args=[another.pk]))
        self.assertContains(response, "openstreetmap.org/?mlat=")
        self.assertNotContains(response, "Private field")
        self.assertNotContains(response, 'data-lat="25.1"')

    def test_sidebar_requires_explicit_farm_selection(self):
        response = self.client.get(reverse("core:home"))
        self.assertIsNone(response.context["current_farm"])
        self.assertNotContains(response, 'class="farm-navigation"')
        for route in ["climate:dashboard", "rotations:explorer", "simulator:workbench", "reports:detail"]:
            self.assertNotContains(response, f'href="{reverse(route, args=[self.farm.pk])}"')

    def test_selected_farm_has_nested_direct_tool_links(self):
        second = Farm.objects.create(owner_session=self.farm.owner_session, **{**Farm.example_defaults(), "name": "Second farm"})
        tools = {"climate": "climate:dashboard", "rotations": "rotations:explorer", "simulator": "simulator:workbench", "reports": "reports:detail", "chatbot": "chatbot:index"}
        for farm in [self.farm, second]:
            response = self.client.get(reverse("farms:detail", args=[farm.pk]))
            self.assertContains(response, 'class="farm-navigation"')
            self.assertContains(response, 'class="farm-tool-links"')
            self.assertEqual(response.context["current_farm"], farm)
            for tool, route in tools.items():
                target = reverse(route) + f"?farm={farm.pk}" if tool == "chatbot" else reverse(route, args=[farm.pk])
                self.assertContains(response, f'href="{target}"')
                self.assertNotContains(response, f'?tool={tool}')
                page = self.client.get(target)
                self.assertEqual(page.context["selected_farm" if tool == "chatbot" else "farm"], farm)

    def test_overview_and_farm_list_keep_only_the_top_level_menu_after_selection(self):
        self.client.get(reverse("farms:detail", args=[self.farm.pk]))
        for route in ["core:home", "farms:list"]:
            response = self.client.get(reverse(route))
            self.assertNotContains(response, 'class="farm-navigation"')
            self.assertNotContains(response, 'class="farm-tool-links"')
            self.assertContains(response, f'href="{reverse("core:home")}"')
            self.assertContains(response, f'href="{reverse("farms:list")}"')

    def test_foreign_or_deleted_selection_cannot_populate_sidebar(self):
        for pk in [999999, Farm.objects.create(owner_session="foreign", **Farm.example_defaults()).pk]:
            session = self.client.session
            session["current_farm_id"] = pk
            session.save()
            self.assertIsNone(self.client.get(reverse("core:home")).context["current_farm"])

    def test_deleting_another_farm_preserves_selection(self):
        other = Farm.objects.create(owner_session=self.farm.owner_session, **Farm.example_defaults())
        self.client.get(reverse("farms:detail", args=[self.farm.pk]))
        self.client.post(reverse("farms:delete", args=[other.pk]))
        self.assertEqual(self.client.session["current_farm_id"], self.farm.pk)

    def test_delete_and_refresh_reject_get(self):
        for route in ["farms:delete", "climate:refresh"]:
            with self.subTest(route=route):
                response = self.client.get(reverse(route, kwargs={"pk": self.farm.pk}))
                self.assertEqual(response.status_code, 405)
        self.assertTrue(Farm.objects.filter(pk=self.farm.pk).exists())

    def test_owned_farm_pages_render_from_one_saved_nasa_baseline(self):
        ensure_analysis(self.farm)
        for route in ["farms:detail", "climate:dashboard", "rotations:explorer", "simulator:workbench", "reports:detail"]:
            with self.subTest(route=route):
                response = self.client.get(reverse(route, kwargs={"pk": self.farm.pk}))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, self.farm.name)
        self.network_mock.assert_called_once()

    def test_edit_replaces_stale_analysis(self):
        old = ensure_analysis(self.farm)
        old_scores = {s["id"]: s["composite_score"] for s in old.strategies}
        response = self.client.post(reverse("farms:edit", kwargs={"pk": self.farm.pk}), self.form_data(irrigation_availability="abundant"))
        self.assertEqual(response.status_code, 302)
        self.farm.refresh_from_db()
        self.assertEqual(self.farm.irrigation_availability, "abundant")
        fresh = Analysis.objects.get(farm=self.farm)
        new_scores = {s["id"]: s["composite_score"] for s in fresh.strategies}
        self.assertNotEqual(old_scores, new_scores)
        self.assertEqual(Analysis.objects.filter(farm=self.farm).count(), 1)

    def test_admin_edit_invalidates_saved_analysis(self):
        from django.contrib.admin import AdminSite
        from farms.admin import FarmAdmin
        ensure_analysis(self.farm)
        self.farm.irrigation_availability = "abundant"
        FarmAdmin(Farm, AdminSite()).save_model(None, self.farm, None, change=True)
        self.assertFalse(Analysis.objects.filter(farm=self.farm).exists())
        fresh = ensure_analysis(Farm.objects.get(pk=self.farm.pk))
        current = next(s for s in fresh.strategies if s["type"] == "existing")
        self.assertFalse(any("limited irrigation" in reason for reason in current["blocked_reasons"]))

    def test_zero_change_scenario_matches_baseline(self):
        response = self.client.post(reverse("simulator:workbench", kwargs={"pk": self.farm.pk}), {
            "rainfall_delta_pct": "0", "temp_delta_c": "0",
            "irrigation": self.farm.irrigation_availability, "priority": self.farm.farming_priority,
        })
        self.assertEqual(response.status_code, 200)
        result = response.context["result"]
        self.assertEqual(len(result["strategies_comparison"]), 3)
        for strategy in result["strategies_comparison"]:
            self.assertEqual(strategy["score_change_delta"], 0)
        self.network_mock.assert_called_once()

    def test_out_of_range_scenario_returns_form_errors(self):
        response = self.client.post(reverse("simulator:workbench", kwargs={"pk": self.farm.pk}), {
            "rainfall_delta_pct": "-95", "temp_delta_c": "20",
            "irrigation": "limited", "priority": "water_conservation",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("rainfall_delta_pct", response.context["form"].errors)
        self.assertIn("temp_delta_c", response.context["form"].errors)
        self.assertIsNone(response.context["result"])

    def test_nasa_example_creation_is_session_scoped_and_reusable(self):
        first = self.client.post(reverse("core:demo"))
        second = self.client.post(reverse("core:demo"))
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.url, first.url)
        outsider = Client()
        separate = outsider.post(reverse("core:demo"))
        self.assertEqual(separate.status_code, 302)
        self.assertNotEqual(separate.url, first.url)
        self.assertEqual(outsider.get(first.url).status_code, 404)
        farm = Farm.objects.get(pk=int(first.url.rstrip("/").split("/")[-1]))
        self.assertEqual(farm.name, "Rajshahi example farm")
        self.assertEqual(farm.analysis.climate["status"], "live")
        self.assertEqual(farm.analysis.climate["raw_response"], self.nasa_payload)

    def test_csrf_blocks_untrusted_creation(self):
        protected = Client(enforce_csrf_checks=True)
        response = protected.post(reverse("farms:create"), self.form_data())
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Farm.objects.filter(name="North field").exists())

    def test_json_and_csv_exports_are_downloads(self):
        for output_format in ["json", "csv"]:
            with self.subTest(output_format=output_format):
                response = self.client.get(reverse("reports:download", kwargs={"pk": self.farm.pk, "format": output_format}))
                self.assertEqual(response.status_code, 200)
                self.assertIn("attachment", response["Content-Disposition"])
                text = response.content.decode("utf-8-sig")
                self.assertIn("NASA POWER", text)
                if output_format == "json":
                    self.assertIsInstance(response.json(), dict)
                    self.assertEqual(response.json()["climate"]["raw_response"], self.nasa_payload)
                else:
                    self.assertGreater(len(list(csv.reader(StringIO(text)))), 3)

    def test_export_ownership_and_unsupported_format(self):
        outsider = Client()
        url = reverse("reports:download", kwargs={"pk": self.farm.pk, "format": "json"})
        self.assertEqual(outsider.get(url).status_code, 404)
        invalid = reverse("reports:download", kwargs={"pk": self.farm.pk, "format": "exe"})
        self.assertEqual(self.client.get(invalid).status_code, 404)

    def test_nasa_source_download_is_the_original_response_and_private(self):
        url = reverse("climate:nasa_source", kwargs={"pk": self.farm.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(response.json(), self.nasa_payload)
        self.assertEqual(Client().get(url).status_code, 404)

    def test_nasa_outage_preserves_farm_without_inventing_analysis(self):
        self.network_mock.side_effect = requests.Timeout("NASA request timed out")
        response = self.client.post(reverse("farms:create"), self.form_data())
        self.assertEqual(response.status_code, 302)
        farm = Farm.objects.get(name="North field")
        self.assertFalse(Analysis.objects.filter(farm=farm).exists())
        profile = self.client.get(response.url)
        self.assertEqual(profile.status_code, 200)
        self.assertIsNone(profile.context["climate"])
        self.assertEqual(profile.context["strategies"], [])
        self.assertTrue(profile.context["climate_error"])

    def test_nasa_outage_blocks_dashboards_simulation_and_reports(self):
        self.network_mock.side_effect = requests.Timeout("NASA request timed out")
        for route in ["climate:dashboard", "rotations:explorer", "simulator:workbench", "reports:detail"]:
            with self.subTest(route=route):
                response = self.client.get(reverse(route, kwargs={"pk": self.farm.pk}))
                self.assertEqual(response.status_code, 503)
                self.assertTemplateUsed(response, "climate/unavailable.html")
                self.assertTrue(response.context["climate_error"])
        for output_format in ["json", "csv"]:
            response = self.client.get(reverse("reports:download", kwargs={"pk": self.farm.pk, "format": output_format}))
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("Content-Disposition", response.headers)
        response = self.client.post(reverse("simulator:workbench", kwargs={"pk": self.farm.pk}), {
            "rainfall_delta_pct": "-20", "temp_delta_c": "2", "irrigation": "limited", "priority": "water_conservation"})
        self.assertEqual(response.status_code, 503)
        self.assertFalse(Analysis.objects.filter(farm=self.farm).exists())

    def test_nasa_source_is_unavailable_during_outage(self):
        self.network_mock.side_effect = requests.Timeout("NASA request timed out")
        response = self.client.get(reverse("climate:nasa_source", kwargs={"pk": self.farm.pk}))
        self.assertEqual(response.status_code, 503)
        self.assertIn("error", response.json())
        self.assertNotIn("Content-Disposition", response.headers)

    def test_failed_refresh_retains_the_last_genuine_nasa_snapshot(self):
        saved = ensure_analysis(self.farm)
        saved_climate, saved_scores = deepcopy(saved.climate), deepcopy(saved.strategies)
        self.network_mock.side_effect = requests.Timeout("NASA request timed out")
        response = self.client.post(reverse("climate:refresh", kwargs={"pk": self.farm.pk}))
        self.assertEqual(response.status_code, 302)
        saved.refresh_from_db()
        self.assertEqual(saved.climate, saved_climate)
        self.assertEqual(saved.strategies, saved_scores)
        dashboard = self.client.get(reverse("climate:dashboard", kwargs={"pk": self.farm.pk}))
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.context["climate"]["status"], "live")
        self.assertEqual(dashboard.context["climate"]["raw_response"], self.nasa_payload)
        self.assertEqual(self.network_mock.call_count, 2)

    def test_legacy_sample_analysis_is_replaced_with_nasa_data(self):
        legacy = Analysis.objects.create(farm=self.farm, climate={"status": "demo", "source": "Old synthetic example"}, strategies=[{"name": "Old sample score"}])
        fresh = ensure_analysis(self.farm)
        self.assertEqual(fresh.pk, legacy.pk)
        self.assertEqual(fresh.climate["status"], "live")
        self.assertEqual(fresh.climate["raw_response"], self.nasa_payload)
        self.assertEqual(len(fresh.strategies), 3)
        self.network_mock.assert_called_once()

    def test_legacy_sample_cannot_be_exported_when_nasa_is_down(self):
        Analysis.objects.create(farm=self.farm, climate={"status": "demo", "source": "Old synthetic example"}, strategies=[{"name": "Old sample score"}])
        self.network_mock.side_effect = requests.Timeout("NASA request timed out")
        response = self.client.get(reverse("reports:download", kwargs={"pk": self.farm.pk, "format": "json"}))
        self.assertEqual(response.status_code, 503)
        self.assertNotContains(response, "Old sample score", status_code=503)
        self.assertNotIn("Content-Disposition", response.headers)

    def test_csv_does_not_execute_farmer_text_as_a_formula(self):
        self.farm.name = '=HYPERLINK("https://example.invalid/","field")'
        self.farm.save()
        response = self.client.get(reverse("reports:download", kwargs={"pk": self.farm.pk, "format": "csv"}))
        rows = list(csv.reader(StringIO(response.content.decode("utf-8-sig"))))
        self.assertTrue(rows[0][1].startswith("'="))
        self.assertIn(["Soil pH", "Unknown; requires a soil test"], rows)

    def test_delete_removes_linked_analysis(self):
        ensure_analysis(self.farm)
        response = self.client.post(reverse("farms:delete", kwargs={"pk": self.farm.pk}))
        self.assertRedirects(response, reverse("farms:list"))
        self.assertFalse(Farm.objects.filter(pk=self.farm.pk).exists())
        self.assertFalse(Analysis.objects.filter(farm_id=self.farm.pk).exists())

    def test_language_redirect_does_not_accept_external_destination(self):
        response = self.client.post(reverse("core:language"), {"language": "bn", "next": "https://example.invalid/"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:home"))

    def test_language_toggle_renders_bengali_navigation(self):
        response = self.client.post(reverse("core:language"), {"language": "bn", "next": reverse("core:home")}, follow=True)
        self.assertContains(response, '<html lang="bn">')
        self.assertContains(response, "আমার খামার")

    def test_health_endpoint_reports_django(self):
        response = self.client.get(reverse("core:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["framework"], "Django")
