import re
import markdown
from django.utils.text import slugify
from django.utils.html import escape
from markdown.extensions.toc import TocExtension
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension
from markdown.extensions.footnotes import FootnoteExtension
from markdown.extensions.attr_list import AttrListExtension
from markdown.extensions.def_list import DefListExtension
from markdown.extensions.abbr import AbbrExtension


def normalize_tags(tag_string):
    """
    Normalize comma-separated tags to lowercase, trimmed, de-duplicated.
    
    Args:
        tag_string: String of comma-separated tags
    
    Returns:
        Normalized string of tags
    """
    if not tag_string:
        return ''
    
    tags = []
    seen = set()
    
    for tag in tag_string.split(','):
        # Clean up the tag
        tag = tag.strip().lower()
        tag = ' '.join(tag.split())  # Normalize whitespace
        tag = re.sub(r'[^\w\s-]', '', tag)  # Remove special characters
        
        # Add to list if valid and not duplicate
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    
    return ', '.join(tags)


def render_markdown(content, safe_mode=True):
    """
    Render markdown content to HTML with extensions.
    
    Args:
        content: Markdown content string
        safe_mode: Whether to escape HTML in the content
    
    Returns:
        Tuple of (rendered_html, table_of_contents)
    """
    if not content:
        return '', []
    
    # Configure extensions
    extensions = [
        'markdown.extensions.extra',
        'markdown.extensions.nl2br',
        CodeHiliteExtension(
            linenums=False,
            css_class='highlight',
            guess_lang=True
        ),
        TocExtension(
            baselevel=2,
            permalink=True,
            permalink_class='headerlink',
            title='Table of Contents'
        ),
        FencedCodeExtension(),
        TableExtension(),
        FootnoteExtension(),
        AttrListExtension(),
        DefListExtension(),
        AbbrExtension(),
    ]
    
    # Create markdown instance
    md = markdown.Markdown(
        extensions=extensions,
        output_format='html5'
    )
    
    # Render content
    html = md.convert(content)
    
    # Get table of contents
    toc = getattr(md, 'toc', '')
    
    # Extract TOC items for sidebar
    toc_items = extract_toc_items(toc) if toc else []
    
    return html, toc_items


def extract_toc_items(toc_html):
    """
    Extract table of contents items from HTML.
    
    Args:
        toc_html: HTML string of table of contents
    
    Returns:
        List of TOC items with title, anchor, and level
    """
    if not toc_html:
        return []
    
    items = []
    # Parse TOC HTML to extract items
    # This is a simplified version - you might want to use BeautifulSoup for more robust parsing
    pattern = r'<a.*?href="#(.*?)".*?>(.*?)</a>'
    matches = re.findall(pattern, toc_html)
    
    for anchor, title in matches:
        # Clean up title (remove permalink symbols, etc.)
        title = re.sub(r'<.*?>', '', title)  # Remove HTML tags
        title = title.replace('¶', '').strip()  # Remove permalink symbol
        
        items.append({
            'anchor': anchor,
            'title': title,
            'url': f'#{anchor}'
        })
    
    return items


def extract_headings(content):
    """
    Extract headings from markdown content.
    
    Args:
        content: Markdown content string
    
    Returns:
        List of headings with level and text
    """
    if not content:
        return []
    
    headings = []
    lines = content.split('\n')
    
    for line in lines:
        # Match markdown headings
        match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if match:
            level = len(match.group(1))
            text = match.group(2).strip()
            headings.append({
                'level': level,
                'text': text,
                'slug': slugify(text)
            })
    
    return headings


def estimate_reading_time(content):
    """
    Estimate reading time for content.
    
    Args:
        content: Text content
    
    Returns:
        Estimated reading time in minutes
    """
    if not content:
        return 1
    
    # Average reading speed: 200-250 words per minute
    words = len(content.split())
    minutes = max(1, words // 200)
    
    return minutes


def generate_summary(content, max_length=500):
    """
    Generate a summary from content.
    
    Args:
        content: Full text content
        max_length: Maximum length of summary
    
    Returns:
        Summary string
    """
    if not content:
        return ''
    
    # Remove markdown formatting
    text = re.sub(r'#+ ', '', content)  # Remove headers
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # Remove bold
    text = re.sub(r'\*(.*?)\*', r'\1', text)  # Remove italic
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # Remove links
    text = re.sub(r'`([^`]+)`', r'\1', text)  # Remove inline code
    text = re.sub(r'```[^`]*```', '', text)  # Remove code blocks
    text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', '', text)  # Remove images
    
    # Clean up whitespace
    text = ' '.join(text.split())
    
    # Truncate to max length
    if len(text) > max_length:
        text = text[:max_length].rsplit(' ', 1)[0] + '...'
    
    return text


def highlight_search_terms(text, search_terms):
    """
    Highlight search terms in text.
    
    Args:
        text: Text to highlight in
        search_terms: List of terms to highlight
    
    Returns:
        HTML with highlighted terms
    """
    if not text or not search_terms:
        return escape(text)
    
    # Escape the text first
    text = escape(text)
    
    # Highlight each term
    for term in search_terms:
        if term:
            # Case-insensitive replacement
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            text = pattern.sub(
                lambda m: f'<mark class="highlight">{m.group()}</mark>',
                text
            )
    
    return text


def parse_search_query(query):
    """
    Parse search query into terms and operators.
    
    Args:
        query: Search query string
    
    Returns:
        Dictionary with parsed query components
    """
    if not query:
        return {'terms': [], 'required': [], 'excluded': []}
    
    terms = []
    required = []
    excluded = []
    
    # Split query into tokens
    tokens = query.split()
    
    for token in tokens:
        if token.startswith('+'):
            # Required term
            required.append(token[1:])
        elif token.startswith('-'):
            # Excluded term
            excluded.append(token[1:])
        else:
            # Regular term
            terms.append(token)
    
    return {
        'terms': terms,
        'required': required,
        'excluded': excluded
    }


def format_file_size(size_in_bytes):
    """
    Format file size in human-readable format.
    
    Args:
        size_in_bytes: File size in bytes
    
    Returns:
        Formatted string
    """
    if not size_in_bytes:
        return '0 B'
    
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    size = float(size_in_bytes)
    unit_index = 0
    
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
    
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.1f} {units[unit_index]}"


def generate_breadcrumbs(article):
    """
    Generate breadcrumb navigation for an article.
    
    Args:
        article: Article instance
    
    Returns:
        List of breadcrumb items
    """
    breadcrumbs = [
        {'name': 'Knowledge Base', 'url': '/kb/'}
    ]
    
    if article.category:
        # Add category hierarchy
        categories = []
        current = article.category
        while current:
            categories.insert(0, current)
            current = current.parent
        
        for cat in categories:
            breadcrumbs.append({
                'name': cat.name,
                'url': f'/kb/category/{cat.slug}/'
            })
    
    # Add article
    breadcrumbs.append({
        'name': article.title,
        'url': None  # Current page
    })
    
    return breadcrumbs


def export_article_to_markdown(article):
    """
    Export article to markdown format with metadata.
    
    Args:
        article: Article instance
    
    Returns:
        Markdown string with front matter
    """
    # Generate front matter
    front_matter = [
        '---',
        f'title: {article.title}',
        f'author: {article.author.get_full_name() or article.author.username}',
        f'date: {article.published_at or article.created_at}',
        f'category: {article.category.name if article.category else "Uncategorized"}',
        f'tags: {article.tags}',
        f'difficulty: {article.get_difficulty_display()}',
        '---',
        ''
    ]
    
    # Combine with content
    return '\n'.join(front_matter) + '\n' + article.content


def import_markdown_to_article(markdown_content, author):
    """
    Import markdown content with front matter to create an article.
    
    Args:
        markdown_content: Markdown string with optional front matter
        author: User instance for the author
    
    Returns:
        Article instance (not saved)
    """
    from .models import Article, Category
    
    # Parse front matter if present
    metadata = {}
    content = markdown_content
    
    if markdown_content.startswith('---'):
        parts = markdown_content.split('---', 2)
        if len(parts) >= 3:
            # Parse YAML-like front matter
            front_matter = parts[1].strip()
            content = parts[2].strip()
            
            for line in front_matter.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    metadata[key.strip()] = value.strip()
    
    # Create article instance
    article = Article(
        title=metadata.get('title', 'Untitled'),
        content=content,
        author=author,
        tags=metadata.get('tags', ''),
        summary=generate_summary(content, 500),
        status='draft'  # Always import as draft
    )
    
    # Set category if specified
    if 'category' in metadata:
        try:
            article.category = Category.objects.get(name=metadata['category'])
        except Category.DoesNotExist:
            pass
    
    # Set difficulty if specified
    difficulty_map = {
        'Beginner': 'beginner',
        'Intermediate': 'intermediate',
        'Advanced': 'advanced'
    }
    if 'difficulty' in metadata:
        article.difficulty = difficulty_map.get(
            metadata['difficulty'], 
            'beginner'
        )
    
    return article