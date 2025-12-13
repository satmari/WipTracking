from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class TeamUserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError("The username must be set")

        username = username.lower().strip()
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")

        return self.create_user(username, password, **extra_fields)


class Subdepartment(models.Model):
    subdepartment = models.CharField(max_length=100, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Subdepartment"
        verbose_name_plural = "Subdepartments"
        ordering = ["subdepartment"]

    def __str__(self):
        return self.subdepartment


class TeamUser(AbstractUser):
    email = None  # remove email

    subdepartment = models.ForeignKey(
        "Subdepartment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Subdepartment",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    objects = TeamUserManager()

    class Meta:
        verbose_name = "Team User"
        verbose_name_plural = "Team Users"

    def __str__(self):
        return self.username


class Calendar(models.Model):
    date = models.DateField(verbose_name="Date")
    team_user = models.ForeignKey(
        TeamUser,
        on_delete=models.CASCADE,
        related_name="calendar_entries",
        verbose_name="Team User",
    )
    shift_start = models.TimeField(verbose_name="Shift start")
    shift_end = models.TimeField(verbose_name="Shift end")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Calendar entry"
        verbose_name_plural = "Calendar"
        ordering = ["-date", "team_user__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["date", "team_user"],
                name="unique_calendar_per_user_date",
            )
        ]

    def __str__(self):
        return f"{self.date} - {self.team_user} ({self.shift_start}–{self.shift_end})"


class Operator(models.Model):
    badge_num = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Badge Number",
    )
    name = models.CharField(max_length=100, verbose_name="Name")
    act = models.BooleanField(default=True, verbose_name="Active")
    pin_code = models.CharField(max_length=20, verbose_name="Pin Code")
    func = models.CharField(max_length=100, verbose_name="Function")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Operator"
        verbose_name_plural = "Operators"
        ordering = ["badge_num"]

    def __str__(self):
        return f"{self.badge_num} - {self.name}"


# --------- PRO ---------

class Pro(models.Model):
    pro_name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="PRO Name"
    )

    # ostala polja su opcionalna
    sku = models.CharField(
        max_length=100,
        verbose_name="SKU",
        blank=True
    )
    qty = models.PositiveIntegerField(
        verbose_name="Quantity",
        null=True,
        blank=True
    )
    del_date = models.DateField(
        verbose_name="Delivery date",
        null=True,
        blank=True
    )
    status = models.BooleanField(
        default=True,
        verbose_name="Active",
    )
    destination = models.CharField(
        max_length=100,
        verbose_name="Destination",
        blank=True
    )
    tpp = models.CharField(
        max_length=50,
        verbose_name="TPP",
        blank=True
    )
    skeda = models.CharField(
        max_length=50,
        verbose_name="Skeda",
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "PRO"
        verbose_name_plural = "PROs"
        ordering = ["del_date", "pro_name"]

    def __str__(self):
        return self.pro_name


class ProSubdepartment(models.Model):
    pro = models.ForeignKey(
        Pro,
        on_delete=models.CASCADE,
        related_name="pro_subdepartments",
        verbose_name="PRO",
    )
    subdepartment = models.ForeignKey(
        Subdepartment,
        on_delete=models.CASCADE,
        related_name="pro_subdepartments",
        verbose_name="Subdepartment",
    )
    active = models.BooleanField(default=True, verbose_name="Active")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "PRO Subdepartment"
        verbose_name_plural = "PRO Subdepartments"
        constraints = [
            models.UniqueConstraint(
                fields=["pro", "subdepartment"],
                name="unique_pro_subdepartment",
            )
        ]

    def __str__(self):
        return f"{self.pro.pro_name} -> {self.subdepartment} ({'active' if self.active else 'inactive'})"


# --------- ROUTING ---------

class Routing(models.Model):
    sku = models.CharField(
        max_length=100,
        verbose_name="SKU",
    )
    subdepartment = models.ForeignKey(
        Subdepartment,
        on_delete=models.CASCADE,
        related_name="routings",
        verbose_name="Subdepartment",
    )
    version = models.CharField(
        max_length=20,
        verbose_name="Version",
    )

    version_description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Version description",
    )

    declaration_type = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Declaration type",
    )

    ready = models.BooleanField(          # NOVO POLJE
        default=False,
        verbose_name="Ready",
    )

    status = models.BooleanField(
        default=True,
        verbose_name="Active",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Routing"
        verbose_name_plural = "Routings"
        constraints = [
            models.UniqueConstraint(
                fields=["sku", "subdepartment", "version"],
                name="unique_routing_sku_subdep_version",
            )
        ]
        ordering = ["sku", "version"]

    def __str__(self):
        return f"{self.sku} / {self.subdepartment} / {self.version}"


# --------- OPERATION ---------

class Operation(models.Model):
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Operation name",
    )
    subdepartment = models.ForeignKey(
        Subdepartment,
        on_delete=models.CASCADE,
        related_name="operations",
        verbose_name="Subdepartment",
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Operation description",
    )

    status = models.BooleanField(           # NOVO POLJE
        default=True,
        verbose_name="Active",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Operation"
        verbose_name_plural = "Operations"
        ordering = ["subdepartment__subdepartment", "name"]

    def __str__(self):
        return f"{self.name} / {self.subdepartment}"


# --------- ROUTING_OPERATION ---------

class RoutingOperation(models.Model):
    routing = models.ForeignKey(
        Routing,
        on_delete=models.CASCADE,
        related_name="routing_operations",
        verbose_name="Routing",
    )
    operation = models.ForeignKey(
        Operation,
        on_delete=models.CASCADE,
        related_name="routing_operations",
        verbose_name="Operation",
    )

    operation_description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Operation description",
    )
    smv = models.DecimalField(
        max_digits=7,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name="SMV",
    )
    smv_ita = models.DecimalField(
        max_digits=7,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name="SMV ITA",
    )
    declaration_type = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Declaration type",
    )
    final_operation = models.BooleanField(
        default=False,
        verbose_name="Final operation",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Routing Operation"
        verbose_name_plural = "Routing Operations"
        constraints = [
            models.UniqueConstraint(
                fields=["routing", "operation"],
                name="unique_routing_operation",
            )
        ]
        ordering = ["routing", "id"]

    def __str__(self):
        return f"{self.routing} -> {self.operation}"

    def clean(self):
        super().clean()
        if self.routing and self.operation:
            if self.routing.subdepartment_id != self.operation.subdepartment_id:
                raise ValidationError(
                    "Routing and Operation must belong to the same Subdepartment."
                )


# --------- LOGIN OPERATOR ---------

class LoginOperator(models.Model):
    STATUS_CHOICES = (
        ('ACTIVE', 'ACTIVE'),
        ('COMPLETED', 'COMPLETED'),
        ('ERROR', 'ERROR'),
        ('IGNORE', 'IGNORE'),
    )

    operator = models.ForeignKey(
        Operator,
        on_delete=models.CASCADE,
        related_name='operators',
        verbose_name='Operator',
    )
    team_user = models.ForeignKey(
        TeamUser,
        on_delete=models.CASCADE,
        related_name='team_users',
        verbose_name='Team user',
    )

    # stvarno vreme (server)
    login_actual = models.DateTimeField(verbose_name='Login actual')
    login_team_date = models.DateField(verbose_name='Login team date')
    login_team_time = models.TimeField(verbose_name='Login team time')

    logoff_actual = models.DateTimeField(
        verbose_name='Logoff actual',
        null=True,
        blank=True,
    )
    logoff_team_date = models.DateField(
        verbose_name='Logoff team date',
        null=True,
        blank=True,
    )
    logoff_team_time = models.TimeField(
        verbose_name='Logoff team time',
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='ACTIVE',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Login Operator'
        verbose_name_plural = 'Login Operator'
        ordering = ['-login_actual']

    def __str__(self):
        return f'{self.operator} / {self.team_user} / {self.status}'

# ------------ DECLARATIONS

class Declaration(models.Model):
    """
    Declaration record created by Team users.
    """
    # auto id field will be used (id)
    decl_date = models.DateField(
        verbose_name="Declaration date",
        default=timezone.localdate
    )
    teamuser = models.ForeignKey(
        'TeamUser',
        on_delete=models.CASCADE,
        related_name='declarations',
        verbose_name='Team user',
    )
    subdepartment = models.ForeignKey(
        'Subdepartment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Subdepartment',
    )
    pro = models.ForeignKey(
        'Pro',
        on_delete=models.CASCADE,
        related_name='declarations',
        verbose_name='PRO',
    )
    routing = models.ForeignKey(
        'Routing',
        on_delete=models.CASCADE,
        related_name='declarations',
        verbose_name='Routing',
    )
    routing_operation = models.ForeignKey(
        'RoutingOperation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='declarations',
        verbose_name='Routing operation',
    )
    smv = models.DecimalField(
        max_digits=7,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name='SMV',
    )
    smv_ita = models.DecimalField(
        max_digits=7,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name='SMV ITA',
    )
    qty = models.PositiveIntegerField(
        verbose_name='Quantity',
    )
    # multiple operators possible (one or more) — blank allowed because TEAM type skips this step
    operators = models.ManyToManyField(
        'Operator',
        blank=True,
        related_name='declarations',
        verbose_name='Operators'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Declaration"
        verbose_name_plural = "Declarations"
        ordering = ['-decl_date', 'teamuser__username']

    def __str__(self):
        return f"Decl {self.id} - {self.pro} / {self.routing} / {self.qty}"