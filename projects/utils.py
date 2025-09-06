from django.db.models import Max
from django.utils.text import slugify

SLUG_MAX_TRIES = 50
POSITION_STEP = 100

DEFAULT_TASK_COLUMNS = [
    ("To Do", 0),
    ("In Progress", 100),
    ("Review", 200),
    ("Done", 300),
]

DEFAULT_ROADMAP_COLUMNS = [
    ("Ideas", 0),
    ("Needs Review", 100),
    ("Approved", 200),
    ("Rejected", 300),
]


def unique_slugify(instance, base_value, slug_field_name: str = "slug") -> str:
    """
    Generate a unique slug for `instance` based on `base_value`, capped at SLUG_MAX_TRIES.
    """
    base_slug = slugify(base_value)[:50] or "project"
    Model = instance.__class__
    slug_field = slug_field_name
    slug = base_slug
    n = 2
    while Model.objects.filter(**{slug_field: slug}).exclude(pk=instance.pk).exists() and n <= SLUG_MAX_TRIES:
        slug = f"{base_slug}-{n}"
        n += 1
    return slug


def next_position_for_column(task_queryset) -> int:
    """
    Given a queryset of tasks (already filtered to the column and optionally select_for_update()),
    return the next sparse position.
    """
    max_pos = task_queryset.aggregate(maxp=Max("position"))["maxp"]
    return (max_pos or 0) + POSITION_STEP
