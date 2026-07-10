import os
import uuid

from django.conf import settings
from django.db import transaction
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from documentacion.services.r2_storage import delete_document, upload_document
from reportes.services.report_file_extraction import extract_text_from_report_file, validate_report_file

from .models import Amonestacion, DocumentoLaboral
from .serializers import AmonestacionSerializer, DocumentoLaboralSerializer
from .services.openai_service import AmonestacionGenerationError, generar_carta


class DocumentoLaboralViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DocumentoLaboralSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        return DocumentoLaboral.objects.filter(activo=True)

    @action(detail=False, methods=["post"], url_path="cargar")
    def cargar(self, request):
        archivo = request.FILES.get("archivo")
        tipo = request.data.get("tipo")
        if tipo not in dict(DocumentoLaboral.TIPOS):
            return Response({"tipo": "Tipo de documento inválido."}, status=status.HTTP_400_BAD_REQUEST)
        if not archivo:
            return Response({"archivo": "Debes adjuntar un archivo."}, status=status.HTTP_400_BAD_REQUEST)

        validate_report_file(archivo, getattr(settings, "AMONESTACIONES_DOCUMENT_MAX_SIZE", 20 * 1024 * 1024))
        texto = extract_text_from_report_file(archivo)
        if not texto.strip():
            return Response(
                {"archivo": "No fue posible extraer texto. El PDF puede ser una imagen escaneada."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        extension = os.path.splitext(archivo.name)[1].lower()[:10]
        key = f"documentos/amonestaciones/{tipo}/{uuid.uuid4().hex}{extension}"
        archivo.seek(0)
        upload_document(archivo, key)
        try:
            with transaction.atomic():
                anteriores = DocumentoLaboral.objects.select_for_update().filter(tipo=tipo, activo=True)
                anteriores.update(activo=False)
                documento = DocumentoLaboral.objects.create(
                    tipo=tipo, nombre_original=archivo.name, mime_type=archivo.content_type or "",
                    size=archivo.size, storage_key=key, texto_extraido=texto, creado_por=request.user,
                )
        except Exception:
            delete_document(key)
            raise

        return Response(self.get_serializer(documento).data, status=status.HTTP_201_CREATED)


class AmonestacionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Amonestacion.objects.select_related("persona", "instalacion")
    serializer_class = AmonestacionSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        contrato = DocumentoLaboral.objects.filter(tipo=DocumentoLaboral.CONTRATO, activo=True).first()
        riohs = DocumentoLaboral.objects.filter(tipo=DocumentoLaboral.RIOHS, activo=True).first()
        faltantes = []
        if not contrato:
            faltantes.append("Contrato de Trabajo")
        if not riohs:
            faltantes.append("Reglamento Interno")
        if faltantes:
            return Response(
                {"detail": f"Debes cargar antes: {', '.join(faltantes)}."}, status=status.HTTP_400_BAD_REQUEST
            )

        amonestacion = Amonestacion(
            **serializer.validated_data, contrato=contrato, riohs=riohs, creado_por=request.user
        )
        try:
            amonestacion.carta = generar_carta(amonestacion, contrato.texto_extraido, riohs.texto_extraido)
        except AmonestacionGenerationError as exc:
            return Response(
                {"detail": f"No fue posible generar la carta: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        amonestacion.save()
        return Response(self.get_serializer(amonestacion).data, status=status.HTTP_201_CREATED)
