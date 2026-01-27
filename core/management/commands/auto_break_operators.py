from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from django.db import transaction
from datetime import timedelta
import os

from core.models import LoginOperator, Calendar


LOG_FILE = os.path.join(settings.BASE_DIR, "log", "AutoBreak30.txt")


def run_auto_break(today=None, stdout=None):
    now_local = timezone.localtime()
    today = today or now_local.date()
    date_from = today - timedelta(days=60)

    # ⚠️ BITNO:
    # koristimo ISKLJUČIVO team date / team time
    qs = (
        LoginOperator.objects
        .filter(
            status="COMPLETED",
            break_time__isnull=True,
            login_team_date__gte=date_from,
            login_team_date__lte=today,
            login_team_time__isnull=False,
            logoff_team_time__isnull=False,
        )
        .select_related("team_user", "operator")
        .order_by("login_team_date")
    )

    total = qs.count()
    updated = 0
    skipped = 0

    lines = []
    lines.append(f"[{now_local}] AUTO BREAK CHECK ({date_from} → {today})")
    lines.append(f"Candidates: {total}")

    for lo in qs:
        try:
            # calendar po TEAM logici
            cal = Calendar.objects.filter(
                team_user=lo.team_user,
                date=lo.login_team_date
            ).first()

            if not cal:
                skipped += 1
                continue

            # FULL SHIFT = TEAM TIME == SHIFT TIME
            if lo.login_team_time != cal.shift_start:
                skipped += 1
                continue

            if lo.logoff_team_time != cal.shift_end:
                skipped += 1
                continue

            with transaction.atomic():
                lo.break_time = 30
                lo.save(update_fields=["break_time", "updated_at"])

            updated += 1

            op = lo.operator
            label = f"{op.badge_num} {op.name}" if op else "N/A"
            lines.append(f"+ ID {lo.id} -> break=30 [{lo.login_team_date}] ({label})")


        except Exception:
            skipped += 1

    lines.append(f"Done. Updated {updated}, skipped {skipped}")

    # write log
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write("\n" + "=" * 80 + "\n")
        for l in lines:
            f.write(l + "\n")

    if stdout:
        for l in lines:
            stdout.write(l + "\n")

    return updated, skipped


class Command(BaseCommand):
    help = "Auto-assign 30 min break for full-shift completed operators (TEAM time only)"

    def handle(self, *args, **options):
        run_auto_break(stdout=self.stdout)
