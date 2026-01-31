# planners/views.py
from django import forms
# import datetime
from datetime import datetime, date, time, timedelta
import os
from decimal import Decimal, InvalidOperation


from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.views.generic import (TemplateView, ListView, CreateView, UpdateView, DeleteView, FormView, DetailView )


from django.contrib import messages
from django.db import connections, transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.db.models import Q, Sum, OuterRef, Exists
from django.contrib.auth.models import Group
from django.db.models import Count
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.forms.widgets import CheckboxSelectMultiple
from django.forms import HiddenInput
from django.core.exceptions import ValidationError
from django.conf import settings


from core.models import *


class PlannerAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = "core:login"

    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.groups.filter(name__iexact="PLANNERS").exists()


# ---------- DASHBOARD ----------


class PlannerDashboardView(PlannerAccessMixin, TemplateView):
    template_name = "planners/planner_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        today = timezone.localdate()

        # =========================================================
        # OSNOVNI TOTAL BROJEVI
        # =========================================================
        context["users_count"] = TeamUser.objects.count()
        context["subdepartments_count"] = Subdepartment.objects.count()
        context["operators_count"] = Operator.objects.count()
        context["calendar_count"] = Calendar.objects.count()
        context["pro_count"] = Pro.objects.count()
        context["routing_count"] = Routing.objects.count()
        context["operation_count"] = Operation.objects.count()
        context["routing_operation_count"] = RoutingOperation.objects.count()

        context["users_active_count"] = TeamUser.objects.filter(is_active=True).count()
        context["users_inactive_count"] = TeamUser.objects.filter(is_active=False).count()

        context["operators_active_count"] = Operator.objects.filter(act=True).count()
        context["operators_inactive_count"] = Operator.objects.filter(act=False).count()

        context["pro_active_count"] = Pro.objects.filter(status=True).count()
        context["pro_inactive_count"] = Pro.objects.filter(status=False).count()

        context["routing_active_count"] = Routing.objects.filter(status=True).count()
        context["routing_inactive_count"] = Routing.objects.filter(status=False).count()
        context["routing_ready_count"] = Routing.objects.filter(ready=True).count()
        context["routing_not_ready_count"] = Routing.objects.filter(ready=False).count()

        context["operation_active_count"] = Operation.objects.filter(status=True).count()
        context["operation_inactive_count"] = Operation.objects.filter(status=False).count()

        context["active_operator_login_count"] = LoginOperator.objects.filter(status="ACTIVE").count()
        context["login_completed_count"] = LoginOperator.objects.filter(status="COMPLETED").count()
        context["login_ignore_count"] = LoginOperator.objects.filter(status="IGNORE").count()
        context["login_error_count"] = LoginOperator.objects.filter(status="ERROR").count()

        context["downtime_count"] = Downtime.objects.count()
        context["downtime_fixed_count"] = Downtime.objects.filter(fixed_duration=True).count()
        context["downtime_variable_count"] = Downtime.objects.filter(fixed_duration=False).count()

        context["downtime_declaration_count"] = DowntimeDeclaration.objects.count()

        # =========================================================
        # DECLARATIONS (TODAY)
        # =========================================================
        context["declarations_count"] = Declaration.objects.filter(decl_date=today).count()

        context["declarations_qty_by_user"] = list(
            Declaration.objects
            .filter(decl_date=today)
            .values("teamuser__username")
            .annotate(total_qty=Sum("qty"))
            .order_by("-total_qty")[:5]
        )

        # =========================================================
        # BREAKS
        # =========================================================
        context["breaks_count"] = Break.objects.count()
        context["operator_breaks_total"] = OperatorBreak.objects.count()
        context["operator_breaks_today"] = OperatorBreak.objects.filter(date=today).count()

        context["operator_breaks_by_team"] = list(
            OperatorBreak.objects
            .filter(date=today)
            .values(
                "team_user__username",
                "break_type__break_time_start",
                "break_type__break_time_end",
            )
            .annotate(operators_count=Count("operator", distinct=True))
            .order_by("team_user__username", "break_type__break_time_start")
        )

        # =========================================================
        # OPERATOR CAPACITY – TODAY (ONLY COUNT)
        # =========================================================
        context["operator_capacity_count"] = (
            LoginOperator.objects
            .filter(
                login_team_date=today,
                status__in=["ACTIVE", "COMPLETED"]
            )
            .values("operator")
            .distinct()
            .count()
        )



        return context


# ---------- SUBDEPARTMENT ----------


class SubdepartmentListView(PlannerAccessMixin, ListView):
    model = Subdepartment
    template_name = "planners/subdepartment_list.html"
    context_object_name = "subdepartments"


class SubdepartmentCreateView(PlannerAccessMixin, CreateView):
    model = Subdepartment
    fields = ["subdepartment"]
    template_name = "planners/subdepartment_form.html"
    success_url = reverse_lazy("planners:subdepartment_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f"Subdepartment '{self.object.subdepartment}' created successfully.",
        )
        return response


class SubdepartmentUpdateView(PlannerAccessMixin, UpdateView):
    model = Subdepartment
    fields = ["subdepartment"]
    template_name = "planners/subdepartment_form.html"
    success_url = reverse_lazy("planners:subdepartment_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.info(
            self.request,
            f"Subdepartment '{self.object.subdepartment}' updated successfully.",
        )
        return response


class SubdepartmentDeleteView(PlannerAccessMixin, DeleteView):
    model = Subdepartment
    template_name = "planners/confirm_delete.html"
    success_url = reverse_lazy("planners:subdepartment_list")

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        name = self.object.subdepartment

        related_calendar_qs = Calendar.objects.filter(
            team_user__subdepartment=self.object
        )
        deleted_count = related_calendar_qs.count()
        related_calendar_qs.delete()

        if deleted_count:
            messages.error(
                request,
                f"Subdepartment '{name}' has been deleted. "
                f"{deleted_count} related calendar entries were also removed.",
            )
        else:
            messages.error(
                request,
                f"Subdepartment '{name}' has been deleted. "
                f"No related calendar entries were found.",
            )

        return super().delete(request, *args, **kwargs)


# ---------- OPERATOR ----------


class OperatorListView(PlannerAccessMixin, ListView):
    model = Operator
    template_name = "planners/operator_list.html"
    context_object_name = "operators"


class OperatorCreateView(PlannerAccessMixin, CreateView):
    model = Operator
    fields = ["badge_num", "name", "act", "pin_code", "func"]
    template_name = "planners/operator_form.html"
    success_url = reverse_lazy("planners:operator_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f"Operator '{self.object.name}' created successfully.",
        )
        return response


class OperatorUpdateView(PlannerAccessMixin, UpdateView):
    model = Operator
    fields = ["badge_num", "name", "act", "pin_code", "func"]
    template_name = "planners/operator_form.html"
    success_url = reverse_lazy("planners:operator_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.info(
            self.request,
            f"Operator '{self.object.name}' updated successfully.",
        )
        return response


class OperatorDeleteView(PlannerAccessMixin, DeleteView):
    model = Operator
    template_name = "planners/confirm_delete.html"
    success_url = reverse_lazy("planners:operator_list")

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        name = obj.name
        response = super().delete(request, *args, **kwargs)
        messages.error(
            request,
            f"Operator '{name}' has been deleted.",
        )
        return response


class OperatorSyncView(PlannerAccessMixin, View):
    def post(self, request, *args, **kwargs):
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

        try:
            with connections["inteos"].cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()

                for badge_num, name, act, pin_code, func in rows:
                    badge_num_str = (
                        str(badge_num).strip() if badge_num is not None else ""
                    )
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

            messages.success(
                request,
                f"Synchronization with Inteos finished. "
                f"Created {created} and updated {updated} operators.",
            )

        except Exception as e:
            messages.error(
                request,
                f"Error during synchronization with Inteos: {e}",
            )

        return redirect("planners:operator_list")

    def get(self, request, *args, **kwargs):
        return redirect("planners:operator_list")


# ---------- TEAMUSER ----------


class TeamUserListView(PlannerAccessMixin, ListView):
    model = TeamUser
    template_name = "planners/user_list.html"
    context_object_name = "users"


class TeamUserCreateView(PlannerAccessMixin, CreateView):
    model = TeamUser
    fields = ["username", "first_name", "last_name", "subdepartment", "team_location", "login_grace_period", "is_active"]
    template_name = "planners/user_form.html"
    success_url = reverse_lazy("planners:user_list")

    def form_valid(self, form):
        obj = form.save(commit=False)

        # ➤ Password = username (stalno, ne privremeno)
        obj.set_password(obj.username)

        obj.save()

        # ➤ Automatski dodeli TEAMS grupu
        team_group, created = Group.objects.get_or_create(name="TEAMS")
        obj.groups.add(team_group)

        messages.success(
            self.request,
            f"Team User '{obj.username}' created and added to TEAMS group.",
        )

        return redirect(self.success_url)


class TeamUserUpdateView(PlannerAccessMixin, UpdateView):
    model = TeamUser
    fields = ["username", "first_name", "last_name", "subdepartment", "team_location", "login_grace_period", "is_active"]
    template_name = "planners/user_form.html"
    success_url = reverse_lazy("planners:user_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.info(
            self.request,
            f"Team User '{self.object.username}' updated.",
        )
        return response


# ---------- CALENDAR ----------


class CalendarBulkCreateForm(forms.Form):
    team_user = forms.ModelChoiceField(
        queryset=TeamUser.objects.filter(
            subdepartment__isnull=False, is_active=True
        ).order_by("username"),
        label="Team User",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    date_from = forms.DateField(
        label="From date",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    date_to = forms.DateField(
        label="To date",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    HOURS_CHOICES = [(f"{h:02d}:00", f"{h:02d}:00") for h in range(24)]

    shift_start = forms.ChoiceField(
        choices=HOURS_CHOICES,
        label="Shift start",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    shift_end = forms.ChoiceField(
        choices=HOURS_CHOICES,
        label="Shift end",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def clean(self):
        cleaned = super().clean()
        df = cleaned.get("date_from")
        dt = cleaned.get("date_to")
        ss = cleaned.get("shift_start")
        se = cleaned.get("shift_end")

        if df and dt and df > dt:
            self.add_error("date_to", "End date must be on or after start date.")

        if ss and se and ss >= se:
            self.add_error("shift_end", "Shift end must be after shift start.")

        return cleaned


class CalendarListView(PlannerAccessMixin, ListView):
    model = Calendar
    template_name = "planners/calendar_list.html"
    context_object_name = "calendar_entries"
    paginate_by = None
    # paginate_by = 50

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related("team_user", "team_user__subdepartment")
        )
        return qs.order_by("date", "team_user__username")


class CalendarBulkCreateView(PlannerAccessMixin, FormView):
    template_name = "planners/calendar_form.html"
    form_class = CalendarBulkCreateForm
    success_url = reverse_lazy("planners:calendar_list")

    def form_valid(self, form):
        user = form.cleaned_data["team_user"]
        date_from = form.cleaned_data["date_from"]
        date_to = form.cleaned_data["date_to"]
        shift_start = form.cleaned_data["shift_start"]
        shift_end = form.cleaned_data["shift_end"]

        # Convert HH:MM strings to time
        if isinstance(shift_start, str):
            shift_start = datetime.strptime(shift_start, "%H:%M").time()
        if isinstance(shift_end, str):
            shift_end = datetime.strptime(shift_end, "%H:%M").time()

        now_local = timezone.localtime(timezone.now())
        today = now_local.date()
        current_time = now_local.time()

        created_dates = []
        updated_dates = []

        selected_str_dates = self.request.POST.getlist("selected_dates")
        # DEBUG – privremeno:
        # messages.info(
        #     self.request,
        #     f"DEBUG selected_dates: {selected_str_dates}"
        # )
        dates_to_process = []

        if not selected_str_dates:
            form.add_error(None, "Please select at least one day in the calendar grid.")
            return self.form_invalid(form)

        for s in selected_str_dates:
            try:
                # d = datetime.date.fromisoformat(s)
                d = date.fromisoformat(s)
            except ValueError:
                continue
            if date_from <= d <= date_to:
                dates_to_process.append(d)

        # messages.info(
        #     self.request,
        #     f"DEBUG dates_to_process: {[d.isoformat() for d in dates_to_process]}"
        # )

        # RULE 1 — NO PAST DAYS
        for d in dates_to_process:
            if d < today:
                messages.error(
                    self.request,
                    f"You cannot modify past date: {d}",
                )
                return redirect("planners:calendar_add")

        # RULE 2 — TODAY RESTRICTIONS
        for d in dates_to_process:
            if d == today:
                existing = Calendar.objects.filter(team_user=user, date=today).first()

                if existing:
                    # TODAY — SHIFT ACTIVE
                    if existing.shift_start <= current_time <= existing.shift_end:
                        messages.error(
                            self.request,
                            (
                                f"Cannot modify today's shift ({existing.shift_start}–{existing.shift_end}) "
                                f"because it is currently ACTIVE."
                            ),
                        )
                        return redirect("planners:calendar_add")

                    # TODAY — SHIFT FINISHED
                    if existing.shift_end < current_time:
                        messages.error(
                            self.request,
                            (
                                f"Cannot modify today's shift ({existing.shift_start}–{existing.shift_end}) "
                                f"because it has already FINISHED."
                            ),
                        )
                        return redirect("planners:calendar_add")

                # If no shift exists for today → allowed

        # CREATE / UPDATE
        for current in dates_to_process:
            obj, created = Calendar.objects.get_or_create(
                date=current,
                team_user=user,
                defaults={
                    "shift_start": shift_start,
                    "shift_end": shift_end,
                },
            )

            if created:
                created_dates.append(current)
            else:
                obj.shift_start = shift_start
                obj.shift_end = shift_end
                obj.save()
                updated_dates.append(current)

        # SUCCESS MESSAGES
        if created_dates:
            created_str = ", ".join([d.strftime("%d.%m.%Y.") for d in created_dates])
            messages.success(
                self.request,
                f"Created {len(created_dates)} new entries for {user.username}: {created_str}",
            )

        if updated_dates:
            updated_str = ", ".join([d.strftime("%d.%m.%Y.") for d in updated_dates])
            messages.info(
                self.request,
                f"Updated {len(updated_dates)} calendar entries for {user.username}: {updated_str}",
            )

        return super().form_valid(form)


class CalendarBulkDeleteForm(forms.Form):
    team_user = forms.ModelChoiceField(
        queryset=TeamUser.objects.filter(
            subdepartment__isnull=False, is_active=True
        ).order_by("username"),
        label="Team User",
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class CalendarBulkDeleteView(PlannerAccessMixin, TemplateView):
    template_name = "planners/calendar_delete.html"

    def get(self, request, *args, **kwargs):
        form = CalendarBulkDeleteForm(request.GET or None)
        entries = None

        if form.is_valid():
            user = form.cleaned_data["team_user"]
            today = timezone.localdate()

            entries = Calendar.objects.filter(
                team_user=user,
                date__gte=today,
            ).order_by("date")

        context = self.get_context_data(form=form, entries=entries)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        form = CalendarBulkDeleteForm(request.POST)
        entries = None

        if form.is_valid():
            user = form.cleaned_data["team_user"]
            ids = request.POST.getlist("selected_entries")

            qs = Calendar.objects.filter(team_user=user, id__in=ids)

            now_local = timezone.localtime(timezone.now())
            today = now_local.date()
            current_time = now_local.time()

            # DELETE RULES
            for cal in qs:
                if cal.date < today:
                    messages.error(
                        request,
                        f"Cannot delete Calendar entry for {cal.date} — it is in the past.",
                    )
                    return redirect("planners:calendar_delete")

                if cal.date == today and cal.shift_start <= current_time:
                    messages.error(
                        request,
                        f"Cannot delete today's entry ({cal.date}) — shift already started.",
                    )
                    return redirect("planners:calendar_delete")

            count = qs.count()
            qs.delete()

            messages.error(
                request,
                f"Deleted {count} calendar entries for {user.username}.",
            )

            today = timezone.localdate()
            entries = Calendar.objects.filter(
                team_user=user,
                date__gte=today,
            ).order_by("date")

        context = self.get_context_data(form=form, entries=entries)
        return self.render_to_response(context)


# ---------- PRO FORM ----------


class ProForm(forms.ModelForm):
    # helper fields used only in create mode to build SKU
    style = forms.CharField(
        required=False,
        max_length=9,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    color = forms.CharField(
        required=False,
        max_length=4,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    size = forms.CharField(
        required=False,
        max_length=4,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )

    class Meta:
        model = Pro
        fields = [
            "pro_name",
            "sku",
            "qty",
            "del_date",
            "status",
            "destination",
            "tpp",
            "skeda",
        ]
        widgets = {
            "del_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "sku": forms.TextInput(attrs={"class": "form-control"}),  # hidden in create
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # CREATE mode
        if not (self.instance and self.instance.pk):
            self.fields["sku"].widget = forms.HiddenInput()
        else:
            # EDIT mode
            self.fields.pop("style", None)
            self.fields.pop("color", None)
            self.fields.pop("size", None)

    def clean_style(self):
        return (self.cleaned_data.get("style") or "").strip()

    def clean_color(self):
        return (self.cleaned_data.get("color") or "").strip()

    def clean_size(self):
        return (self.cleaned_data.get("size") or "").strip()

    def save(self, commit=True):
        instance = super().save(commit=False)

        # ONLY on create → build SKU
        if not instance.pk:
            style = self.cleaned_data.get("style", "")
            color = self.cleaned_data.get("color", "")
            size = self.cleaned_data.get("size", "")

            # style: exactly 9 chars (right-pad with spaces)
            style_part = style[:9].ljust(9)

            # color: exactly 4 chars (right-pad with spaces)
            color_part = color[:4].ljust(4)

            # size: no padding, no trimming (just append)
            sku_value = f"{style_part}{color_part}{size}"

            instance.sku = sku_value

        if commit:
            instance.save()
        return instance


class ProSubdepartmentMixin:
    def _update_subdepartments(self, pro, selected_ids):
        selected_ids = set(int(i) for i in selected_ids)

        existing = ProSubdepartment.objects.filter(pro=pro)
        existing_map = {ps.subdepartment_id: ps for ps in existing}

        for sid in selected_ids:
            ps = existing_map.get(sid)
            if ps:
                if not ps.active:
                    ps.active = True
                    ps.save()
            else:
                ProSubdepartment.objects.create(
                    pro=pro,
                    subdepartment_id=sid,
                    active=True,
                )

        for sid, ps in existing_map.items():
            if sid not in selected_ids and ps.active:
                ps.active = False
                ps.save()


class ProListView(PlannerAccessMixin, ListView):
    model = Pro
    template_name = "planners/pro_list.html"
    context_object_name = "pros"
    paginate_by = None
    # paginate_by = 50

    def get_queryset(self):
        return (
            Pro.objects.all()
            .prefetch_related("pro_subdepartments__subdepartment")
            .order_by("del_date", "pro_name")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # postoji routing za isti (SKU + subdepartment)
        routing_exists = Routing.objects.filter(
            sku=OuterRef("pro__sku"),
            subdepartment=OuterRef("subdepartment"),
        )

        # aktivni PRO subdepartments koji NEMAJU routing
        missing = (
            ProSubdepartment.objects
            .filter(active=True, pro__sku__isnull=False)
            .annotate(has_routing=Exists(routing_exists))
            .filter(has_routing=False)
            .select_related("pro", "subdepartment")
            .order_by("pro__pro_name")
        )

        context["pros_without_routing"] = missing
        context["pros_without_routing_count"] = missing.count()

        return context


class ProCreateView(PlannerAccessMixin, ProSubdepartmentMixin, CreateView):
    model = Pro
    form_class = ProForm
    template_name = "planners/pro_form.html"
    success_url = reverse_lazy("planners:pro_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["all_subdepartments"] = Subdepartment.objects.order_by("subdepartment")
        context["selected_subdepartment_ids"] = set()
        return context

    def form_valid(self, form):
        response = super().form_valid(form)

        selected = self.request.POST.getlist("subdepartments")
        self._update_subdepartments(self.object, selected)

        messages.success(
            self.request,
            f"PRO '{self.object.pro_name}' je uspešno kreiran.",
        )
        return response


class ProUpdateView(PlannerAccessMixin, ProSubdepartmentMixin, UpdateView):
    model = Pro
    form_class = ProForm
    template_name = "planners/pro_form.html"
    success_url = reverse_lazy("planners:pro_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["all_subdepartments"] = Subdepartment.objects.order_by("subdepartment")

        active_ids = ProSubdepartment.objects.filter(
            pro=self.object,
            active=True,
        ).values_list("subdepartment_id", flat=True)

        context["selected_subdepartment_ids"] = set(active_ids)
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        selected = self.request.POST.getlist("subdepartments")
        self._update_subdepartments(self.object, selected)

        messages.info(
            self.request,
            f"PRO '{self.object.pro_name}' je uspešno ažuriran.",
        )
        return response


class ProDeleteView(PlannerAccessMixin, DeleteView):
    model = Pro
    template_name = "planners/confirm_delete.html"
    success_url = reverse_lazy("planners:pro_list")

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        pro_name = self.object.pro_name
        response = super().delete(request, *args, **kwargs)

        messages.error(
            request,
            f"PRO '{pro_name}' je obrisan.",
        )
        return response


class POSummaryLookupForm(forms.Form):
    pro = forms.CharField(
        label="POSummary PRO",
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )


class POSummaryLookupView(PlannerAccessMixin, FormView):
    template_name = "planners/pro_form_posum.html"
    form_class = POSummaryLookupForm

    def form_valid(self, form):
        pro_val = form.cleaned_data["pro"].strip()

        query = """
            SELECT TOP (1)
               [pro],
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

        try:
            with connections["posummary"].cursor() as cursor:
                cursor.execute(query, [pro_val])
                row = cursor.fetchone()
        except Exception as e:
            messages.error(self.request, f"Error while querying POSummary: {e}")
            return self.form_invalid(form)

        if not row:
            messages.error(self.request, f"No POSummary data found for PRO '{pro_val}'.")
            return self.form_invalid(form)

        cols = ["pro", "style", "color", "size", "qty", "delivery_date", "status", "destination", "tpp", "skeda"]
        fetched = dict(zip(cols, row))

        dd = fetched.get("delivery_date")

        if isinstance(dd, datetime):
            dd = dd.date()
        elif isinstance(dd, date):
            pass  # already date
        else:
            dd = None

        fetched["delivery_date"] = dd.isoformat() if dd else None

        # store in session
        self.request.session["posummary_fetched"] = fetched
        self.request.session.modified = True

        return redirect("planners:posummary_pro_create")


class POSummaryProCreateView(PlannerAccessMixin, ProSubdepartmentMixin, CreateView):
    model = Pro
    form_class = ProForm
    template_name = "planners/pro_form_from_posummary.html"
    success_url = reverse_lazy("planners:pro_list")

    def get_initial(self):
        init = super().get_initial()
        fetched = self.request.session.get("posummary_fetched")
        if not fetched:
            return init

        init["pro_name"] = fetched.get("pro") or ""
        init["style"] = fetched.get("style") or ""
        init["color"] = fetched.get("color") or ""
        init["size"] = fetched.get("size") or ""
        init["qty"] = fetched.get("qty") or None

        dd = fetched.get("delivery_date")
        if dd:
            try:
                # dd in session is ISO string
                if isinstance(dd, str):
                    # init["del_date"] = datetime.date.fromisoformat(dd)
                    init["del_date"] = date.fromisoformat(dd)
                elif isinstance(dd, datetime):
                    init["del_date"] = dd.date()
                elif isinstance(dd, datetime.date):
                    init["del_date"] = dd
                else:
                    init["del_date"] = None
            except Exception:
                init["del_date"] = None

        s = fetched.get("status")
        s_str = str(s).strip().lower() if s is not None else ""
        init["status"] = True if (s_str == "open" or s in (1, "1", True)) else False

        init["destination"] = fetched.get("destination") or ""
        init["tpp"] = fetched.get("tpp") or ""
        init["skeda"] = fetched.get("skeda") or ""
        return init

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["all_subdepartments"] = Subdepartment.objects.order_by("subdepartment")
        ctx["selected_subdepartment_ids"] = set()
        ctx["posummary_preview"] = self.request.session.get("posummary_fetched")
        ctx["from_posummary"] = True
        return ctx

    def form_valid(self, form):
        # defensive: ensure session still has the fetched data
        fetched = self.request.session.get("posummary_fetched")
        if not fetched:
            messages.error(self.request, "POSummary data expired — please fetch the PRO again.")
            return redirect("planners:posummary_lookup")

        # Ensure required fields from POSummary are applied if form didn't override them
        # (e.g. tpp/skeda might be missing from form post if widget name differs)
        try:
            # prefer values posted in the form; fallback to session fetched
            if not form.cleaned_data.get("tpp"):
                form.instance.tpp = fetched.get("tpp") or ""
            if not form.cleaned_data.get("skeda"):
                form.instance.skeda = fetched.get("skeda") or ""
        except Exception:
            # ignore and rely on whatever form provided
            pass

        # Force Active status when created from POSummary
        form.instance.status = True

        response = super().form_valid(form)

        # update subdepartments
        selected = self.request.POST.getlist("subdepartments")
        self._update_subdepartments(self.object, selected)

        # clear session fetch after successful create
        if "posummary_fetched" in self.request.session:
            del self.request.session["posummary_fetched"]
            self.request.session.modified = True

        messages.success(self.request, f"PRO '{self.object.pro_name}' created from POSummary.")
        return response

    def get(self, request, *args, **kwargs):
        if "posummary_fetched" not in request.session:
            messages.error(request, "No POSummary data found in session — please fetch a PRO first.")
            return redirect("planners:posummary_lookup")
        return super().get(request, *args, **kwargs)


class UpdateAllProFromPOSummaryView(PlannerAccessMixin, View):

    def post(self, request, *args, **kwargs):

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

        updated = 0
        unchanged = 0
        set_inactive = 0

        # ---------- LOG SETUP ----------
        log_dir = os.path.join(settings.BASE_DIR, "log")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "pro_posummary_update.txt")

        pros = Pro.objects.filter(status=True)
        now = datetime.now()

        try:
            with connections["posummary"].cursor() as cursor, \
                 open(log_path, "a", encoding="utf-8") as log_file:

                # ---------- START LOG ----------
                log_file.write("\n" + "=" * 60 + "\n")
                log_file.write(
                    f"{now} | POSummary BULK UPDATE STARTED\n"
                    f"Triggered by: {request.user}\n"
                    f"Active PRO count: {pros.count()}\n"
                )

                for pro in pros:
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

                    # ---------- SKU ----------
                    style_part = (style or "")[:9].ljust(9)
                    color_part = (color or "")[:4].ljust(4)
                    size_part = size or ""
                    new_sku = f"{style_part}{color_part}{size_part}"

                    if new_sku != pro.sku:
                        changes.append(f"sku: '{pro.sku}' → '{new_sku}'")
                        pro.sku = new_sku

                    # ---------- QTY ----------
                    if qty is not None and qty != pro.qty:
                        changes.append(f"qty: {pro.qty} → {qty}")
                        pro.qty = qty

                    # ---------- DELIVERY DATE ----------
                    if isinstance(delivery_date, datetime):
                        delivery_date = delivery_date.date()

                    if delivery_date != pro.del_date:
                        changes.append(f"del_date: {pro.del_date} → {delivery_date}")
                        pro.del_date = delivery_date

                    # ---------- DESTINATION ----------
                    destination = destination or ""
                    if destination != pro.destination:
                        changes.append(
                            f"destination: '{pro.destination}' → '{destination}'"
                        )
                        pro.destination = destination

                    # ---------- TPP ----------
                    tpp = tpp or ""
                    if tpp != pro.tpp:
                        changes.append(f"tpp: '{pro.tpp}' → '{tpp}'")
                        pro.tpp = tpp

                    # ---------- SKEDA ----------
                    skeda = skeda or ""
                    if skeda != pro.skeda:
                        changes.append(f"skeda: '{pro.skeda}' → '{skeda}'")
                        pro.skeda = skeda

                    # ---------- STATUS ----------
                    status_str = str(status_raw).strip().lower()
                    if status_str == "closed" and pro.status:
                        pro.status = False
                        set_inactive += 1
                        changes.append("status: Active → Inactive")

                    # ---------- SAVE + LOG ----------
                    if changes:
                        pro.save()
                        updated += 1

                        log_file.write(
                            f"{datetime.now()} | "
                            f"PRO {pro.pro_name} | "
                            + " | ".join(changes)
                            + "\n"
                        )
                    else:
                        unchanged += 1

                # ---------- FINISH LOG ----------
                log_file.write(
                    f"{datetime.now()} | POSummary BULK UPDATE FINISHED\n"
                    f"Updated: {updated}, Unchanged: {unchanged}, Set Inactive: {set_inactive}\n"
                )
                log_file.write("=" * 60 + "\n")

            messages.success(
                request,
                f"POSummary sync finished. "
                f"Updated: {updated}, "
                f"Unchanged: {unchanged}, "
                f"Set Inactive: {set_inactive}"
            )

        except Exception as e:
            messages.error(
                request,
                f"Error during POSummary synchronization: {e}"
            )

        return redirect("planners:pro_list")

    def get(self, request, *args, **kwargs):
        return redirect("planners:pro_list")





# ---------- ROUTING  ---------


class RoutingListView(PlannerAccessMixin, ListView):
    model = Routing
    template_name = "planners/routing_list.html"
    context_object_name = "routings"
    paginate_by = None
    # paginate_by = 50

    def get_queryset(self):
        return (
            Routing.objects
            .select_related("subdepartment")
            .annotate(op_count=Count("routing_operations"))
            .order_by("sku", "version")
        )


class RoutingOperationByRoutingListView(PlannerAccessMixin, ListView):
    model = RoutingOperation
    template_name = "planners/routing_operation_list.html"
    context_object_name = "routing_ops"
    paginate_by = None
    # paginate_by = 50

    def get_queryset(self):
        routing_id = self.kwargs["routing_id"]
        return (
            RoutingOperation.objects
            .filter(routing_id=routing_id)
            .select_related("routing", "operation", "routing__subdepartment")
            .order_by("id")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        routing = Routing.objects.select_related("subdepartment").get(pk=self.kwargs["routing_id"])
        context["current_routing"] = routing
        return context


class RoutingForm(forms.ModelForm):
    DECLARATION_CHOICES = [
        ("", "— Select —"),
        ("Operator", "Operator"),
        ("Team", "Team"),
    ]

    declaration_type = forms.ChoiceField(
        choices=DECLARATION_CHOICES,
        required=True,
        label="Declaration type",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    status = forms.BooleanField(
        required=False,
        label="Active",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = Routing
        fields = [
            "sku",
            "subdepartment",
            "version",
            "version_description",
            "declaration_type",
            "ready",
            "status",
        ]
        widgets = {
            "sku": forms.TextInput(attrs={"class": "form-control"}),
            "version": forms.TextInput(attrs={"class": "form-control"}),
            "version_description": forms.TextInput(attrs={"class": "form-control"}),
            "subdepartment": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # NEW routing → status checked by default
        if not self.instance or not self.instance.pk:
            self.fields["status"].initial = True
        else:
            # EDIT MODE → lock key fields
            self.fields["sku"].disabled = True
            self.fields["subdepartment"].disabled = True
            self.fields["version"].disabled = True

            self.fields["sku"].widget.attrs.setdefault("readonly", "readonly")
            self.fields["version"].widget.attrs.setdefault("readonly", "readonly")

        # `ready` is backend-controlled
        self.fields["ready"].disabled = True

    def clean_sku(self):
        sku = self.cleaned_data.get("sku", "").strip()

        if len(sku) not in (14, 15):
            raise forms.ValidationError(
                "SKU must be exactly 14 or 15 characters long."
            )

        return sku

    def clean_declaration_type(self):
        value = self.cleaned_data.get("declaration_type")
        if not value:
            raise forms.ValidationError(
                "Please select declaration type (Operator or Team)."
            )
        if value not in ("Operator", "Team"):
            raise forms.ValidationError("Invalid declaration type.")
        return value


class RoutingCreateView(PlannerAccessMixin, CreateView):
    model = Routing
    form_class = RoutingForm
    template_name = "planners/routing_form.html"
    success_url = reverse_lazy("planners:routing_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f"Routing created: SKU '{self.object.sku}', "
            f"Subdepartment '{self.object.subdepartment.subdepartment}', "
            f"Version '{self.object.version}'.",
        )

        return redirect(
            "planners:routing_operation_by_routing",
            routing_id=self.object.pk,
        )


class RoutingUpdateView(PlannerAccessMixin, UpdateView):
    model = Routing
    form_class = RoutingForm
    template_name = "planners/routing_form.html"
    success_url = reverse_lazy("planners:routing_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.info(
            self.request,
            f"Routing updated: SKU '{self.object.sku}', "
            f"Subdepartment '{self.object.subdepartment.subdepartment}', "
            f"Version '{self.object.version}'.",
        )
        return response


class RoutingDeleteView(PlannerAccessMixin, DeleteView):
    model = Routing
    template_name = "planners/confirm_delete.html"
    success_url = reverse_lazy("planners:routing_list")

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        sku = self.object.sku
        sd_name = self.object.subdepartment.subdepartment
        version = self.object.version

        response = super().delete(request, *args, **kwargs)

        messages.error(
            request,
            f"Routing deleted: SKU '{sku}', "
            f"Subdepartment '{sd_name}', "
            f"Version '{version}'.",
        )
        return response


class RoutingCopySelectForm(forms.Form):
    """
    STEP 1:
    - target_sku: novi SKU za koji pravimo routing
    - source_routing: postojeći routing iz kog kopiramo operations
    """
    target_sku = forms.CharField(
        max_length=100,
        label="SKU for which to create routing",
        widget=forms.TextInput(attrs={"class": "form-control"})
    )

    source_routing = forms.ModelChoiceField(
        label="Routing from which to copy",
        queryset=Routing.objects.select_related("subdepartment").order_by(
            "sku", "subdepartment__subdepartment", "version"
        ),
        widget=forms.Select(attrs={"class": "form-select"})
    )

    def clean_target_sku(self):
        value = self.cleaned_data["target_sku"].strip()
        if not value:
            raise forms.ValidationError("Please enter target SKU.")
        return value


class RoutingCopyStep1View(PlannerAccessMixin, FormView):
    """
    Prvi ekran: unesemo novi SKU + izaberemo routing koji kopiramo.
    """
    template_name = "planners/routing_copy_step1.html"
    form_class = RoutingCopySelectForm

    def form_valid(self, form):
        target_sku = form.cleaned_data["target_sku"]
        source_routing = form.cleaned_data["source_routing"]

        # Redirect na STEP 2 sa parametrima u query stringu
        url = (
            reverse("planners:routing_copy_step2")
            + f"?target_sku={target_sku}&source_id={source_routing.pk}"
        )
        return redirect(url)


class RoutingCopyStep11View(RoutingCopyStep1View):
    """
    Quick-copy entrypoint when user clicks 'Copy' on a routing row.
    Does NOT pass custom kwargs into form constructor (avoids BaseForm.__init__ errors).
    Instead it customizes the already-created form in get_form().
    """
    def get_form(self, form_class=None):
        # instantiate form the normal way (FormView will call form_class(**get_form_kwargs()))
        form = super().get_form(form_class)

        # try to read from_routing_id from GET or POST
        from_routing_id = self.request.GET.get("from_routing_id") or self.request.POST.get("from_routing_id")
        if not from_routing_id:
            return form

        try:
            src = Routing.objects.select_related("subdepartment").get(pk=from_routing_id)
        except (Routing.DoesNotExist, ValueError, TypeError):
            # invalid id -> return form unmodified
            return form

        # build base queryset in same order as RoutingCopySelectForm would do
        base_qs = Routing.objects.select_related("subdepartment").order_by(
            "sku", "subdepartment__subdepartment", "version"
        )

        # filter queryset to the source's subdepartment
        try:
            sd = src.subdepartment
            form.fields["source_routing"].queryset = base_qs.filter(subdepartment=sd)
        except Exception:
            # if anything odd happens, ignore and leave queryset as-is
            pass

        # pre-select the routing we clicked
        try:
            # set initial for the field (so the select shows the value)
            form.initial = dict(form.initial or {})
            form.initial["source_routing"] = src.pk
            # also set the bound value if no data (so it renders selected)
            if not self.request.method in ("POST", "PUT"):
                form.fields["source_routing"].initial = src.pk
        except Exception:
            pass

        return form


class RoutingCopyStep2View(PlannerAccessMixin, TemplateView):
    """
    Drugi ekran:
      - prikaz svih RoutingOperation za izabrani routing
      - čekiramo koje želimo da kopiramo
      - potvrdom kreiramo novi Routing (ako ne postoji)
        + nove RoutingOperation za novi SKU
      - nakon kopije: izračunava se i ažurira target_routing.ready
    """
    template_name = "planners/routing_copy_step2.html"

    def _get_source_and_target(self):
        """
        Helper za izvlačenje source_routing i target_sku
        iz GET/POST parametara.
        """
        source_id = self.request.GET.get("source_id") or self.request.POST.get("source_id")
        target_sku = self.request.GET.get("target_sku") or self.request.POST.get("target_sku")

        if not source_id or not target_sku:
            return None, None

        try:
            source = Routing.objects.select_related("subdepartment").get(pk=source_id)
        except Routing.DoesNotExist:
            return None, None

        return source, target_sku.strip()

    def get(self, request, *args, **kwargs):
        source, target_sku = self._get_source_and_target()

        if not source or not target_sku:
            messages.error(request, "Invalid copy parameters. Please start again.")
            return redirect("planners:routing_copy_step1")

        routing_ops = (
            RoutingOperation.objects
            .filter(routing=source)
            .select_related("operation")
            .order_by("id")
        )

        context = {
            "source_routing": source,
            "target_sku": target_sku,
            "routing_ops": routing_ops,
        }
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        source, target_sku = self._get_source_and_target()

        if not source or not target_sku:
            messages.error(request, "Invalid copy parameters. Please start again.")
            return redirect("planners:routing_copy_step1")

        selected_ids = request.POST.getlist("selected_ops")
        if not selected_ids:
            messages.error(request, "Please select at least one operation to copy.")
            url = (
                reverse("planners:routing_copy_step2")
                + f"?target_sku={target_sku}&source_id={source.pk}"
            )
            return redirect(url)

        # 1) napravi ili nađi ciljnu Routing kombinaciju
        target_routing, created_routing = Routing.objects.get_or_create(
            sku=target_sku,
            subdepartment=source.subdepartment,
            version=source.version,
            defaults={
                "version_description": source.version_description,
                "declaration_type": source.declaration_type,
                "status": source.status,
                "ready": False,   # novi routing nije "ready" dok ga ne završiš
            },
        )

        created_ops = 0
        skipped_ops = 0

        for op_id in selected_ids:
            try:
                src_ro = RoutingOperation.objects.get(pk=op_id, routing=source)
            except RoutingOperation.DoesNotExist:
                continue

            obj, created = RoutingOperation.objects.get_or_create(
                routing=target_routing,
                operation=src_ro.operation,
                defaults={
                    "operation_description": src_ro.operation_description,
                    "smv": src_ro.smv,
                    "smv_ita": src_ro.smv_ita,
                    "final_operation": src_ro.final_operation,
                },
            )
            if created:
                created_ops += 1
            else:
                skipped_ops += 1

        msg = (
            f"Copied {created_ops} operation(s) from "
            f"{source.sku} / {source.subdepartment} / {source.version} "
            f"to SKU '{target_routing.sku}'."
        )
        if skipped_ops:
            msg += f" {skipped_ops} operation(s) already existed and were skipped."

        messages.success(request, msg)

        # -----------------------------
        # NOVO: update target_routing.ready
        # -----------------------------
        try:
            ops_qs = target_routing.routing_operations.all()
            total_ops = ops_qs.count()
            final_ops = ops_qs.filter(final_operation=True).count()

            new_ready = (total_ops >= 1 and final_ops == 1)
            if target_routing.ready != new_ready:
                target_routing.ready = new_ready
                target_routing.save(update_fields=["ready", "updated_at"])
                messages.info(
                    request,
                    f"Routing '{target_routing.sku}' ready status updated to: {'Ready' if new_ready else 'Not ready'}."
                )
        except Exception as e:
            # ne smemo pucati kopiranje zbog problema u update-u statusa
            messages.warning(request, f"Warning while updating routing ready status: {e}")

        # Odmah prikažemo listu operation-a za novi routing
        # return redirect(
        #     "planners:routing_operation_by_routing",
        #     routing_id=target_routing.pk,
        # )
        # Vracamo na routing list
        return redirect("planners:routing_list")


# ---------- OPERATION  ---------


class OperationListView(PlannerAccessMixin, ListView):
    model = Operation
    template_name = "planners/operation_list.html"
    context_object_name = "operations"
    paginate_by = None
    # paginate_by = 50

    def get_queryset(self):
        return (
            Operation.objects.select_related("subdepartment")
            .order_by("subdepartment__subdepartment", "name")
        )


class OperationForm(forms.ModelForm):
    status = forms.BooleanField(
        required=False,
        label="Active",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = Operation
        fields = [
            "name",
            "subdepartment",
            "description",
            "status",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.TextInput(attrs={"class": "form-control"}),
            "subdepartment": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Create mode → status default = True
        if not self.instance or not self.instance.pk:
            self.fields["status"].initial = True

        # Edit mode → lock name + lock subdepartment
        if self.instance and self.instance.pk:
            self.fields["name"].widget.attrs["readonly"] = True

            # 🔒 lock subdepartment like in routing
            self.fields["subdepartment"].disabled = True
            self.fields["subdepartment"].widget.attrs["readonly"] = True


class OperationCreateView(PlannerAccessMixin, CreateView):
    model = Operation
    form_class = OperationForm
    template_name = "planners/operation_form.html"
    success_url = reverse_lazy("planners:operation_list")

    def form_valid(self, form):
        response = super().form_valid(form)

        messages.success(
            self.request,
            f"Operation created: '{self.object.name}' "
            f"for Subdepartment '{self.object.subdepartment.subdepartment}'.",
        )
        return response


class OperationUpdateView(PlannerAccessMixin, UpdateView):
    model = Operation
    form_class = OperationForm
    template_name = "planners/operation_form.html"
    success_url = reverse_lazy("planners:operation_list")

    def form_valid(self, form):
        response = super().form_valid(form)

        messages.info(
            self.request,
            f"Operation updated: '{self.object.name}' "
            f"for Subdepartment '{self.object.subdepartment.subdepartment}'.",
        )
        return response


class OperationDeleteView(PlannerAccessMixin, DeleteView):
    model = Operation
    template_name = "planners/confirm_delete.html"
    success_url = reverse_lazy("planners:operation_list")

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        op_name = self.object.name
        sd_name = self.object.subdepartment.subdepartment

        response = super().delete(request, *args, **kwargs)

        messages.error(
            request,
            f"Operation deleted: '{op_name}' "
            f"from Subdepartment '{sd_name}'.",
        )
        return response


# ---------- ROUTING_OPERATION ---------


class RoutingReadyMixin:
    """
    Održava polje Routing.ready u skladu sa routing operation linijama.

    Pravilo:
      - postoji bar JEDAN RoutingOperation za dati routing
      - i TAČNO jedan ima final_operation=True
        → routing.ready = True
      - u svim ostalim slučajevima → routing.ready = False
    """
    def update_routing_ready(self, routing: Routing):
        qs = routing.routing_operations.all()
        total_ops = qs.count()
        final_ops = qs.filter(final_operation=True).count()

        routing.ready = (total_ops >= 1 and final_ops == 1)
        routing.save(update_fields=["ready", "updated_at"])


class RoutingOperationListView(PlannerAccessMixin, ListView):
    model = RoutingOperation
    template_name = "planners/routing_operation_list.html"
    context_object_name = "routing_ops"
    paginate_by = None
    # paginate_by = 50

    def get_queryset(self):
        return (
            RoutingOperation.objects
            .select_related("routing", "operation", "routing__subdepartment")
            .order_by("routing__sku", "id")
        )


class RoutingOperationForm(forms.ModelForm):
    class Meta:
        model = RoutingOperation
        fields = [
            "routing",
            "operation",
            "operation_description",
            "smv",
            "smv_ita",
            "final_operation",
        ]
        widgets = {
            "routing": forms.Select(
                attrs={"class": "form-select", "id": "id_routing"}
            ),
            "operation": forms.Select(
                attrs={"class": "form-select", "id": "id_operation"}
            ),
            "operation_description": forms.TextInput(attrs={"class": "form-control"}),
            "smv": forms.NumberInput(attrs={"class": "form-control", "step": "0.001"}),
            "smv_ita": forms.NumberInput(attrs={"class": "form-control", "step": "0.001"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # SMV polja moraju da se unesu
        self.fields["smv"].required = True
        self.fields["smv_ita"].required = False

        # -------- ROUTING QUERYSET --------
        base_routing_qs = (
            Routing.objects
            .select_related("subdepartment")
            .order_by("sku", "version")
        )

        if self.instance and self.instance.pk and self.instance.routing_id:
            # EDIT MODE → dozvoli SVE active + trenutni routing (čak i ako je inactive)
            self.fields["routing"].queryset = base_routing_qs.filter(
                Q(status=True) | Q(pk=self.instance.routing_id)
            )
        else:
            # CREATE MODE → samo active
            self.fields["routing"].queryset = base_routing_qs.filter(status=True)

        # -------- OPERATION QUERYSET (samo active, osim instance u edit modu) --------
        base_ops_qs = (
            Operation.objects
            .select_related("subdepartment")
            .order_by("subdepartment__subdepartment", "name")
        )

        if self.instance and self.instance.pk and self.instance.operation_id:
            # EDIT MODE → svi active + ova operation (čak i ako je inactive)
            base_ops_qs = base_ops_qs.filter(
                Q(status=True) | Q(pk=self.instance.operation_id)
            )
        else:
            # CREATE MODE → samo active
            base_ops_qs = base_ops_qs.filter(status=True)

        self.fields["operation"].queryset = base_ops_qs

        # -------- Filtriranje operacija po subdepartmentu iz izabranog routinga --------
        routing_obj = None

        # 1) routing iz POST-a (create)
        if self.data.get("routing"):
            try:
                routing_obj = Routing.objects.select_related("subdepartment").get(
                    pk=self.data.get("routing")
                )
            except Routing.DoesNotExist:
                routing_obj = None
        # 2) ili iz instance (edit mode / initial)
        elif self.instance and self.instance.pk and self.instance.routing_id:
            routing_obj = self.instance.routing

        # Filtriranje po subdepartmentu ima smisla samo kod NOVOG zapisa
        if routing_obj and not (self.instance and self.instance.pk):
            self.fields["operation"].queryset = base_ops_qs.filter(
                subdepartment=routing_obj.subdepartment
            )


class RoutingOperationCreateView(RoutingReadyMixin, PlannerAccessMixin, CreateView):
    model = RoutingOperation
    form_class = RoutingOperationForm
    template_name = "planners/routing_operation_form.html"
    success_url = reverse_lazy("planners:routing_operation_list")

    def form_valid(self, form):
        response = super().form_valid(form)

        # posle kreiranja – izračunaj ready za taj routing
        self.update_routing_ready(self.object.routing)

        messages.success(
            self.request,
            f"✔ Created Routing Operation → "
            f"{self.object.routing.sku} (v{self.object.routing.version}) → "
            f"{self.object.operation.name}",
        )
        return response


class RoutingOperationUpdateView(RoutingReadyMixin, PlannerAccessMixin, UpdateView):
    model = RoutingOperation
    form_class = RoutingOperationForm
    template_name = "planners/routing_operation_form.html"
    success_url = reverse_lazy("planners:routing_operation_list")

    def form_valid(self, form):
        # routing / operation ne smeju da se menjaju (čak ni kroz dev tools)
        original = self.get_object()
        form.instance.routing = original.routing
        form.instance.operation = original.operation

        response = super().form_valid(form)

        # posle edit-a – opet izračunaj ready
        self.update_routing_ready(self.object.routing)

        messages.info(
            self.request,
            f"Updated Routing Operation → "
            f"{self.object.routing.sku} (v{self.object.routing.version}) → "
            f"{self.object.operation.name}",
        )
        return response


class RoutingOperationDeleteView(RoutingReadyMixin, PlannerAccessMixin, DeleteView):
    model = RoutingOperation
    template_name = "planners/confirm_delete.html"
    success_url = reverse_lazy("planners:routing_operation_list")

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        routing = obj.routing  # zapamti pre brisanja

        messages.error(
            request,
            f"⚠ Deleted Routing Operation → "
            f"{obj.routing.sku} (v{obj.routing.version}) → {obj.operation.name}",
        )

        response = super().delete(request, *args, **kwargs)

        # posle brisanja – ponovo izračunaj ready
        self.update_routing_ready(routing)

        return response



# ---------- LOGIN OPERATOR ----------


class LoginOperatorForm(forms.ModelForm):
    class Meta:
        model = LoginOperator
        fields = "__all__"
        widgets = {
            "login_actual": forms.DateTimeInput(
                format="%d.%m.%Y. %H:%M",
                attrs={"class": "vTextField"},
            ),
            "logoff_actual": forms.DateTimeInput(
                format="%d.%m.%Y. %H:%M",
                attrs={"class": "vTextField"},
            ),
            "login_team_date": forms.DateInput(
                format="%d.%m.%Y.",
                attrs={"class": "vDateField"},
            ),
            "logoff_team_date": forms.DateInput(
                format="%d.%m.%Y.",
                attrs={"class": "vDateField"},
            ),
            "login_team_time": forms.TimeInput(
                format="%H:%M",
                attrs={"class": "vTimeField"},
            ),
            "logoff_team_time": forms.TimeInput(
                format="%H:%M",
                attrs={"class": "vTimeField"},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # input formati koje Django očekuje pri submitu
        self.fields["login_actual"].input_formats = ["%d.%m.%Y. %H:%M"]
        self.fields["logoff_actual"].input_formats = ["%d.%m.%Y. %H:%M"]
        self.fields["login_team_date"].input_formats = ["%d.%m.%Y."]
        self.fields["logoff_team_date"].input_formats = ["%d.%m.%Y."]
        self.fields["login_team_time"].input_formats = ["%H:%M"]
        self.fields["logoff_team_time"].input_formats = ["%H:%M"]

        # OPERATOR queryset = only active operators
        try:
            self.fields["operator"].queryset = Operator.objects.filter(act=True).order_by("badge_num")
        except Exception:
            pass

        # Make logoff fields optional in the form (should remain blank on create)
        if "logoff_actual" in self.fields:
            self.fields["logoff_actual"].required = False
        if "logoff_team_date" in self.fields:
            self.fields["logoff_team_date"].required = False
        if "logoff_team_time" in self.fields:
            self.fields["logoff_team_time"].required = False


class LoginOperatorListView(PlannerAccessMixin, ListView):
    model = LoginOperator
    template_name = "planners/login_operator_list.html"
    context_object_name = "login_operators"
    paginate_by = None

    def get_queryset(self):
        # Prikaži samo sesije gde je operator i dalje active (Operator.act = True)
        return (
            LoginOperator.objects
            .select_related("operator", "team_user")
            .order_by("-login_actual")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # count logins that still use OLD break logic (NULL)
        context["break_null_count"] = (
            LoginOperator.objects
            .filter(break_time__isnull=True)
            .count()
        )

        return context


class LoginOperatorCreateView(PlannerAccessMixin, CreateView):
    model = LoginOperator
    form_class = LoginOperatorForm
    template_name = "planners/login_operator_form.html"
    success_url = reverse_lazy("planners:login_operator_list")

    def get_form(self, form_class=None):
        """
        Customize form in create mode:
        - operator = only active
        - hide status (set to ACTIVE server-side) and hide login_actual + logoff fields
        - leave login_team_date and login_team_time VISIBLE so user can choose them
        """
        form = super().get_form(form_class)

        # limit operator queryset to active operators
        try:
            form.fields["operator"].queryset = Operator.objects.filter(act=True).order_by("badge_num")
        except Exception:
            pass

        # Hide status field in create mode and set initial to ACTIVE
        if "status" in form.fields:
            try:
                form.fields["status"].widget = HiddenInput()
                form.fields["status"].required = False
                form.initial.setdefault("status", "ACTIVE")
            except Exception:
                pass

        # Hide fields that must be filled automatically on create:
        # keep login_team_date/login_team_time visible (so user can choose),
        # but hide login_actual and all logoff fields.
        hidden_fields = [
            "login_actual",
            "logoff_actual",
            "logoff_team_date",
            "logoff_team_time",
        ]
        for fname in hidden_fields:
            if fname in form.fields:
                form.fields[fname].widget = HiddenInput()
                form.fields[fname].required = False
                form.initial.setdefault(fname, None)

        # Ensure logoff fields are not required
        for fname in ("logoff_actual", "logoff_team_date", "logoff_team_time"):
            if fname in form.fields:
                form.fields[fname].required = False

        return form

    def form_valid(self, form):
        """
        Server-side defaults + validation (calendar/shift) done here:
        - login_actual = now (UTC)
        - login_team_date/time = chosen by user (if provided) or now_local by default
        - ensure selected Team user has Calendar entry for that date and that time is within shift
        - leave logoff_* empty on create
        """
        now_utc = timezone.now()
        now_local = timezone.localtime(now_utc)
        default_team_date = now_local.date()
        default_team_time = now_local.time().replace(microsecond=0)

        # Team user chosen in form
        team_user = form.cleaned_data.get("team_user")
        if not team_user:
            form.add_error("team_user", "Please select a Team user.")
            return self.form_invalid(form)

        # Use provided login_team_date/time if present, otherwise default to current local
        provided_date = form.cleaned_data.get("login_team_date")
        provided_time = form.cleaned_data.get("login_team_time")

        team_date = provided_date or default_team_date
        team_time = provided_time or default_team_time

        # Validate calendar entry exists for that team_user + team_date
        cal = Calendar.objects.filter(team_user=team_user, date=team_date).first()
        if not cal:
            form.add_error(
                "team_user",
                f"No calendar entry found for {team_user.username} on {team_date}."
            )
            return self.form_invalid(form)

        # check time within shift (inclusive)
        # Note: Calendar.shift_start/shift_end are time objects
        if not (cal.shift_start <= team_time <= cal.shift_end):
            form.add_error(
                "login_team_time",
                f"Selected time {team_time} is outside the team's shift ({cal.shift_start}–{cal.shift_end})."
            )
            return self.form_invalid(form)

        # fill instance server-side
        inst = form.instance

        # status default (hidden in form) → ensure ACTIVE if not provided
        try:
            inst.status = form.cleaned_data.get("status") or "ACTIVE"
        except Exception:
            inst.status = "ACTIVE"

        # login_actual stored as UTC
        inst.login_actual = now_utc
        inst.login_team_date = team_date
        inst.login_team_time = team_time

        # ensure logoff fields blank on creation
        inst.logoff_actual = None
        inst.logoff_team_date = None
        inst.logoff_team_time = None

        response = super().form_valid(form)

        messages.success(
            self.request,
            f"Operator login created: Operator '{self.object.operator}', Team user '{self.object.team_user}'.",
        )
        return response


class LoginOperatorUpdateView(PlannerAccessMixin, UpdateView):
    model = LoginOperator
    form_class = LoginOperatorForm
    template_name = "planners/login_operator_form.html"
    success_url = reverse_lazy("planners:login_operator_list")

    # -------------------------------------------------
    # CONTEXT (for break dropdown 0–30)
    # -------------------------------------------------
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["range_0_30"] = range(0, 31)
        return ctx

    # -------------------------------------------------
    # FORM SETUP
    # -------------------------------------------------
    def get_form(self, form_class=None):
        """
        Hide actual login/logoff fields (we don't want them editable),
        but ensure their current values are present in form.initial so
        hidden inputs are rendered and browser posts them back.
        """
        form = super().get_form(form_class)
        obj = self.get_object()

        for fname in ("login_actual", "logoff_actual"):
            if fname in form.fields:
                form.fields[fname].widget = HiddenInput()
                form.fields[fname].required = False

                val = getattr(obj, fname, None)
                if val is not None:
                    form.initial.setdefault(fname, val)

        return form

    # -------------------------------------------------
    # SAVE LOGIC
    # -------------------------------------------------
    def form_valid(self, form):
        """
        - handle quick break_time buttons (0 / 30)
        - preserve login_actual / logoff_actual
        - validate calendar / shift
        """

        # -------------------------------------------------
        # HANDLE QUICK BREAK BUTTONS (override dropdown)
        # -------------------------------------------------
        set_break = self.request.POST.get("set_break")
        if set_break in ("0", "30"):
            form.instance.break_time = int(set_break)

        # -------------------------------------------------
        # PRESERVE ACTUAL TIMESTAMPS
        # -------------------------------------------------
        obj = self.get_object()

        if not form.cleaned_data.get("login_actual"):
            form.instance.login_actual = obj.login_actual

        if not form.cleaned_data.get("logoff_actual"):
            form.instance.logoff_actual = obj.logoff_actual

        # -------------------------------------------------
        # VALIDATE CALENDAR / SHIFT
        # -------------------------------------------------
        team_user = form.cleaned_data.get("team_user") or obj.team_user
        login_team_date = form.cleaned_data.get("login_team_date") or obj.login_team_date
        login_team_time = form.cleaned_data.get("login_team_time") or obj.login_team_time

        if not team_user:
            form.add_error("team_user", "Please select a Team user.")
            return self.form_invalid(form)

        if not login_team_date:
            form.add_error("login_team_date", "Please provide login team date.")
            return self.form_invalid(form)

        cal = Calendar.objects.filter(
            team_user=team_user,
            date=login_team_date
        ).first()

        if not cal:
            form.add_error(
                "team_user",
                f"No calendar entry found for {team_user.username} on {login_team_date}."
            )
            return self.form_invalid(form)

        if not login_team_time:
            form.add_error("login_team_time", "Please provide login team time.")
            return self.form_invalid(form)

        if not (cal.shift_start <= login_team_time <= cal.shift_end):
            form.add_error(
                "login_team_time",
                f"Selected time {login_team_time} is outside the team's shift "
                f"({cal.shift_start}–{cal.shift_end})."
            )
            return self.form_invalid(form)

        # -------------------------------------------------
        # SAVE
        # -------------------------------------------------
        response = super().form_valid(form)

        if set_break in ("0", "30"):
            messages.success(
                self.request,
                f"Break time set to {set_break} minutes."
            )
        else:
            messages.info(
                self.request,
                "Operator login updated."
            )

        return response


class LoginOperatorDeleteView(PlannerAccessMixin, DeleteView):
    model = LoginOperator
    template_name = "planners/confirm_delete.html"
    success_url = reverse_lazy("planners:login_operator_list")

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        op = obj.operator
        tu = obj.team_user

        response = super().delete(request, *args, **kwargs)

        messages.error(
            request,
            f"Operator login deleted: Operator '{op}', Team user '{tu}'.",
        )
        return response


# ---------- LOGOUT  ----------

class _LOStep1TeamUserForm(forms.Form):
    team_user = forms.ModelChoiceField(
        queryset=TeamUser.objects.filter(
            is_active=True,
            subdepartment__isnull=False
        ).order_by("username"),
        label="Select Team user",
        widget=forms.Select(attrs={
            "class": "form-select select2",
            "id": "id_lo_team_user",
        }),
    )


class _LOStep2OperatorsForm(forms.Form):
    operators = forms.ModelMultipleChoiceField(
        queryset=Operator.objects.none(),
        required=True,
        widget=forms.CheckboxSelectMultiple(
            attrs={"class": "form-check-input"}
        ),
        label="Active operators (today)",
    )

    def __init__(self, *args, **kwargs):
        qs = kwargs.pop("queryset", None)
        super().__init__(*args, **kwargs)
        if qs is not None:
            self.fields["operators"].queryset = qs


class _LOStep3TimeForm(forms.Form):
    logoff_team_time = forms.TimeField(
        label="Logoff team time",
        widget=forms.TimeInput(
            format="%H:%M",
            attrs={"class": "form-control"}
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["logoff_team_time"].input_formats = ["%H:%M"]


class LoginOperatorLogoutWizardView(PlannerAccessMixin, View):
    template_name = "planners/login_operator_logout_wizard.html"

    # ------------------
    # session helpers
    # ------------------
    def _get_wip(self, request):
        return request.session.get("logout_wip", {})

    def _save_wip(self, request, wip):
        request.session["logout_wip"] = wip
        request.session.modified = True

    def _render(self, request, step, form):
        percent = int((step - 1) / 3 * 100)
        return render(request, self.template_name, {
            "step": step,
            "form": form,
            "percent": percent,
        })

    # ------------------
    # GET
    # ------------------
    def get(self, request):
        step = int(request.GET.get("step", 1))
        wip = self._get_wip(request)

        if step == 1:
            form = _LOStep1TeamUserForm(
                initial={"team_user": wip.get("team_user")}
            )

        elif step == 2:
            if not wip.get("team_user"):
                return redirect("?step=1")

            today = timezone.localdate()

            sessions = LoginOperator.objects.filter(
                team_user_id=wip["team_user"],
                login_team_date=today,
                status="ACTIVE",
                logoff_actual__isnull=True,
            )

            ops_qs = Operator.objects.filter(
                pk__in=sessions.values_list("operator_id", flat=True)
            ).distinct().order_by("badge_num")

            form = _LOStep2OperatorsForm(
                queryset=ops_qs,
                initial={"operators": wip.get("operators", [])}
            )

        elif step == 3:
            form = _LOStep3TimeForm(
                initial={"logoff_team_time": wip.get("logoff_team_time")}
            )

        else:
            return redirect("?step=1")

        return self._render(request, step, form)

    # ------------------
    # POST
    # ------------------
    def post(self, request):
        step = int(request.POST.get("step", 1))
        wip = self._get_wip(request)

        if step == 1:
            form = _LOStep1TeamUserForm(request.POST)
            if form.is_valid():
                wip["team_user"] = form.cleaned_data["team_user"].id
                self._save_wip(request, wip)
                return redirect(request.path + "?step=2")

        elif step == 2:
            today = timezone.localdate()

            sessions = LoginOperator.objects.filter(
                team_user_id=wip["team_user"],
                login_team_date=today,
                status="ACTIVE",
                logoff_actual__isnull=True,
            )

            ops_qs = Operator.objects.filter(
                pk__in=sessions.values_list("operator_id", flat=True)
            ).distinct()

            form = _LOStep2OperatorsForm(request.POST, queryset=ops_qs)
            if form.is_valid():
                wip["operators"] = list(
                    form.cleaned_data["operators"].values_list("id", flat=True)
                )
                self._save_wip(request, wip)
                return redirect(request.path + "?step=3")


        elif step == 3:
            form = _LOStep3TimeForm(request.POST)
            if form.is_valid():
                wip["logoff_team_time"] = form.cleaned_data[
                    "logoff_team_time"
                ].isoformat()
                self._save_wip(request, wip)
                return redirect(
                    reverse("planners:login_operator_logout_save")
                )

        return self._render(request, step, form)


class LoginOperatorLogoutSaveView(PlannerAccessMixin, View):

    def get(self, request):
        wip = request.session.get("logout_wip")

        if not wip:
            messages.error(request, "No logout in progress.")
            return redirect("planners:login_operator_list")

        team_user = TeamUser.objects.get(pk=wip["team_user"])
        operator_ids = wip.get("operators", [])
        logoff_time = time.fromisoformat(wip["logoff_team_time"])
        today = timezone.localdate()

        calendar = Calendar.objects.filter(
            team_user=team_user,
            date=today
        ).first()

        if not calendar:
            messages.error(request, "No calendar entry for today.")
            return redirect(
                reverse("planners:login_operator_logout_wizard") + "?step=3"
            )

        if not (calendar.shift_start <= logoff_time <= calendar.shift_end):
            messages.error(
                request,
                f"Time outside shift ({calendar.shift_start}–{calendar.shift_end})."
            )
            return redirect(
                reverse("planners:login_operator_logout_wizard") + "?step=3"
            )

        now_utc = timezone.now()

        qs = LoginOperator.objects.filter(
            team_user=team_user,
            operator_id__in=operator_ids,
            login_team_date=today,
            status="ACTIVE",
            logoff_actual__isnull=True,
        )

        count = 0
        for lo in qs:
            lo.logoff_actual = now_utc
            lo.logoff_team_date = today
            lo.logoff_team_time = logoff_time
            lo.status = "COMPLETED"
            lo.save()
            count += 1

        request.session.pop("logout_wip", None)
        request.session.modified = True

        messages.success(request, f"{count} operators logged out.")
        return redirect("planners:login_operator_list")


class LoginOperatorLogoutCancelView(PlannerAccessMixin, View):
    def get(self, request):
        request.session.pop("logout_wip", None)
        request.session.modified = True
        messages.info(request, "Logout canceled.")
        return redirect("planners:login_operator_list")



# ---------- Manual logout operators  ---------


class ManualLogoutOperatorsView(LoginRequiredMixin, View):
    """
    Manual auto-logout for ACTIVE LoginOperator sessions.

    Behavior:
      - Selects ACTIVE sessions with login_team_date <= today.
      - For previous days: always completes the session.
      - For today:
          * completes ONLY if now > calendar.shift_end
          * otherwise skips (shift still active)
      - Writes a detailed log to:
        <project_root>/log/ManualLogoutOperators.txt
    """

    LOG_FILE = os.path.join(settings.BASE_DIR, "log", "ManualLogoutOperators.txt")

    def post(self, request, *args, **kwargs):
        now_utc = timezone.now()
        now_local = timezone.localtime(now_utc)
        today = now_local.date()

        sessions_qs = (
            LoginOperator.objects
            .filter(status="ACTIVE", login_team_date__lte=today)
            .select_related("team_user", "operator")
        )

        total = sessions_qs.count()
        completed = 0
        skipped_no_calendar = 0
        skipped_no_shift_end = 0
        skipped_shift_not_finished = 0
        failures = []

        completed_details = []
        skipped_details = []

        for session in sessions_qs:
            login_date = session.login_team_date

            try:
                calendar_entry = Calendar.objects.filter(
                    team_user=session.team_user,
                    date=login_date,
                ).first()

                if not calendar_entry:
                    skipped_no_calendar += 1
                    skipped_details.append({
                        "id": session.id,
                        "reason": "no calendar",
                        "team_user": getattr(session.team_user, "username", None),
                        "login_date": login_date,
                    })
                    continue

                if not calendar_entry.shift_end:
                    skipped_no_shift_end += 1
                    skipped_details.append({
                        "id": session.id,
                        "reason": "missing shift_end",
                        "team_user": getattr(session.team_user, "username", None),
                        "login_date": login_date,
                    })
                    continue

                # If session is today, check if shift already ended
                if login_date == today:
                    shift_end_dt = timezone.make_aware(
                        datetime.combine(login_date, calendar_entry.shift_end),
                        timezone.get_current_timezone()
                    )

                    if now_local < shift_end_dt:
                        skipped_shift_not_finished += 1
                        skipped_details.append({
                            "id": session.id,
                            "reason": "shift not finished yet",
                            "team_user": getattr(session.team_user, "username", None),
                            "login_date": login_date,
                        })
                        continue

                shift_end = calendar_entry.shift_end

                with transaction.atomic():
                    session.logoff_actual = now_utc
                    session.logoff_team_date = calendar_entry.date
                    session.logoff_team_time = shift_end
                    session.status = "COMPLETED"

                    session.save(update_fields=[
                        "logoff_actual",
                        "logoff_team_date",
                        "logoff_team_time",
                        "status",
                        "updated_at",
                    ])

                completed += 1

                # Human-readable operator label
                if session.operator:
                    badge = getattr(session.operator, "badge_num", "")
                    name = getattr(session.operator, "name", "")
                    op_label = f"{badge} - {name}".strip(" -")
                else:
                    op_label = "N/A"

                completed_details.append({
                    "id": session.id,
                    "operator": op_label,
                    "team_user": getattr(session.team_user, "username", None),
                    "login_team_date": login_date,
                    "logoff_team_time": shift_end,
                })

            except Exception as e:
                err = str(e)
                if len(err) > 300:
                    err = err[:297] + "..."
                failures.append((session.id, err))

        ignored = skipped_no_calendar + skipped_no_shift_end + skipped_shift_not_finished

        # Summary
        header = f"Manual auto-logout finished at {now_local.strftime('%d.%m.%Y %H:%M:%S')}:"
        summary_lines = [
            header,
            f"Total ACTIVE sessions considered: {total}",
            f"  • {completed} session(s) COMPLETED",
            f"  • {ignored} skipped "
            f"({skipped_shift_not_finished} shift not finished, "
            f"{skipped_no_shift_end} missing shift_end, "
            f"{skipped_no_calendar} no Calendar)",
        ]

        if failures:
            summary_lines.append(f"  • {len(failures)} session(s) failed due to errors")

        details_lines = []
        if completed_details:
            details_lines.extend(["", "Completed sessions:"])
            for d in completed_details:
                details_lines.append(
                    f"  - ID {d['id']}: Operator [{d['operator']}], "
                    f"TeamUser [{d['team_user']}], "
                    f"Login date [{d['login_team_date']}], "
                    f"Logoff team time [{d['logoff_team_time']}]"
                )

        if skipped_details:
            details_lines.extend(["", "Skipped sessions:"])
            for s in skipped_details:
                details_lines.append(
                    f"  - ID {s['id']}: TeamUser [{s.get('team_user')}], "
                    f"Login date [{s.get('login_date')}], "
                    f"Reason: {s['reason']}"
                )

        failure_lines = []
        if failures:
            failure_lines.extend(["", "Failures (exceptions):"])
            for sid, err in failures:
                failure_lines.append(f"  - ID {sid}: {err}")

        messages.info(
            request,
            f"Manual auto-logout finished: "
            f"{completed} completed, {ignored} skipped, {len(failures)} failed."
        )

        # Write logfile
        try:
            os.makedirs(os.path.dirname(self.LOG_FILE), exist_ok=True)
            with open(self.LOG_FILE, "a", encoding="utf-8") as f:
                f.write("\n" + "=" * 80 + "\n")
                for line in summary_lines + details_lines + failure_lines:
                    f.write(line + "\n")
                f.write("=" * 80 + "\n")
        except Exception as log_err:
            messages.error(
                request,
                f"Warning: could not write manual-logout log file: {log_err}"
            )

        return redirect("planners:login_operator_list")


# ---------- DECLARATIONS ----------


class DeclarationForm(forms.ModelForm):
    teamuser = forms.ModelChoiceField(
        queryset=TeamUser.objects.filter(is_active=True).order_by("username"),
        label="Team User",
        widget=forms.Select(attrs={"class": "form-select", "id": "id_teamuser"}),
    )

    operators = forms.ModelMultipleChoiceField(
        queryset=Operator.objects.filter(act=True).order_by("badge_num"),
        required=False,
        label="Operators",
        widget=forms.SelectMultiple(
            attrs={"class": "form-select select2-operators", "id": "id_operators"}
        ),
    )

    class Meta:
        model = Declaration
        fields = [
            "teamuser",
            "subdepartment",
            "pro",
            "routing",
            "routing_operation",
            "smv",
            "smv_ita",
            "qty",
            "operators",
        ]
        widgets = {
            "subdepartment": forms.Select(
                attrs={"class": "form-select", "id": "id_subdepartment"}
            ),
            "pro": forms.Select(attrs={"class": "form-select", "id": "id_pro"}),
            "routing": forms.Select(attrs={"class": "form-select", "id": "id_routing"}),
            "routing_operation": forms.Select(
                attrs={"class": "form-select", "id": "id_routing_operation"}
            ),
            "smv": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.001"}
            ),
            "smv_ita": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.001"}
            ),
            "qty": forms.NumberInput(
                attrs={"class": "form-control", "min": "1"}
            ),
        }

    def __init__(self, *args, **kwargs):
        # kwargs from view
        pro = kwargs.pop("pro", None)
        routing = kwargs.pop("routing", None)
        operators_qs = kwargs.pop("operators_qs", None)
        subdepartment = kwargs.pop("subdepartment", None)

        super().__init__(*args, **kwargs)

        instance = self.instance if self.instance.pk else None

        # -------------------------------------------------
        # Subdepartment (preserve on edit)
        # -------------------------------------------------
        if instance and instance.subdepartment:
            self.fields["subdepartment"].initial = instance.subdepartment

        # -------------------------------------------------
        # PRO queryset
        # - create: only active PROs
        # - edit: include instance.pro even if inactive
        # -------------------------------------------------
        pro_qs = Pro.objects.filter(status=True)

        if instance and instance.pro:
            pro_qs = pro_qs | Pro.objects.filter(pk=instance.pro.pk)

        self.fields["pro"].queryset = (
            pro_qs.distinct().order_by("del_date", "pro_name")
        )

        # -------------------------------------------------
        # Routing queryset (depends on PRO + subdepartment)
        # -------------------------------------------------
        effective_pro = pro or (instance.pro if instance else None)

        if effective_pro:
            qs = Routing.objects.filter(
                status=True,
                ready=True,
                sku__iexact=effective_pro.sku,
            )
            if subdepartment:
                qs = qs.filter(subdepartment=subdepartment)
            self.fields["routing"].queryset = qs.order_by("sku", "version")
        else:
            self.fields["routing"].queryset = Routing.objects.none()

        # -------------------------------------------------
        # Routing operation queryset (depends on routing)
        # -------------------------------------------------
        effective_routing = routing or (instance.routing if instance else None)

        if effective_routing:
            self.fields["routing_operation"].queryset = (
                effective_routing.routing_operations.all().order_by("id")
            )
        else:
            self.fields["routing_operation"].queryset = RoutingOperation.objects.none()

        # -------------------------------------------------
        # Operators queryset
        # -------------------------------------------------
        if operators_qs is not None:
            self.fields["operators"].queryset = operators_qs
        else:
            self.fields["operators"].queryset = (
                Operator.objects.filter(act=True).order_by("badge_num")
            )

        # -------------------------------------------------
        # Optional fields
        # -------------------------------------------------
        self.fields["smv"].required = False
        self.fields["smv_ita"].required = False


class _PStep1TeamUserForm(forms.Form):
    teamuser = forms.ModelChoiceField(
        queryset=TeamUser.objects.filter(
            is_active=True,
            subdepartment__isnull=False
        ).order_by("username"),
        label="Select Team user",
        widget=forms.Select(attrs={
            "class": "form-select",
            "id": "id_w_teamuser"
        }),
    )


class _PStep2DateForm(forms.Form):
    work_date = forms.DateField(
        label="Select date",
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": "form-control",
            }
        ),
    )


class _PStep2ProForm(forms.Form):
    pro = forms.ModelChoiceField(queryset=Pro.objects.filter(status=True).order_by("del_date", "pro_name"), label="Select PRO")

    def __init__(self, *args, **kwargs):
        subdepartment = kwargs.pop("subdepartment", None)
        super().__init__(*args, **kwargs)
        if subdepartment:
            # Only PROs linked to that subdepartment
            self.fields["pro"].queryset = (
                Pro.objects.filter(
                    pro_subdepartments__subdepartment=subdepartment,
                    pro_subdepartments__active=True,
                    status=True,
                )
                .distinct()
                .order_by("del_date", "pro_name")
            )
        self.fields["pro"].widget.attrs.update({"class": "form-select", "data-placeholder": "— Select PRO —"})


class _PStep3RoutingForm(forms.Form):
    routing = forms.ModelChoiceField(
        queryset=Routing.objects.none(),
        label="Select Routing",
        widget=forms.RadioSelect
    )

    def __init__(self, *args, **kwargs):
        pro = kwargs.pop("pro", None)
        subdepartment = kwargs.pop("subdepartment", None)
        super().__init__(*args, **kwargs)

        if not pro:
            self.fields["routing"].queryset = Routing.objects.none()
            return

        qs = Routing.objects.filter(
            status=True,
            ready=True,
            sku__iexact=pro.sku,
        )

        if subdepartment:
            qs = qs.filter(subdepartment=subdepartment)

        qs = qs.order_by("version")
        self.fields["routing"].queryset = qs

        # auto-select ako ima samo jedan routing
        if qs.count() == 1:
            self.initial["routing"] = qs.first().id


class _PStep4RoutingOperationForm(forms.Form):
    routing_operation = forms.ModelChoiceField(
        queryset=RoutingOperation.objects.none(),
        label="Select Operation",
        widget=forms.RadioSelect
    )

    def __init__(self, *args, **kwargs):
        routing = kwargs.pop("routing", None)
        super().__init__(*args, **kwargs)

        if not routing:
            self.fields["routing_operation"].queryset = RoutingOperation.objects.none()
            return

        qs = routing.routing_operations.all().order_by("id")
        self.fields["routing_operation"].queryset = qs

        # auto-select ako ima samo jedna operacija
        if qs.count() == 1:
            self.initial["routing_operation"] = qs.first().id


class _PStep5QtyForm(forms.Form):
    qty = forms.IntegerField(
        min_value=1,
        label="Quantity",
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "1", "style": "max-width:160px;"}),
    )


class _PStep6OperatorsForm(forms.Form):
    """
    Use SelectMultiple so we can apply select2 and achieve the same UI as edit page.
    The view provides queryset via the 'queryset' kwarg.
    """
    operators = forms.ModelMultipleChoiceField(
        queryset=Operator.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(
            attrs={"class": "form-check-input"}
        ),
        label="Operators",
    )

    def __init__(self, *args, **kwargs):
        qs = kwargs.pop("queryset", None)
        super().__init__(*args, **kwargs)
        if qs is not None:
            self.fields["operators"].queryset = qs


# Declaration CRUD + Wizard Views


class DeclarationListView(PlannerAccessMixin, ListView):
    model = Declaration
    template_name = "planners/declaration_list.html"
    context_object_name = "declarations"
    paginate_by = None

    def get_queryset(self):
        return (
            Declaration.objects
            .select_related("teamuser", "subdepartment", "pro", "routing", "routing_operation")
            .prefetch_related("operators")
            .annotate(op_count=Count("operators"))
            .order_by("-decl_date", "teamuser__username")
        )


class DeclarationDetailView(PlannerAccessMixin, DetailView):
    model = Declaration
    template_name = "planners/declaration_detail.html"
    context_object_name = "declaration"

    def get_queryset(self):
        return Declaration.objects.select_related("teamuser", "subdepartment", "pro", "routing", "routing_operation").prefetch_related("operators")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        d = self.object
        ctx["op_count"] = d.operators.count()
        ctx["created_at_fmt"] = d.created_at.strftime("%d.%m.%Y. %H:%M") if getattr(d, "created_at", None) else "-"
        ctx["updated_at_fmt"] = d.updated_at.strftime("%d.%m.%Y. %H:%M") if getattr(d, "updated_at", None) else "-"
        return ctx


class DeclarationUpdateView(PlannerAccessMixin, UpdateView):
    model = Declaration
    form_class = DeclarationForm
    template_name = "planners/declaration_form.html"
    success_url = reverse_lazy("planners:declaration_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        instance = self.get_object()

        # ===== KLJUČNO ZA EDIT =====
        # prosleđujemo INSTANCE vrednosti formi
        # da queryset-i ne budu prazni
        if instance.subdepartment:
            kwargs["subdepartment"] = instance.subdepartment

        if instance.pro:
            kwargs["pro"] = instance.pro

        if instance.routing:
            kwargs["routing"] = instance.routing

        # operators queryset (po potrebi možeš suziti)
        kwargs["operators_qs"] = Operator.objects.filter(
            act=True
        ).order_by("badge_num")

        return kwargs


class DeclarationDeleteView(PlannerAccessMixin, DeleteView):
    model = Declaration
    template_name = "planners/confirm_delete.html"
    success_url = reverse_lazy("planners:declaration_list")

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        pk = obj.id
        response = super().delete(request, *args, **kwargs)
        messages.error(request, f"Declaration #{pk} deleted.")
        return response


class DeclarationWizardPlannerView(PlannerAccessMixin, View):
    template_name = "planners/declaration_step_planner.html"

    # ------------------
    # session helpers
    # ------------------
    def _get_wip(self, request):
        return request.session.get("planner_declaration_wip", {})

    def _save_wip(self, request, wip):
        request.session["planner_declaration_wip"] = wip
        request.session.modified = True

    def _build_preview(self, wip):
        preview = {
            "teamuser": None,
            "subdepartment": None,
            "date": wip.get("work_date"),
            "pro": None,
            "routing": None,
            "routing_operation": None,
            "qty": wip.get("qty"),
        }

        if wip.get("teamuser"):
            try:
                tu = TeamUser.objects.get(pk=wip["teamuser"])
                preview["teamuser"] = tu.username
                preview["subdepartment"] = tu.subdepartment.subdepartment if tu.subdepartment else None
            except TeamUser.DoesNotExist:
                pass

        if wip.get("pro"):
            try:
                preview["pro"] = Pro.objects.get(pk=wip["pro"]).pro_name
            except Pro.DoesNotExist:
                pass

        if wip.get("routing"):
            try:
                r = Routing.objects.get(pk=wip["routing"])
                preview["routing"] = f"{r.sku} / {r.version}"
            except Routing.DoesNotExist:
                pass

        if wip.get("routing_operation"):
            try:
                ro = RoutingOperation.objects.select_related("operation").get(pk=wip["routing_operation"])
                preview["routing_operation"] = ro.operation.name
            except RoutingOperation.DoesNotExist:
                pass

        return preview

    def _render(self, request, step, form, wip):
        percent = int((step - 1) / 6 * 100)  # 7 steps
        return render(request, self.template_name, {
            "step": step,
            "form": form,
            "percent": percent,
            "wip_preview": self._build_preview(wip),
        })

    # ------------------
    # GET
    # ------------------
    def get(self, request):
        step = int(request.GET.get("step", 1))
        wip = self._get_wip(request)

        teamuser_subdep = None
        if wip.get("teamuser"):
            try:
                teamuser_subdep = TeamUser.objects.get(pk=wip["teamuser"]).subdepartment
            except TeamUser.DoesNotExist:
                pass

        if step == 1:
            form = _PStep1TeamUserForm(initial={"teamuser": wip.get("teamuser")})

        elif step == 2:
            form = _PStep2DateForm(initial={"work_date": wip.get("work_date")})


        elif step == 3:

            subdep = TeamUser.objects.get(pk=wip["teamuser"]).subdepartment
            form = _PStep2ProForm(request.POST, subdepartment=subdep)

        elif step == 4:
            pro = get_object_or_404(Pro, pk=wip.get("pro"))
            form = _PStep3RoutingForm(initial={"routing": wip.get("routing")}, pro=pro, subdepartment=teamuser_subdep)

        elif step == 5:
            routing = get_object_or_404(Routing, pk=wip.get("routing"))
            form = _PStep4RoutingOperationForm(
                initial={"routing_operation": wip.get("routing_operation")},
                routing=routing
            )

        elif step == 6:
            form = _PStep5QtyForm(initial={"qty": wip.get("qty")})

        elif step == 7:
            if not wip.get("work_date") or not wip.get("teamuser"):
                return redirect(reverse("planners:declaration_wizard") + "?step=1")

            work_date = date.fromisoformat(wip["work_date"])

            sessions = LoginOperator.objects.filter(
                team_user_id=wip["teamuser"],
                login_team_date=work_date,
            ).filter(status__in=['ACTIVE', 'COMPLETED'])


            ops_qs = Operator.objects.filter(
                pk__in=sessions.values_list("operator_id", flat=True)
            ).distinct().order_by("badge_num")

            form = _PStep6OperatorsForm(
                queryset=ops_qs,
                initial={"operators": wip.get("operators", [])}
            )

        else:
            return redirect(reverse("planners:declaration_wizard") + "?step=1")

        return self._render(request, step, form, wip)

    # ------------------
    # POST
    # ------------------
    def post(self, request):
        step = int(request.POST.get("step", 1))
        wip = self._get_wip(request)

        if step == 1:
            form = _PStep1TeamUserForm(request.POST)
            if form.is_valid():
                tu = form.cleaned_data["teamuser"]
                wip["teamuser"] = tu.id
                wip["subdepartment"] = tu.subdepartment_id
                self._save_wip(request, wip)
                return redirect(reverse("planners:declaration_wizard") + "?step=2")

        elif step == 2:
            form = _PStep2DateForm(request.POST)
            if form.is_valid():
                work_date = form.cleaned_data["work_date"]

                try:
                    calendar = Calendar.objects.get(
                        team_user_id=wip["teamuser"],
                        date=work_date
                    )
                except Calendar.DoesNotExist:
                    messages.error(request, "No calendar entry for this date.")
                    return redirect(reverse("planners:declaration_wizard") + "?step=2")

                wip["work_date"] = work_date.isoformat()
                wip["shift_start"] = calendar.shift_start.isoformat()
                self._save_wip(request, wip)
                return redirect(reverse("planners:declaration_wizard") + "?step=3")

        elif step == 3:
            form = _PStep2ProForm(request.POST)
            if form.is_valid():
                wip["pro"] = form.cleaned_data["pro"].id
                self._save_wip(request, wip)
                return redirect(reverse("planners:declaration_wizard") + "?step=4")

        elif step == 4:
            pro = get_object_or_404(Pro, pk=wip["pro"])
            form = _PStep3RoutingForm(request.POST, pro=pro)
            if form.is_valid():
                wip["routing"] = form.cleaned_data["routing"].id
                self._save_wip(request, wip)
                return redirect(reverse("planners:declaration_wizard") + "?step=5")

        elif step == 5:
            routing = get_object_or_404(Routing, pk=wip["routing"])
            form = _PStep4RoutingOperationForm(request.POST, routing=routing)
            if form.is_valid():
                ro = form.cleaned_data["routing_operation"]
                wip["routing_operation"] = ro.id

                self._save_wip(request, wip)
                return redirect(reverse("planners:declaration_wizard") + "?step=6")

        elif step == 6:
            form = _PStep5QtyForm(request.POST)
            if form.is_valid():
                wip["qty"] = form.cleaned_data["qty"]
                self._save_wip(request, wip)
                return redirect(reverse("planners:declaration_wizard") + "?step=7")

        elif step == 7:
            work_date = date.fromisoformat(wip["work_date"])

            sessions = LoginOperator.objects.filter(
                team_user_id=wip["teamuser"],
                login_team_date=work_date,
            ).filter(status__in=['ACTIVE', 'COMPLETED'])

            ops_qs = Operator.objects.filter(
                pk__in=sessions.values_list("operator_id", flat=True)
            ).distinct()

            form = _PStep6OperatorsForm(request.POST, queryset=ops_qs)
            if form.is_valid():
                wip["operators"] = list(
                    form.cleaned_data["operators"].values_list("id", flat=True)
                )
                self._save_wip(request, wip)
                return redirect(reverse("planners:declaration_save_planner"))

        return self._render(request, step, form, wip)


class DeclarationSavePlannerView(PlannerAccessMixin, View):
    """
    Create Declaration from planner_wip and clear session.
    Uses selected work_date and Calendar.shift_start
    for created_at / updated_at.
    """

    def get(self, request, *args, **kwargs):
        wip = request.session.get("planner_declaration_wip")

        if not wip:
            messages.error(request, "No declaration in progress.")
            return redirect(reverse("planners:declaration_list"))

        # -----------------------
        # REQUIRED DATA
        # -----------------------
        try:
            teamuser = TeamUser.objects.get(pk=wip["teamuser"])
            pro = Pro.objects.get(pk=wip["pro"])
            routing = Routing.objects.get(pk=wip["routing"])
        except Exception:
            messages.error(request, "Invalid wizard data (teamuser / pro / routing).")
            request.session.pop("planner_declaration_wip", None)
            return redirect(reverse("planners:declaration_list"))

        # -----------------------
        # DATE + SHIFT
        # -----------------------
        try:
            work_date = date.fromisoformat(wip["work_date"])
            shift_start = time.fromisoformat(wip["shift_start"])
        except Exception:
            messages.error(request, "Invalid date or shift data.")
            return redirect(reverse("planners:declaration_wizard") + "?step=2")

        decl_datetime = timezone.make_aware(
            datetime.combine(work_date, shift_start)
        )

        # -----------------------
        # DEFENSIVE CHECK
        # -----------------------
        if teamuser.subdepartment_id and routing.subdepartment_id != teamuser.subdepartment_id:
            messages.error(
                request,
                "Selected routing does not belong to the Team user's subdepartment."
            )
            request.session.pop("planner_declaration_wip", None)
            return redirect(reverse("planners:declaration_list"))

        # -----------------------
        # ROUTING OPERATION
        # -----------------------
        routing_operation = None
        if wip.get("routing_operation"):
            try:
                routing_operation = RoutingOperation.objects.get(
                    pk=wip["routing_operation"]
                )
            except RoutingOperation.DoesNotExist:
                routing_operation = None

        # -----------------------
        # QTY
        # -----------------------
        qty = int(wip.get("qty", 0))
        if qty <= 0:
            messages.error(request, "Invalid quantity.")
            return redirect(reverse("planners:declaration_wizard") + "?step=6")

        # -----------------------
        # CREATE DECLARATION
        # -----------------------
        decl = Declaration.objects.create(
            decl_date=work_date,
            teamuser=teamuser,
            subdepartment=teamuser.subdepartment,
            pro=pro,
            routing=routing,
            routing_operation=routing_operation,
            qty=qty,
            smv=(wip.get("smv") or (routing_operation.smv if routing_operation else None)),
            smv_ita=(wip.get("smv_ita") or (routing_operation.smv_ita if routing_operation else None)),
            created_at=decl_datetime,
            updated_at=decl_datetime,
        )

        # -----------------------
        # OPERATORS (STEP 7)
        # -----------------------
        if routing.declaration_type and routing.declaration_type.strip().upper() == "OPERATOR":
            operator_ids = wip.get("operators", []) or []

            if not operator_ids:
                decl.delete()
                messages.error(
                    request,
                    "Declaration requires operators but none selected."
                )
                return redirect(reverse("planners:declaration_wizard") + "?step=7")

            decl.operators.add(*operator_ids)

        # -----------------------
        # CLEANUP & FINISH
        # -----------------------
        request.session.pop("planner_declaration_wip", None)
        request.session.modified = True

        messages.success(request, f"Declaration #{decl.id} created.")
        return redirect(reverse("planners:declaration_list"))


class DeclarationCreateView(PlannerAccessMixin, CreateView):
    """
    Classic single-form create (kept for backwards compatibility). Prefer using wizard for planners.
    """
    model = Declaration
    form_class = DeclarationForm
    template_name = "planners/declaration_form.html"
    success_url = reverse_lazy("planners:declaration_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        pro_id = self.request.GET.get("pro") or (self.request.POST.get("pro") if self.request.method == "POST" else None)
        routing_id = self.request.GET.get("routing") or (self.request.POST.get("routing") if self.request.method == "POST" else None)
        subdep_id = self.request.GET.get("subdepartment") or (self.request.POST.get("subdepartment") if self.request.method == "POST" else None)

        if pro_id:
            try:
                kwargs["pro"] = Pro.objects.get(pk=pro_id)
            except Pro.DoesNotExist:
                pass
        if routing_id:
            try:
                kwargs["routing"] = Routing.objects.get(pk=routing_id)
            except Routing.DoesNotExist:
                pass
        if subdep_id:
            try:
                kwargs["subdepartment"] = Subdepartment.objects.get(pk=subdep_id)
            except Subdepartment.DoesNotExist:
                pass

        kwargs["operators_qs"] = Operator.objects.filter(act=True).order_by("badge_num")
        return kwargs

    def form_valid(self, form):
        teamuser = form.cleaned_data.get("teamuser")
        if teamuser and not form.cleaned_data.get("subdepartment"):
            form.instance.subdepartment = teamuser.subdepartment

        ro = form.cleaned_data.get("routing_operation")
        if ro:
            if not form.cleaned_data.get("smv") and ro.smv is not None:
                form.instance.smv = ro.smv
            if not form.cleaned_data.get("smv_ita") and ro.smv_ita is not None:
                form.instance.smv_ita = ro.smv_ita

        response = super().form_valid(form)
        operators = form.cleaned_data.get("operators")
        if operators:
            self.object.operators.set(operators)
        else:
            self.object.operators.clear()

        messages.success(self.request, f"Declaration #{self.object.id} created.")
        return response


class DeclarationWizardCancelView(PlannerAccessMixin, View):
    """
    Clear planner wizard session WIP and redirect to declarations list.
    """
    def get(self, request, *args, **kwargs):
        request.session.pop("planner_declaration_wip", None)
        request.session.modified = True
        messages.info(request, "Declaration canceled.")
        return redirect(reverse("planners:declaration_list"))



# ---------- BREAKS ----------

class BreakListView(PlannerAccessMixin, ListView):
    model = Break
    template_name = "planners/break_list.html"
    context_object_name = "breaks"
    ordering = ["break_time_start"]


class BreakCreateView(PlannerAccessMixin, CreateView):
    model = Break
    fields = ["break_name", "break_time_start", "break_time_end"]
    template_name = "planners/break_form.html"
    success_url = reverse_lazy("planners:break_list")

    def form_valid(self, form):
        start = form.cleaned_data["break_time_start"]
        end = form.cleaned_data["break_time_end"]

        start_dt = datetime.combine(datetime.today(), start)
        end_dt = datetime.combine(datetime.today(), end)

        if start_dt >= end_dt:
            form.add_error(
                "break_time_end",
                "End time must be after start time."
            )
            return self.form_invalid(form)

        if (end_dt - start_dt) != timedelta(minutes=30):
            form.add_error(
                "break_time_end",
                "Break duration must be exactly 30 minutes."
            )
            return self.form_invalid(form)

        messages.success(
            self.request,
            f"Break '{form.cleaned_data['break_name']}' created."
        )
        return super().form_valid(form)


class BreakUpdateView(PlannerAccessMixin, UpdateView):
    model = Break
    fields = ["break_name", "break_time_start", "break_time_end"]
    template_name = "planners/break_form.html"
    success_url = reverse_lazy("planners:break_list")

    def form_valid(self, form):
        start = form.cleaned_data["break_time_start"]
        end = form.cleaned_data["break_time_end"]

        start_dt = datetime.combine(datetime.today(), start)
        end_dt = datetime.combine(datetime.today(), end)

        if start_dt >= end_dt:
            form.add_error(
                "break_time_end",
                "End time must be after start time."
            )
            return self.form_invalid(form)

        if (end_dt - start_dt) != timedelta(minutes=30):
            form.add_error(
                "break_time_end",
                "Break duration must be exactly 30 minutes."
            )
            return self.form_invalid(form)

        messages.info(
            self.request,
            f"Break '{self.object.break_name}' updated."
        )
        return super().form_valid(form)


class BreakDeleteView(PlannerAccessMixin, DeleteView):
    model = Break
    template_name = "planners/break_confirm_delete.html"
    success_url = reverse_lazy("planners:break_list")

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()

        if OperatorBreak.objects.filter(break_type=self.object).exists():
            messages.error(
                request,
                f"Break '{self.object.break_name}' cannot be deleted because it is already used."
            )
            return redirect(self.success_url)

        messages.success(
            request,
            f"Break '{self.object.break_name}' deleted."
        )
        return super().delete(request, *args, **kwargs)



# ---------- OPERATOR BREAK LIST ----------

class OperatorBreakListView(PlannerAccessMixin, ListView):
    model = OperatorBreak
    template_name = "planners/operator_break_list.html"
    context_object_name = "operator_breaks"

    def get_queryset(self):
        return (
            OperatorBreak.objects
            .select_related("operator", "break_type", "team_user")
            .order_by("-date", "team_user__username", "operator__badge_num")
        )


class OperatorBreakUpdateView(PlannerAccessMixin, UpdateView):
    model = OperatorBreak
    fields = ["team_user", "date", "break_type", "operator"]
    template_name = "planners/operator_break_form.html"
    success_url = reverse_lazy("planners:operator_break_list")

    def form_valid(self, form):
        messages.info(self.request, "Operator break updated.")
        return super().form_valid(form)


class OperatorBreakDeleteView(PlannerAccessMixin, DeleteView):
    model = OperatorBreak
    template_name = "planners/operator_break_confirm_delete.html"
    success_url = reverse_lazy("planners:operator_break_list")

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        messages.warning(
            request,
            f"Operator break deleted: "
            f"{self.object.team_user.username} | "
            f"{self.object.operator} | "
            f"{self.object.date} | "
            f"{self.object.break_type.break_name}"
        )
        return super().delete(request, *args, **kwargs)


# ---------- WIZARD FORMS ----------

class _OBStep1TeamUserForm(forms.Form):
    team_user = forms.ModelChoiceField(
        queryset=TeamUser.objects.filter(is_active=True),
        label="Select Team user",
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class _OBStep2DateForm(forms.Form):
    work_date = forms.DateField(
        label="Select date",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )


class _OBStep3BreakForm(forms.Form):
    break_type = forms.ModelChoiceField(
        queryset=Break.objects.all().order_by("break_time_start"),
        label="Select break",
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class _OBStep4OperatorsForm(forms.Form):
    operators = forms.ModelMultipleChoiceField(
        queryset=Operator.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Operators",
        required=True,
    )

    def __init__(self, *args, **kwargs):
        qs = kwargs.pop("queryset", None)
        super().__init__(*args, **kwargs)
        if qs is not None:
            self.fields["operators"].queryset = qs


# ---------- OPERATOR BREAK WIZARD ----------

class OperatorBreakWizardView(PlannerAccessMixin, View):
    template_name = "planners/operator_break_step.html"

    # helpers
    def _get_wip(self, request):
        return request.session.get("operator_break_wip", {})

    def _save_wip(self, request, wip):
        request.session["operator_break_wip"] = wip
        request.session.modified = True

    def _go(self, step):
        return redirect(
            f"{reverse('planners:operator_break_declare')}?step={step}"
        )

    def _render(self, request, step, form):
        return render(request, self.template_name, {
            "step": step,
            "form": form,
            "percent": step * 25,
        })

    # ---------- GET ----------
    def get(self, request):
        step = int(request.GET.get("step", 1))
        wip = self._get_wip(request)

        if step == 1:
            form = _OBStep1TeamUserForm(initial={"team_user": wip.get("team_user")})

        elif step == 2:
            form = _OBStep2DateForm(initial={"work_date": wip.get("date")})

        elif step == 3:
            form = _OBStep3BreakForm(initial={"break_type": wip.get("break")})

        elif step == 4:
            work_date = date.fromisoformat(wip["date"])

            sessions = LoginOperator.objects.filter(
                team_user_id=wip["team_user"],
                login_team_date=work_date,
                status__in=["ACTIVE", "COMPLETED"],
            )

            ops_qs = Operator.objects.filter(
                id__in=sessions.values_list("operator_id", flat=True)
            ).distinct()

            form = _OBStep4OperatorsForm(queryset=ops_qs)

        else:
            return self._go(1)

        return self._render(request, step, form)

    # ---------- POST ----------
    def post(self, request):
        step = int(request.POST.get("step", 1))
        wip = self._get_wip(request)

        # STEP 1 — TEAM
        if step == 1:
            form = _OBStep1TeamUserForm(request.POST)
            if form.is_valid():
                wip["team_user"] = form.cleaned_data["team_user"].id
                self._save_wip(request, wip)
                return self._go(2)

        # STEP 2 — DATE
        elif step == 2:
            form = _OBStep2DateForm(request.POST)
            if form.is_valid():
                date_val = form.cleaned_data["work_date"]

                if not Calendar.objects.filter(
                    team_user_id=wip["team_user"],
                    date=date_val
                ).exists():
                    messages.error(request, "No calendar entry for selected team and date.")
                    return self._go(2)

                wip["date"] = date_val.isoformat()
                self._save_wip(request, wip)
                return self._go(3)

        # STEP 3 — BREAK
        elif step == 3:
            form = _OBStep3BreakForm(request.POST)
            if form.is_valid():
                wip["break"] = form.cleaned_data["break_type"].id
                self._save_wip(request, wip)
                return self._go(4)

        # STEP 4 — OPERATORS (FINAL SAVE)
        elif step == 4:
            work_date = date.fromisoformat(wip["date"])

            sessions = LoginOperator.objects.filter(
                team_user_id=wip["team_user"],
                login_team_date=work_date,
                status__in=["ACTIVE", "COMPLETED"],
            )

            ops_qs = Operator.objects.filter(
                id__in=sessions.values_list("operator_id", flat=True)
            ).distinct()

            form = _OBStep4OperatorsForm(request.POST, queryset=ops_qs)
            if form.is_valid():

                # 🚫 RESTRIKCIJA — drugi team isti dan
                invalid_ops = []
                for op in form.cleaned_data["operators"]:
                    if OperatorBreak.objects.filter(
                        operator=op,
                        date=work_date
                    ).exclude(team_user_id=wip["team_user"]).exists():
                        invalid_ops.append(str(op))

                if invalid_ops:
                    messages.error(
                        request,
                        "Break NOT saved. Operator(s) already have break for another team: "
                        + ", ".join(invalid_ops)
                    )
                    return self._go(4)

                # ✅ SAVE
                for op in form.cleaned_data["operators"]:
                    OperatorBreak.objects.update_or_create(
                        team_user_id=wip["team_user"],
                        date=work_date,
                        operator=op,
                        defaults={"break_type_id": wip["break"]},
                    )

                request.session.pop("operator_break_wip", None)
                messages.success(request, "Operator break(s) declared.")
                return redirect("planners:operator_break_list")

        return self._render(request, step, form)

# ----------  BREAK 30 ---------------------

class ManualAssignBreak30View(PlannerAccessMixin, View):
    def post(self, request):
        from core.management.commands.auto_break_operators import run_auto_break

        updated, skipped = run_auto_break()

        messages.success(
            request,
            f"Auto break finished: {updated} updated, {skipped} skipped."
        )

        return redirect("planners:login_operator_list")


# ---------- OPERATOR CAPACITY ----------


class OperatorCapacityTodayView(PlannerAccessMixin, TemplateView):
    template_name = "planners/operator_capacity_today.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # -----------------------------
        # DATE
        # -----------------------------
        date_str = self.request.GET.get("date")
        if date_str:
            try:
                selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                selected_date = timezone.localdate()
        else:
            selected_date = timezone.localdate()

        rows = []

        operators = Operator.objects.filter(
            operators__login_team_date=selected_date,
            operators__status__in=["ACTIVE", "COMPLETED"],
        ).distinct()

        for op in operators:

            # -----------------------------
            # WORK TIME (LOGIN / LOGOFF)
            # -----------------------------
            sessions = LoginOperator.objects.filter(
                operator=op,
                login_team_date=selected_date,
                status__in=["ACTIVE", "COMPLETED"],
                login_team_time__isnull=False,
                logoff_team_time__isnull=False,
            ).order_by("login_team_time")

            session_ranges = []
            sessions_minutes = Decimal("0.0")

            team_name = None
            first_session = sessions.first()
            if first_session and first_session.team_user:
                team_name = first_session.team_user.username

            for s in sessions:
                start = s.login_team_time
                end = s.logoff_team_time

                if end <= start:
                    continue

                session_ranges.append(
                    f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}"
                )

                delta = (
                    datetime.combine(selected_date, end)
                    - datetime.combine(selected_date, start)
                )
                sessions_minutes += Decimal(delta.total_seconds()) / Decimal("60")

            # -----------------------------
            # BREAK TIME (SUM PER DAY)
            # -----------------------------
            break_minutes = (
                LoginOperator.objects.filter(
                    operator=op,
                    login_team_date=selected_date,
                    break_time__isnull=False,
                )
                .aggregate(total=Sum("break_time"))["total"]
                or 0
            )
            break_minutes = Decimal(break_minutes)

            # -----------------------------
            # DOWNTIME (SUM PER DAY)
            # -----------------------------
            downtime_minutes = (
                DowntimeDeclaration.objects.filter(
                    login_operator__operator=op,
                    login_operator__login_team_date=selected_date,
                )
                .aggregate(total=Sum("downtime_total"))["total"]
                or 0
            )
            downtime_minutes = Decimal(downtime_minutes)

            # -----------------------------
            # AVAILABLE MINUTES
            # -----------------------------
            available_minutes = max(
                sessions_minutes - break_minutes - downtime_minutes,
                Decimal("0.0")
            )

            # -----------------------------
            # WORKED / DECLARATIONS
            # -----------------------------
            worked_qty = Decimal("0.0")
            worked_minutes = Decimal("0.0")
            used_smv = None

            declarations = Declaration.objects.filter(
                decl_date=selected_date,
                operators=op,
                smv__isnull=False,
            )

            for d in declarations:
                qty = Decimal(d.qty)
                smv = Decimal(d.smv)
                worked_qty += qty
                worked_minutes += qty * smv
                used_smv = smv

            efficiency = (
                (worked_minutes / available_minutes) * Decimal("100")
                if available_minutes > 0
                else Decimal("0.0")
            )

            rows.append({
                "operator": op,
                "team": team_name,
                "session_ranges": session_ranges,
                "break_minutes": round(break_minutes, 1),
                "downtime_minutes": round(downtime_minutes, 1),
                "available_min": round(available_minutes, 1),
                "worked_qty": round(worked_qty, 1),
                "worked_smv": round(used_smv, 2) if used_smv else None,
                "worked_min": round(worked_minutes, 1),
                "efficiency": round(efficiency, 1),
            })

        rows.sort(key=lambda x: x["efficiency"], reverse=True)

        context["rows"] = rows
        context["selected_date"] = selected_date
        return context


# ---------- DOWNTIME  ------------

class DowntimeListView(PlannerAccessMixin, ListView):
    model = Downtime
    template_name = "planners/downtime_list.html"
    context_object_name = "downtimes"
    ordering = ["subdepartment__subdepartment", "downtime_name"]

class DowntimeForm(forms.ModelForm):
    class Meta:
        model = Downtime
        fields = [
            "downtime_name",
            "subdepartment",
            "fixed_duration",
            "downtime_value",
        ]
        widgets = {
            "downtime_name": forms.TextInput(attrs={"class": "form-control"}),
            "subdepartment": forms.Select(attrs={"class": "form-select"}),
            "fixed_duration": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "downtime_value": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": "0",
                }
            ),
        }

    def clean(self):
        cleaned = super().clean()
        fixed = cleaned.get("fixed_duration")
        value = cleaned.get("downtime_value")

        if fixed and value is None:
            self.add_error(
                "downtime_value",
                "Downtime value is required when fixed duration is enabled."
            )

        return cleaned


# ---------- DOWNTIME  ------------


class DowntimeListView(PlannerAccessMixin, ListView):
    model = Downtime
    template_name = "planners/downtime_list.html"
    context_object_name = "downtimes"
    ordering = ["subdepartment__subdepartment", "downtime_name"]


class DowntimeCreateView(PlannerAccessMixin, CreateView):
    model = Downtime
    form_class = DowntimeForm
    template_name = "planners/downtime_form.html"
    success_url = reverse_lazy("planners:downtime_list")

    def form_valid(self, form):
        messages.success(
            self.request,
            f"Downtime '{form.instance.downtime_name}' created."
        )
        return super().form_valid(form)


class DowntimeUpdateView(PlannerAccessMixin, UpdateView):
    model = Downtime
    form_class = DowntimeForm
    template_name = "planners/downtime_form.html"
    success_url = reverse_lazy("planners:downtime_list")

    def form_valid(self, form):
        messages.info(
            self.request,
            f"Downtime '{form.instance.downtime_name}' updated."
        )
        return super().form_valid(form)


# ---------- DOWNTIME DECLARATION EDIT  ------------


class DowntimeDeclarationListView(PlannerAccessMixin, ListView):
    model = DowntimeDeclaration
    template_name = "planners/downtime_declaration_list.html"
    context_object_name = "items"
    paginate_by = 50
    ordering = ["-created_at"]


class DowntimeDeclarationForm(forms.ModelForm):
    class Meta:
        model = DowntimeDeclaration
        fields = ["downtime_value", "repetition"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        downtime = self.instance.downtime

        if downtime.fixed_duration:
            # 🧊 FIXED DOWNTIME
            # value je zaključan, repetition editable
            self.fields["downtime_value"].disabled = True

        else:
            # 🔥 NON-FIXED DOWNTIME
            # repetition je UVEK 1 i sakriven
            self.fields["repetition"].widget = forms.HiddenInput()
            self.fields["repetition"].initial = 1

    def save(self, commit=True):
        obj = super().save(commit=False)
        downtime = obj.downtime

        if downtime.fixed_duration:
            # 🧊 fixed → value se NE menja
            obj.downtime_value = self.instance.downtime_value
        else:
            # 🔥 non-fixed → repetition uvek 1
            obj.repetition = 1

        # total se računa u model.save()
        if commit:
            obj.save()

        return obj


class DowntimeDeclarationFormView(LoginRequiredMixin, View):
    template_name = "planners/downtime_declaration_form.html"

    def get(self, request, pk):
        obj = get_object_or_404(DowntimeDeclaration, pk=pk)
        form = DowntimeDeclarationForm(instance=obj)
        return render(request, self.template_name, {
            "form": form,
            "obj": obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(DowntimeDeclaration, pk=pk)
        form = DowntimeDeclarationForm(request.POST, instance=obj)

        if form.is_valid():
            form.save()
            return redirect("planners:downtime_declaration_list")

        return render(request, self.template_name, {
            "form": form,
            "obj": obj,
        })


class DowntimeDeclarationDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(DowntimeDeclaration, pk=pk)
        obj.delete()
        return redirect("planners:downtime_declaration_list")


# ---------- DOWNTIME DECLARATION CREATION IN STEPS  ------------


class _DTStep1TeamUserForm(forms.Form):
    teamuser = forms.ModelChoiceField(
        queryset=TeamUser.objects.filter(
            is_active=True,
            subdepartment__isnull=False
        ).order_by("username"),
        label="Select Team",
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class _DTStep2DateForm(forms.Form):
    work_date = forms.DateField(
        label="Select date",
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"}
        ),
    )


class _DTStep3LoginOperatorsForm(forms.Form):
    login_operators = forms.ModelMultipleChoiceField(
        queryset=LoginOperator.objects.none(),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        label="Operators with login",
        required=True,
    )

    def __init__(self, *args, **kwargs):
        qs = kwargs.pop("queryset", None)
        super().__init__(*args, **kwargs)
        if qs is not None:
            self.fields["login_operators"].queryset = qs


class _DTStep4DowntimeForm(forms.Form):
    downtime = forms.ModelChoiceField(
        queryset=Downtime.objects.none(),
        label="Select Downtime",
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, **kwargs):
        subdepartment = kwargs.pop("subdepartment", None)
        super().__init__(*args, **kwargs)
        if subdepartment:
            self.fields["downtime"].queryset = (
                Downtime.objects
                .filter(subdepartment=subdepartment)
                .order_by("downtime_name")
            )


class _DTStep5DurationForm(forms.Form):
    downtime_value = forms.DecimalField(
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=6,
        label="Downtime value (minutes)",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        required=False,
    )

    repetition = forms.IntegerField(
        min_value=1,
        label="Repetition",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        required=False,
        initial=1,
    )

    def __init__(self, *args, **kwargs):
        fixed_duration = kwargs.pop("fixed_duration", False)
        super().__init__(*args, **kwargs)

        if fixed_duration:
            self.fields["downtime_value"].disabled = True
        else:
            self.fields["repetition"].widget = HiddenInput()
            self.fields["repetition"].required = False


# =========================
# WIZARD (STEP 1–5)
# =========================

class DowntimeDeclarationWizardView(PlannerAccessMixin, View):
    template_name = "planners/downtime_declaration_step_planner.html"

    # -------- session helpers --------

    def _get_wip(self, request):
        return request.session.get("planner_downtime_wip", {})

    def _save_wip(self, request, wip):
        request.session["planner_downtime_wip"] = wip
        request.session.modified = True

    def _render(self, request, step, form, wip):
        percent = int((step - 1) / 5 * 100)
        return render(request, self.template_name, {
            "step": step,
            "form": form,
            "percent": percent,
        })

    # -------- GET --------

    def get(self, request):
        step = int(request.GET.get("step", 1))
        wip = self._get_wip(request)

        if step == 1:
            form = _DTStep1TeamUserForm(
                initial={"teamuser": wip.get("teamuser")}
            )

        elif step == 2:
            form = _DTStep2DateForm(
                initial={"work_date": wip.get("work_date")}
            )

        elif step == 3:
            work_date = date.fromisoformat(wip["work_date"])

            qs = (
                LoginOperator.objects
                .filter(
                    team_user_id=wip["teamuser"],
                    login_team_date=work_date,
                )
                .exclude(status="IGNORE")
                .order_by("operator_id", "login_actual")
            )

            seen = set()
            login_operator_ids = []

            for lo in qs:
                if lo.operator_id not in seen:
                    seen.add(lo.operator_id)
                    login_operator_ids.append(lo.id)

            filtered_qs = LoginOperator.objects.filter(
                id__in=login_operator_ids
            )

            form = _DTStep3LoginOperatorsForm(
                queryset=filtered_qs,
                initial={"login_operators": wip.get("login_operators", [])}
            )

        elif step == 4:
            tu = TeamUser.objects.get(pk=wip["teamuser"])
            form = _DTStep4DowntimeForm(
                subdepartment=tu.subdepartment,
                initial={"downtime": wip.get("downtime")}
            )

        elif step == 5:
            dt = Downtime.objects.get(pk=wip["downtime"])
            form = _DTStep5DurationForm(
                fixed_duration=dt.fixed_duration,
                initial={
                    "downtime_value": wip.get("downtime_value"),
                    "repetition": wip.get("repetition", 1),
                }
            )

        else:
            return redirect("?step=1")

        return self._render(request, step, form, wip)

    # -------- POST --------

    def post(self, request):
        step = int(request.POST.get("step", 1))
        wip = self._get_wip(request)

        # STEP 1 — TEAM
        if step == 1:
            form = _DTStep1TeamUserForm(request.POST)
            if form.is_valid():
                wip["teamuser"] = form.cleaned_data["teamuser"].id
                self._save_wip(request, wip)
                return redirect(
                    reverse("planners:downtime_declaration_wizard") + "?step=2"
                )

        # STEP 2 — DATE
        elif step == 2:
            form = _DTStep2DateForm(request.POST)
            if form.is_valid():
                wip["work_date"] = form.cleaned_data["work_date"].isoformat()
                self._save_wip(request, wip)
                return redirect(
                    reverse("planners:downtime_declaration_wizard") + "?step=3"
                )

        # STEP 3 — OPERATORS
        elif step == 3:
            work_date = date.fromisoformat(wip["work_date"])

            qs = (
                LoginOperator.objects
                .filter(
                    team_user_id=wip["teamuser"],
                    login_team_date=work_date,
                )
                .exclude(status="IGNORE")
                .order_by("operator_id", "login_actual")
            )

            seen = set()
            login_operator_ids = []

            for lo in qs:
                if lo.operator_id not in seen:
                    seen.add(lo.operator_id)
                    login_operator_ids.append(lo.id)

            filtered_qs = LoginOperator.objects.filter(
                id__in=login_operator_ids
            )

            form = _DTStep3LoginOperatorsForm(
                request.POST,
                queryset=filtered_qs
            )

            if form.is_valid():
                wip["login_operators"] = list(
                    form.cleaned_data["login_operators"]
                    .values_list("id", flat=True)
                )
                self._save_wip(request, wip)
                return redirect(
                    reverse("planners:downtime_declaration_wizard") + "?step=4"
                )

        # STEP 4 — DOWNTIME
        elif step == 4:
            tu = TeamUser.objects.get(pk=wip["teamuser"])
            form = _DTStep4DowntimeForm(
                request.POST,
                subdepartment=tu.subdepartment
            )

            if form.is_valid():
                dt = form.cleaned_data["downtime"]
                wip["downtime"] = dt.id
                wip["fixed_duration"] = dt.fixed_duration

                if dt.fixed_duration:
                    # 🔥 KLJUČNO — Decimal → string
                    wip["downtime_value"] = str(dt.downtime_value)
                    wip["repetition"] = 1

                self._save_wip(request, wip)
                return redirect(
                    reverse("planners:downtime_declaration_wizard") + "?step=5"
                )

        # STEP 5 — DURATION
        elif step == 5:
            dt = Downtime.objects.get(pk=wip["downtime"])
            form = _DTStep5DurationForm(
                request.POST,
                fixed_duration=dt.fixed_duration
            )

            if form.is_valid():
                if not dt.fixed_duration:
                    # 🔥 Decimal → string
                    wip["downtime_value"] = str(
                        form.cleaned_data["downtime_value"]
                    )
                    wip["repetition"] = 1
                else:
                    wip["repetition"] = form.cleaned_data.get("repetition", 1)

                self._save_wip(request, wip)
                return redirect(
                    reverse("planners:downtime_declaration_save")
                )

        return self._render(request, step, form, wip)


# =========================
# SAVE
# =========================

class DowntimeDeclarationSaveView(PlannerAccessMixin, View):
    def get(self, request):
        wip = request.session.get("planner_downtime_wip")

        if not wip:
            messages.error(request, "No downtime declaration in progress.")
            return redirect("planners:downtime_declaration_list")

        # -----------------------
        # SAFE DECIMAL CONVERSION
        # -----------------------
        try:
            downtime_value = Decimal(str(wip["downtime_value"]))
        except (InvalidOperation, TypeError, KeyError):
            messages.error(
                request,
                "Invalid downtime value. Please re-enter downtime duration."
            )
            return redirect(
                reverse("planners:downtime_declaration_wizard") + "?step=5"
            )

        repetition = int(wip.get("repetition", 1))

        # -----------------------
        # CREATE DECLARATIONS
        # -----------------------
        for lo_id in wip["login_operators"]:
            DowntimeDeclaration.objects.create(
                login_operator_id=lo_id,
                downtime_id=wip["downtime"],
                downtime_value=downtime_value,
                repetition=repetition,
            )

        # -----------------------
        # CLEAN SESSION
        # -----------------------
        request.session.pop("planner_downtime_wip", None)
        request.session.modified = True

        messages.success(
            request,
            "Downtime declarations created."
        )

        return redirect("planners:downtime_declaration_list")


# =========================
# CANCEL
# =========================

class DowntimeDeclarationWizardCancelView(PlannerAccessMixin, View):
    def get(self, request):
        request.session.pop("planner_downtime_wip", None)
        request.session.modified = True
        messages.info(request, "Downtime declaration canceled.")
        return redirect("planners:downtime_declaration_list")

# dashboard

def dashboard_view(request):
    # default poslednjih 7 dana
    today = timezone.localdate()
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    subdep_id = request.GET.get("subdepartment")

    if not date_from:
        date_from = today - timedelta(days=6)
    if not date_to:
        date_to = today

    # base queryset za declarations
    decl_qs = Declaration.objects.filter(decl_date__range=[date_from, date_to])

    if subdep_id:
        decl_qs = decl_qs.filter(subdepartment_id=subdep_id)

    # -------------------------
    # 1) Total declared qty po danima (line chart)
    # -------------------------
    qty_by_day = (
        decl_qs
        .values("decl_date")
        .annotate(total_qty=Sum("qty"))
        .order_by("decl_date")
    )
    chart1_labels = [str(x["decl_date"]) for x in qty_by_day]
    chart1_data = [x["total_qty"] or 0 for x in qty_by_day]

    # -------------------------
    # 2) Total declarations count po danima (line chart)
    # -------------------------
    decl_count_by_day = (
        decl_qs
        .values("decl_date")
        .annotate(cnt=Count("id"))
        .order_by("decl_date")
    )
    chart2_labels = [str(x["decl_date"]) for x in decl_count_by_day]
    chart2_data = [x["cnt"] or 0 for x in decl_count_by_day]

    # -------------------------
    # 3) Qty po Subdepartment (bar chart)
    # -------------------------
    qty_by_subdep = (
        decl_qs
        .values("subdepartment__subdepartment")
        .annotate(total_qty=Sum("qty"))
        .order_by("-total_qty")
    )
    chart3_labels = [x["subdepartment__subdepartment"] or "N/A" for x in qty_by_subdep]
    chart3_data = [x["total_qty"] or 0 for x in qty_by_subdep]

    # -------------------------
    # 4) Top 10 operacija po qty (bar chart)
    # -------------------------
    top_ops = (
        decl_qs
        .values("routing_operation__operation__name")
        .annotate(total_qty=Sum("qty"))
        .order_by("-total_qty")[:10]
    )
    chart4_labels = [x["routing_operation__operation__name"] or "N/A" for x in top_ops]
    chart4_data = [x["total_qty"] or 0 for x in top_ops]

    # -------------------------
    # 5) Downtime total po tipu (bar chart)
    # (povezano preko login_operator -> created_at filter)
    # -------------------------
    downtime_qs = DowntimeDeclaration.objects.filter(
        created_at__date__range=[date_from, date_to]
    )

    downtime_by_type = (
        downtime_qs
        .values("downtime__downtime_name")
        .annotate(total_minutes=Sum("downtime_total"))
        .order_by("-total_minutes")[:10]
    )
    chart5_labels = [x["downtime__downtime_name"] for x in downtime_by_type]
    chart5_data = [float(x["total_minutes"] or 0) for x in downtime_by_type]

    # -------------------------
    # 6) Logins po statusu (pie chart)
    # -------------------------
    login_qs = LoginOperator.objects.filter(login_actual__date__range=[date_from, date_to])

    logins_by_status = (
        login_qs
        .values("status")
        .annotate(cnt=Count("id"))
        .order_by("-cnt")
    )
    chart6_labels = [x["status"] for x in logins_by_status]
    chart6_data = [x["cnt"] or 0 for x in logins_by_status]

    context = {
        "date_from": str(date_from),
        "date_to": str(date_to),
        "subdepartments": Subdepartment.objects.all(),
        "selected_subdepartment": subdep_id or "",

        "chart1_labels": chart1_labels,
        "chart1_data": chart1_data,

        "chart2_labels": chart2_labels,
        "chart2_data": chart2_data,

        "chart3_labels": chart3_labels,
        "chart3_data": chart3_data,

        "chart4_labels": chart4_labels,
        "chart4_data": chart4_data,

        "chart5_labels": chart5_labels,
        "chart5_data": chart5_data,

        "chart6_labels": chart6_labels,
        "chart6_data": chart6_data,
    }

    return render(request, "planners/planner_dashboard_charts.html", context)


# ---------- AJAX ENDPOINTS ----------

def ajax_get_routings(request):
    pro_id = request.GET.get("pro_id")
    subdep_id = request.GET.get("subdepartment")  # optional: filter by subdepartment id
    data = []
    if pro_id:
        try:
            pro = Pro.objects.get(pk=pro_id)
            qs = Routing.objects.filter(status=True, ready=True, sku=pro.sku)
            if subdep_id:
                try:
                    sd = Subdepartment.objects.get(pk=subdep_id)
                    qs = qs.filter(subdepartment=sd)
                except Subdepartment.DoesNotExist:
                    # ignore invalid subdepartment param
                    pass
            data = [{"id": r.id, "text": f"{r.sku} / {r.version}"} for r in qs.order_by("version")]
        except Pro.DoesNotExist:
            pass
    return JsonResponse({"results": data})


def ajax_get_routing_operations(request):
    routing_id = request.GET.get("routing_id")
    data = []
    if routing_id:
        try:
            routing = Routing.objects.get(pk=routing_id)
            qs = routing.routing_operations.all().order_by("id")
            data = [{"id": ro.id, "text": ro.operation.name} for ro in qs]
        except Routing.DoesNotExist:
            pass
    return JsonResponse({"results": data})


def ajax_get_teamuser(request):
    """
    Returns JSON { subdepartment_id: <id or ''>, subdepartment_name: <name or ''> }
    Used by classic declaration page to populate #id_subdepartment when teamuser selected.
    """
    teamuser_id = request.GET.get("teamuser_id")
    data = {"subdepartment_id": None, "subdepartment_name": None}
    if teamuser_id:
        try:
            tu = TeamUser.objects.select_related("subdepartment").get(pk=teamuser_id)
            if tu.subdepartment:
                data["subdepartment_id"] = tu.subdepartment.id
                data["subdepartment_name"] = tu.subdepartment.subdepartment
            else:
                data["subdepartment_id"] = None
                data["subdepartment_name"] = None
        except TeamUser.DoesNotExist:
            pass
    return JsonResponse(data)


def ajax_team_user_active_logins(request):
    team_user_id = request.GET.get("team_user")
    today = timezone.localdate()

    data = []

    if team_user_id:
        qs = (
            LoginOperator.objects
            .select_related("operator")
            .filter(
                team_user_id=team_user_id,
                login_team_date=today,
                status="ACTIVE",
                logoff_actual__isnull=True,
            )
            .order_by("operator__badge_num")
        )

        for lo in qs:
            data.append({
                "id": lo.id,
                "operator": str(lo.operator),
                "login_time": lo.login_team_time.strftime("%H:%M"),
            })

    return JsonResponse({"results": data})