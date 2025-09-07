import re
from django.utils.text import slugify


def normalize_tags(tag_string):
    """Normalize comma-separated tags to lowercase, trimmed, de-duplicated."""
    tags = []
    seen = set()
    for tag in (tag_string or '').split(','):
        tag = tag.strip().lower()
        tag = ' '.join(tag.split())  # Normalize whitespace
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return ', '.join(tags)


def extract_images_from_markdown(content):
    """Extract image URLs from markdown content."""
    pattern = r'!\[.*?\]\((.*?)\)'
    return re.findall(pattern, content)


def generate_table_of_contents(content):
    """Generate a table of contents from markdown headers."""
    lines = content.split('\n')
    toc = []
    for line in lines:
        if line.startswith('#'):
            level = len(line.split()[0])
            title = line.lstrip('#').strip()
            slug = slugify(title)
            toc.append({
                'level': level,
                'title': title,
                'slug': slug
            })
    return toc