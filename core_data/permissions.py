from rest_framework.permissions import SAFE_METHODS, BasePermission

from .access import user_has_capability


class CapabilityPermission(BasePermission):
    message = "You do not have permission to perform this action."

    def has_permission(self, request, view):
        required = self.required_capability(request, view)
        if not required:
            return True
        return user_has_capability(request.user, required)

    def required_capability(self, request, view):
        action = getattr(view, "action", None)
        capability_by_action = getattr(view, "capability_by_action", {})
        if action and action in capability_by_action:
            return capability_by_action[action]

        capability_by_method = getattr(view, "capability_by_method", {})
        if request.method in capability_by_method:
            return capability_by_method[request.method]

        required = getattr(view, "required_capability", None)
        if required:
            return required

        if request.method not in SAFE_METHODS:
            return getattr(view, "write_capability", None)
        return getattr(view, "read_capability", None)
