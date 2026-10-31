"""Check nationwide location coverage and the coordinates used by farm forms."""
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from farms.forms import FarmForm
from farms.models import Farm
from farms.regions import REGIONS, REGIONS_BY_ID
from rotations.services import get_regions

EXPECTED_DISTRICTS = {
    "Barishal": "barguna barishal bhola jhalokathi patuakhali pirojpur".split(),
    "Chattogram": "bandarban brahmanbaria chandpur chattogram coxs_bazar cumilla feni khagrachhari lakshmipur noakhali rangamati".split(),
    "Dhaka": "dhaka faridpur gazipur gopalganj kishoreganj madaripur manikganj munshiganj narayanganj narsingdi rajbari shariatpur tangail".split(),
    "Khulna": "bagerhat chuadanga jashore jhenaidah khulna kushtia magura meherpur narail satkhira".split(),
    "Mymensingh": "jamalpur mymensingh netrokona sherpur".split(),
    "Rajshahi": "bogura chapainawabganj joypurhat naogaon natore pabna rajshahi sirajganj".split(),
    "Rangpur": "dinajpur gaibandha kurigram lalmonirhat nilphamari panchagarh rangpur thakurgaon".split(),
    "Sylhet": "habiganj moulvibazar sunamganj sylhet".split(),
}

def farm_data(region):
    return {"name": "District field", "location_name": "Rajshahi, Bangladesh", "region": region,
        "latitude": "24.3745", "longitude": "88.6042", "farm_size_acres": "3",
        "current_crops": ["aman_rice", "boro_rice"], "soil_type": "unknown", "soil_ph": "",
        "drainage": "unknown", "irrigation_availability": "limited",
        "farming_priority": "water_conservation", "budget": "medium"}

class DistrictCatalogTests(SimpleTestCase):
    def test_complete_membership_under_all_eight_divisions(self):
        self.assertEqual(len(REGIONS), 64)
        self.assertEqual(len(REGIONS_BY_ID), 64)
        self.assertEqual({region["division"] for region in REGIONS}, set(EXPECTED_DISTRICTS))
        for division, expected in EXPECTED_DISTRICTS.items():
            with self.subTest(division=division):
                self.assertEqual({region["id"] for region in REGIONS if region["division"] == division}, set(expected))

    def test_every_district_form_sets_its_own_location_without_inventing_soil(self):
        for region in REGIONS:
            with self.subTest(district=region["id"]):
                form = FarmForm(data=farm_data(region["id"]))
                self.assertTrue(form.is_valid(), form.errors)
                farm = form.save(commit=False)
                self.assertEqual((farm.latitude, farm.longitude), (region["lat"], region["lon"]))
                self.assertEqual(farm.location_name, region["name"])
                self.assertEqual(farm.soil_type, "unknown")
                self.assertIsNone(farm.soil_ph)
                self.assertEqual(round(farm.latitude, 4), farm.latitude)
                self.assertEqual(round(farm.longitude, 4), farm.longitude)
                self.assertTrue(region["district_bn"] and region["division_bn"])

    def test_old_district_spelling_is_accepted_without_duplicate_options(self):
        form = FarmForm(data=farm_data("jessore"))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["region"], "jashore")
        self.assertEqual(form.cleaned_data["location_name"], REGIONS_BY_ID["jashore"]["name"])

    def test_unknown_district_is_rejected(self):
        form = FarmForm(data=farm_data("invented_district"))
        self.assertFalse(form.is_valid())
        self.assertIn("region", form.errors)

    def test_edit_retains_selected_district_for_unchanged_preset(self):
        district = REGIONS_BY_ID["sylhet"]
        farm = Farm(pk=100, name="Sylhet field", location_name=district["name"], latitude=district["lat"], longitude=district["lon"])
        self.assertEqual(FarmForm(instance=farm)["region"].value(), "sylhet")

    def test_rotation_region_lookup_uses_the_same_catalog(self):
        self.assertEqual(get_regions(), REGIONS)

class DistrictPageTests(TestCase):
    def setUp(self):
        session = self.client.session
        session["language"] = "en"
        session.save()

    def test_rendered_dropdown_and_map_share_all_64_districts(self):
        response = self.client.get(reverse("farms:create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<optgroup", count=8)
        self.assertEqual(len(response.context["regions"]), 64)
        self.assertContains(response, "All 64 districts")
        for district in REGIONS:
            self.assertContains(response, f'value="{district["id"]}"')
