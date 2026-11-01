from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def ledger_totals(farm):
    totals = {row["entry_type"]: row["total"] for row in farm.ledger_entries.values("entry_type").annotate(total=Sum("amount"))}
    income, expenses = totals.get("income", Decimal("0")), totals.get("expense", Decimal("0"))
    return {"income": income, "expenses": expenses, "net": income - expenses}


def soil_comparison(tests):
    """Compare the latest two supplied measurements of each metric."""
    tests = list(tests)
    comparisons = []
    for field, label, unit in [("ph", _("pH"), ""), ("nitrogen", _("Nitrogen"), "mg/kg"), ("phosphorus", _("Phosphorus"), "mg/kg"), ("potassium", _("Potassium"), "mg/kg")]:
        measurements = [(record.tested_on, getattr(record, field)) for record in tests if getattr(record, field) is not None][:2]
        latest = measurements[0] if measurements else None
        previous = measurements[1] if len(measurements) > 1 else None
        comparisons.append({"label": label, "unit": unit, "latest": latest[1] if latest else None, "latest_date": latest[0] if latest else None, "previous": previous[1] if previous else None, "previous_date": previous[0] if previous else None, "change": latest[1] - previous[1] if previous else None})
    return comparisons


def farm_record_summary(farm):
    today = timezone.localdate()
    pending = farm.calendar_events.filter(completed=False)
    return {"overdue_count": pending.filter(due_date__lt=today).count(), "today_count": pending.filter(due_date=today).count(), "next_events": pending.filter(due_date__gte=today)[:4], "finances": ledger_totals(farm), "diary_count": farm.diary_entries.count(), "soil_test_count": farm.soil_tests.count()}
