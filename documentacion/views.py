# documentacion/views.py
import io
import logging
import os
import shutil
import subprocess
import tempfile
import zipfile

from django.http import HttpResponse
from rest_framework import viewsets, generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from instalacion.models import Instalacion
from .models import DocumentoItem, EstadoDocumentacion, DocumentoInstalacion, documento_upload_key
from .serializers import DocumentoItemSerializer, EstadoDocumentacionSerializer, DocumentoInstalacionSerializer, \
    DocumentoInstalacionUploadSerializer
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .services.r2_storage import (
    upload_document,
    upload_file_path,
    download_document_to_path,
    download_document_to_fileobj,
    delete_document,
    generate_signed_url,
)


logger = logging.getLogger(__name__)


def user_can_access_instalacion(user, instalacion: Instalacion) -> bool:
    """
    Ajusta esta lógica a tu modelo real de permisos.
    Por ahora: solo usuarios autenticados.
    (Luego lo amarramos a empresa/instalación/rol como ya tienes en InOut).
    """
    return True


def documento_extension(doc: DocumentoInstalacion) -> str:
    _, ext = os.path.splitext(doc.nombre_original or doc.storage_key or "")
    return ext.lower()


def documento_download_filename(doc: DocumentoInstalacion) -> str:
    ext = documento_extension(doc)
    base = f"{doc.titulo} - {doc.instalacion.nombre}".strip()
    safe = "".join(char for char in base if char not in '\\/:*?"<>|').strip()
    return f"{safe or 'documento'}{ext}"


def sanitize_download_name(value: str, fallback: str = "documento") -> str:
    safe = "".join(char for char in str(value or "") if char not in '\\/:*?"<>|')
    safe = " ".join(safe.split()).strip().strip(".")
    return safe or fallback


def documento_zip_filename(doc: DocumentoInstalacion) -> str:
    if doc.nombre_original:
        raw_name = os.path.basename(doc.nombre_original.replace("\\", "/"))
        base, ext = os.path.splitext(raw_name)
        return f"{sanitize_download_name(base, f'documento_{doc.id}')}{ext.lower()}"

    ext = documento_extension(doc)
    parts = [doc.titulo, doc.categoria, f"documento_{doc.id}"]
    base = " - ".join(part for part in parts if part)
    return f"{sanitize_download_name(base, f'documento_{doc.id}')}{ext}"


def unique_zip_name(filename: str, used_names: set[str]) -> str:
    if filename not in used_names:
        used_names.add(filename)
        return filename

    base, ext = os.path.splitext(filename)
    counter = 2
    while True:
        candidate = f"{base} ({counter}){ext}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        counter += 1


def documento_preview_pdf_filename(doc: DocumentoInstalacion) -> str:
    base = f"{doc.titulo} - {doc.instalacion.nombre}".strip()
    safe = "".join(char for char in base if char not in '\\/:*?"<>|').strip()
    return f"{safe or 'documento'}.pdf"


def documento_es_pdf(doc: DocumentoInstalacion) -> bool:
    values = [
        doc.nombre_original,
        doc.storage_key,
        doc.mime_type,
    ]
    normalized = [str(value).lower() for value in values if value]
    return any(
        value == "application/pdf"
        or value.endswith(".pdf")
        or value.split("?")[0].endswith(".pdf")
        for value in normalized
    )


def documento_es_convertible_a_pdf(doc: DocumentoInstalacion) -> bool:
    office_extensions = {
        ".doc",
        ".docx",
        ".odt",
        ".rtf",
        ".xls",
        ".xlsx",
        ".ods",
        ".ppt",
        ".pptx",
        ".odp",
    }
    office_mime_fragments = (
        "msword",
        "officedocument",
        "opendocument",
        "rtf",
        "ms-excel",
        "ms-powerpoint",
    )
    mime_type = (doc.mime_type or "").lower()
    return documento_extension(doc) in office_extensions or any(
        fragment in mime_type for fragment in office_mime_fragments
    )


def get_office_converter_command():
    return shutil.which("soffice") or shutil.which("libreoffice")

class DocumentoItemViewSet(viewsets.ModelViewSet):
    queryset = DocumentoItem.objects.all()
    serializer_class = DocumentoItemSerializer

class EstadoDocumentacionViewSet(viewsets.ModelViewSet):
    queryset = EstadoDocumentacion.objects.all()
    serializer_class = EstadoDocumentacionSerializer

# NUEVA vista para creación masiva
class EstadoDocumentacionCreateAPIView(generics.CreateAPIView):
    queryset = EstadoDocumentacion.objects.all()
    serializer_class = EstadoDocumentacionSerializer

    def create(self, request, *args, **kwargs):
        many = isinstance(request.data, list)
        serializer = self.get_serializer(data=request.data, many=many)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def documentos_por_instalacion(request, instalacion_id: int):
    instalacion = get_object_or_404(Instalacion, id=instalacion_id)


    if not user_can_access_instalacion(request.user, instalacion):
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "GET":
        qs = DocumentoInstalacion.objects.filter(instalacion=instalacion)
        return Response(DocumentoInstalacionSerializer(qs, many=True).data)

    # POST upload
    serializer = DocumentoInstalacionUploadSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    file = serializer.validated_data["file"]
    titulo = serializer.validated_data["titulo"]
    categoria = serializer.validated_data.get("categoria", "")
    clasificacion = serializer.validated_data.get("clasificacion", "confidencial")
    estado_directiva = serializer.validated_data.get("estado_directiva", "sin_tramitar")

    key = documento_upload_key(instalacion.id, getattr(file, "name", ""))

    # Subir a R2
    upload_document(file=file, key=key)

    doc = DocumentoInstalacion.objects.create(
        instalacion=instalacion,
        titulo=titulo,
        categoria=categoria,
        clasificacion=clasificacion,
        estado_directiva=estado_directiva,
        storage_key=key,
        nombre_original=getattr(file, "name", "") or "",
        mime_type=getattr(file, "content_type", "") or "",
        size=getattr(file, "size", 0) or 0,
        creado_por=request.user,
    )

    return Response(
        {
            "id": doc.id,
            "message": "Documento subido correctamente",
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def documentos_instalacion_zip(request, instalacion_id: int):
    instalacion = get_object_or_404(Instalacion, id=instalacion_id)

    if not user_can_access_instalacion(request.user, instalacion):
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    documentos = list(
        DocumentoInstalacion.objects.filter(instalacion=instalacion).order_by("created_at", "id")
    )
    if not documentos:
        return Response(
            {"detail": "La instalación no tiene documentos para descargar."},
            status=status.HTTP_404_NOT_FOUND,
        )

    zip_buffer = io.BytesIO()
    used_names = set()
    added_count = 0
    failed_count = 0

    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for doc in documentos:
            try:
                file_buffer = io.BytesIO()
                download_document_to_fileobj(doc.storage_key, file_buffer)
                file_buffer.seek(0)
                zip_file.writestr(
                    unique_zip_name(documento_zip_filename(doc), used_names),
                    file_buffer.read(),
                )
                added_count += 1
            except Exception:
                failed_count += 1
                logger.exception(
                    "No se pudo agregar el documento %s de la instalación %s al ZIP.",
                    doc.id,
                    instalacion.id,
                )

    if added_count == 0:
        return Response(
            {
                "detail": "No se pudo descargar ningún archivo de la instalación desde el storage.",
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    zip_buffer.seek(0)
    zip_filename = f"Documentacion_{sanitize_download_name(instalacion.nombre, f'instalacion_{instalacion.id}')}.zip"
    response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{zip_filename}"'
    if failed_count:
        response["X-Skipped-Documents"] = str(failed_count)
    return response


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def reemplazar_documento_instalacion(request, instalacion_id: int, documento_id: int):
    instalacion = get_object_or_404(Instalacion, id=instalacion_id)
    doc = get_object_or_404(
        DocumentoInstalacion,
        id=documento_id,
        instalacion=instalacion,
    )

    if not user_can_access_instalacion(request.user, instalacion):
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    serializer = DocumentoInstalacionUploadSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    file = serializer.validated_data["file"]
    titulo = serializer.validated_data["titulo"]
    categoria = serializer.validated_data.get("categoria", "")
    clasificacion = serializer.validated_data.get("clasificacion", "confidencial")
    old_key = doc.storage_key
    new_key = documento_upload_key(instalacion.id, getattr(file, "name", ""))

    try:
        upload_document(file=file, key=new_key)
    except Exception as exc:
        return Response(
            {
                "detail": "No se pudo subir el nuevo archivo a Cloudflare R2.",
                "error": str(exc),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    doc.titulo = titulo
    doc.categoria = categoria
    doc.clasificacion = clasificacion
    doc.storage_key = new_key
    doc.nombre_original = getattr(file, "name", "") or ""
    doc.mime_type = getattr(file, "content_type", "") or ""
    doc.size = getattr(file, "size", 0) or 0
    doc.creado_por = request.user
    doc.save(
        update_fields=[
            "titulo",
            "categoria",
            "clasificacion",
            "storage_key",
            "nombre_original",
            "mime_type",
            "size",
            "creado_por",
        ]
    )

    delete_warning = None
    if old_key and old_key != new_key:
        try:
            delete_document(old_key)
        except Exception as exc:
            delete_warning = str(exc)

    data = DocumentoInstalacionSerializer(doc).data
    response = {
        **data,
        "message": "Documento reemplazado correctamente",
    }
    if delete_warning:
        response["warning"] = "Documento actualizado, pero no se pudo eliminar el archivo anterior en R2."
        response["delete_error"] = delete_warning

    return Response(response, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def documento_access(request, documento_id: int):
    doc = get_object_or_404(DocumentoInstalacion, id=documento_id)

    if not user_can_access_instalacion(request.user, doc.instalacion):
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    # URL temporal (por defecto 60s). Puedes subirlo a 120s si quieres.
    url = generate_signed_url(
        doc.storage_key,
        expires=60,
        filename=documento_download_filename(doc),
        disposition="attachment",
    )

    return Response({"url": url, "filename": documento_download_filename(doc)})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def documento_preview(request, documento_id: int):
    doc = get_object_or_404(DocumentoInstalacion, id=documento_id)

    if not user_can_access_instalacion(request.user, doc.instalacion):
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    preview_filename = documento_preview_pdf_filename(doc)

    if documento_es_pdf(doc):
        url = generate_signed_url(
            doc.storage_key,
            expires=60,
            filename=preview_filename,
            disposition="inline",
        )
        return Response(
            {
                "url": url,
                "filename": preview_filename,
                "mime_type": "application/pdf",
                "generated": False,
            }
        )

    if not documento_es_convertible_a_pdf(doc):
        return Response(
            {"detail": "Vista previa no disponible para este tipo de archivo"},
            status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )

    converter = get_office_converter_command()
    if not converter:
        return Response(
            {
                "detail": "No se pudo generar la vista previa PDF. LibreOffice/soffice no está instalado en el servidor.",
            },
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )

    ext = documento_extension(doc) or ".docx"
    preview_key = f"documentos/previews/instalacion_{doc.instalacion_id}/documento_{doc.id}.pdf"

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, f"documento{ext}")
            output_dir = os.path.join(tmpdir, "pdf")
            os.makedirs(output_dir, exist_ok=True)

            download_document_to_path(doc.storage_key, input_path)

            subprocess.run(
                [
                    converter,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    output_dir,
                    input_path,
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=90,
            )

            output_path = os.path.join(output_dir, "documento.pdf")
            if not os.path.exists(output_path):
                return Response(
                    {"detail": "No se pudo generar el PDF de vista previa."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            upload_file_path(output_path, preview_key, "application/pdf")
    except subprocess.TimeoutExpired:
        return Response(
            {"detail": "La conversión a PDF excedió el tiempo máximo permitido."},
            status=status.HTTP_504_GATEWAY_TIMEOUT,
        )
    except subprocess.CalledProcessError as exc:
        error = exc.stderr.decode("utf-8", errors="ignore") if exc.stderr else str(exc)
        return Response(
            {
                "detail": "LibreOffice no pudo convertir el documento a PDF.",
                "error": error,
            },
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    except Exception as exc:
        return Response(
            {
                "detail": "No se pudo generar la vista previa PDF.",
                "error": str(exc),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    url = generate_signed_url(
        preview_key,
        expires=60,
        filename=preview_filename,
        disposition="inline",
    )

    return Response(
        {
            "url": url,
            "filename": preview_filename,
            "mime_type": "application/pdf",
            "generated": True,
        }
    )
