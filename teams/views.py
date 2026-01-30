from django import forms
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView
from django.views import View
from django.shortcuts import redirect, get_object_or_404, render
from django.contrib import messages
from django.utils import timezone
from django.urls import reverse
from django.forms.widgets import CheckboxSelectMultiple, HiddenInput
from datetime import datetime, timedelta
from django.db.models import Min


from core.models import *


class TeamAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = "core:login"

    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.groups.filter(name__iexact="TEAMS").exists()


# ---------- DASHBOARD  ----------

class TeamDashboardView(TeamAccessMixin, TemplateView):
    template_name = "teams/team_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        today = timezone.localdate()
        now_local = timezone.localtime(timezone.now())
        current_time = now_local.time()

        # današnja smena za ovog team user-a (ako postoji)
        calendar_entry = Calendar.objects.filter(
            team_user=self.request.user,
            date=today,
        ).first()

        # default vrednosti
        shift_state = None          # "active", "inactive", "no_shift"
        shift_alert_class = None    # "success", "warning", "danger"

        if calendar_entry:
            shift_start = calendar_entry.shift_start
            shift_end = calendar_entry.shift_end

            if shift_start <= current_time <= shift_end:
                # smena upravo traje
                shift_state = "active"
                shift_alert_class = "success"
            else:
                # postoji smena, ali trenutno nije u toku
                shift_state = "inactive"
                shift_alert_class = "warning"
        else:
            # nema smene za danas
            shift_state = "no_shift"
            shift_alert_class = "danger"

        context["calendar_entry"] = calendar_entry
        context["shift_state"] = shift_state
        context["shift_alert_class"] = shift_alert_class
        return context


# ---------- FORM ----------

class OperatorLoginForm(forms.Form):
    badge_num = forms.CharField(label="Badge number", max_length=50)

    def clean_badge_num(self):
        return self.cleaned_data["badge_num"].strip()


# ---------- LOGIN PAGE ----------


class OperatorLoginView(TeamAccessMixin, TemplateView):
    template_name = "teams/operator_login.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        today = timezone.localdate()
        now_local = timezone.localtime(timezone.now())
        current_time = now_local.time()

        # forma
        context["login_form"] = OperatorLoginForm()

        # današnja smena za ovog team user-a
        calendar_entry = Calendar.objects.filter(
            team_user=self.request.user,
            date=today,
        ).first()

        # default vrednosti za status smene
        shift_state = None          # "active", "inactive", "no_shift"
        shift_alert_class = None    # "success", "warning", "danger"

        if calendar_entry:
            shift_start = calendar_entry.shift_start
            shift_end = calendar_entry.shift_end

            if shift_start <= current_time <= shift_end:
                shift_state = "active"
                shift_alert_class = "success"
            else:
                shift_state = "inactive"
                shift_alert_class = "warning"
        else:
            shift_state = "no_shift"
            shift_alert_class = "danger"

        # aktivne sesije ovog tima
        active_sessions = (
            LoginOperator.objects.filter(team_user=self.request.user, status="ACTIVE")
            .select_related("operator")
        )

        context["calendar_entry"] = calendar_entry
        context["shift_state"] = shift_state
        context["shift_alert_class"] = shift_alert_class
        context["active_sessions"] = active_sessions
        return context

    def post(self, request, *args, **kwargs):
        form = OperatorLoginForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Invalid badge number.")
            return redirect("teams:operator_login")

        badge_num = form.cleaned_data["badge_num"]

        try:
            operator = Operator.objects.get(badge_num__iexact=badge_num, act=True)
        except Operator.DoesNotExist:
            messages.error(request, "Operator not found or not active.")
            return redirect("teams:operator_login")

        # now u UTC, local_now u lokalnoj zoni
        now = timezone.now()
        local_now = timezone.localtime(now)
        current_date = local_now.date()
        current_time = local_now.time()

        # mora da postoji današnja smena za OVAJ tim
        calendar_entry = Calendar.objects.filter(
            team_user=request.user,
            date=current_date,
        ).first()

        if not calendar_entry:
            messages.error(
                request,
                "You cannot log in operators – no shift found in Calendar for today.",
            )
            return redirect("teams:operator_login")

        shift_start = calendar_entry.shift_start
        shift_end = calendar_entry.shift_end

        # ne sme posle kraja smene
        if current_time > shift_end:
            messages.error(request, "You cannot log in operators after the end of the shift.")
            return redirect("teams:operator_login")

        # --- PROVERA POSTOJEĆIH AKTIVNIH SESIJA ---

        active_today_qs = LoginOperator.objects.filter(
            operator=operator,
            status="ACTIVE",
            login_team_date=current_date,
        )

        # 1) već prijavljen u istom timu
        same_team_session = active_today_qs.filter(team_user=request.user).first()
        if same_team_session:
            messages.error(request, "This operator is already logged in this team today.")
            return redirect("teams:operator_login")

        # 2) prijavljen u drugom timu → auto logout
        other_team_sessions = active_today_qs.exclude(team_user=request.user)

        for s in other_team_sessions:
            other_calendar = Calendar.objects.filter(
                team_user=s.team_user,
                date=current_date,
            ).first()

            s.logoff_actual = now  # UTC

            if other_calendar:
                other_shift_start = other_calendar.shift_start
                other_shift_end = other_calendar.shift_end

                login_local_time = timezone.localtime(s.login_actual).time()

                # IGNORE: login i logout pre smene
                if login_local_time < other_shift_start and current_time < other_shift_start:
                    s.logoff_team_date = other_calendar.date
                    s.logoff_team_time = other_shift_start
                    s.status = "IGNORE"
                else:
                    s.logoff_team_date = other_calendar.date
                    if current_time <= other_shift_end:
                        s.logoff_team_time = current_time
                    else:
                        s.logoff_team_time = other_shift_end
                    s.status = "COMPLETED"
            else:
                s.logoff_team_date = current_date
                s.logoff_team_time = current_time
                s.status = "COMPLETED"

            s.save()

        if other_team_sessions.exists():
            messages.info(
                request,
                "Operator was logged out from another team and will be logged in to this team.",
            )

        # ------------------------------------------------------------------
        # LOGIN TEAM TIME LOGIKA (sa login_grace_period)
        # ------------------------------------------------------------------

        grace_minutes = request.user.login_grace_period or 0

        shift_start_dt = datetime.combine(current_date, shift_start)
        grace_limit_dt = shift_start_dt + timedelta(minutes=grace_minutes)
        current_dt = datetime.combine(current_date, current_time)

        if current_dt <= grace_limit_dt:
            # pre smene ili unutar grace perioda
            team_time = shift_start
        else:
            # posle grace perioda
            team_time = current_time

        team_date = calendar_entry.date

        LoginOperator.objects.create(
            operator=operator,
            team_user=request.user,
            login_actual=now,          # UTC
            login_team_date=team_date,
            login_team_time=team_time, # lokalno, sa grace logikom
        )

        messages.success(request, f"Operator {operator} logged in.")
        return redirect("teams:operator_login")


# ---------- LOGOUT PAGE ----------

class OperatorLogoutView(TeamAccessMixin, TemplateView):
    template_name = "teams/operator_logout.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        today = timezone.localdate()

        context["calendar_entry"] = Calendar.objects.filter(team_user=self.request.user, date=today).first()

        context["active_sessions"] = (
            LoginOperator.objects.filter(team_user=self.request.user, status="ACTIVE").select_related("operator")
        )
        return context

    def post(self, request, *args, **kwargs):
        session_id = request.POST.get("session_id")
        session = get_object_or_404(LoginOperator, id=session_id, team_user=request.user, status="ACTIVE")

        now = timezone.now()
        local_now = timezone.localtime(now)
        current_date = local_now.date()
        current_time = local_now.time()

        calendar_entry = Calendar.objects.filter(team_user=request.user, date=current_date).first()

        # default fallback (lokalno)
        team_date = current_date
        team_time = current_time
        new_status = "COMPLETED"

        if calendar_entry:
            shift_start = calendar_entry.shift_start
            shift_end = calendar_entry.shift_end

            login_local_time = timezone.localtime(session.login_actual).time()

            # slučaj IGNORE: prijava i odjava pre početka smene
            if login_local_time < shift_start and current_time < shift_start:
                team_date = calendar_entry.date
                team_time = shift_start
                new_status = "IGNORE"
            else:
                # standardna logika:
                # - u toku smene -> actual
                # - posle smene -> shift_end
                team_date = calendar_entry.date
                if current_time <= shift_end:
                    team_time = current_time
                else:
                    team_time = shift_end
        # ako nema calendar_entry, ostaje fallback COMPLETED + actual

        session.logoff_actual = now  # UTC
        session.logoff_team_date = team_date
        session.logoff_team_time = team_time
        session.status = new_status
        session.save()

        if new_status == "IGNORE":
            messages.info(request, f"Operator {session.operator} logged out before shift start (status IGNORE).")
        else:
            messages.success(request, f"Operator {session.operator} logged out.")
        return redirect("teams:operator_logout")


# ---------- DECLARATION WIZARD (multi-step, inline forms) ----------


class _Step1ProForm(forms.Form):
    pro = forms.ModelChoiceField(queryset=Pro.objects.filter(status=True), label="Select PRO")

    def __init__(self, *args, **kwargs):
        subdepartment = kwargs.pop("subdepartment", None)
        super().__init__(*args, **kwargs)
        if subdepartment:
            self.fields["pro"].queryset = Pro.objects.filter(
                pro_subdepartments__subdepartment=subdepartment,
                pro_subdepartments__active=True,
                status=True,
            ).distinct()
        # widget attrs so Select2 / styling picks it up
        self.fields["pro"].widget.attrs.update({
            "class": "form-select",
            "data-placeholder": "— Select PRO —",
        })


class _Step2RoutingForm(forms.Form):
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

        qs = qs.order_by("sku", "version")
        self.fields["routing"].queryset = qs

        # ✅ AUTO SELECT ako postoji samo jedan routing
        if qs.count() == 1:
            self.initial["routing"] = qs.first().id


class _Step3RoutingOperationForm(forms.Form):
    routing_operation = forms.ModelChoiceField(
        queryset=RoutingOperation.objects.none(),
        label="Select Routing Operation",
        widget=forms.RadioSelect
    )

    def __init__(self, *args, **kwargs):
        routing = kwargs.pop("routing", None)
        super().__init__(*args, **kwargs)

        if not routing:
            self.fields["routing_operation"].queryset = RoutingOperation.objects.none()
            return

        qs = routing.routing_operations.all().order_by("operation__name")
        self.fields["routing_operation"].queryset = qs

        # ✅ AUTO SELECT ako postoji samo jedna operacija
        if qs.count() == 1:
            self.initial["routing_operation"] = qs.first().id


class _Step4QtyForm(forms.Form):
    qty = forms.IntegerField(min_value=1, label="Quantity")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["qty"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Enter produced quantity",
            "min": "1",
            "style": "max-width:240px;"
        })


class _Step5OperatorsForm(forms.Form):
    operators = forms.ModelMultipleChoiceField(
        queryset=Operator.objects.none(),
        required=False,
        widget=CheckboxSelectMultiple,
        label="Operators",
    )

    def __init__(self, *args, **kwargs):
        qs = kwargs.pop("queryset", None)
        super().__init__(*args, **kwargs)
        if qs is not None:
            self.fields["operators"].queryset = qs


# ==========================================================
# TEAM DOWNTIME WIZARD  ✅ FIXED
# ==========================================================

class _TDStep1LoginOperatorsForm(forms.Form):
    login_operators = forms.ModelMultipleChoiceField(
        queryset=LoginOperator.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
        label="Operators",
    )

    def __init__(self, *args, **kwargs):
        qs = kwargs.pop("queryset", None)
        super().__init__(*args, **kwargs)

        if qs is not None:
            self.fields["login_operators"].queryset = qs

        # 👇 LABEL: samo badge + ime
        self.fields["login_operators"].label_from_instance = (
            lambda lo: f"{lo.operator.badge_num} - {lo.operator.name}"
        )


class _TDStep2DowntimeForm(forms.Form):
    downtime = forms.ModelChoiceField(
        queryset=Downtime.objects.none(),
        widget=forms.RadioSelect,
        label="Select Downtime",
    )

    def __init__(self, *args, **kwargs):
        subdepartment = kwargs.pop("subdepartment", None)
        super().__init__(*args, **kwargs)
        if subdepartment:
            self.fields["downtime"].queryset = Downtime.objects.filter(
                subdepartment=subdepartment
            ).order_by("downtime_name")


class _TDStep3DurationForm(forms.Form):
    downtime_value = forms.DecimalField(
        decimal_places=2,
        max_digits=6,
        min_value=Decimal("0.01"),
        required=False,
        label="Downtime (minutes)",
    )

    repetition = forms.IntegerField(
        min_value=1,
        initial=1,
        required=False,
        label="Repetition",
    )

    def __init__(self, *args, **kwargs):
        fixed_duration = kwargs.pop("fixed_duration", False)
        super().__init__(*args, **kwargs)

        if fixed_duration:
            # downtime_value → readonly / disabled
            self.fields["downtime_value"].required = False
            self.fields["downtime_value"].widget.attrs.update({
                "disabled": True,
            })

            # repetition → USER MUST ENTER
            self.fields["repetition"].required = True

        else:
            # downtime_value → USER ENTERS
            self.fields["downtime_value"].required = True

            # repetition → hidden, always = 1
            self.fields["repetition"].widget = HiddenInput()
            self.initial["repetition"] = 1


class TeamDowntimeWizardView(TeamAccessMixin, View):
    template_name = "teams/downtime_step.html"

    def _get_wip(self, request):
        return request.session.get("team_downtime_wip", {})

    def _save_wip(self, request, wip):
        request.session["team_downtime_wip"] = wip
        request.session.modified = True

    def get(self, request):
        step = int(request.GET.get("step", 1))
        wip = self._get_wip(request)

        if step == 1:
            base_qs = LoginOperator.objects.filter(
                team_user=request.user,
                login_team_date=timezone.localdate(),
                status__in=["ACTIVE", "COMPLETED"],
            )

            first_ids = (
                base_qs
                .values("operator_id")
                .annotate(first_id=Min("id"))
                .values_list("first_id", flat=True)
            )

            qs = LoginOperator.objects.filter(id__in=first_ids)
            form = _TDStep1LoginOperatorsForm(
                queryset=qs,
                initial={"login_operators": wip.get("login_operators", [])}
            )

        elif step == 2:
            form = _TDStep2DowntimeForm(
                subdepartment=request.user.subdepartment,
                initial={"downtime": wip.get("downtime")}
            )


        elif step == 3:
            dt = Downtime.objects.get(pk=wip["downtime"])
            form = _TDStep3DurationForm(
                fixed_duration=dt.fixed_duration,
                initial={
                    "downtime_value": dt.downtime_value if dt.fixed_duration else wip.get("downtime_value"),
                    "repetition": wip.get("repetition", 1),
                }
            )
        else:
            return redirect("teams:downtime_wizard")

        return render(request, self.template_name, {
            "step": step,
            "form": form,
            "percent": int((step - 1) / 3 * 100),
        })

    def post(self, request):
        step = int(request.POST.get("step"))
        wip = self._get_wip(request)

        if step == 1:
            base_qs = LoginOperator.objects.filter(
                team_user=request.user,
                login_team_date=timezone.localdate(),
                status__in=["ACTIVE", "COMPLETED"],
            )

            first_ids = (
                base_qs
                .values("operator_id")
                .annotate(first_id=Min("id"))
                .values_list("first_id", flat=True)
            )

            qs = LoginOperator.objects.filter(id__in=first_ids)
            form = _TDStep1LoginOperatorsForm(request.POST, queryset=qs)
            if form.is_valid():
                wip["login_operators"] = list(
                    form.cleaned_data["login_operators"].values_list("id", flat=True)
                )
                self._save_wip(request, wip)
                return redirect(f"{reverse('teams:downtime_wizard')}?step=2")

        elif step == 2:
            form = _TDStep2DowntimeForm(request.POST, subdepartment=request.user.subdepartment)
            if form.is_valid():
                dt = form.cleaned_data["downtime"]
                wip["downtime"] = dt.id
                if dt.fixed_duration:
                    wip["downtime_value"] = str(dt.downtime_value)
                    wip["repetition"] = 1
                self._save_wip(request, wip)
                return redirect(f"{reverse('teams:downtime_wizard')}?step=3")

        elif step == 3:
            dt = Downtime.objects.get(pk=wip["downtime"])
            form = _TDStep3DurationForm(request.POST, fixed_duration=dt.fixed_duration)
            if form.is_valid():

                if dt.fixed_duration:
                    downtime_value = Decimal(dt.downtime_value)
                    repetition = int(form.cleaned_data["repetition"])
                else:
                    downtime_value = Decimal(form.cleaned_data["downtime_value"])
                    repetition = 1

                wip["downtime_value"] = str(downtime_value)
                wip["repetition"] = repetition
                wip["downtime_total"] = str(downtime_value * repetition)

                self._save_wip(request, wip)
                return redirect("teams:downtime_wizard_save")

        return render(request, self.template_name, {"form": form, "step": step})


class TeamDowntimeSaveView(TeamAccessMixin, View):
    def get(self, request):
        wip = request.session.get("team_downtime_wip")
        if not wip:
            messages.error(request, "No downtime in progress.")
            return redirect("teams:team_dashboard")

        for lo_id in wip["login_operators"]:
            DowntimeDeclaration.objects.create(
                login_operator_id=lo_id,
                downtime_id=wip["downtime"],
                downtime_value=Decimal(wip["downtime_value"]),
                repetition=int(wip["repetition"]),
                downtime_total=Decimal(wip["downtime_total"]),
            )

        request.session.pop("team_downtime_wip", None)
        messages.success(request, "Downtime declared.")
        return redirect("teams:team_dashboard")


class TeamDowntimeWizardCancelView(TeamAccessMixin, View):
    def get(self, request):
        request.session.pop("team_downtime_wip", None)
        messages.info(request, "Downtime canceled.")
        return redirect("teams:team_dashboard")


# Session helper
def _clear_decl_session(session):
    if "declaration_wip" in session:
        del session["declaration_wip"]


# helper to build human readable preview for template
def _build_wip_preview(wip):
    preview = {
        "pro_name": None,
        "routing_label": None,
        "operation_name": None,
        "qty": wip.get("qty"),
        "operators": [],
        "subdepartment_name": None,
    }

    # PRO
    pro_id = wip.get("pro")
    if pro_id:
        try:
            pro = Pro.objects.get(pk=pro_id)
            preview["pro_name"] = pro.pro_name
        except Pro.DoesNotExist:
            preview["pro_name"] = f"ID:{pro_id}"

    # Routing
    routing_id = wip.get("routing")
    if routing_id:
        try:
            routing = Routing.objects.get(pk=routing_id)
            preview["routing_label"] = f"{routing.sku} / {routing.version}"
        except Routing.DoesNotExist:
            preview["routing_label"] = f"ID:{routing_id}"

    # RoutingOperation
    ro_id = wip.get("routing_operation")
    if ro_id:
        try:
            ro = RoutingOperation.objects.select_related("operation").get(pk=ro_id)
            preview["operation_name"] = str(ro.operation)
        except RoutingOperation.DoesNotExist:
            preview["operation_name"] = f"ID:{ro_id}"

    # Operators (names)
    op_ids = wip.get("operators", []) or []
    if op_ids:
        ops = Operator.objects.filter(pk__in=op_ids).order_by("badge_num")
        preview["operators"] = [f"{o.badge_num} - {o.name}" for o in ops]

    # Subdepartment name
    sd_id = wip.get("subdepartment")
    if sd_id:
        try:
            sd = Subdepartment.objects.get(pk=sd_id)
            preview["subdepartment_name"] = sd.subdepartment
        except Subdepartment.DoesNotExist:
            preview["subdepartment_name"] = f"ID:{sd_id}"

    return preview


class DeclarationWizardView(TeamAccessMixin, View):
    """
    Multi-step declaration wizard using inline forms and session-backed WIP.
    Steps: 1 PRO -> 2 Routing -> 3 RoutingOperation -> 4 Qty -> 5 Operators (conditional)
    Use query param ?step=N for GET and hidden input 'step' for POST.
    """
    template_name = "teams/declaration_step.html"

    def _render_with_context(self, request, step, form, wip):
        """
        helper to compute percent, preview and checkbox_fields and render template
        """
        percent = max(0, min(100, (step - 1) * 25))
        wip_preview = _build_wip_preview(wip)

        # detect checkbox fields for cleaner template logic
        checkbox_fields = [name for name, f in form.fields.items() if isinstance(f.widget, CheckboxSelectMultiple)]

        context = {
            "step": step,
            "form": form,
            "percent": percent,
            "wip_preview": wip_preview,
            "checkbox_fields": checkbox_fields,
        }
        return render(request, self.template_name, context)

    def get(self, request, *args, **kwargs):
        step = int(request.GET.get("step", 1))
        wip = request.session.get("declaration_wip", {})
        user_subdep = request.user.subdepartment

        if step == 1:
            form = _Step1ProForm(initial={"pro": wip.get("pro")}, subdepartment=user_subdep)
        elif step == 2:
            pro_id = wip.get("pro")
            if not pro_id:
                messages.error(request, "Please select a PRO first.")
                return redirect(f"{reverse('teams:declare_output')}?step=1")
            pro = get_object_or_404(Pro, pk=pro_id)
            # pass subdepartment=user_subdep to filter routings to team user's subdepartment
            form = _Step2RoutingForm(initial={"routing": wip.get("routing")}, pro=pro, subdepartment=user_subdep)
        elif step == 3:
            routing_id = wip.get("routing")
            if not routing_id:
                messages.error(request, "Please select a Routing first.")
                return redirect(f"{reverse('teams:declare_output')}?step=2")
            routing = get_object_or_404(Routing, pk=routing_id)
            form = _Step3RoutingOperationForm(initial={"routing_operation": wip.get("routing_operation")}, routing=routing)
        elif step == 4:
            form = _Step4QtyForm(initial={"qty": wip.get("qty")})
        elif step == 5:
            routing_id = wip.get("routing")
            if not routing_id:
                messages.error(request, "Please select a Routing first.")
                return redirect(f"{reverse('teams:declare_output')}?step=2")
            routing = get_object_or_404(Routing, pk=routing_id)
            # Skip operators if declaration_type == TEAM
            if routing.declaration_type and routing.declaration_type.strip().upper() == "TEAM":
                return redirect(reverse("teams:declare_output_save"))
            # otherwise prepare operators queryset from today's active sessions for this team
            today = timezone.localdate()
            sessions_today = LoginOperator.objects.filter(
                team_user=request.user,
                login_team_date=today,
                status__in=["ACTIVE", "COMPLETED"],
            ).select_related("operator")

            ops_qs = Operator.objects.filter(id__in=sessions_today.values_list("operator_id", flat=True)).distinct()
            form = _Step5OperatorsForm(queryset=ops_qs, initial={"operators": wip.get("operators", [])})
        else:
            messages.error(request, "Invalid step.")
            return redirect(f"{reverse('teams:declare_output')}?step=1")

        return self._render_with_context(request, step, form, wip)

    def post(self, request, *args, **kwargs):
        step = int(request.POST.get("step", 1))
        wip = request.session.get("declaration_wip", {})
        user_subdep = request.user.subdepartment

        if step == 1:
            form = _Step1ProForm(request.POST, subdepartment=user_subdep)
            if form.is_valid():
                wip["pro"] = form.cleaned_data["pro"].id
                wip["subdepartment"] = user_subdep.id if user_subdep else None
                request.session["declaration_wip"] = wip
                return redirect(f"{reverse('teams:declare_output')}?step=2")
        elif step == 2:
            pro_id = wip.get("pro")
            if not pro_id:
                messages.error(request, "Please select a PRO first.")
                return redirect(f"{reverse('teams:declare_output')}?step=1")
            pro = get_object_or_404(Pro, pk=pro_id)
            # pass subdepartment here as well so only routings for this subdepartment are shown/validated
            form = _Step2RoutingForm(request.POST, pro=pro, subdepartment=user_subdep)
            if form.is_valid():
                wip["routing"] = form.cleaned_data["routing"].id
                request.session["declaration_wip"] = wip
                return redirect(f"{reverse('teams:declare_output')}?step=3")
        elif step == 3:
            routing_id = wip.get("routing")
            if not routing_id:
                messages.error(request, "Please select a Routing first.")
                return redirect(f"{reverse('teams:declare_output')}?step=2")
            routing = get_object_or_404(Routing, pk=routing_id)
            form = _Step3RoutingOperationForm(request.POST, routing=routing)
            if form.is_valid():
                ro = form.cleaned_data["routing_operation"]
                wip["routing_operation"] = ro.id
                wip["smv"] = str(ro.smv) if ro.smv is not None else None
                wip["smv_ita"] = str(ro.smv_ita) if ro.smv_ita is not None else None
                request.session["declaration_wip"] = wip
                return redirect(f"{reverse('teams:declare_output')}?step=4")
        elif step == 4:
            form = _Step4QtyForm(request.POST)
            if form.is_valid():
                wip["qty"] = form.cleaned_data["qty"]
                request.session["declaration_wip"] = wip
                routing_id = wip.get("routing")
                routing = get_object_or_404(Routing, pk=routing_id)
                if routing.declaration_type and routing.declaration_type.strip().upper() == "TEAM":
                    return redirect(reverse("teams:declare_output_save"))
                else:
                    return redirect(f"{reverse('teams:declare_output')}?step=5")
        elif step == 5:
            today = timezone.localdate()

            sessions_today = LoginOperator.objects.filter(
                team_user=request.user,
                login_team_date=today,
                status__in=["ACTIVE", "COMPLETED"],
            )

            ops_qs = Operator.objects.filter(id__in=sessions_today.values_list("operator_id", flat=True)).distinct()

            form = _Step5OperatorsForm(request.POST, queryset=ops_qs)
            if form.is_valid():
                selected_ids = list(form.cleaned_data["operators"].values_list("id", flat=True))
                if not selected_ids:
                    messages.error(request, "Please select at least one operator.")
                    return redirect(f"{reverse('teams:declare_output')}?step=5")
                wip["operators"] = selected_ids
                request.session["declaration_wip"] = wip
                return redirect(reverse("teams:declare_output_save"))
        else:
            messages.error(request, "Invalid step.")
            return redirect(f"{reverse('teams:declare_output')}?step=1")

        # invalid form -> re-render same step with errors (use helper to build context)
        return self._render_with_context(request, step, form, wip)


class DeclarationSaveView(TeamAccessMixin, View):
    """
    Finalize & persist Declaration using session WIP, then clear session.
    """
    def get(self, request, *args, **kwargs):
        wip = request.session.get("declaration_wip")
        if not wip:
            messages.error(request, "No declaration in progress.")
            return redirect(reverse("teams:team_dashboard"))

        try:
            pro = Pro.objects.get(id=wip["pro"])
            routing = Routing.objects.get(id=wip["routing"])
        except (Pro.DoesNotExist, Routing.DoesNotExist):
            messages.error(request, "Invalid PRO or Routing in WIP.")
            _clear_decl_session(request.session)
            return redirect(reverse("teams:team_dashboard"))

        # Defensive check: routing must belong to current user's subdepartment
        if routing.subdepartment_id != request.user.subdepartment_id:
            messages.error(request, "Selected routing does not belong to your subdepartment.")
            _clear_decl_session(request.session)
            return redirect(reverse("teams:team_dashboard"))

        routing_operation = None
        if wip.get("routing_operation"):
            try:
                routing_operation = RoutingOperation.objects.get(id=wip["routing_operation"])
            except RoutingOperation.DoesNotExist:
                routing_operation = None

        qty = int(wip.get("qty", 0))
        if qty <= 0:
            messages.error(request, "Invalid quantity.")
            return redirect(f"{reverse('teams:declare_output')}?step=4")

        decl = Declaration.objects.create(
            decl_date=timezone.localdate(),
            teamuser=request.user,
            subdepartment=request.user.subdepartment,
            pro=pro,
            routing=routing,
            routing_operation=routing_operation,
            qty=qty,
            smv=(wip.get("smv") or (routing_operation.smv if routing_operation else None)),
            smv_ita=(wip.get("smv_ita") or (routing_operation.smv_ita if routing_operation else None)),
        )

        # if routing requires operators
        if routing.declaration_type and routing.declaration_type.strip().upper() == "OPERATOR":
            operator_ids = wip.get("operators", [])
            if not operator_ids:
                decl.delete()
                messages.error(request, "Declaration requires operators but none selected.")
                return redirect(f"{reverse('teams:declare_output')}?step=5")
            decl.operators.add(*operator_ids)

        _clear_decl_session(request.session)
        messages.success(request, f"Declaration saved.")
        return redirect(reverse("teams:team_dashboard"))


class DeclarationWizardCancelView(TeamAccessMixin, View):
    """
    Clear the teams declaration wizard WIP from session and redirect to team dashboard.
    """
    def get(self, request, *args, **kwargs):
        # Use helper if available
        try:
            _clear_decl_session(request.session)
        except Exception:
            # fallback: remove key directly
            request.session.pop("declaration_wip", None)
            request.session.modified = True

        messages.info(request, "Declaration canceled.")
        return redirect(reverse("teams:team_dashboard"))



# ---------- DECLARE BREAK (INLINE FORMS) ----------

class _BreakStep1Form(forms.Form):
    break_type = forms.ChoiceField(
        label="Select break",
        required=True,
        choices=[],  # puni se ručno
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        choices = [("", "— Select break —")]
        for b in Break.objects.all().order_by("break_time_start"):
            choices.append((
                str(b.id),
                f"{b.break_name} ({b.break_time_start:%H:%M}–{b.break_time_end:%H:%M})"
            ))

        self.fields["break_type"].choices = choices
        self.fields["break_type"].widget.attrs.update({
            "class": "form-select",
        })




class _BreakStep2OperatorsForm(forms.Form):
    operators = forms.ModelMultipleChoiceField(
        queryset=Operator.objects.none(),
        widget=CheckboxSelectMultiple,
        label="Operators",
        required=True,
    )

    def __init__(self, *args, **kwargs):
        qs = kwargs.pop("queryset", None)
        super().__init__(*args, **kwargs)
        if qs is not None:
            self.fields["operators"].queryset = qs


class DeclareBreakWizardView(TeamAccessMixin, View):
    template_name = "teams/declare_break_step.html"

    def _render(self, request, step, form):
        checkbox_fields = [
            name for name, f in form.fields.items()
            if isinstance(f.widget, CheckboxSelectMultiple)
        ]
        return render(request, self.template_name, {
            "step": step,
            "form": form,
            "percent": 50 if step == 2 else 0,
            "checkbox_fields": checkbox_fields,
        })

    def get(self, request, *args, **kwargs):
        step = int(request.GET.get("step", 1))
        wip = request.session.get("break_wip", {})

        if step == 1:
            if wip.get("break"):
                form = _BreakStep1Form(initial={"break_type": wip.get("break")})
            else:
                form = _BreakStep1Form()

        elif step == 2:
            today = timezone.localdate()

            sessions = LoginOperator.objects.filter(
                team_user=request.user,
                login_team_date=today,
                status="ACTIVE",
            ).select_related("operator")

            ops_qs = Operator.objects.filter(
                id__in=sessions.values_list("operator_id", flat=True)
            ).distinct().order_by("badge_num")

            form = _BreakStep2OperatorsForm(
                queryset=ops_qs,
                initial={"operators": wip.get("operators", [])},
            )
        else:
            return redirect(f"{reverse('teams:declare_break')}?step=1")

        return self._render(request, step, form)

    def post(self, request, *args, **kwargs):
        step = int(request.POST.get("step", 1))
        wip = request.session.get("break_wip", {})

        if step == 1:
            form = _BreakStep1Form(request.POST)
            if form.is_valid():
                wip["break"] = int(form.cleaned_data["break_type"])
                request.session["break_wip"] = wip
                return redirect(f"{reverse('teams:declare_break')}?step=2")

        elif step == 2:
            today = timezone.localdate()

            sessions = LoginOperator.objects.filter(
                team_user=request.user,
                login_team_date=today,
                status="ACTIVE",
            )

            ops_qs = Operator.objects.filter(
                id__in=sessions.values_list("operator_id", flat=True)
            ).distinct()

            form = _BreakStep2OperatorsForm(request.POST, queryset=ops_qs)
            if form.is_valid():
                wip["operators"] = list(
                    form.cleaned_data["operators"].values_list("id", flat=True)
                )
                request.session["break_wip"] = wip
                return redirect("teams:declare_break_save")

        return self._render(request, step, form)


class DeclareBreakSaveView(TeamAccessMixin, View):
    def get(self, request, *args, **kwargs):
        wip = request.session.get("break_wip")
        if not wip:
            messages.error(request, "No break declaration in progress.")
            return redirect("teams:team_dashboard")

        break_type = get_object_or_404(Break, id=wip["break"])
        today = timezone.localdate()
        team_user = request.user

        # PRAVILO 3:
        # operator ima pauzu danas, ali za DRUGI team → ERROR
        conflicts = OperatorBreak.objects.filter(
            operator_id__in=wip["operators"],
            date=today,
        ).exclude(team_user=team_user)

        if conflicts.exists():
            ops = ", ".join(
                str(ob.operator) for ob in conflicts.select_related("operator")
            )
            messages.error(
                request,
                f"Break NOT saved. Operator(s) already have a break today for another team: {ops}"
            )
            request.session.pop("break_wip", None)
            return redirect("teams:team_dashboard")

        created_count = 0
        updated_count = 0

        # PRAVILO 1 i 2:
        # - nema pauze → CREATE
        # - ima pauzu za isti team → OVERWRITE
        for op_id in wip["operators"]:
            obj, created = OperatorBreak.objects.update_or_create(
                date=today,
                operator_id=op_id,
                team_user=team_user,
                defaults={
                    "break_type": break_type,
                }
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        request.session.pop("break_wip", None)

        messages.success(
            request,
            f"Break saved: {created_count} created, {updated_count} updated."
        )
        return redirect("teams:team_dashboard")
