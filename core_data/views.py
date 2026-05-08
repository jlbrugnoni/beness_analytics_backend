from django.shortcuts import HttpResponse
from django.contrib.auth import authenticate
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework import status, viewsets, filters, pagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
import cloudinary.uploader
import re
from urllib.parse import urlparse
from django.contrib.auth.models import Group
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.core.cache import cache
from core_data.decorators import server_cache_viewset
from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.db import transaction
from rest_framework.renderers import JSONRenderer
from datetime import datetime, timedelta
from .models import (Center, CustomUser, Objective, 
                     Position, 
                     Prop, 
                     Machine,
                     Room,
                     Exercise, RoutineSession, RoutineSessionLog, 
                     Spring, 
                     ExerciseSpringConfig,
                     GeneralRoutineAssignment,
                     Routine,
                     RoutineExercise, Tag,
                     DailyRoutineAssignment,
                     SessionSeries,
                     LoginLog
                     )

from .serializers import (
    RoutineSessionSerializer, RoutineSessionLogSerializer, TagSerializer, UserSerializer, ChangePasswordSerializer,  # ✅ Añadir aquí
    ObjectiveSerializer, PositionSerializer, 
    PropSerializer, MachineSerializer, 
    ExerciseSerializer,
    SpringSerializer, ExerciseSpringConfigSerializer,
    RoutineSerializer, RoutineExerciseSerializer,
    GeneralRoutineAssignmentSerializer,
    DailyRoutineAssignmentSerializer,
    SessionSeriesSerializer,
    LoginLogSerializer
)

User = get_user_model()


### 🚀 USER MANAGEMENT ###
class UserViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        users = User.objects.filter(is_superuser=False)
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def retrieve(self, request, pk=None):
        try:
            user = User.objects.get(pk=pk)
            serializer = UserSerializer(user)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

    def create(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():            
            password = request.data.get("password")
            groups = serializer.validated_data.pop("groups", [])
            if not password:
                return Response({'error': 'Email and password are required'}, status=status.HTTP_400_BAD_REQUEST)

            user = serializer.save()
            user.set_password(password)  # Hash password
            user.save()
            if groups:
                user.groups.set(groups)
            return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        try:
            user = User.objects.get(pk=pk)
            serializer = UserSerializer(user, data=request.data, partial=True)

            if serializer.is_valid():
                user = serializer.save()

                if "password" in request.data and request.data["password"]:
                    user.set_password(request.data["password"])
                    user.save()

                return Response(UserSerializer(user).data, status=status.HTTP_200_OK)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'])
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            if not user.check_password(serializer.validated_data['old_password']):
                return Response({'error': 'Old password is incorrect'}, status=status.HTTP_400_BAD_REQUEST)

            new_password = serializer.validated_data['new_password']
            try:
                validate_password(new_password, user)
            except ValidationError as e:
                return Response({'error': e.messages}, status=status.HTTP_400_BAD_REQUEST)

            user.set_password(new_password)
            user.save()
            return Response({'message': 'Password updated successfully'}, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        try:
            user = User.objects.get(pk=pk)
            user.delete()
            return Response({'message': 'User deleted successfully'}, status=status.HTTP_204_NO_CONTENT)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def all_users(request):
    try:
        users = CustomUser.objects.filter(is_active=True).order_by("first_name", "last_name")
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data, status=200)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

### 🔐 AUTH VIEWS ###

def get_client_ip(request):
    """Obtiene la IP real del cliente, considerando proxies."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@api_view(['POST'])
def login_view(request):
    email = request.data.get('email')
    password = request.data.get('password')
    login_type = request.data.get('login_type', 'main')  # 'main' o 'sub'

    if not email or not password:
        return Response({'message': 'Email and password are required'}, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(request, email=email, password=password)
    
    # Obtener datos para el log
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    if user:
        # Registrar login exitoso
        LoginLog.objects.create(
            user=user,
            ip_address=ip_address,
            login_type=login_type,
            user_agent=user_agent,
            success=True
        )
        
        token, _ = Token.objects.get_or_create(user=user)
        permissions = list(user.get_all_permissions())
        return Response({
            'token': token.key,
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_staff': user.is_staff,
            'permissions': permissions,
            'image': user.image,
            'message': 'Login successful'
        }, status=status.HTTP_200_OK)
    
    # Registrar intento fallido (si el usuario existe)
    try:
        failed_user = User.objects.get(email=email)
        LoginLog.objects.create(
            user=failed_user,
            ip_address=ip_address,
            login_type=login_type,
            user_agent=user_agent,
            success=False
        )
    except User.DoesNotExist:
        pass  # No registramos si el usuario no existe
    
    return Response({'message': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

@api_view(['POST'])
def validate_token_view(request):
    token_key = request.data.get('token')

    if not token_key:
        return Response({'message': 'Token is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        token = Token.objects.get(key=token_key)
        return Response({'valid': True}, status=status.HTTP_200_OK)
    except Token.DoesNotExist:
        return Response({'valid': False}, status=status.HTTP_401_UNAUTHORIZED)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    Token.objects.filter(user=request.user).delete()
    return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_log_view(request):
    """Registra el cierre de sesión de un usuario en la tabla LoginLog"""
    user = request.user
    
    # Obtener datos para el log
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    # Crear el registro con login_type='logout'
    LoginLog.objects.create(
        user=user,
        ip_address=ip_address,
        login_type='logout',
        user_agent=user_agent,
        success=True
    )
    
    return Response({'message': 'Logout log registered successfully'}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def delete_image(request):
    """Deletes an image from Cloudinary securely using a signed request"""
    public_id = request.data.get("public_id")

    if not public_id:
        return Response({"error": "Public ID is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        result = cloudinary.uploader.destroy(public_id)
        return Response({"message": "Image deleted successfully", "result": result}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class BaseViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)  # ✅ Set created_by & updated_by        
        cache.clear() 

    def perform_update(self, serializer):
        print(f"🛠️ perform_update ejecutado en {self.__class__.__name__}")
        """Handles updating the instance, replacing/removing image if needed."""

        instance = self.get_object()
        old_image_url = instance.image  # Store existing image
        updated_data = serializer.validated_data

        print(f"🔥 Incoming Update Data: {self.request.data}")
        print(f"🔥 Existing Image URL: {old_image_url}")

        # ✅ Check if the user explicitly removed the image
        new_image_url = self.request.data.get("image")
        if new_image_url == "":  # If empty string, delete the old image
            if old_image_url:
                try:
                    public_id = old_image_url.split("/")[-1].split(".")[0]
                    print(f"✅ Deleting Old Image: {public_id}")
                    cloudinary_result = cloudinary.uploader.destroy(public_id, invalidate=True)
                    print(f"🔥 Cloudinary Delete Response: {cloudinary_result}")

                except Exception as e:
                    print(f"❌ Error deleting Cloudinary image: {e}")

            updated_data["image"] = None  # ✅ Remove image from the database

        elif new_image_url and new_image_url != old_image_url:
            try:
                # ✅ Replace image logic (if a new image is uploaded)
                if old_image_url:
                    public_id = old_image_url.split("/")[-1].split(".")[0]
                    cloudinary.uploader.destroy(public_id, invalidate=True)

                updated_data["image"] = new_image_url

            except Exception as e:
                print(f"❌ Error replacing Cloudinary image: {e}")

        # ✅ Save updated instance
        updated_data.pop("updated_by", None) 
        serializer.save(updated_by=self.request.user, **updated_data)
        print(f"✅ Updated Image: {updated_data.get('image')}")        
        cache.clear()     

    def get_cloudinary_public_id(self, file_url):
        """
        Extracts the Cloudinary public_id from a URL by removing unnecessary parts.
        Example:
        - Input:  "https://res.cloudinary.com/dynhweyz7/image/upload/v1738536691/images_ntmhdv.jpg"
        - Output: "images_ntmhdv"
        """
        if not file_url:
            return None

        try:
            parsed_url = urlparse(file_url)
            path = parsed_url.path  # Extracts '/image/upload/v1738536691/images_ntmhdv.jpg'
            
            # ✅ Remove leading `/v1234567890/` (versioning)
            path = re.sub(r"/v\d+/", "/", path)

            # ✅ Extract public ID (removes `/image/upload/`)
            match = re.search(r"/upload/(.*)", path)
            if match:
                public_id_with_extension = match.group(1)  # Example: 'images_ntmhdv.jpg'
                public_id = public_id_with_extension.rsplit(".", 1)[0]  # Remove `.jpg` or `.mp4`

                print(f"✅ Corrected Public ID Extraction: {public_id}")  # Debugging Log
                return public_id

            return None
        except Exception as e:
            print(f"❌ Error extracting public_id: {e}")
            return None
        
        
    def destroy(self, request, *args, **kwargs):
        """
        Delete Cloudinary image/video before removing the instance from the database.
        """
        instance = self.get_object()

        # ✅ Delete image from Cloudinary if it exists
        if instance.image:
            public_id = self.get_cloudinary_public_id(instance.image)
            if public_id:
                try:
                    print(f"🔥 Deleting Cloudinary Image: {public_id}")
                    cloudinary.uploader.destroy(public_id, invalidate=True)
                    print(f"✅ Image {public_id} deleted from Cloudinary")
                except Exception as e:
                    print(f"❌ Error deleting image: {e}")

        # ✅ Delete video from Cloudinary if it exists
        if instance.video:
            public_id = self.get_cloudinary_public_id(instance.video)
            if public_id:
                try:
                    print(f"🔥 Deleting Cloudinary Video: {public_id}")
                    cloudinary.uploader.destroy(public_id, resource_type="video", invalidate=True)
                    print(f"✅ Video {public_id} deleted from Cloudinary")
                except Exception as e:
                    print(f"❌ Error deleting video: {e}")
        cache.clear() 
        return super().destroy(request, *args, **kwargs)


class ObjectiveViewSet(BaseViewSet):
    queryset = Objective.objects.all().order_by('-created_at')
    serializer_class = ObjectiveSerializer



@method_decorator(server_cache_viewset(60 * 60 * 24, key_prefix="position_list"), name="list")
class PositionViewSet(BaseViewSet):
    serializer_class = PositionSerializer

    def get_queryset(self):        
        return Position.objects.all().order_by("-created_at")



@api_view(["GET"])
@permission_classes([IsAuthenticated])
@server_cache_viewset(settings.CACHE_SECONDS, key_prefix="all_positions")
def all_positions(request):
    """ ✅ Returns all positions without pagination (con caché de servidor) """
    try:        
        positions = Position.objects.all()
        serializer = PositionSerializer(positions, many=True)
        return Response(serializer.data, status=200)
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@method_decorator(server_cache_viewset(60 * 60 * 24, key_prefix="prop_list"), name="list")
class PropViewSet(BaseViewSet):
    serializer_class = PropSerializer

    def get_queryset(self):        
        return Prop.objects.all().order_by("-created_at")

    @action(detail=False, methods=["get"], url_path="all")
    @method_decorator(server_cache_viewset(60 * 60 * 24, key_prefix="prop_list"), name="dispatch")
    def all(self, request):
        print("📦 Método 'all' ejecutado (esto debería verse solo si NO hay caché)")
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@server_cache_viewset(settings.CACHE_SECONDS, key_prefix="all_props")
def all_props(request):    
    try:        
        props = Prop.objects.all()
        serializer = PropSerializer(props, many=True)
        return Response(serializer.data, status=200)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@method_decorator(server_cache_viewset(60 * 60 * 24, key_prefix="machine_list"), name="list")
class MachineViewSet(BaseViewSet):
    serializer_class = MachineSerializer

    def get_queryset(self):        
        return Machine.objects.all().order_by("-created_at")

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@server_cache_viewset(settings.CACHE_SECONDS, key_prefix="all_machines")
def all_machines(request):
    """ ✅ Returns all machines without pagination (con caché de servidor) """
    try:        
        machines = Machine.objects.all()
        serializer = MachineSerializer(machines, many=True)
        return Response(serializer.data, status=200)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@server_cache_viewset(settings.CACHE_SECONDS, key_prefix="all_tags")
def all_tags(request):    
    try:        
        tags = Tag.objects.all()
        serializer = TagSerializer(tags, many=True)
        return Response(serializer.data, status=200)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def all_centers_and_rooms(request):
    try:
        centers = Center.objects.prefetch_related('rooms').all()
        data = []

        for center in centers:
            data.append({
                "id": center.id,
                "name": center.name,
                "rooms": [
                    {"id": room.id, "name": room.name, "center": center.id}
                    for room in center.rooms.all()
                ]
            })

        return Response(data, status=200)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@method_decorator(cache_page(60 * 10), name='list')
class SpringViewSet(viewsets.ModelViewSet):
    queryset = Spring.objects.all().order_by('spring_type', 'name')
    serializer_class = SpringSerializer
    permission_classes = [IsAuthenticated]
    
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def all_springs(request):
    """ ✅ Returns all springs without pagination """
    try:
        springs = Spring.objects.all()
        serializer = SpringSerializer(springs, many=True)
        return Response(serializer.data, status=200)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

class ExerciseSpringConfigViewSet(viewsets.ModelViewSet):
    queryset = ExerciseSpringConfig.objects.all()
    serializer_class = ExerciseSpringConfigSerializer
    permission_classes = [IsAuthenticated]
    
class ExerciseViewSet(viewsets.ModelViewSet):
    """ ✅ API View for managing Exercises """
    queryset = Exercise.objects.all().order_by('-created_at')
    serializer_class = ExerciseSerializer
    permission_classes = [IsAuthenticated]
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        'position__name': ['exact', 'in'],
        'prop__name': ['exact', 'in'],
        'machine__name': ['exact', 'in'],
        'group': ['exact', 'in'],
        'box': ['exact', 'in'],
        'head_position': ['exact', 'in'],
        'unilateral': ['exact'],
        'active': ['exact'],
        'name': ['icontains'], 
        'code': ['icontains'],
        'spring_configurations__spring__name': ['exact', 'in'],
    }
    search_fields = ['name', 'code']

    def get_queryset(self):
        queryset = super().get_queryset()

        # ✅ Handle name search filter
        name_search = self.request.query_params.get('name__icontains', None)
        if name_search:
            queryset = queryset.filter(name__icontains=name_search)

        code_search = self.request.query_params.get('code__icontains', None)
        if code_search:
            queryset = queryset.filter(code__icontains=code_search)

        # ✅ Handle multiple values for filters that allow multi-selection
        multi_select_filters = ['position__name', 'prop__name', 'machine__name', 'group', 'head_position']

        for field in multi_select_filters:
            param_values = self.request.query_params.get(field, None)
            if param_values:
                value_list = param_values.split(",")  # Convert "Tronco,Piernas" → ["Tronco", "Piernas"]
                queryset = queryset.filter(**{f"{field}__in": value_list})

        # ✅ Handle exact match filters
        exact_filters = ['box', 'unilateral', 'active']
        for field in exact_filters:
            value = self.request.query_params.get(field, None)
            if value in ['true', 'false']:
                queryset = queryset.filter(**{field: value.lower() == 'true'})  # Convert "true"/"false" to Boolean
        
        tag_ids = self.request.query_params.get('tag__id__in', None)
        if tag_ids:
            tag_id_list = [int(t.strip()) for t in tag_ids.split(',') if t.strip().isdigit()]
            # Contar solo las tags del ejercicio que están en la lista filtrada
            queryset = queryset.annotate(
                matching_tags=Count('tags', filter=Q(tags__id__in=tag_id_list), distinct=True)
            ).filter(matching_tags=len(tag_id_list))

             
        # ✅ Permitir override del page_size
        page_size = self.request.query_params.get('page_size', None)
        if page_size:
            self.paginator.page_size = int(page_size)

        return queryset

    def perform_create(self, serializer):
        print(f"🔍 Datos recibidos: {self.request.data}")
        print(f"🔍 Serializer validated_data: {serializer.validated_data}")
        print(f"🔍 Nombre validado: {serializer.validated_data.get('name')}")
        print(f"🔍 Longitud validada: {len(serializer.validated_data.get('name', ''))}")
        
        try:
            exercise = serializer.save(created_by=self.request.user, updated_by=self.request.user)
            print(f"✅ Ejercicio creado exitosamente: {exercise.id}")
        except Exception as e:
            print(f"❌ Error al guardar: {e}")
            print(f"❌ Tipo de error: {type(e)}")
            raise e
    
        tag_ids = self.request.data.get("tags", [])
        if isinstance(tag_ids, list):
            exercise.tags.set(tag_ids)

        # ✅ Handle Spring Configuration for newly created exercises
        spring_ids = self.request.data.get("springs", [])

        for spring_id in spring_ids:
            try:
                spring = Spring.objects.get(id=spring_id)
                ExerciseSpringConfig.objects.create(exercise=exercise, spring=spring)
            except Spring.DoesNotExist:
                print(f"⚠️ Spring with ID {spring_id} not found!")

        print(f"✅ Springs Assigned: {spring_ids}")
    
    def perform_update(self, serializer):
        """ ✅ Handle updating exercise and managing associated springs """
        instance = self.get_object()
        old_image_url = instance.image
        old_video_url = instance.video
        updated_data = serializer.validated_data

        print(f"🔥 Incoming Update Data: {self.request.data}")
        
        # ✅ Handle image deletion
        new_image_url = self.request.data.get("image")
        if new_image_url == "":  # If empty string, delete old image
            if old_image_url:
                self.delete_cloudinary_file(old_image_url, "image")
            updated_data["image"] = None

        # ✅ Handle video deletion
        new_video_url = self.request.data.get("video")
        if new_video_url == "":  # If empty string, delete old video
            if old_video_url:
                self.delete_cloudinary_file(old_video_url, "video")
            updated_data["video"] = None

        # ✅ Replace media logic
        if new_image_url and new_image_url != old_image_url:
            self.delete_cloudinary_file(old_image_url, "image")
            updated_data["image"] = new_image_url

        if new_video_url and new_video_url != old_video_url:
            self.delete_cloudinary_file(old_video_url, "video")
            updated_data["video"] = new_video_url

        # ✅ Save exercise before updating springs
        exercise = serializer.save(updated_by=self.request.user)

        tag_ids = self.request.data.get("tags", [])
        if isinstance(tag_ids, list):
            exercise.tags.set(tag_ids)

        # ✅ Handle Spring Configuration
        spring_ids = self.request.data.get("springs", [])

        # ✅ Clear previous springs and add new ones
        ExerciseSpringConfig.objects.filter(exercise=exercise).delete()
        for spring_id in spring_ids:
            try:
                spring = Spring.objects.get(id=spring_id)
                ExerciseSpringConfig.objects.create(exercise=exercise, spring=spring)
            except Spring.DoesNotExist:
                print(f"⚠️ Spring with ID {spring_id} not found!")

        print(f"✅ Springs Updated: {spring_ids}")

    def delete_cloudinary_file(self, file_url, file_type):
        """ ✅ Delete Cloudinary file if it exists """
        public_id = self.extract_cloudinary_public_id(file_url)
        if public_id:
            try:
                cloudinary.uploader.destroy(public_id, resource_type=file_type if file_type == "video" else "image")
                print(f"✅ {file_type.capitalize()} {public_id} deleted from Cloudinary")
            except Exception as e:
                print(f"❌ Error deleting {file_type}: {e}")

    def extract_cloudinary_public_id(self, file_url):
        """ ✅ Extract Cloudinary public_id from a URL """
        try:
            filename = file_url.split("/")[-1]  # Get last part of the URL
            public_id = filename.split(".")[0]  # Remove extension
            return public_id
        except Exception as e:
            print(f"❌ Error extracting public_id: {e}")
            return None

    def update_springs(self, request, pk=None):
        """ ✅ Updates the springs assigned to an exercise """
        exercise = self.get_object()
        spring_ids = request.data.get('springs', [])

        # Clear existing springs and set new ones
        exercise.spring_configurations.all().delete()
        for spring_id in spring_ids:
            spring = Spring.objects.get(id=spring_id)
            ExerciseSpringConfig.objects.create(exercise=exercise, spring=spring)

        return Response({'message': 'Springs updated successfully'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def set_springs(self, request, pk=None):
        """ ✅ Endpoint to set springs for an exercise """
        return self.update_springs(request, pk)

    @action(detail=True, methods=['get'])
    def get_springs(self, request, pk=None):
        """ ✅ Retrieves the springs assigned to an exercise """
        exercise = self.get_object()
        springs = exercise.spring_configurations.all()
        serializer = ExerciseSpringConfigSerializer(springs, many=True)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        """
        ✅ Delete Cloudinary image and video before removing the instance from the database.
        """
        instance = self.get_object()

        # ✅ Delete image from Cloudinary if it exists
        if instance.image:
            self.delete_cloudinary_file(instance.image, "image")

        # ✅ Delete video from Cloudinary if it exists
        if instance.video:
            self.delete_cloudinary_file(instance.video, "video")

        return super().destroy(request, *args, **kwargs)



class RoutineViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Pilates workout routines"""
    queryset = Routine.objects.all().order_by('-created_at')
    serializer_class = RoutineSerializer
    permission_classes = [IsAuthenticated]
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        'prop__name': ['exact', 'in'],
        'machines__name': ['exact', 'in'],
        'on_edit': ['exact'],
    }
    search_fields = ['name']

    def get_queryset(self):
        queryset = super().get_queryset()

        # ✅ Multi-select filters (text fields)
        multi_select_filters = ['position__name', 'prop__name', 'machine__name', 'group']
        for field in multi_select_filters:
            value = self.request.query_params.get(field, None)
            if value:
                values_list = value.split(",")
                queryset = queryset.filter(**{f"exercise__{field}__in": values_list}).distinct()

        # ✅ Exact match filters (booleans)
        exact_filters = ['box', 'unilateral']
        for field in exact_filters:
            value = self.request.query_params.get(field, None)
            if value in ['true', 'false']:
                queryset = queryset.filter(**{f"exercise__{field}": value.lower() == 'true'}).distinct()

        # ✅ Tags: rutina debe tener ejercicios con las tags filtradas
        tag_ids = self.request.query_params.get("tag__id__in", None)
        if tag_ids:
            tag_id_list = [int(t.strip()) for t in tag_ids.split(",") if t.strip().isdigit()]
            queryset = queryset.annotate(
                matching_tags=Count("tags", filter=Q(tags__id__in=tag_id_list), distinct=True)
            ).filter(matching_tags=len(tag_id_list))

        return queryset
    
    def perform_create(self, serializer):
        """ Set the created_by and updated_by fields when a routine is created """
        routine = serializer.save(created_by=self.request.user, updated_by=self.request.user)
        
        tag_ids = self.request.data.get("tags", [])
        if isinstance(tag_ids, list):
            routine.tags.set(tag_ids)

    def perform_update(self, serializer):
        """ Update the updated_by field when a routine is edited """
        routine = serializer.save(updated_by=self.request.user)
        
        tag_ids = self.request.data.get("tags", [])
        if isinstance(tag_ids, list):
            routine.tags.set(tag_ids)

    @action(detail=True, methods=['post'])
    def add_exercise(self, request, pk=None):
        """Adds an exercise to a routine with order, reps, or time."""
        routine = self.get_object()
        exercise_id = request.data.get("exercise_id")
        order = request.data.get("order")
        repetitions = request.data.get("repetitions")
        duration_seconds = request.data.get("duration_seconds")
        comment = request.data.get("comment")

        if not exercise_id or not order:
            return Response({"error": "Exercise ID and order are required."}, status=400)

        try:
            exercise = Exercise.objects.get(id=exercise_id)
            RoutineExercise.objects.create(
                routine=routine,
                exercise=exercise,
                order=order,
                repetitions=repetitions,
                duration_seconds=duration_seconds,
                comment=comment
            )
            return Response({"message": "Exercise added to routine."}, status=201)
        except Exercise.DoesNotExist:
            return Response({"error": "Exercise not found."}, status=404)

    @action(detail=True, methods=['post'])
    def update_exercises(self, request, pk=None):
        """Bulk updates exercises in a routine (order, reps, time)."""
        routine = self.get_object()
        exercises = request.data.get("exercises", [])

        if not exercises:
            return Response({"error": "No exercises provided."}, status=400)

        # Clear previous exercises
        RoutineExercise.objects.filter(routine=routine).delete()

        # Add new exercises
        for item in exercises:
            try:
                exercise = Exercise.objects.get(id=item["exercise_id"])
                RoutineExercise.objects.create(
                    routine=routine,
                    exercise=exercise,
                    order=item["order"],
                    repetitions=item.get("repetitions"),
                    duration_seconds=item.get("duration_seconds")
                )
            except Exercise.DoesNotExist:
                continue  # Skip exercises that don't exist

        return Response({"message": "Routine exercises updated."}, status=200)

    @action(detail=True, methods=['post'])
    def finalize(self, request, pk=None):
        """Marks a routine as finalized (`on_edit=False`)."""
        routine = self.get_object()
        routine.on_edit = False
        routine.save()
        return Response({"message": "Routine finalized."}, status=200)
    
    @action(detail=True, methods=['post'])
    def add_exercise(self, request, pk=None):
        """ Adds an exercise to a specific routine, auto-assigning the order """
        try:
            routine = self.get_object()  # Retrieves the routine from {routine_id} in URL
            exercise_id = request.data.get("exercise_id")
            repetitions = request.data.get("repetitions", None)
            duration_seconds = request.data.get("duration_seconds", None)
            comment = request.data.get("comment", None)

            if not exercise_id:
                return Response({"error": "Exercise ID is required."}, status=status.HTTP_400_BAD_REQUEST)

            try:
                exercise = Exercise.objects.get(id=exercise_id)

                # ✅ Get the last exercise order in the routine
                last_exercise = RoutineExercise.objects.filter(routine=routine).order_by("-order").first()
                next_order = last_exercise.order + 1 if last_exercise else 1  # If no exercises, start at 1

                # Create the RoutineExercise entry with auto-incremented order
                RoutineExercise.objects.create(
                    routine=routine,
                    exercise=exercise,
                    order=next_order,
                    repetitions=repetitions,
                    duration_seconds=duration_seconds,
                    comment=comment
                )

                
                return Response({"message": f"Exercise '{exercise.name}' added to routine '{routine.name}' at position {next_order}."}, status=status.HTTP_201_CREATED)

            except Exercise.DoesNotExist:
                return Response({"error": "Exercise not found."}, status=status.HTTP_404_NOT_FOUND)

        except Routine.DoesNotExist:
            return Response({"error": "Routine not found."}, status=status.HTTP_404_NOT_FOUND)

    
    @action(detail=True, methods=['post'])
    def remove_exercise(self, request, pk=None):
        """Removes a specific exercise instance from a routine by RoutineExercise ID"""
        routine = self.get_object()
        routine_exercise_id = request.data.get("routine_exercise_id")  # ✅ Expect a specific instance ID

        if not routine_exercise_id:
            return Response({"error": "Routine Exercise ID is required."}, status=400)

        try:
            routine_exercise = RoutineExercise.objects.get(id=routine_exercise_id, routine=routine)
            deleted_order = routine_exercise.order
            routine_exercise.delete()

            # ✅ Update the order of remaining exercises
            remaining_exercises = RoutineExercise.objects.filter(routine=routine).order_by("order")

            for index, exercise in enumerate(remaining_exercises, start=1):
                exercise.order = index
                exercise.save()

            return Response({"message": "Exercise removed and order updated."}, status=200)

        except RoutineExercise.DoesNotExist:
            return Response({"error": "RoutineExercise instance not found."}, status=404)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def all_routines(request):
    try:
        routines = Routine.objects.all().order_by("name")
        serializer = RoutineSerializer(routines, many=True)
        return Response(serializer.data, status=200)
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def routines_basic(request):
    """Returns only basic routine info: id, name, duration with optional filtering"""
    from django.db.models import Q, Count
    
    try:
        on_edit = request.GET.get("on_edit", None)
        page = int(request.GET.get("page", 1))
        page_size = int(request.GET.get("page_size", 1000))
        
        queryset = Routine.objects.all()
        
        # Filter by on_edit status
        if on_edit is not None:
            queryset = queryset.filter(on_edit=(on_edit.lower() == "true"))
        
        # ✅ Multi-select filters (same as RoutineViewSet)
        multi_select_filters = ['position__name', 'prop__name', 'machine__name', 'group']
        for field in multi_select_filters:
            value = request.GET.get(f"{field}__in", None)
            if value:
                values_list = [v.strip() for v in value.split(",") if v.strip()]
                if values_list:
                    queryset = queryset.filter(**{f"routine_exercises__exercise__{field}__in": values_list}).distinct()

        # ✅ Exact match filters (booleans)
        exact_filters = ['box', 'unilateral']
        for field in exact_filters:
            value = request.GET.get(f"{field}__in", None)
            if value:
                queryset = queryset.filter(**{f"routine_exercises__exercise__{field}": value}).distinct()

        # ✅ Tags: rutina debe tener ejercicios con las tags filtradas
        tag_ids = request.GET.get("tag__id__in", None)
        if tag_ids:
            tag_id_list = [int(t.strip()) for t in tag_ids.split(",") if t.strip().isdigit()]
            if tag_id_list:
                queryset = queryset.annotate(
                    matching_tags=Count("tags", filter=Q(tags__id__in=tag_id_list), distinct=True)
                ).filter(matching_tags=len(tag_id_list))
        
        queryset = queryset.order_by("name")
        
        # Paginate results
        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        
        results = list(page_obj.object_list.values('id', 'name', 'duration'))
        
        return Response({
            'count': paginator.count,
            'results': results
        }, status=200)
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def routines_info(request):
    """Returns routine info for listing pages: basic fields + machine_names, prop, created_by, number_exercises"""
    from django.core.paginator import Paginator
    from django.db.models import Count, Q
    
    try:
        on_edit = request.GET.get("on_edit", None)
        page = int(request.GET.get("page", 1))
        page_size = int(request.GET.get("page_size", 15))
        
        queryset = Routine.objects.select_related('prop', 'created_by').prefetch_related('machines')
        
        if on_edit is not None:
            queryset = queryset.filter(on_edit=(on_edit.lower() == "true"))
        
        # ✅ Multi-select filters (same as RoutineViewSet)
        multi_select_filters = ['position__name', 'prop__name', 'machine__name', 'group']
        for field in multi_select_filters:
            value = request.GET.get(f"{field}__in", None)
            if value:
                values_list = [v.strip() for v in value.split(",") if v.strip()]
                if values_list:
                    queryset = queryset.filter(**{f"routine_exercises__exercise__{field}__in": values_list}).distinct()

        # ✅ Exact match filters (booleans)
        exact_filters = ['box', 'unilateral']
        for field in exact_filters:
            value = request.GET.get(f"{field}__in", None)
            if value:
                queryset = queryset.filter(**{f"routine_exercises__exercise__{field}": value}).distinct()

        # ✅ Tags: rutina debe tener ejercicios con las tags filtradas
        tag_ids = request.GET.get("tag__id__in", None)
        if tag_ids:
            tag_id_list = [int(t.strip()) for t in tag_ids.split(",") if t.strip().isdigit()]
            if tag_id_list:
                queryset = queryset.annotate(
                    matching_tags=Count("tags", filter=Q(tags__id__in=tag_id_list), distinct=True)
                ).filter(matching_tags=len(tag_id_list))
        
        queryset = queryset.annotate(
            exercise_count=Count('routine_exercises', distinct=True)
        ).order_by('name')
        
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        
        results = []
        for routine in page_obj:
            results.append({
                'id': routine.id,
                'name': routine.name,
                'duration': routine.duration,
                'number_exercises': routine.exercise_count,
                'machine_names': [m.name for m in routine.machines.all()],
                'prop': routine.prop.name if routine.prop else None,
                'created_by': routine.created_by.username if routine.created_by else "N/A",
                'on_edit': routine.on_edit
            })
        
        return Response({
            'count': paginator.count,
            'results': results
        }, status=200)
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def exercises_basic(request):
    """Returns only basic exercise info: id, name, image, video (no related tables)"""
    from django.core.paginator import Paginator
    from django.db.models import Count, Q
    
    try:
        page = int(request.GET.get("page", 1))
        page_size = int(request.GET.get("page_size", 1000))
        
        queryset = Exercise.objects.all()
        
        # ✅ Handle name search filter
        name_search = request.GET.get('name__icontains', None)
        if name_search:
            queryset = queryset.filter(name__icontains=name_search)
        
        # ✅ Multi-select filters
        multi_select_filters = ['position__name', 'prop__name', 'machine__name', 'group']
        for field in multi_select_filters:
            value = request.GET.get(f"{field}__in", None)
            if value:
                values_list = [v.strip() for v in value.split(",") if v.strip()]
                if values_list:
                    queryset = queryset.filter(**{f"{field}__in": values_list})

        # ✅ Exact match filters (booleans)
        exact_filters = ['box', 'unilateral']
        for field in exact_filters:
            value = request.GET.get(f"{field}__in", None)
            if value:
                queryset = queryset.filter(**{field: value})

        # ✅ Tags filter
        tag_ids = request.GET.get('tag__id__in', None)
        if tag_ids:
            tag_id_list = [int(t.strip()) for t in tag_ids.split(',') if t.strip().isdigit()]
            queryset = queryset.annotate(
                matching_tags=Count('tags', filter=Q(tags__id__in=tag_id_list), distinct=True)
            ).filter(matching_tags=len(tag_id_list))
        
        queryset = queryset.order_by('name')
        
        # Paginate results
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        
        # Return only basic fields
        results = list(page_obj.object_list.values('id', 'name', 'image', 'video'))
        
        return Response({
            'count': paginator.count,
            'results': results
        }, status=200)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    

### 🚀 UTILITIES ###
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_groups(request):    
    try:
        groups = Group.objects.all().values('id', 'name')
        return Response(list(groups))
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reorder_routine_exercises(request):
    routine_id = request.data.get("routine_id")
    exercises = request.data.get("exercises", [])

    if not routine_id:
        return Response({"error": "Missing routine_id"}, status=400)

    valid_ids = set(
        RoutineExercise.objects.filter(routine_id=routine_id).values_list("id", flat=True)
    )

    try:
        with transaction.atomic():
            # Paso 1: poner valores temporales seguros
            for item in exercises:
                id_on_routine = item.get("id_on_routine")
                if id_on_routine in valid_ids:
                    RoutineExercise.objects.filter(id=id_on_routine).update(order=9999 + id_on_routine)

            # Paso 2: aplicar el nuevo orden
            for item in exercises:
                id_on_routine = item.get("id_on_routine")
                new_order = item.get("order")
                if id_on_routine in valid_ids and new_order is not None:
                    RoutineExercise.objects.filter(id=id_on_routine).update(order=new_order)

        return Response({"status": "ok"})
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    
class FlexiblePageNumberPagination(pagination.PageNumberPagination):
    """Paginación que permite sobrescribir page_size desde query params"""
    page_size = 15
    page_size_query_param = 'page_size'
    max_page_size = 10000


class AssignmentPropagationMixin:
    def _validate_assignment_date(self, assignment_date):
        allow_past_assignments = getattr(settings, "ALLOW_PAST_DAILY_ASSIGNMENTS", False)
        today = timezone.localdate()

        if not allow_past_assignments and assignment_date < today:
            raise DRFValidationError(
                {
                    "date": (
                        "Assignments cannot be created or edited for past dates. "
                        f"Today is {today.isoformat()}."
                    )
                }
            )

    def _sync_daily_assignment_with_general(self, assignment, save=True):
        general_assignment = GeneralRoutineAssignment.objects.filter(
            date=assignment.date,
            active=True,
        ).select_related("routine").first()

        assignment.general_routine_assignment = general_assignment
        assignment.overrides_general_assignment = bool(
            general_assignment and assignment.routine_id != general_assignment.routine_id
        )

        if save:
            assignment.save(update_fields=[
                "general_routine_assignment",
                "overrides_general_assignment",
                "updated_at",
            ])

    def _apply_assignment_to_sessions(self, assignment, overwrite_manual=False):
        day_sessions = RoutineSession.objects.filter(
            room=assignment.room,
            scheduled_at__date=assignment.date,
        )

        today = timezone.localdate()
        skipped_overridden_sessions = 0
        skipped_past_sessions = day_sessions.filter(scheduled_at__date__lt=today).count()
        day_sessions = day_sessions.filter(scheduled_at__date__gte=today)

        skipped_non_programmed_sessions = day_sessions.exclude(state=0).count()
        updated_sessions = 0

        day_sessions = day_sessions.filter(state=0)

        if not overwrite_manual:
            skipped_overridden_sessions = day_sessions.filter(
                routine_manually_overridden=True
            ).count()
            day_sessions = day_sessions.filter(routine_manually_overridden=False)

        updated_sessions = day_sessions.update(
            routine=assignment.routine,
            daily_routine_assignment=assignment,
            routine_manually_overridden=False,
        )

        return {
            "updated_sessions": updated_sessions,
            "skipped_overridden_sessions": skipped_overridden_sessions,
            "skipped_non_programmed_sessions": skipped_non_programmed_sessions,
            "skipped_past_sessions": skipped_past_sessions,
        }

    def _validate_assignment_delete_date(self, assignment_date):
        if assignment_date < timezone.localdate():
            raise DRFValidationError(
                {"date": "Past assignments cannot be deleted or cleared."}
            )

    def _clear_assignment_sessions(self, assignment, *, keep_assignment_link):
        day_sessions = RoutineSession.objects.filter(
            room=assignment.room,
            scheduled_at__date=assignment.date,
        )

        today = timezone.localdate()
        skipped_past_sessions = day_sessions.filter(scheduled_at__date__lt=today).count()
        day_sessions = day_sessions.filter(scheduled_at__date__gte=today)

        skipped_non_programmed_sessions = day_sessions.exclude(state=0).count()
        day_sessions = day_sessions.filter(state=0)

        preserved_manual_overrides = day_sessions.filter(
            routine_manually_overridden=True
        ).count()

        cleared_sessions = day_sessions.filter(
            routine_manually_overridden=False
        ).update(
            routine=None,
            daily_routine_assignment=assignment if keep_assignment_link else None,
            routine_manually_overridden=False,
        )

        if not keep_assignment_link:
            day_sessions.filter(
                routine_manually_overridden=True,
                daily_routine_assignment=assignment,
            ).update(daily_routine_assignment=None)

        return {
            "cleared_sessions": cleared_sessions,
            "preserved_manual_overrides": preserved_manual_overrides,
            "skipped_non_programmed_sessions": skipped_non_programmed_sessions,
            "skipped_past_sessions": skipped_past_sessions,
        }


class DailyRoutineAssignmentViewSet(AssignmentPropagationMixin, viewsets.ModelViewSet):
    queryset = DailyRoutineAssignment.objects.select_related(
        "center",
        "room",
        "routine",
        "general_routine_assignment",
        "general_routine_assignment__routine",
    ).all()
    serializer_class = DailyRoutineAssignmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        center_id = params.get("center_id")
        room_id = params.get("room_id")
        date_value = params.get("date")
        date_gte = params.get("date__gte")
        date_lte = params.get("date__lte")
        active = params.get("active")

        if center_id:
            queryset = queryset.filter(center_id=center_id)
        if room_id:
            queryset = queryset.filter(room_id=room_id)
        if date_value:
            parsed = parse_date(date_value)
            if parsed:
                queryset = queryset.filter(date=parsed)
        if date_gte:
            parsed = parse_date(date_gte)
            if parsed:
                queryset = queryset.filter(date__gte=parsed)
        if date_lte:
            parsed = parse_date(date_lte)
            if parsed:
                queryset = queryset.filter(date__lte=parsed)
        if active is not None:
            queryset = queryset.filter(active=active.lower() == "true")

        return queryset.order_by("date", "room__name")

    def perform_create(self, serializer):
        assignment_date = serializer.validated_data["date"]
        self._validate_assignment_date(assignment_date)
        assignment = serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user,
        )
        self._sync_daily_assignment_with_general(assignment)
        self._apply_assignment_to_sessions(assignment, overwrite_manual=True)

    def perform_update(self, serializer):
        overwrite_manual = self.request.data.get("overwrite_manual", False)
        overwrite_manual = str(overwrite_manual).lower() == "true" if isinstance(overwrite_manual, str) else bool(overwrite_manual)
        assignment_date = serializer.validated_data.get("date", serializer.instance.date)
        self._validate_assignment_date(assignment_date)
        assignment = serializer.save(updated_by=self.request.user)
        self._sync_daily_assignment_with_general(assignment)
        self._apply_assignment_to_sessions(assignment, overwrite_manual=overwrite_manual)

    def destroy(self, request, *args, **kwargs):
        assignment = self.get_object()
        self._validate_assignment_delete_date(assignment.date)

        with transaction.atomic():
            payload = self._clear_single_daily_assignment(assignment, request.user)

        return Response(payload, status=status.HTTP_200_OK)

    def _clear_single_daily_assignment(self, assignment, user):
        if assignment.general_routine_assignment_id:
            assignment.routine = None
            assignment.overrides_general_assignment = True
            assignment.updated_by = user
            assignment.active = True
            assignment.save(update_fields=[
                "routine",
                "overrides_general_assignment",
                "updated_by",
                "updated_at",
                "active",
            ])
            result = self._clear_assignment_sessions(assignment, keep_assignment_link=True)
            return {
                "message": "Daily assignment cleared and preserved as a room override.",
                "action": "cleared",
                "assignment_id": assignment.id,
                **result,
            }

        result = self._clear_assignment_sessions(assignment, keep_assignment_link=False)
        assignment.active = False
        assignment.updated_by = user
        assignment.save(update_fields=["active", "updated_by", "updated_at"])
        return {
            "message": "Daily assignment removed.",
            "action": "deactivated",
            "assignment_id": assignment.id,
            **result,
        }

    @action(detail=False, methods=["post"], url_path="clear-day")
    def clear_day(self, request):
        center_id = request.data.get("center_id")
        date_value = request.data.get("date")

        if not center_id:
            return Response({"error": "center_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not date_value or not parse_date(date_value):
            return Response({"error": "A valid date is required"}, status=status.HTTP_400_BAD_REQUEST)

        assignment_date = parse_date(date_value)
        self._validate_assignment_delete_date(assignment_date)

        assignments = DailyRoutineAssignment.objects.filter(
            center_id=center_id,
            date=assignment_date,
            active=True,
        ).select_related("general_routine_assignment", "room")

        if not assignments.exists():
            return Response(
                {"error": "No active daily assignments found for that center and date."},
                status=status.HTTP_404_NOT_FOUND,
            )

        cleared_assignments = 0
        deactivated_assignments = 0
        cleared_sessions = 0
        preserved_manual_overrides = 0
        skipped_non_programmed_sessions = 0
        skipped_past_sessions = 0

        with transaction.atomic():
            for assignment in assignments:
                result = self._clear_single_daily_assignment(assignment, request.user)
                cleared_assignments += 1
                if result["action"] == "deactivated":
                    deactivated_assignments += 1
                cleared_sessions += result["cleared_sessions"]
                preserved_manual_overrides += result["preserved_manual_overrides"]
                skipped_non_programmed_sessions += result["skipped_non_programmed_sessions"]
                skipped_past_sessions += result["skipped_past_sessions"]

        return Response(
            {
                "message": "Center day assignments cleared.",
                "center_id": int(center_id),
                "date": assignment_date,
                "cleared_assignments": cleared_assignments,
                "deactivated_assignments": deactivated_assignments,
                "cleared_sessions": cleared_sessions,
                "preserved_manual_overrides": preserved_manual_overrides,
                "skipped_non_programmed_sessions": skipped_non_programmed_sessions,
                "skipped_past_sessions": skipped_past_sessions,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="bulk-assign")
    def bulk_assign(self, request):
        room_ids = request.data.get("room_ids", [])
        date_value = request.data.get("date")
        routine_id = request.data.get("routine_id")
        center_id = request.data.get("center_id")
        overwrite_manual = request.data.get("overwrite_manual", False)
        overwrite_manual = str(overwrite_manual).lower() == "true" if isinstance(overwrite_manual, str) else bool(overwrite_manual)

        if not room_ids:
            return Response({"error": "room_ids is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not date_value or not parse_date(date_value):
            return Response({"error": "A valid date is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not routine_id:
            return Response({"error": "routine_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not center_id:
            return Response({"error": "center_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        assignment_date = parse_date(date_value)
        self._validate_assignment_date(assignment_date)

        try:
            center = Center.objects.get(id=center_id)
            routine = Routine.objects.get(id=routine_id)
        except (Center.DoesNotExist, Routine.DoesNotExist):
            return Response({"error": "Center or routine not found"}, status=status.HTTP_404_NOT_FOUND)

        rooms = Room.objects.filter(id__in=room_ids, center=center)
        if rooms.count() != len(set(room_ids)):
            return Response(
                {"error": "One or more selected rooms do not belong to the selected center"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created_count = 0
        updated_count = 0
        sessions_updated = 0
        overridden_sessions = 0
        non_programmed_sessions = 0
        past_sessions = 0

        with transaction.atomic():
            for room in rooms:
                assignment, created = DailyRoutineAssignment.objects.get_or_create(
                    date=assignment_date,
                    room=room,
                    defaults={
                        "center": center,
                        "routine": routine,
                        "general_routine_assignment": GeneralRoutineAssignment.objects.filter(date=assignment_date, active=True).first(),
                        "active": True,
                        "created_by": request.user,
                        "updated_by": request.user,
                    },
                )

                if not created:
                    assignment.center = center
                    assignment.routine = routine
                    assignment.active = True
                    assignment.updated_by = request.user
                    self._sync_daily_assignment_with_general(assignment, save=False)
                    assignment.save(update_fields=[
                        "center",
                        "routine",
                        "general_routine_assignment",
                        "overrides_general_assignment",
                        "active",
                        "updated_by",
                        "updated_at",
                    ])
                else:
                    self._sync_daily_assignment_with_general(assignment, save=True)

                if created:
                    created_count += 1
                else:
                    updated_count += 1

                result = self._apply_assignment_to_sessions(
                    assignment,
                    overwrite_manual=overwrite_manual,
                )
                sessions_updated += result["updated_sessions"]
                overridden_sessions += result["skipped_overridden_sessions"]
                non_programmed_sessions += result["skipped_non_programmed_sessions"]
                past_sessions += result["skipped_past_sessions"]

        return Response(
            {
                "message": "Daily routine assignments processed successfully",
                "date": assignment_date,
                "center_id": center.id,
                "room_ids": list(rooms.values_list("id", flat=True)),
                "created_assignments": created_count,
                "updated_assignments": updated_count,
                "updated_sessions": sessions_updated,
                "skipped_overridden_sessions": overridden_sessions,
                "skipped_non_programmed_sessions": non_programmed_sessions,
                "skipped_past_sessions": past_sessions,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="week-summary")
    def week_summary(self, request):
        center_id = request.query_params.get("center_id")
        start_date_raw = request.query_params.get("start_date")

        if not center_id:
            return Response({"error": "center_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        start_date = parse_date(start_date_raw) if start_date_raw else None
        if not start_date:
            return Response({"error": "A valid start_date is required"}, status=status.HTTP_400_BAD_REQUEST)

        end_date = start_date + timedelta(days=6)
        rooms = Room.objects.filter(center_id=center_id)
        room_ids = list(rooms.values_list("id", flat=True))
        general_assignments = GeneralRoutineAssignment.objects.filter(
            date__gte=start_date,
            date__lte=end_date,
            active=True,
        ).select_related("routine")

        assignments = DailyRoutineAssignment.objects.filter(
            center_id=center_id,
            date__gte=start_date,
            date__lte=end_date,
            active=True,
        ).select_related("routine", "room", "general_routine_assignment", "general_routine_assignment__routine")

        sessions = RoutineSession.objects.filter(
            room_id__in=room_ids,
            scheduled_at__date__gte=start_date,
            scheduled_at__date__lte=end_date,
        ).select_related("routine", "daily_routine_assignment")

        general_assignment_map = {assignment.date.isoformat(): assignment for assignment in general_assignments}
        assignment_map = {}
        for assignment in assignments:
            assignment_map.setdefault(assignment.date.isoformat(), []).append(assignment)

        sessions_by_date = {}
        for session in sessions:
            date_key = session.scheduled_at.date().isoformat()
            sessions_by_date.setdefault(date_key, []).append(session)

        summary = []
        for offset in range(7):
            current_date = start_date + timedelta(days=offset)
            date_key = current_date.isoformat()
            general_assignment = general_assignment_map.get(date_key)
            day_assignments = assignment_map.get(date_key, [])
            day_sessions = sessions_by_date.get(date_key, [])
            assigned_assignments = [assignment for assignment in day_assignments if assignment.routine_id]
            assigned_routine_ids = {assignment.routine_id for assignment in assigned_assignments}
            overriding_assignments = [assignment for assignment in day_assignments if assignment.overrides_general_assignment]
            rooms_following_general_count = sum(
                1 for assignment in day_assignments if not assignment.overrides_general_assignment and assignment.routine_id
            )
            follows_general_assignment = bool(
                general_assignment
                and assigned_assignments
                and len(overriding_assignments) == 0
                and len(assigned_routine_ids) == 1
                and next(iter(assigned_routine_ids)) == general_assignment.routine_id
            )

            summary.append({
                "date": date_key,
                "sessions_count": len(day_sessions),
                "rooms_count": len(room_ids),
                "assigned_rooms_count": len(assigned_assignments),
                "routine_count": len(assigned_routine_ids),
                "single_routine_name": assigned_assignments[0].routine.name if len(assigned_routine_ids) == 1 and assigned_assignments else None,
                "has_assignments": bool(assigned_assignments),
                "has_mixed_assignments": len(assigned_routine_ids) > 1,
                "cleared_rooms_count": sum(1 for assignment in day_assignments if assignment.routine_id is None and assignment.active),
                "has_general_assignment": general_assignment is not None,
                "general_routine_name": general_assignment.routine.name if general_assignment else None,
                "general_routine_id": general_assignment.routine_id if general_assignment else None,
                "overriding_rooms_count": len(overriding_assignments),
                "rooms_following_general_count": rooms_following_general_count,
                "follows_general_assignment": follows_general_assignment,
                "overridden_sessions_count": sum(
                    1 for session in day_sessions if session.routine_manually_overridden
                ),
            })

        return Response(
            {
                "center_id": int(center_id),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": summary,
            },
            status=status.HTTP_200_OK,
        )


class GeneralRoutineAssignmentViewSet(AssignmentPropagationMixin, viewsets.ModelViewSet):
    queryset = GeneralRoutineAssignment.objects.select_related("routine").all()
    serializer_class = GeneralRoutineAssignmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        date_value = params.get("date")
        date_gte = params.get("date__gte")
        date_lte = params.get("date__lte")
        active = params.get("active")

        if date_value:
            parsed = parse_date(date_value)
            if parsed:
                queryset = queryset.filter(date=parsed)
        if date_gte:
            parsed = parse_date(date_gte)
            if parsed:
                queryset = queryset.filter(date__gte=parsed)
        if date_lte:
            parsed = parse_date(date_lte)
            if parsed:
                queryset = queryset.filter(date__lte=parsed)
        if active is not None:
            queryset = queryset.filter(active=active.lower() == "true")

        return queryset.order_by("date")

    def perform_create(self, serializer):
        overwrite_room_overrides = self._parse_bool(self.request.data.get("overwrite_room_overrides", False))
        overwrite_manual = self._parse_bool(self.request.data.get("overwrite_manual", False))
        assignment_date = serializer.validated_data["date"]
        self._validate_assignment_date(assignment_date)
        general_assignment = serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user,
        )
        self._propagate_general_assignment(
            general_assignment,
            overwrite_room_overrides=overwrite_room_overrides,
            overwrite_manual=overwrite_manual,
        )

    def perform_update(self, serializer):
        overwrite_room_overrides = self._parse_bool(self.request.data.get("overwrite_room_overrides", False))
        overwrite_manual = self._parse_bool(self.request.data.get("overwrite_manual", False))
        assignment_date = serializer.validated_data.get("date", serializer.instance.date)
        self._validate_assignment_date(assignment_date)
        general_assignment = serializer.save(updated_by=self.request.user)
        self._propagate_general_assignment(
            general_assignment,
            overwrite_room_overrides=overwrite_room_overrides,
            overwrite_manual=overwrite_manual,
        )

    def destroy(self, request, *args, **kwargs):
        general_assignment = self.get_object()
        self._validate_assignment_delete_date(general_assignment.date)

        room_assignments = DailyRoutineAssignment.objects.filter(
            general_routine_assignment=general_assignment,
            active=True,
        )

        cleared_sessions = 0
        preserved_manual_overrides = 0
        skipped_non_programmed_sessions = 0
        skipped_past_sessions = 0
        preserved_room_overrides = 0
        deactivated_room_assignments = 0
        detached_room_overrides = 0

        with transaction.atomic():
            for assignment in room_assignments:
                if assignment.overrides_general_assignment:
                    assignment.general_routine_assignment = None
                    assignment.overrides_general_assignment = False
                    assignment.updated_by = request.user
                    assignment.save(update_fields=[
                        "general_routine_assignment",
                        "overrides_general_assignment",
                        "updated_by",
                        "updated_at",
                    ])
                    preserved_room_overrides += 1
                    detached_room_overrides += 1
                    continue

                result = self._clear_assignment_sessions(assignment, keep_assignment_link=False)
                cleared_sessions += result["cleared_sessions"]
                preserved_manual_overrides += result["preserved_manual_overrides"]
                skipped_non_programmed_sessions += result["skipped_non_programmed_sessions"]
                skipped_past_sessions += result["skipped_past_sessions"]

                assignment.active = False
                assignment.updated_by = request.user
                assignment.save(update_fields=["active", "updated_by", "updated_at"])
                deactivated_room_assignments += 1

            general_assignment.active = False
            general_assignment.updated_by = request.user
            general_assignment.save(update_fields=["active", "updated_by", "updated_at"])

        return Response(
            {
                "message": "General assignment removed.",
                "action": "deactivated",
                "general_assignment_id": general_assignment.id,
                "deactivated_room_assignments": deactivated_room_assignments,
                "preserved_room_overrides": preserved_room_overrides,
                "detached_room_overrides": detached_room_overrides,
                "cleared_sessions": cleared_sessions,
                "preserved_manual_overrides": preserved_manual_overrides,
                "skipped_non_programmed_sessions": skipped_non_programmed_sessions,
                "skipped_past_sessions": skipped_past_sessions,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="bulk-assign")
    def bulk_assign(self, request):
        date_value = request.data.get("date")
        routine_id = request.data.get("routine_id")
        overwrite_room_overrides = self._parse_bool(request.data.get("overwrite_room_overrides", False))
        overwrite_manual = self._parse_bool(request.data.get("overwrite_manual", False))
        notes = request.data.get("notes")

        if not date_value or not parse_date(date_value):
            return Response({"error": "A valid date is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not routine_id:
            return Response({"error": "routine_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        assignment_date = parse_date(date_value)
        self._validate_assignment_date(assignment_date)

        try:
            routine = Routine.objects.get(id=routine_id)
        except Routine.DoesNotExist:
            return Response({"error": "Routine not found"}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            general_assignment, created = GeneralRoutineAssignment.objects.get_or_create(
                date=assignment_date,
                defaults={
                    "routine": routine,
                    "notes": notes,
                    "active": True,
                    "created_by": request.user,
                    "updated_by": request.user,
                },
            )

            if not created:
                general_assignment.routine = routine
                general_assignment.notes = notes
                general_assignment.active = True
                general_assignment.updated_by = request.user
                general_assignment.save(update_fields=["routine", "notes", "active", "updated_by", "updated_at"])

            result = self._propagate_general_assignment(
                general_assignment,
                overwrite_room_overrides=overwrite_room_overrides,
                overwrite_manual=overwrite_manual,
            )

        return Response(
            {
                "message": "General routine assignment processed successfully",
                "general_assignment_id": general_assignment.id,
                "date": assignment_date,
                "created": created,
                **result,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="week-summary")
    def week_summary(self, request):
        start_date_raw = request.query_params.get("start_date")
        start_date = parse_date(start_date_raw) if start_date_raw else None
        if not start_date:
            return Response({"error": "A valid start_date is required"}, status=status.HTTP_400_BAD_REQUEST)

        end_date = start_date + timedelta(days=6)
        general_assignments = GeneralRoutineAssignment.objects.filter(
            date__gte=start_date,
            date__lte=end_date,
            active=True,
        ).select_related("routine")

        room_assignments = DailyRoutineAssignment.objects.filter(
            date__gte=start_date,
            date__lte=end_date,
            active=True,
        ).select_related("routine", "center", "general_routine_assignment")

        sessions = RoutineSession.objects.filter(
            scheduled_at__date__gte=start_date,
            scheduled_at__date__lte=end_date,
        ).select_related("daily_routine_assignment")

        general_map = {assignment.date.isoformat(): assignment for assignment in general_assignments}
        room_assignment_map = {}
        for assignment in room_assignments:
            room_assignment_map.setdefault(assignment.date.isoformat(), []).append(assignment)

        sessions_map = {}
        for session in sessions:
            sessions_map.setdefault(session.scheduled_at.date().isoformat(), []).append(session)

        summary = []
        for offset in range(7):
            current_date = start_date + timedelta(days=offset)
            date_key = current_date.isoformat()
            general_assignment = general_map.get(date_key)
            day_room_assignments = room_assignment_map.get(date_key, [])
            day_sessions = sessions_map.get(date_key, [])
            centers_with_assignments = {assignment.center_id for assignment in day_room_assignments}
            rooms_with_overrides = [assignment for assignment in day_room_assignments if assignment.overrides_general_assignment]
            centers_with_room_overrides = {assignment.center_id for assignment in rooms_with_overrides}

            summary.append({
                "date": date_key,
                "general_assignment_id": general_assignment.id if general_assignment else None,
                "has_general_assignment": general_assignment is not None,
                "general_routine_name": general_assignment.routine.name if general_assignment else None,
                "general_routine_id": general_assignment.routine_id if general_assignment else None,
                "notes": general_assignment.notes if general_assignment else None,
                "centers_count": len(centers_with_assignments),
                "rooms_count": len(day_room_assignments),
                "assigned_centers_count": len({assignment.center_id for assignment in day_room_assignments if assignment.routine_id}),
                "assigned_rooms_count": sum(1 for assignment in day_room_assignments if assignment.routine_id),
                "sessions_count": len(day_sessions),
                "overridden_room_assignments_count": len(rooms_with_overrides),
                "centers_with_room_overrides_count": len(centers_with_room_overrides),
                "overridden_sessions_count": sum(
                    1 for session in day_sessions if session.routine_manually_overridden
                ),
                "has_room_overrides": bool(rooms_with_overrides),
            })

        return Response(
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": summary,
            },
            status=status.HTTP_200_OK,
        )

    def _parse_bool(self, value):
        return str(value).lower() == "true" if isinstance(value, str) else bool(value)

    def _propagate_general_assignment(self, general_assignment, overwrite_room_overrides=False, overwrite_manual=False):
        rooms = Room.objects.filter(
            routinesessions__scheduled_at__date=general_assignment.date
        ).select_related("center").distinct()

        created_assignments = 0
        updated_assignments = 0
        preserved_room_overrides = 0
        sessions_updated = 0
        skipped_overridden_sessions = 0
        skipped_non_programmed_sessions = 0
        skipped_past_sessions = 0
        targeted_centers = set()
        targeted_rooms = set()

        for room in rooms:
            targeted_rooms.add(room.id)
            targeted_centers.add(room.center_id)
            assignment, created = DailyRoutineAssignment.objects.get_or_create(
                date=general_assignment.date,
                room=room,
                defaults={
                    "center": room.center,
                    "routine": general_assignment.routine,
                    "general_routine_assignment": general_assignment,
                    "overrides_general_assignment": False,
                    "active": True,
                    "created_by": self.request.user,
                    "updated_by": self.request.user,
                },
            )

            preserve_override = (
                not created
                and assignment.overrides_general_assignment
                and assignment.routine_id != general_assignment.routine_id
                and not overwrite_room_overrides
            )

            if not created:
                assignment.center = room.center
                assignment.general_routine_assignment = general_assignment
                assignment.active = True
                assignment.updated_by = self.request.user

                if preserve_override:
                    assignment.overrides_general_assignment = True
                    preserved_room_overrides += 1
                else:
                    assignment.routine = general_assignment.routine
                    assignment.overrides_general_assignment = False

                assignment.save(update_fields=[
                    "center",
                    "routine",
                    "general_routine_assignment",
                    "overrides_general_assignment",
                    "active",
                    "updated_by",
                    "updated_at",
                ])

            result = self._apply_assignment_to_sessions(
                assignment,
                overwrite_manual=overwrite_manual,
            )

            sessions_updated += result["updated_sessions"]
            skipped_overridden_sessions += result["skipped_overridden_sessions"]
            skipped_non_programmed_sessions += result["skipped_non_programmed_sessions"]
            skipped_past_sessions += result["skipped_past_sessions"]

            if created:
                created_assignments += 1
            else:
                updated_assignments += 1

        return {
            "targeted_centers_count": len(targeted_centers),
            "targeted_rooms_count": len(targeted_rooms),
            "created_room_assignments": created_assignments,
            "updated_room_assignments": updated_assignments,
            "preserved_room_overrides": preserved_room_overrides,
            "updated_sessions": sessions_updated,
            "skipped_overridden_sessions": skipped_overridden_sessions,
            "skipped_non_programmed_sessions": skipped_non_programmed_sessions,
            "skipped_past_sessions": skipped_past_sessions,
        }


class RoutineSessionViewSet(viewsets.ModelViewSet):
    queryset = RoutineSession.objects.select_related(
        'room', 
        'room__center', 
        'routine', 
        'user', 
        'session_series'
    ).all().order_by('-scheduled_at')
    serializer_class = RoutineSessionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = FlexiblePageNumberPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
                        
        user_permissions = self.request.user.get_all_permissions()
        is_admin = any(perm in user_permissions for perm in [
            "core_data.add_routinesession", 
            "core_data.delete_routinesession"
        ])

        # Forzar solo sesiones de usuario si no es admin.
        if not is_admin:
            queryset = queryset.filter(user=self.request.user)
        
        center_id = params.get("center_id")
        room_id = params.get("room_id")
        room_id__in = params.get("room_id__in")
        routine_id = params.get("routine_id")
        user_id = params.get("user_id")
        scheduled_at__gte = params.get("scheduled_at__gte")
        scheduled_at__lte = params.get("scheduled_at__lte")

        if center_id:
            queryset = queryset.filter(center_id=center_id)

        if room_id:
            queryset = queryset.filter(room_id=room_id)
        
        if room_id__in:
            room_ids = [int(rid) for rid in room_id__in.split(',') if rid.strip()]
            queryset = queryset.filter(room_id__in=room_ids)

        if routine_id:
            queryset = queryset.filter(routine_id=routine_id)
        
        if user_id and is_admin:
            queryset = queryset.filter(user_id=user_id)

        if scheduled_at__gte:
            queryset = queryset.filter(scheduled_at__gte=parse_datetime(scheduled_at__gte))

        if scheduled_at__lte:
            queryset = queryset.filter(scheduled_at__lte=parse_datetime(scheduled_at__lte))

        return queryset.order_by("scheduled_at")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        instance = self.get_object()
        new_routine = serializer.validated_data.get("routine", instance.routine)
        routine_changed = new_routine != instance.routine
        is_past_session = instance.scheduled_at.date() < timezone.localdate()

        if routine_changed and (instance.state != 0 or is_past_session):
            raise DRFValidationError(
                {
                    "routine_id": (
                        "The class can only be changed while the session is in "
                        "'Programada' state and scheduled for today or a future date."
                    )
                }
            )

        manual_override = instance.routine_manually_overridden
        if instance.daily_routine_assignment and routine_changed:
            assignment_routine = instance.daily_routine_assignment.routine
            manual_override = new_routine != assignment_routine

        serializer.save(routine_manually_overridden=manual_override)

    def partial_update(self, request, *args, **kwargs):
        """Permite actualizaciones parciales (PATCH) para campos como state y userFeedback"""
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)
    
    @action(detail=True, methods=['patch'], url_path='update-series')
    def update_series(self, request, pk=None):
        """
        Updates future sessions of a series with the same changes
        - Only applies to sessions with scheduled_at >= current session
        - The routine is NOT applied to other sessions (only to the current one)
        - Allows changing: name, duration, room, user, and TIME (but not date)
        PATCH /api/data/routinesessions/{id}/update-series/
        """
        session = self.get_object()
        
        if not session.session_series:
            return Response({
                'error': 'Esta sesión no pertenece a ninguna serie'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Obtener solo las sesiones FUTURAS de la misma serie (>= a la fecha de esta sesión)
        series_sessions = RoutineSession.objects.filter(
            session_series=session.session_series,
            scheduled_at__gte=session.scheduled_at
        )
        
        # Campos que se pueden actualizar en bloque (SIN routine_id)
        updateable_fields = ['name', 'duration', 'room_id', 'user_id']
        update_data = {}
        
        for field in updateable_fields:
            if field in request.data:
                update_data[field] = request.data[field]
        
        # Manejar actualización de hora (pero no fecha)
        new_time = request.data.get('time')  # Formato "HH:MM" o "HH:MM:SS"
        
        if new_time:
            from datetime import datetime, time as datetime_time
            # Convertir string a time object
            if isinstance(new_time, str):
                time_parts = new_time.split(':')
                hour = int(time_parts[0])
                minute = int(time_parts[1]) if len(time_parts) > 1 else 0
                second = int(time_parts[2]) if len(time_parts) > 2 else 0
                new_time_obj = datetime_time(hour, minute, second)
            
            # Actualizar cada sesión manteniendo su fecha pero cambiando la hora
            for sess in series_sessions:
                old_datetime = sess.scheduled_at
                new_datetime = datetime.combine(old_datetime.date(), new_time_obj)
                sess.scheduled_at = new_datetime
                sess.save()
        
        # Actualizar los otros campos en bloque si hay
        if update_data:
            series_sessions.update(**update_data)
        
        updated_count = series_sessions.count()
        
        return Response({
            'message': f'Se actualizaron {updated_count} sesiones futuras de la serie',
            'series_id': session.session_series.id,
            'series_name': session.session_series.name,
            'updated_count': updated_count,
            'updated_fields': list(update_data.keys()) + (['time'] if new_time else [])
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['delete'], url_path='delete-series')
    def delete_series(self, request, pk=None):
        """
        Deletes this session and all subsequent sessions of the series
        DELETE /api/data/routinesessions/{id}/delete-series/
        """
        session = self.get_object()
        
        if not session.session_series:
            return Response({
                'error': 'Esta sesión no pertenece a ninguna serie'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Obtener esta sesión y todas las posteriores de la serie
        series_sessions = RoutineSession.objects.filter(
            session_series=session.session_series,
            scheduled_at__gte=session.scheduled_at
        )
        
        deleted_count = series_sessions.count()
        series_name = session.session_series.name
        series_id = session.session_series.id
        
        # Eliminar las sesiones
        series_sessions.delete()
        
        return Response({
            'message': f'Se eliminaron {deleted_count} sesiones de la serie',
            'series_id': series_id,
            'series_name': series_name,
            'deleted_count': deleted_count
        }, status=status.HTTP_200_OK)


class RoutineSessionLogViewSet(viewsets.ModelViewSet):
    renderer_classes = [JSONRenderer]
    """ViewSet for creating and querying logs from mobile app and web"""
    queryset = RoutineSessionLog.objects.all().order_by('id')
    serializer_class = RoutineSessionLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Desactivar paginación para obtener todos los logs
        
    http_method_names = ['get', 'post']
    
    def get_queryset(self):
        """Filter logs by routine_session if parameter is provided"""
        queryset = super().get_queryset()
        routine_session = self.request.query_params.get('routine_session', None)
        if routine_session is not None:
            queryset = queryset.filter(routine_session_id=routine_session)
        else:
            # If routine_session is not provided, return empty queryset
            queryset = queryset.none()
        return queryset

    def create(self, request, *args, **kwargs):
        """Create a log with data sent from mobile app"""
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            # ✅ Guardar directamente sin modificar el usuario
            log = serializer.save()
            
            return Response({
                'message': 'Log created successfully',
                'log': self.get_serializer(log).data
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SessionSeriesViewSet(viewsets.ModelViewSet):
    """ViewSet for managing recurring session series"""
    queryset = SessionSeries.objects.all().order_by('-created_at')
    serializer_class = SessionSeriesSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['room', 'routine', 'user', 'active']
    search_fields = ['name']
    ordering_fields = ['created_at', 'start_date', 'end_date']
    
    def get_queryset(self):
        """Filter series based on user permissions"""
        queryset = super().get_queryset()
        params = self.request.query_params
        
        user_permissions = self.request.user.get_all_permissions()
        is_admin = any(perm in user_permissions for perm in [
            "core_data.add_sessionseries", 
            "core_data.delete_sessionseries"
        ])
        
        # If not admin, show only their series
        if not is_admin:
            queryset = queryset.filter(user=self.request.user)
        
        # Additional filters
        room_id = params.get("room_id")
        user_id = params.get("user_id")
        active = params.get("active")
        
        if room_id:
            queryset = queryset.filter(room_id=room_id)
        
        if user_id and is_admin:
            queryset = queryset.filter(user_id=user_id)
        
        if active is not None:
            queryset = queryset.filter(active=active.lower() == 'true')
        
        return queryset
    
    def perform_create(self, serializer):
        """Save who created the series and generate sessions automatically"""
        with transaction.atomic():
            series = serializer.save(created_by=self.request.user)
            # Generate sessions automatically
            self._generate_sessions_for_series(series)
    
    def _generate_sessions_for_series(self, series):
        """
        Generates all individual sessions based on series configuration (weekly)
        - Name and duration are applied to ALL sessions
        - The routine is only applied to the FIRST session
        """
        from datetime import datetime, timedelta
        
        sessions_to_create = []
        current_date = series.start_date
        is_first_session = True
        
        # Convert weekdays from JSON if necessary and ensure they are numbers
        weekdays = series.weekdays if isinstance(series.weekdays, list) else []
        weekday_numbers = []
        for day in weekdays:
            if isinstance(day, int):
                weekday_numbers.append(day)
            elif isinstance(day, str) and day.isdigit():
                weekday_numbers.append(int(day))
        
        weekday_numbers = sorted(set(weekday_numbers))  # Remove duplicates and sort
        
        # Iterate through each day from start_date to end_date
        while current_date <= series.end_date:
            # Check if the weekday is in the list
            if current_date.weekday() in weekday_numbers:
                # Combine date with start time
                scheduled_datetime = datetime.combine(
                    current_date,
                    series.time
                )
                
                sessions_to_create.append(RoutineSession(
                    name=series.name,  
                    room=series.room,
                    routine=series.routine if is_first_session else None,  
                    user=series.user,
                    scheduled_at=scheduled_datetime,
                    duration=series.duration,  
                    session_series=series,
                    created_by=series.created_by
                ))
                
                is_first_session = False  
            
            # Move to next day
            current_date += timedelta(days=1)
        
        # Create all sessions in a single operation
        if sessions_to_create:
            RoutineSession.objects.bulk_create(sessions_to_create)
            
        return len(sessions_to_create)
    
    @action(detail=True, methods=['post'])
    def generate_sessions(self, request, pk=None):
        """
        Endpoint to generate/regenerate all sessions for a series
        POST /api/sessionseries/{id}/generate_sessions/
        """
        series = self.get_object()
        
        # Optional: delete existing sessions before regenerating
        delete_existing = request.data.get('delete_existing', False)
        if delete_existing:
            series.generated_sessions.all().delete()
        
        # Generate sessions
        sessions_created = self._generate_sessions_for_series(series)
        
        return Response({
            'message': f'Successfully generated {sessions_created} sessions',
            'series_id': series.id,
            'sessions_created': sessions_created
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['get'])
    def sessions(self, request, pk=None):
        """
        Endpoint to view all generated sessions for a series
        GET /api/sessionseries/{id}/sessions/
        """
        series = self.get_object()
        sessions = series.generated_sessions.all().order_by('scheduled_at')
        serializer = RoutineSessionSerializer(sessions, many=True)
        
        return Response({
            'series_id': series.id,
            'series_name': series.name,
            'sessions_count': sessions.count(),
            'sessions': serializer.data
        }, status=status.HTTP_200_OK)


class LoginLogViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet para consultar logs de inicio de sesión (solo lectura)."""
    queryset = LoginLog.objects.all()
    serializer_class = LoginLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['user', 'login_type', 'success']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filtrar por rango de fechas si se proporcionan."""
        queryset = super().get_queryset()
        
        # Filtro por usuario específico
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        # Filtro por rango de fechas
        from_date = self.request.query_params.get('from_date')
        to_date = self.request.query_params.get('to_date')
        
        if from_date:
            queryset = queryset.filter(created_at__gte=from_date)
        if to_date:
            queryset = queryset.filter(created_at__lte=to_date)
        
        return queryset
