from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user')
router.register(r'objectives', views.ObjectiveViewSet, basename='objective')
router.register(r'positions', views.PositionViewSet, basename='position')
router.register(r'props', views.PropViewSet, basename='prop')
router.register(r'machines', views.MachineViewSet, basename='machine')
router.register(r'exercises', views.ExerciseViewSet, basename='exercise')
router.register(r'springs', views.SpringViewSet, basename='springs')
router.register(r'routines', views.RoutineViewSet, basename='routine')
router.register(r'routinesessions', views.RoutineSessionViewSet, basename='routinesession')
router.register(r'general-routine-assignments', views.GeneralRoutineAssignmentViewSet, basename='general-routine-assignment')
router.register(r'daily-routine-assignments', views.DailyRoutineAssignmentViewSet, basename='daily-routine-assignment')
router.register(r'sessionseries', views.SessionSeriesViewSet, basename='sessionseries')
router.register(r'routine-session-logs', views.RoutineSessionLogViewSet, basename='routine-session-log')
router.register(r'login-logs', views.LoginLogViewSet, basename='login-log')

urlpatterns = [
    path("", include(router.urls)),  # This will automatically include all the viewset urls.
    path('login', views.login_view, name='login-usuarios'),
    path('validate-token', views.validate_token_view, name='validate-token'),
    path('logout', views.logout_view, name='logout-usuarios'),
    path('logout-log/', views.logout_log_view, name='logout-log'),
    path("delete-image/", views.delete_image, name="delete-image"),
    path("all_positions/", views.all_positions, name="all_positions"),
    path("all_props/", views.all_props, name="all_props"),
    path("all_machines/", views.all_machines, name="all_machines"),
    path("all_springs/", views.all_springs, name="all_springs"),    
    path("all_tags/", views.all_tags, name="all_tags"),
    path("all_routines/", views.all_routines, name="all_routines"),
    path("routines_basic/", views.routines_basic, name="routines_basic"),
    path("routines_info/", views.routines_info, name="routines_info"),
    path("exercises_basic/", views.exercises_basic, name="exercises_basic"),
    path("all_users/", views.all_users, name="all_users"),
    path("all_centers_and_rooms/", views.all_centers_and_rooms, name="all_centers_and_rooms"),
    path("routines/<int:pk>/remove_exercise/", views.RoutineViewSet.as_view({'post': 'remove_exercise'}), name="remove-exercise"),   
    path("groups/", views.list_groups, name="list-groups"), 
    path('routines_reorder_exercises/', views.reorder_routine_exercises, name='reorder_routine_exercises'),
]
