from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from .models import *

# ------- HELPER FOR DATE+TIME FORMAT -------
def format_datetime(obj):
    if obj:
        return obj.strftime("%d.%m.%Y. %H:%M")
    return "-"

format_datetime.short_description = "Date/Time"


# --------- CUSTOM FORM FOR LoginOperator (for nice date/time formats) ---------
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

        self.fields["login_actual"].input_formats = ["%d.%m.%Y. %H:%M"]
        self.fields["logoff_actual"].input_formats = ["%d.%m.%Y. %H:%M"]
        self.fields["login_team_date"].input_formats = ["%d.%m.%Y."]
        self.fields["logoff_team_date"].input_formats = ["%d.%m.%Y."]
        self.fields["login_team_time"].input_formats = ["%H:%M"]
        self.fields["logoff_team_time"].input_formats = ["%H:%M"]


# ------- TEAM USER -------
@admin.register(TeamUser)
class TeamUserAdmin(UserAdmin):
    model = TeamUser

    # Formatirana polja
    def created_at_fmt(self, obj):
        return format_datetime(obj.created_at)
    created_at_fmt.short_description = "Created"

    def updated_at_fmt(self, obj):
        return format_datetime(obj.updated_at)
    updated_at_fmt.short_description = "Updated"

    # Prikaz grupa u listi
    def groups_list(self, obj):
        groups = obj.groups.all()
        return ", ".join([g.name for g in groups]) if groups else "-"
    groups_list.short_description = "Groups"

    list_display = (
        "id",
        "username",
        "subdepartment",
        "team_location",
        "login_grace_period",
        "groups_list",
        "is_staff",
        "is_active",
        "created_at_fmt",
        "updated_at_fmt",
    )

    list_filter = (
        "subdepartment",
        "team_location",
        "login_grace_period",
        "is_staff",
        "is_active",
        "groups",
    )

    search_fields = (
        "username",
        "team_location",
        "subdepartment__subdepartment",
    )

    ordering = ("username",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            "Personal info",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "subdepartment",
                    "team_location",
                    "login_grace_period",
                )
            },
        ),
        ("Audit info", {"fields": ("created_at", "updated_at")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "subdepartment",
                    "team_location",
                    "login_grace_period",
                    "password1",
                    "password2",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
    )



    readonly_fields = ("created_at", "updated_at")


# ------- SUBDEPARTMENT -------
@admin.register(Subdepartment)
class SubdepartmentAdmin(admin.ModelAdmin):
    def created_at_fmt(self, obj):
        return format_datetime(obj.created_at)
    created_at_fmt.short_description = "Created"

    def updated_at_fmt(self, obj):
        return format_datetime(obj.updated_at)
    updated_at_fmt.short_description = "Updated"

    list_display = ("id", "subdepartment", "created_at_fmt", "updated_at_fmt")
    search_fields = ("subdepartment",)
    ordering = ("subdepartment",)
    readonly_fields = ("created_at", "updated_at")


# ------- OPERATOR -------
@admin.register(Operator)
class OperatorAdmin(admin.ModelAdmin):
    def created_at_fmt(self, obj):
        return format_datetime(obj.created_at)
    created_at_fmt.short_description = "Created"

    def updated_at_fmt(self, obj):
        return format_datetime(obj.updated_at)
    updated_at_fmt.short_description = "Updated"

    list_display = (
        "id",
        "badge_num",
        "name",
        "act",
        "func",
        "created_at_fmt",
        "updated_at_fmt",
    )
    search_fields = ("badge_num", "name", "func")
    list_filter = ("act", "func")
    ordering = ("badge_num",)
    readonly_fields = ("created_at", "updated_at")


# ------- CALENDAR -------
@admin.register(Calendar)
class CalendarAdmin(admin.ModelAdmin):
    def created_at_fmt(self, obj):
        return format_datetime(obj.created_at)
    created_at_fmt.short_description = "Created"

    def updated_at_fmt(self, obj):
        return format_datetime(obj.updated_at)
    updated_at_fmt.short_description = "Updated"

    list_display = (
        "id",
        "date",
        "team_user",
        "shift_start",
        "shift_end",
        "created_at_fmt",
        "updated_at_fmt",
    )
    list_filter = ("date", "team_user")
    search_fields = ("team_user__username",)
    ordering = ("-date", "team_user__username")
    readonly_fields = ("created_at", "updated_at")


# ------- PRO -------
@admin.register(Pro)
class ProAdmin(admin.ModelAdmin):
    def created_at_fmt(self, obj):
        return format_datetime(obj.created_at)
    created_at_fmt.short_description = "Created"

    def updated_at_fmt(self, obj):
        return format_datetime(obj.updated_at)
    updated_at_fmt.short_description = "Updated"

    list_display = (
        "id",
        "pro_name",
        "sku",
        "qty",
        "del_date",
        "status",
        "destination",
        "tpp",
        "skeda",
        "created_at_fmt",
        "updated_at_fmt",
    )
    list_filter = ("status", "del_date", "destination")
    search_fields = ("pro_name", "sku", "destination", "tpp", "skeda")
    ordering = ("del_date", "pro_name")
    readonly_fields = ("created_at", "updated_at")


# ------- PRO SUBDEPARTMENT -------
@admin.register(ProSubdepartment)
class ProSubdepartmentAdmin(admin.ModelAdmin):
    def created_at_fmt(self, obj):
        return format_datetime(obj.created_at)
    created_at_fmt.short_description = "Created"

    def updated_at_fmt(self, obj):
        return format_datetime(obj.updated_at)
    updated_at_fmt.short_description = "Updated"

    list_display = (
        "id",
        "pro",
        "subdepartment",
        "active",
        "created_at_fmt",
        "updated_at_fmt",
    )
    list_filter = ("active", "subdepartment")
    search_fields = ("pro__pro_name", "subdepartment__subdepartment")
    ordering = ("pro__del_date", "subdepartment__subdepartment")
    readonly_fields = ("created_at", "updated_at")


# ------- ROUTING -------
@admin.register(Routing)
class RoutingAdmin(admin.ModelAdmin):
    def created_at_fmt(self, obj):
        return format_datetime(obj.created_at)
    created_at_fmt.short_description = "Created"

    def updated_at_fmt(self, obj):
        return format_datetime(obj.updated_at)
    updated_at_fmt.short_description = "Updated"

    list_display = (
        "id",
        "sku",
        "subdepartment",
        "version",
        "status",
        "version_description",
        "created_at_fmt",
        "updated_at_fmt",
    )
    search_fields = ("sku", "version", "subdepartment__subdepartment")
    list_filter = ("subdepartment", "status")
    ordering = ("sku", "version")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "sku",
                    "subdepartment",
                    "version",
                    "status",
                    "version_description",
                )
            },
        ),
        ("Audit info", {"fields": ("created_at", "updated_at")}),
    )


# ------- OPERATION -------
@admin.register(Operation)
class OperationAdmin(admin.ModelAdmin):
    def created_at_fmt(self, obj):
        return format_datetime(obj.created_at)
    created_at_fmt.short_description = "Created"

    def updated_at_fmt(self, obj):
        return format_datetime(obj.updated_at)
    updated_at_fmt.short_description = "Updated"

    list_display = (
        "id",
        "name",
        "subdepartment",
        "description",
        "created_at_fmt",
        "updated_at_fmt",
    )
    search_fields = ("name", "description", "subdepartment__subdepartment")
    list_filter = ("subdepartment",)
    ordering = ("subdepartment__subdepartment", "name")
    readonly_fields = ("created_at", "updated_at")


# ------- ROUTING OPERATION -------
@admin.register(RoutingOperation)
class RoutingOperationAdmin(admin.ModelAdmin):
    def created_at_fmt(self, obj):
        return format_datetime(obj.created_at)
    created_at_fmt.short_description = "Created"

    def updated_at_fmt(self, obj):
        return format_datetime(obj.updated_at)
    updated_at_fmt.short_description = "Updated"

    list_display = (
        "id",
        "routing",
        "operation",
        "operation_description",
        "smv",
        "declaration_type",
        "final_operation",
        "created_at_fmt",
        "updated_at_fmt",
    )
    list_filter = ("routing", "operation", "final_operation")
    search_fields = (
        "routing__sku",
        "routing__version",
        "operation__name",
        "operation_description",
    )
    ordering = ("routing", "id")
    readonly_fields = ("created_at", "updated_at")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "routing":
            kwargs["queryset"] = Routing.objects.filter(status=True).order_by(
                "sku", "version"
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ------- LOGIN OPERATOR -------
@admin.register(LoginOperator)
class LoginOperatorAdmin(admin.ModelAdmin):
    form = LoginOperatorForm

    def login_actual_fmt(self, obj):
        return format_datetime(obj.login_actual)
    login_actual_fmt.short_description = "Login actual"

    def logoff_actual_fmt(self, obj):
        return format_datetime(obj.logoff_actual)
    logoff_actual_fmt.short_description = "Logoff actual"

    def created_at_fmt(self, obj):
        return format_datetime(obj.created_at)
    created_at_fmt.short_description = "Created"

    def updated_at_fmt(self, obj):
        return format_datetime(obj.updated_at)
    updated_at_fmt.short_description = "Updated"

    list_display = (
        "id",
        "operator",
        "team_user",
        "status",
        "login_actual_fmt",
        "logoff_actual_fmt",
        "login_team_date",
        "login_team_time",
        "logoff_team_date",
        "logoff_team_time",
        "break_time",
        "created_at_fmt",
        "updated_at_fmt",
    )

    list_filter = (
        "status",
        "team_user",
        "operator",
        "login_team_date",
        "logoff_team_date",
        "break_time",
    )

    search_fields = (
        "operator__badge_num",
        "operator__name",
        "team_user__username",
        "status",
    )

    ordering = ("-login_actual",)
    readonly_fields = ("created_at", "updated_at")


# ------- DECLARATION -------
@admin.register(Declaration)
class DeclarationAdmin(admin.ModelAdmin):
    """
    Admin for Declaration model. Shows operators in list view and
    provides horizontal filter for selecting operators in the form.
    """
    def created_at_fmt(self, obj):
        return format_datetime(obj.created_at)
    created_at_fmt.short_description = "Created"

    def updated_at_fmt(self, obj):
        return format_datetime(obj.updated_at)
    updated_at_fmt.short_description = "Updated"

    def operators_display(self, obj):
        ops = obj.operators.all()
        if not ops:
            return "-"
        return ", ".join([f"{o.badge_num} - {o.name}" for o in ops])
    operators_display.short_description = "Operators"

    list_display = (
        "id",
        "decl_date",
        "teamuser",
        "subdepartment",
        "pro",
        "routing",
        "routing_operation",
        "qty",
        "smv",
        "smv_ita",
        "operators_display",
        "created_at_fmt",
        "updated_at_fmt",
    )

    list_filter = ("decl_date", "teamuser", "subdepartment", "pro", "routing")
    search_fields = (
        "id",
        "teamuser__username",
        "pro__pro_name",
        "routing__sku",
        "routing__version",
    )
    ordering = ("-decl_date", "teamuser__username")
    readonly_fields = ("created_at", "updated_at")

    # usability: horizontal filter for operators (good for many operators)
    filter_horizontal = ("operators",)

    fieldsets = (
        (None, {"fields": ("decl_date", "teamuser", "subdepartment")}),
        ("Work info", {"fields": ("pro", "routing", "routing_operation", "qty", "smv", "smv_ita", "operators")}),
        ("Audit info", {"fields": ("created_at", "updated_at")}),
    )


# ------- BREAK -------
@admin.register(Break)
class BreakAdmin(admin.ModelAdmin):

    def created_at_fmt(self, obj):
        return format_datetime(obj.created_at)
    created_at_fmt.short_description = "Created"

    def updated_at_fmt(self, obj):
        return format_datetime(obj.updated_at)
    updated_at_fmt.short_description = "Updated"

    list_display = (
        "id",
        "break_name",
        "break_time_start",
        "break_time_end",
        "created_at_fmt",
        "updated_at_fmt",
    )

    search_fields = ("break_name",)
    ordering = ("break_time_start",)
    readonly_fields = ("created_at", "updated_at")


# ------- OPERATOR BREAK -------
@admin.register(OperatorBreak)
class OperatorBreakAdmin(admin.ModelAdmin):

    def created_at_fmt(self, obj):
        return format_datetime(obj.created_at)
    created_at_fmt.short_description = "Created"

    def updated_at_fmt(self, obj):
        return format_datetime(obj.updated_at)
    updated_at_fmt.short_description = "Updated"

    list_display = (
        "id",
        "date",
        "operator",
        "break_type",
        "created_at_fmt",
        "updated_at_fmt",
    )

    list_filter = (
        "date",
        "break_type",
        "operator",
    )

    search_fields = (
        "operator__badge_num",
        "operator__name",
        "break_type__break_name",
    )

    ordering = ("-date", "operator")
    readonly_fields = ("created_at", "updated_at")


# ------- DOWNTIME -------

@admin.register(Downtime)
class DowntimeAdmin(admin.ModelAdmin):

    def created_at_fmt(self, obj):
        return format_datetime(obj.created_at)
    created_at_fmt.short_description = "Created"

    def updated_at_fmt(self, obj):
        return format_datetime(obj.updated_at)
    updated_at_fmt.short_description = "Updated"

    list_display = (
        "id",
        "downtime_name",
        "subdepartment",
        "fixed_duration",
        "downtime_value",
        "created_at_fmt",
        "updated_at_fmt",
    )

    list_filter = (
        "subdepartment",
        "fixed_duration",
        "downtime_value",
    )

    search_fields = (
        "downtime_name",
        "subdepartment__subdepartment",
    )

    ordering = (
        "subdepartment__subdepartment",
        "downtime_name",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "downtime_name",
                    "subdepartment",
                    "fixed_duration",
                    "downtime_value",
                )
            },
        ),
        ("Audit info", {"fields": ("created_at", "updated_at")}),
    )

# ------- DOWNTIME DECLARATION -------
@admin.register(DowntimeDeclaration)
class DowntimeDeclarationAdmin(admin.ModelAdmin):

    def created_at_fmt(self, obj):
        return format_datetime(obj.created_at)
    created_at_fmt.short_description = "Created"

    def updated_at_fmt(self, obj):
        return format_datetime(obj.updated_at)
    updated_at_fmt.short_description = "Updated"

    list_display = (
        "id",
        "login_operator",
        "downtime",
        "downtime_value",
        "repetition",
        "downtime_total",
        "created_at_fmt",
        "updated_at_fmt",
    )

    list_filter = (
        "downtime",
        "login_operator",
        "created_at",
    )

    search_fields = (
        "login_operator__operator__badge_num",
        "login_operator__operator__name",
        "downtime__downtime_name",
    )

    ordering = ("-created_at",)

    readonly_fields = (
        "downtime_total",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "login_operator",
                    "downtime",
                )
            },
        ),
        (
            "Values",
            {
                "fields": (
                    "downtime_value",
                    "repetition",
                    "downtime_total",
                )
            },
        ),
        ("Audit info", {"fields": ("created_at", "updated_at")}),
    )
