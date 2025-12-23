from django import forms
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView
from django.views import View
from django.shortcuts import redirect, get_object_or_404, render
from django.contrib import messages
from django.utils import timezone
from django.urls import reverse
from django.forms.widgets import CheckboxSelectMultiple

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

        # ne sme posle kraja smene (koristimo lokalno vreme)
        if current_time > shift_end:
            messages.error(request, "You cannot log in operators after the end of the shift.")
            return redirect("teams:operator_login")

        # --- PROVERA POSTOJEĆIH AKTIVNIH SESIJA ZA OVOG OPERATERA DANAS ---

        active_today_qs = LoginOperator.objects.filter(
            operator=operator, status="ACTIVE", login_team_date=current_date
        )

        # 1) već prijavljen u ISTI tim danas -> poruka, ne dozvoliti login
        same_team_session = active_today_qs.filter(team_user=request.user).first()
        if same_team_session:
            messages.error(request, "This operator is already logged in this team today.")
            return redirect("teams:operator_login")

        # 2) prijavljen u DRUGI tim danas -> automatski ga odjavljujemo iz tog tima
        other_team_sessions = active_today_qs.exclude(team_user=request.user)

        for s in other_team_sessions:
            other_calendar = Calendar.objects.filter(team_user=s.team_user, date=current_date).first()

            # stvarno vreme logoff-a uvek čuvamo kao UTC
            s.logoff_actual = now

            if other_calendar:
                other_shift_start = other_calendar.shift_start
                other_shift_end = other_calendar.shift_end

                # login vreme u lokalnoj zoni
                login_local_time = timezone.localtime(s.login_actual).time()

                # IGNORE slučaj:
                # - login pre početka smene
                # - auto-logout pre početka smene
                if login_local_time < other_shift_start and current_time < other_shift_start:
                    s.logoff_team_date = other_calendar.date
                    s.logoff_team_time = other_shift_start
                    s.status = "IGNORE"
                else:
                    # standardna logika:
                    # - u toku smene -> actual
                    # - posle smene -> shift_end
                    s.logoff_team_date = other_calendar.date
                    if current_time <= other_shift_end:
                        s.logoff_team_time = current_time
                    else:
                        s.logoff_team_time = other_shift_end
                    s.status = "COMPLETED"
            else:
                # fallback ako nema calendar reda za onaj tim
                s.logoff_team_date = current_date
                s.logoff_team_time = current_time
                s.status = "COMPLETED"

            s.save()

        if other_team_sessions.exists():
            messages.info(
                request,
                "Operator was logged out from another team and will be logged in to this team.",
            )

        # --- LOGIN TEAM TIME LOGIKA (lokalno) ---

        # - pre smene -> shift_start
        # - u toku smene -> actual time
        if current_time < shift_start:
            team_time = shift_start
        else:
            team_time = current_time

        team_date = calendar_entry.date

        LoginOperator.objects.create(
            operator=operator,
            team_user=request.user,
            login_actual=now,  # UTC
            login_team_date=team_date,
            login_team_time=team_time,
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

# Inline forms — no separate forms.py required


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
    routing = forms.ModelChoiceField(queryset=Routing.objects.none(), label="Select Routing")

    def __init__(self, *args, **kwargs):
        # accept 'pro' and 'subdepartment' to allow server-side filtering
        pro = kwargs.pop("pro", None)
        subdepartment = kwargs.pop("subdepartment", None)
        super().__init__(*args, **kwargs)

        if pro:
            qs = Routing.objects.filter(
                status=True,
                ready=True,
                sku__iexact=pro.sku,
            )
            # enforce subdepartment filter if provided (team user's subdepartment)
            if subdepartment:
                qs = qs.filter(subdepartment=subdepartment)
            self.fields["routing"].queryset = qs.order_by("sku", "version")
        else:
            self.fields["routing"].queryset = Routing.objects.none()

        self.fields["routing"].widget.attrs.update({
            "class": "form-select",
            "data-placeholder": "— Select Routing —",
        })


class _Step3RoutingOperationForm(forms.Form):
    routing_operation = forms.ModelChoiceField(queryset=RoutingOperation.objects.none(), label="Select Routing Operation")

    def __init__(self, *args, **kwargs):
        routing = kwargs.pop("routing", None)
        super().__init__(*args, **kwargs)
        if routing:
            self.fields["routing_operation"].queryset = routing.routing_operations.all()
        self.fields["routing_operation"].widget.attrs.update({
            "class": "form-select",
            "data-placeholder": "— Select Operation —",
        })


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
