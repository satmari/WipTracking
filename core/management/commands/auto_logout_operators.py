from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import LoginOperator, Calendar


class Command(BaseCommand):
    help = "Automatically log out active operators whose shift has ended."

    def handle(self, *args, **options):

        # Helper – safe ASCII logging (da Task Scheduler ne puca na č/ć/ž)
        def safe_log(message):
            if not isinstance(message, str):
                message = str(message)
            safe = message.encode("ascii", errors="replace").decode("ascii")
            self.stdout.write(safe)

        now_utc = timezone.now()
        now_local = timezone.localtime(now_utc)
        today = now_local.date()
        current_time = now_local.time()

        safe_log(
            f"[{now_local}] Starting auto logout for date {today} "
            f"at local time {current_time}..."
        )

        sessions_qs = (
            LoginOperator.objects
            .filter(status='ACTIVE', login_team_date=today)
            .select_related('team_user', 'operator', 'team_user__subdepartment')
        )

        total = sessions_qs.count()
        updated = 0
        skipped_no_calendar = 0
        skipped_shift_not_finished = 0

        for session in sessions_qs:
            operator = session.operator

            op_name = operator.name or "UNKNOWN"
            op_badge = operator.badge_num or "NO_BADGE"

            # Subdepartment
            subdep = session.team_user.subdepartment
            subdep_name = subdep.subdepartment if subdep else "NO_SUBDEP"

            # Calendar entry
            calendar_entry = Calendar.objects.filter(
                team_user=session.team_user,
                date=today,
            ).first()

            if not calendar_entry:
                skipped_no_calendar += 1
                safe_log(
                    f"- {op_badge} {op_name} ({subdep_name}) skipped: "
                    f"no calendar entry for today."
                )
                continue

            shift_start = calendar_entry.shift_start
            shift_end = calendar_entry.shift_end

            shift_str = f"{shift_start.strftime('%H:%M')} - {shift_end.strftime('%H:%M')}"
            now_str = current_time.strftime('%H:%M:%S')

            # Shift not finished
            if current_time <= shift_end:
                skipped_shift_not_finished += 1
                safe_log(
                    f"- {op_badge} {op_name} ({subdep_name}) skipped: "
                    f"shift not finished ({shift_str}, now {now_str})."
                )
                continue

            # AUTO LOGOUT
            session.logoff_actual = now_utc
            session.logoff_team_date = today
            session.logoff_team_time = shift_end
            session.status = 'COMPLETED'

            session.save(update_fields=[
                'logoff_actual',
                'logoff_team_date',
                'logoff_team_time',
                'status',
                'updated_at',
            ])

            updated += 1

            safe_log(
                f"+ AUTO-LOGOUT {op_badge} {op_name} ({subdep_name}) "
                f"at {shift_end.strftime('%H:%M')}"
            )

        safe_log(
            f"Done. Processed {total} active sessions for {today}, "
            f"auto-logged out {updated}, "
            f"skipped {skipped_no_calendar} without calendar, "
            f"{skipped_shift_not_finished} with unfinished shift."
        )
