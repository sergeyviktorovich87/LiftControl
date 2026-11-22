import re

from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler, StopUpload
from django.http import JsonResponse
from rest_framework.exceptions import ParseError
from rest_framework.parsers import MultiPartParser

MAX_FILE_MB = 100
MAX_FILE_BYTES = MAX_FILE_MB * 1024**2
MAX_MULTIPART_FILES = 5


def limit_non_multipart_api_body(get_response):
    def middleware(request):
        if request.path_info.startswith('/api/') and request.content_type != 'multipart/form-data':
            try:
                length = int(request.META.get('CONTENT_LENGTH') or 0)
            except (TypeError, ValueError):
                return JsonResponse({'detail': 'Некорректный размер запроса.'}, status=400)
            if length > settings.DATA_UPLOAD_MAX_MEMORY_SIZE:
                return JsonResponse({'detail': 'Данные запроса слишком большие.'}, status=413)
        return get_response(request)
    return middleware


class BoundedUploadHandler(FileUploadHandler):
    """Stop oversize files before Django finishes writing them to temporary disk."""

    def handle_raw_input(self, input_data, META, content_length, boundary, encoding=None):
        self.files = 0
        path = self.request.path.rstrip('/')
        multiple = path in ('/api/chat', '/api/commissioning/chat') or re.fullmatch(
            r'/api/commissioning/\d+/(?:messages|lifts/\d+/progress)', path)
        self.max_files = MAX_MULTIPART_FILES if multiple else 1
        self.too_large = bool(content_length and
                              content_length > self.max_files * MAX_FILE_BYTES + 1024**2)

    def reject(self):
        self.request.upload_error = (
            f'Допускается до {self.max_files} вложений размером до {MAX_FILE_MB} МБ каждое.'
        )
        raise StopUpload(connection_reset=True)

    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.files += 1
        if self.too_large or self.files > self.max_files:
            self.reject()

    def receive_data_chunk(self, raw_data, start):
        if start + len(raw_data) > MAX_FILE_BYTES:
            self.reject()
        return raw_data

    def file_complete(self, file_size):
        return None


class BoundedMultiPartParser(MultiPartParser):
    def parse(self, stream, media_type=None, parser_context=None):
        result = super().parse(stream, media_type, parser_context)
        error = getattr(parser_context['request'], 'upload_error', None)
        if error:
            # Django closes the interrupted file but already completed parts
            # belong to this failed request and must also be closed.
            for _, files in result.files.lists():
                for file in files:
                    file.close()
            raise ParseError(error)
        return result
