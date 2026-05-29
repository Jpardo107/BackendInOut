from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import QueryDict
from django.test import SimpleTestCase

from .views import _image_text_values, _validate_images


class ReportesImageValidationTests(SimpleTestCase):
    def test_validate_images_allows_more_than_eight_files(self):
        files = [
            SimpleUploadedFile(
                f"foto_{index}.jpg",
                b"image-bytes",
                content_type="image/jpeg",
            )
            for index in range(9)
        ]

        _validate_images(files)


class ReportesImageTextValuesTests(SimpleTestCase):
    def test_reads_repeated_formdata_values(self):
        data = QueryDict("", mutable=True)
        data.update({"descripciones": "foto uno"})
        data.appendlist("descripciones", "foto dos")

        values = _image_text_values(data, ("descripciones", "descripcionFoto"), 2)

        self.assertEqual(values, ["foto uno", "foto dos"])

    def test_reads_json_array_formdata_value(self):
        data = QueryDict("", mutable=True)
        data.appendlist("recomendacionesFoto", '["rec uno", "rec dos"]')

        values = _image_text_values(data, ("recomendacionesFoto", "recomendacionFoto"), 2)

        self.assertEqual(values, ["rec uno", "rec dos"])

    def test_reads_indexed_values(self):
        data = QueryDict("", mutable=True)
        data.update({"descripcionFoto[0]": "foto uno", "descripcionFoto[1]": "foto dos"})

        values = _image_text_values(data, ("descripciones", "descripcionFoto"), 2)

        self.assertEqual(values, ["foto uno", "foto dos"])
