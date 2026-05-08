from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils.text import slugify
from django.conf import settings
from django.contrib.auth.models import Group

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        """Create and return a regular user."""
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and return a superuser."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if not extra_fields.get('is_staff'):
            raise ValueError('Superuser must have is_staff=True.')
        if not extra_fields.get('is_superuser'):
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=50, unique=True, blank=True, null=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    groups = models.ManyToManyField(Group, blank=True)
    image = models.URLField(blank=True, null=True)
    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    def __str__(self):
        return self.email


class BaseModel(models.Model):
    """ Base model to include common fields like created_by, updated_by, timestamps, and media files """
    name = models.CharField(max_length=150, unique=False)
    slug = models.SlugField(max_length=200, unique=False, blank=True, editable=False)
    description = models.TextField(blank=True, null=True)
    image = models.URLField(blank=True, null=True)  # ✅ Image URL (optional)
    video = models.URLField(blank=True, null=True)  # ✅ Video URL (optional)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="%(class)s_created"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="%(class)s_updated"
    )
    active = models.BooleanField(default=True)

    class Meta:
        abstract = True  # ✅ Prevents table creation for this model

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Objective(BaseModel):
    pass  # ✅ Inherits fields from BaseModel

class Position(BaseModel):
    pass  # ✅ Inherits fields from BaseModel

class Prop(BaseModel):
    pass  # ✅ Inherits fields from BaseModel

class Machine(BaseModel):
    pass  # ✅ Inherits fields from BaseModel

class Center(BaseModel):
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ["name"]

class Room(BaseModel):
    center = models.ForeignKey("core_data.Center", on_delete=models.CASCADE, related_name="rooms")    
    capacity = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('center', 'name')
        ordering = ["center__name", "name"]

class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    image = models.URLField(blank=True, null=True)  # <-- Añade esta línea

    def __str__(self):
        return self.name

class Spring(models.Model):
    """Stores different types of springs used in the reformer or tower."""
    SPRING_TYPES = [
        ('car', 'Carriage'),
        ('tower', 'Tower'),
    ]
    
    name = models.CharField(max_length=50)  # e.g., 'Red', 'Long Yellow'
    spring_type = models.CharField(max_length=10, choices=SPRING_TYPES)  # Carriage or Tower
    
    class Meta:
        unique_together = ('spring_type', 'name')  # ✅ Ensures uniqueness for type + name
    
    def __str__(self):
        return f"{self.spring_type}_{self.name}"


class ExerciseSpringConfig(models.Model):
    """Tracks the spring configurations used in each exercise."""
    exercise = models.ForeignKey("core_data.Exercise", on_delete=models.CASCADE, related_name="spring_configurations")
    spring = models.ForeignKey(Spring, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ('exercise', 'spring')  # Avoid duplicate entries
    
    def __str__(self):
        return f"{self.exercise.name} - {self.spring.name}"


class Exercise(BaseModel):

    # ✅ Foreign Keys
    position = models.ForeignKey("core_data.Position", on_delete=models.SET_NULL, null=True, blank=True)
    prop = models.ForeignKey("core_data.Prop", on_delete=models.SET_NULL, null=True, blank=True)
    machine = models.ForeignKey("core_data.Machine", on_delete=models.SET_NULL, null=True, blank=True)

    # ✅ New Many-to-Many Relationship
    springs = models.ManyToManyField(Spring, through="core_data.ExerciseSpringConfig")

    # ✅ Custom Fields
    code = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    unilateral = models.BooleanField(default=False)  # False = Bilateral, True = Unilateral
    head_position = models.CharField(max_length=50, blank=True, null=True)  # Torre, Barra, Lateral (Passed by frontend)
    box = models.CharField(max_length=50, blank=True, null=True)  # ✅ Presence of the box (True = Yes, False = No)
    group = models.CharField(max_length=50, blank=True, null=True)  # Piernas, Tronco, Brazos, Core (Passed by frontend)
    instructions = models.TextField(blank=True, null=True)  # ✅ Execution instructions

    tags = models.ManyToManyField("core_data.Tag", blank=True, related_name="exercises")

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Routine(BaseModel):
    """A Pilates class or workout routine containing multiple exercises in a specific order."""
    machines = models.ManyToManyField("core_data.Machine", related_name="routines")
    prop = models.ForeignKey("core_data.Prop", on_delete=models.SET_NULL, null=True, blank=True)
    duration = models.PositiveIntegerField()  # Total duration in minutes
    on_edit = models.BooleanField(default=True)  # ✅ If True, the routine is still being edited
    
    tags = models.ManyToManyField("core_data.Tag", blank=True, related_name="routines")


    @property
    def number_exercises(self):
        """Automatically calculates the number of exercises in the routine."""
        return self.routine_exercises.count()  

    # def update_exercise_count(self):
    #     """Automatically updates the number of exercises in the routine."""
    #     self.number_exercises = self.routine_exercises.count()
    #     self.save()

class RoutineExercise(models.Model):
    """Intermediate table to store exercises inside a routine with order, repetitions, and execution time."""
    id = models.AutoField(primary_key=True)
    routine = models.ForeignKey(Routine, on_delete=models.CASCADE, related_name="routine_exercises")
    exercise = models.ForeignKey("core_data.Exercise", on_delete=models.CASCADE, related_name="in_routines")
    order = models.PositiveIntegerField()  # Order of execution
    repetitions = models.PositiveIntegerField(null=True, blank=True)  # Optional: For exercises with reps
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)  # Optional: For exercises with time
    comment = models.TextField(blank=True, null=True) 

    class Meta:
        unique_together = ('routine', 'exercise', 'order')  # Ensure unique order within a routine
        ordering = ["order"]

    def __str__(self):
        return f"{self.routine.name} - {self.exercise.name} (Order {self.order})"
    

class GeneralRoutineAssignment(models.Model):
    """Stores the default routine planned for all centers and rooms on a specific date."""

    id = models.AutoField(primary_key=True)
    date = models.DateField(unique=True, help_text="Fecha de la planificación general")
    routine = models.ForeignKey(
        "core_data.Routine",
        on_delete=models.CASCADE,
        related_name="general_assignments",
    )
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="general_routine_assignment_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="general_routine_assignment_updated",
    )

    class Meta:
        ordering = ["date"]
        verbose_name = "General Routine Assignment"
        verbose_name_plural = "General Routine Assignments"

    def __str__(self):
        return f"{self.date} - {self.routine.name}"
    

class DailyRoutineAssignment(models.Model):
    """Stores the planned routine for a specific room on a specific date."""

    id = models.AutoField(primary_key=True)
    date = models.DateField(help_text="Fecha a la que aplica la asignación diaria")
    center = models.ForeignKey(
        "core_data.Center",
        on_delete=models.CASCADE,
        related_name="daily_routine_assignments",
    )
    room = models.ForeignKey(
        "core_data.Room",
        on_delete=models.CASCADE,
        related_name="daily_routine_assignments",
    )
    routine = models.ForeignKey(
        "core_data.Routine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_assignments",
    )
    general_routine_assignment = models.ForeignKey(
        "core_data.GeneralRoutineAssignment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="room_assignments",
        help_text="Asignación general de la que deriva esta asignación de sala",
    )
    overrides_general_assignment = models.BooleanField(
        default=False,
        help_text="Indica si la asignación de sala difiere de la asignación general del día",
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_routine_assignment_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_routine_assignment_updated",
    )

    class Meta:
        ordering = ["date", "center__name", "room__name"]
        unique_together = ("date", "room")
        verbose_name = "Daily Routine Assignment"
        verbose_name_plural = "Daily Routine Assignments"

    def __str__(self):
        return f"{self.date} - {self.room.name} - {self.routine.name if self.routine else 'Sin clase'}"


class RoutineSession(models.Model):
    """It represents a specific session that takes place in a room, with a routine and an assigned user."""
    
    
    STATE_CHOICES = [
        (0, 'Programada'),
        (1, 'En progreso'),
        (2, 'Completada'),
        (-1, 'Cancelada'),        
    ]
    
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=200, blank=True, null=True, help_text="Nombre descriptivo de la sesión")
    room = models.ForeignKey("core_data.Room", on_delete=models.CASCADE, related_name="routinesessions")
    routine = models.ForeignKey("core_data.Routine", on_delete=models.CASCADE, null=True, blank=True, related_name="routinesessions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="routinesessions")
    scheduled_at = models.DateTimeField()
    duration = models.IntegerField(default=60, help_text="Duración de la sesión en minutos")
    
    # Relación con serie maestra (si la sesión fue generada desde una serie)
    session_series = models.ForeignKey("core_data.SessionSeries", on_delete=models.SET_NULL, null=True, blank=True, related_name="generated_sessions")
    daily_routine_assignment = models.ForeignKey(
        "core_data.DailyRoutineAssignment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_sessions",
        help_text="Asignación diaria que pobló originalmente la rutina de esta sesión",
    )
    routine_manually_overridden = models.BooleanField(
        default=False,
        help_text="Indica si la rutina fue modificada manualmente después de una asignación diaria",
    )
        
    state = models.IntegerField(choices=STATE_CHOICES, default=0)
    userFeedback = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="%(class)s_created"
    )
    
    class Meta:
        ordering = ['-scheduled_at']
        unique_together = ('room', 'scheduled_at') 

    def __str__(self):
        return f"Session in {self.room.name} on {self.scheduled_at} - {self.get_state_display()}"
    
    def get_state_name(self):
        """Devuelve el nombre del estado actual"""
        return self.get_state_display()

class SessionSeries(models.Model):
    """Serie maestra para programar sesiones recurrentes semanales"""
    
    WEEKDAY_CHOICES = [
        (0, 'Lunes'),
        (1, 'Martes'),
        (2, 'Miércoles'),
        (3, 'Jueves'),
        (4, 'Viernes'),
        (5, 'Sábado'),
        (6, 'Domingo'),
    ]
    
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=200, help_text="Nombre descriptivo de la serie")
    
    # Configuración de recurrencia semanal
    weekdays = models.JSONField(help_text="Lista de días de la semana [0-6] para recurrencia semanal")
    duration = models.IntegerField(default=60, help_text="Duración de cada sesión en minutos")
    
    # Rango de fechas
    start_date = models.DateField(help_text="Fecha de inicio de la serie")
    end_date = models.DateField(help_text="Fecha de fin de la serie")
    
    # Hora de las sesiones
    time = models.TimeField(help_text="Hora a la que se programan las sesiones")
    
    # Datos de la sesión (pueden ser opcionales)
    room = models.ForeignKey("core_data.Room", on_delete=models.CASCADE, related_name="session_series")
    routine = models.ForeignKey("core_data.Routine", on_delete=models.SET_NULL, null=True, blank=True, related_name="session_series")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_session_series")
    
    # Metadatos
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="created_session_series"
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Session Series"
        verbose_name_plural = "Session Series"
    
    def __str__(self):
        return f"{self.name} (Semanal: {self.start_date} - {self.end_date})"


class RoutineSessionLog(models.Model):
    """Registra logs de actividades durante una sesión de rutina."""
    
    id = models.AutoField(primary_key=True)
    routine_session = models.ForeignKey(
        "core_data.RoutineSession", 
        on_delete=models.CASCADE, 
        related_name="logs"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="routine_session_logs"
    )
    exercise = models.ForeignKey(
        "core_data.Exercise", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="session_logs"
    )
    log = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Routine Session Log"
        verbose_name_plural = "Routine Session Logs"
    
    def __str__(self):
        exercise_name = self.exercise.name if self.exercise else "General"
        return f"Log: {self.routine_session} - {exercise_name} ({self.created_at})"


class LoginLog(models.Model):
    """Registra los inicios de sesión de usuarios."""
    
    LOGIN_TYPE_CHOICES = [
        ('main', 'Login Principal'),
        ('secondary', 'Login Secundario'),
        ('logout', 'Cierre de Sesión'),
    ]
    
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="login_logs"
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    login_type = models.CharField(
        max_length=10, 
        choices=LOGIN_TYPE_CHOICES, 
        default='main',
        help_text="Tipo de login: principal o sublogin"
    )
    user_agent = models.TextField(blank=True, null=True, help_text="Información del navegador/dispositivo")
    success = models.BooleanField(default=True, help_text="Si el login fue exitoso")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Login Log"
        verbose_name_plural = "Login Logs"
    
    def __str__(self):
        return f"{self.user.email} - {self.get_login_type_display()} - {self.created_at}"
