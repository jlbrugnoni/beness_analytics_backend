from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import serializers

from .models import Center, ClassType, Client, Instructor, LoginLog, ReportImport, Room


User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    groups = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all(), many=True, required=False)
    group_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "date_joined",
            "password",
            "groups",
            "group_name",
            "image",
        ]
        read_only_fields = ["date_joined"]

    def get_group_name(self, obj):
        first_group = obj.groups.first()
        return first_group.name if first_group else None


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)

    def validate_new_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        return value


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ["id", "name"]


class CenterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Center
        fields = "__all__"


class RoomSerializer(serializers.ModelSerializer):
    center_name = serializers.CharField(source="center.name", read_only=True)

    class Meta:
        model = Room
        fields = "__all__"


class InstructorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Instructor
        fields = "__all__"


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = "__all__"


class ClassTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassType
        fields = "__all__"


class ReportImportSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ReportImport
        fields = "__all__"
        read_only_fields = ["uploaded_by", "uploaded_at", "processed_at"]

    def get_uploaded_by_name(self, obj):
        if not obj.uploaded_by:
            return None
        return f"{obj.uploaded_by.first_name} {obj.uploaded_by.last_name}".strip() or obj.uploaded_by.email


class LoginLogSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = LoginLog
        fields = "__all__"
