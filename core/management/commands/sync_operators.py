# core/management/commands/sync_operators.py

from django.core.management.base import BaseCommand
from django.db import connections

from core.models import Operator


class Command(BaseCommand):
    help = "Synchronize operators from Inteos (WEA_PersData) into local Operator table."

    def handle(self, *args, **options):
        query = """
            SELECT [BadgeNum],
                   [Name],
                   [FlgAct] AS Act,
                   [PinCode],
                   [Func]
            FROM [BdkCLZG].[dbo].[WEA_PersData]
            WHERE [BadgeNum] LIKE 'R%' OR [BadgeNum] LIKE 'Z%'
        """

        created = 0
        updated = 0

        self.stdout.write("Starting operator sync from Inteos...")

        try:
            with connections["inteos"].cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()

                for badge_num, name, act, pin_code, func in rows:
                    badge_num_str = str(badge_num).strip() if badge_num is not None else ""
                    name_str = name.strip() if isinstance(name, str) else ""
                    pin_code_str = str(pin_code).strip() if pin_code is not None else ""
                    func_str = str(func).strip() if func is not None else ""
                    act_bool = bool(act)

                    obj, is_created = Operator.objects.update_or_create(
                        badge_num=badge_num_str,
                        defaults={
                            "name": name_str,
                            "act": act_bool,
                            "pin_code": pin_code_str,
                            "func": func_str,
                        },
                    )

                    if is_created:
                        created += 1
                    else:
                        updated += 1

            self.stdout.write(
                f"Sync finished. Created {created} operator(s), updated {updated} operator(s)."
            )

        except Exception as e:
            # Plain ASCII poruka, da ne puca na encoding
            self.stderr.write(f"Error during operator sync: {e}")
