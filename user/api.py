from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_info(request):
    user = request.user
    return Response({
        'id': user.id,
        'username': user.username,
        'nombres': user.nombres,
        'apellidos': user.apellidos,
        'rut': user.rut,
        'email': user.email,
        'cargo': user.cargo.nombre if user.cargo else None,
    })
