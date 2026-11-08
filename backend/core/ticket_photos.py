import io
import warnings
from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import PermissionDenied, ValidationError
from .access import org
from .models import Ticket, TicketPhoto
from .ticket_flow import can_finish_ticket

def save_photo(user, ticket, upload):
    if not can_finish_ticket(user, ticket):
        raise PermissionDenied('Добавлять фотографии может только исполнитель заявки в работе.')
    if not upload or upload.size > 10 * 1024 * 1024:
        raise ValidationError('Выберите изображение до 10 МБ.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            img = Image.open(upload)
            if img.format not in ('JPEG', 'PNG', 'WEBP') or img.width * img.height > 32000000:
                raise ValueError()
            img.load()
            img = ImageOps.exif_transpose(img).convert('RGB')
            img.thumbnail((2560, 2560))
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=88)
    except (UnidentifiedImageError, OSError, ValueError,
            Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise ValidationError('Не удалось прочитать JPEG, PNG или WebP до 32 Мп.')
    photo = None
    try:
        with transaction.atomic():
            locked = Ticket.objects.select_for_update().get(pk=ticket.pk)
            if not can_finish_ticket(user, locked):
                raise PermissionDenied('Заявка уже закрыта или переназначена.')
            if locked.photos.filter(deleted_at__isnull=True).count() >= 8:
                raise ValidationError('В заявке допускается до 8 фотографий.')
            photo = TicketPhoto(organization=org(user), ticket=locked, uploaded_by=user)
            photo.file.save('repair.jpg', ContentFile(buf.getvalue()), save=False)
            photo.save()
            from .ticket_flow import add_event
            add_event(locked, user, 'photo_added',
                      before=locked.status, after=locked.status)
    except Exception:
        if photo and photo.file.name:
            photo.file.delete(save=False)
        raise
    return photo
