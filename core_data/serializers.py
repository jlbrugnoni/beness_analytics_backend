from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from .models import (Objective,
                     Center,
                     Position,
                     Prop,
                     Machine,
                     Exercise, Room, RoutineSession,
                     Spring,
                     ExerciseSpringConfig,
                     GeneralRoutineAssignment,
                     Routine,
                     RoutineExercise, Tag,
                     DailyRoutineAssignment,
                     RoutineSessionLog,
                     SessionSeries,
                     LoginLog)

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)  # Allow password input but not output
    groups = serializers.PrimaryKeyRelatedField(
            queryset=Group.objects.all(),
            many=True,
            required=False
        )
    group_name = serializers.SerializerMethodField()

    def get_group_name(self, obj):
        first_group = obj.groups.first()
        return first_group.name if first_group else None
    
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'is_active', 'is_staff', 'is_superuser', 'date_joined', 'password','groups', 'group_name','image']
        read_only_fields = ['date_joined']

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)

    def validate_new_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        return value

class SpringSerializer(serializers.ModelSerializer):
    class Meta:
        model = Spring
        fields = '__all__'

class ExerciseSpringConfigSerializer(serializers.ModelSerializer):
    spring = SpringSerializer()  # Serialize the spring object directly

    class Meta:
        model = ExerciseSpringConfig
        fields = ['spring']

class ObjectiveSerializer(serializers.ModelSerializer):
    class Meta:
        model = Objective
        fields = '__all__'  # Includes all model fields

class PositionSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    updated_by = serializers.SerializerMethodField()
    
    class Meta:
        model = Position
        fields = '__all__'
    
    def get_created_by(self, obj):
        return obj.created_by.username if obj.created_by else "N/A"

    def get_updated_by(self, obj):
        return obj.updated_by.username if obj.updated_by else "N/A"

class PropSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    updated_by = serializers.SerializerMethodField()
   
    class Meta:
        model = Prop
        fields = '__all__'
    
    def get_created_by(self, obj):
        return obj.created_by.username if obj.created_by else "N/A"

    def get_updated_by(self, obj):
        return obj.updated_by.username if obj.updated_by else "N/A"

class MachineSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    updated_by = serializers.SerializerMethodField()
    
    class Meta:
        model = Machine
        fields = '__all__'
    
    def get_created_by(self, obj):
        return obj.created_by.username if obj.created_by else "N/A"

    def get_updated_by(self, obj):
        return obj.updated_by.username if obj.updated_by else "N/A"

class ExerciseSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    updated_by = serializers.SerializerMethodField()
    position = serializers.SlugRelatedField(slug_field="name", queryset=Position.objects.all(), allow_null=True)
    prop = serializers.SlugRelatedField(slug_field="name", queryset=Prop.objects.all(), allow_null=True)
    machine = serializers.SlugRelatedField(slug_field="name", queryset=Machine.objects.all(), allow_null=True)
    springs = ExerciseSpringConfigSerializer(source='spring_configurations', many=True, read_only=True)
    tags = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    tag_images = serializers.SerializerMethodField()
    class Meta:
        model = Exercise
        fields = '__all__'

    def get_tag_images(self, obj):
        return [tag.image for tag in obj.tags.all()]

    def get_created_by(self, obj):
        return obj.created_by.username if obj.created_by else "N/A"

    def get_updated_by(self, obj):
        return obj.updated_by.username if obj.updated_by else "N/A"


class RoutineExerciseSerializer(serializers.ModelSerializer):
    # exercise = serializers.SlugRelatedField(slug_field="name", queryset=Exercise.objects.all())
    exercise = ExerciseSerializer()  # ✅ Use the full ExerciseSerializer    
    id_on_routine = serializers.IntegerField(source='id')
    class Meta:
        model = RoutineExercise
        fields = ['id_on_routine', 'exercise', 'order', 'repetitions', 'duration_seconds', 'comment']
        
        
class MachineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Machine
        fields = '__all__'


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = '__all__'

class RoutineSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    updated_by = serializers.SerializerMethodField()
    prop = serializers.SlugRelatedField(slug_field="name", queryset=Prop.objects.all(), allow_null=True)
    machines = serializers.PrimaryKeyRelatedField(
        queryset=Machine.objects.all(), many=True
    )
    machine_names = serializers.SerializerMethodField()

    routine_exercises = RoutineExerciseSerializer(many=True, read_only=True)
    number_exercises = serializers.ReadOnlyField()
    tags = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    tag_images = serializers.SerializerMethodField()
    class Meta:
        model = Routine
        fields = [
            "id", "name", "duration", "number_exercises", "on_edit",
            "machines", "machine_names", "prop", "created_by","routine_exercises","updated_by","tags","tag_images"
        ]
    def get_tag_images(self, obj):
        return [tag.image for tag in obj.tags.all()]
    def get_machine_names(self, obj):
        return [machine.name for machine in obj.machines.all()]
    
    def get_created_by(self, obj):
        return obj.created_by.username if obj.created_by else "N/A"

    def get_updated_by(self, obj):
        return obj.updated_by.username if obj.updated_by else "N/A"
    
class RoutineSessionSerializer(serializers.ModelSerializer):
    room_id = serializers.PrimaryKeyRelatedField(
        queryset=Room.objects.all(),
        source="room"
    )
    routine_id = serializers.PrimaryKeyRelatedField(
        queryset=Routine.objects.all(),
        source="routine",
        required=False,
        allow_null=True
    )
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source="user",
        required=False,
        allow_null=True
    )
    session_series_id = serializers.PrimaryKeyRelatedField(
        queryset=SessionSeries.objects.all(),
        source="session_series",
        required=False,
        allow_null=True
    )

    room = serializers.CharField(source="room.name", read_only=True)
    center = serializers.CharField(source="room.center.name", read_only=True)
    routine = serializers.CharField(source="routine.name", read_only=True)
    routine_duration = serializers.IntegerField(source="routine.duration", read_only=True)
    user = serializers.SerializerMethodField()
    session_series = serializers.SerializerMethodField()
    scheduled_at = serializers.DateTimeField(format="%d/%m/%Y %H:%M")
    state_name = serializers.CharField(source="get_state_display", read_only=True)

    def get_user(self, obj):
        if obj.user:
            return f"{obj.user.first_name} {obj.user.last_name}"
        return ""
    
    def get_session_series(self, obj):
        if obj.session_series:
            return {
                "id": obj.session_series.id,
                "name": obj.session_series.name
            }
        return None

    def get_scheduled_at(self, obj):
        return obj.scheduled_at.strftime("%d/%m/%Y %H:%M")

    class Meta:
        model = RoutineSession
        fields = [
            "id", "name", "scheduled_at", "duration",
            "room_id", "routine_id", "user_id", "session_series_id",
            "room", "center", "routine", "routine_duration", "user", "session_series",
            "state", "userFeedback", "state_name", "routine_manually_overridden"
        ]


class DailyRoutineAssignmentSerializer(serializers.ModelSerializer):
    center_id = serializers.PrimaryKeyRelatedField(
        queryset=Center.objects.all(),
        source="center",
        write_only=True,
        required=False,
    )
    room_id = serializers.PrimaryKeyRelatedField(
        queryset=Room.objects.select_related("center").all(),
        source="room",
        write_only=True,
    )
    routine_id = serializers.PrimaryKeyRelatedField(
        queryset=Routine.objects.all(),
        source="routine",
        write_only=True,
        required=False,
        allow_null=True,
    )
    center = serializers.SerializerMethodField(read_only=True)
    room = serializers.SerializerMethodField(read_only=True)
    routine = serializers.SerializerMethodField(read_only=True)
    assigned_sessions_count = serializers.SerializerMethodField(read_only=True)
    overridden_sessions_count = serializers.SerializerMethodField(read_only=True)
    general_routine_assignment = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DailyRoutineAssignment
        fields = [
            "id",
            "date",
            "active",
            "center_id",
            "room_id",
            "routine_id",
            "center",
            "room",
            "routine",
            "general_routine_assignment",
            "overrides_general_assignment",
            "assigned_sessions_count",
            "overridden_sessions_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, data):
        room = data.get("room") or getattr(self.instance, "room", None)
        center = data.get("center") or getattr(self.instance, "center", None)

        if room and center and room.center_id != center.id:
            raise serializers.ValidationError({
                "room_id": "The selected room does not belong to the selected center."
            })
        return data

    def get_center(self, obj):
        return {
            "id": obj.center.id,
            "name": obj.center.name,
        }

    def get_room(self, obj):
        return {
            "id": obj.room.id,
            "name": obj.room.name,
        }

    def get_routine(self, obj):
        if not obj.routine:
            return None
        return {
            "id": obj.routine.id,
            "name": obj.routine.name,
        }

    def get_assigned_sessions_count(self, obj):
        return obj.assigned_sessions.count()

    def get_overridden_sessions_count(self, obj):
        return obj.assigned_sessions.filter(routine_manually_overridden=True).count()

    def get_general_routine_assignment(self, obj):
        if not obj.general_routine_assignment:
            return None
        return {
            "id": obj.general_routine_assignment.id,
            "date": obj.general_routine_assignment.date,
            "routine": {
                "id": obj.general_routine_assignment.routine.id,
                "name": obj.general_routine_assignment.routine.name,
            },
        }


class GeneralRoutineAssignmentSerializer(serializers.ModelSerializer):
    routine_id = serializers.PrimaryKeyRelatedField(
        queryset=Routine.objects.all(),
        source="routine",
        write_only=True,
    )
    routine = serializers.SerializerMethodField(read_only=True)
    room_assignments_count = serializers.SerializerMethodField(read_only=True)
    overridden_room_assignments_count = serializers.SerializerMethodField(read_only=True)
    overridden_sessions_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = GeneralRoutineAssignment
        fields = [
            "id",
            "date",
            "active",
            "notes",
            "routine_id",
            "routine",
            "room_assignments_count",
            "overridden_room_assignments_count",
            "overridden_sessions_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_routine(self, obj):
        return {
            "id": obj.routine.id,
            "name": obj.routine.name,
        }

    def get_room_assignments_count(self, obj):
        return obj.room_assignments.count()

    def get_overridden_room_assignments_count(self, obj):
        return obj.room_assignments.filter(overrides_general_assignment=True).count()

    def get_overridden_sessions_count(self, obj):
        return RoutineSession.objects.filter(
            daily_routine_assignment__general_routine_assignment=obj,
            routine_manually_overridden=True,
        ).count()

class RoutineSessionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoutineSessionLog
        fields = ['id', 'routine_session', 'user', 'exercise', 'log', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        # Añadir información adicional para mejor legibilidad
        representation['routine_session_name'] = f"Session {instance.routine_session.id}"
        representation['user_name'] = f"{instance.user.first_name} {instance.user.last_name}" if instance.user else None
        representation['exercise_name'] = instance.exercise.name if instance.exercise else "-"
        return representation


class SessionSeriesSerializer(serializers.ModelSerializer):
    """Serializer para gestionar series de sesiones recurrentes"""
    
    # PKs para escritura
    room_id = serializers.PrimaryKeyRelatedField(
        queryset=Room.objects.all(),
        source="room",
        write_only=True
    )
    routine_id = serializers.PrimaryKeyRelatedField(
        queryset=Routine.objects.all(),
        source="routine",
        required=False,
        allow_null=True,
        write_only=True
    )
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source="user",
        required=False,
        allow_null=True,
        write_only=True
    )
    
    # Datos expandidos para lectura
    room = serializers.SerializerMethodField(read_only=True)
    routine = serializers.SerializerMethodField(read_only=True)
    user = serializers.SerializerMethodField(read_only=True)
    
    # Estadísticas
    sessions_count = serializers.SerializerMethodField(read_only=True)
    
    def get_room(self, obj):
        return {
            "id": obj.room.id,
            "name": obj.room.name,
            "center_name": obj.room.center.name if obj.room.center else None
        }
    
    def get_routine(self, obj):
        if obj.routine:
            return {
                "id": obj.routine.id,
                "name": obj.routine.name
            }
        return None
    
    def get_user(self, obj):
        if obj.user:
            return {
                "id": obj.user.id,
                "name": f"{obj.user.first_name} {obj.user.last_name}",
                "email": obj.user.email
            }
        return None
    
    def get_sessions_count(self, obj):
        """Cuenta cuántas sesiones se han generado desde esta serie"""
        return obj.generated_sessions.count()
    
    class Meta:
        model = SessionSeries
        fields = [
            'id', 'name', 'duration',
            'weekdays',
            'start_date', 'end_date', 'time',
            'room_id', 'routine_id', 'user_id',
            'room', 'routine', 'user',
            'active', 'created_at', 'updated_at',
            'sessions_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate(self, data):
        """Validaciones para series semanales"""
        
        # Validar que weekdays esté presente
        if not data.get('weekdays'):
            raise serializers.ValidationError({
                'weekdays': 'Weekdays is required for weekly series'
            })
        
        # Validar rango de fechas
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError({
                'end_date': 'End date must be after start date'
            })
        
        return data


class LoginLogSerializer(serializers.ModelSerializer):
    user_email = serializers.SerializerMethodField()
    login_type_display = serializers.SerializerMethodField()
    
    class Meta:
        model = LoginLog
        fields = ['id', 'user', 'user_email', 'ip_address', 'login_type', 
                  'login_type_display', 'user_agent', 'success', 'created_at']
        read_only_fields = ['created_at']
    
    def get_user_email(self, obj):
        return obj.user.email if obj.user else None
    
    def get_login_type_display(self, obj):
        return obj.get_login_type_display()
