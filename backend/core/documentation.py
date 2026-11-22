"""Exact tag matching for technical documentation in an organization."""
from unicodedata import normalize

from rest_framework.exceptions import ValidationError


def tags(value):
    return frozenset(
        tag for part in value.split(',')
        if (tag := ' '.join(normalize('NFKC', part).casefold().split()))
    )


def normalize_tags(value):
    values = tags(value)
    if len(values) > 12 or any(len(tag) > 50 for tag in values):
        raise ValidationError('Укажите до 12 тегов по 50 символов через запятую.')
    return ', '.join(sorted(values))


def matches_elevator(document, elevator):
    required = tags(document.documentation_tags)
    if required:
        return required.issubset(tags(elevator.documentation_tags))
    return bool(document.manufacturer and
                document.manufacturer.casefold() == elevator.manufacturer.casefold() and
                (not document.model or document.model.casefold() == elevator.model.casefold()))
