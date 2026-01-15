from django.core.management.base import BaseCommand
from django.db import connections
from django.utils import timezone

from core.models import Pro


class Command(BaseCommand):
    help = "Synchronize PRO data from POSummary database."

    def handle(self, *args, **options):

        # ASCII-safe log (isti pattern kao auto_logout)
        def safe_log(message):
            if not isinstance(message, str):
                message = str(message)
            safe = message.encode("ascii", errors="replace").decode("ascii")
            self.stdout.write(safe)

        query = """
            SELECT TOP (1)
                [style],
                [color],
                [size],
                [qty],
                [delivery_date],
                [status_int] AS status,
                [location_all] AS destination,
                [approval] AS tpp,
                [skeda]
            FROM [posummary].[dbo].[pro]
            WHERE [pro] = %s
            ORDER BY [delivery_date] DESC
        """

        now = timezone.localtime()
        safe_log(f"[{now}] --- PRO sync task started ---")

        pros_qs = Pro.objects.filter(status=True)

        total = pros_qs.count()
        updated = 0
        unchanged = 0
        set_inactive = 0

        try:
            with connections["posummary"].cursor() as cursor:

                for pro in pros_qs:
                    cursor.execute(query, [pro.pro_name])
                    row = cursor.fetchone()

                    if not row:
                        unchanged += 1
                        continue

                    (
                        style,
                        color,
                        size,
                        qty,
                        delivery_date,
                        status_raw,
                        destination,
                        tpp,
                        skeda,
                    ) = row

                    changes = []

                    # SKU
                    style_part = (style or "")[:9].ljust(9)
                    color_part = (color or "")[:4].ljust(4)
                    size_part = size or ""
                    new_sku = f"{style_part}{color_part}{size_part}"

                    if new_sku != pro.sku:
                        changes.append(f"sku {pro.sku} -> {new_sku}")
                        pro.sku = new_sku

                    # QTY
                    if qty is not None and qty != pro.qty:
                        changes.append(f"qty {pro.qty} -> {qty}")
                        pro.qty = qty

                    # Delivery date
                    if delivery_date:
                        delivery_date = delivery_date.date()
                        if delivery_date != pro.del_date:
                            changes.append(
                                f"del_date {pro.del_date} -> {delivery_date}"
                            )
                            pro.del_date = delivery_date

                    # Destination
                    destination = destination or ""
                    if destination != pro.destination:
                        changes.append(
                            f"dest {pro.destination} -> {destination}"
                        )
                        pro.destination = destination

                    # TPP
                    tpp = tpp or ""
                    if tpp != pro.tpp:
                        changes.append(f"tpp {pro.tpp} -> {tpp}")
                        pro.tpp = tpp

                    # SKEDA
                    skeda = skeda or ""
                    if skeda != pro.skeda:
                        changes.append(f"skeda {pro.skeda} -> {skeda}")
                        pro.skeda = skeda

                    # Status
                    if str(status_raw).strip().lower() == "closed" and pro.status:
                        pro.status = False
                        set_inactive += 1
                        changes.append("status Active -> Inactive")

                    if changes:
                        pro.save()
                        updated += 1
                        safe_log(
                            f"+ PRO {pro.pro_name}: " + " | ".join(changes)
                        )
                    else:
                        unchanged += 1

            safe_log(
                f"Done. Processed {total}, "
                f"updated {updated}, "
                f"unchanged {unchanged}, "
                f"set inactive {set_inactive}."
            )

        except Exception as e:
            safe_log(f"ERROR during PRO sync: {e}")

        safe_log(f"[{timezone.localtime()}] --- PRO sync task finished ---")
