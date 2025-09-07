# kb/management/commands/setup_kb.py
from django.core.management.base import BaseCommand
from django.db import transaction
from kb.models import Category


class Command(BaseCommand):
    help = 'Setup initial KB categories and structure'
    
    def handle(self, *args, **options):
        with transaction.atomic():
            categories = [
                ('Getting Started', 'getting-started', 'Initial setup and configuration guides', 10),
                ('Development', 'development', 'Development guidelines and best practices', 20),
                ('Deployment', 'deployment', 'Deployment procedures and server configuration', 30),
                ('Troubleshooting', 'troubleshooting', 'Common issues and their solutions', 40),
                ('API Documentation', 'api-docs', 'API endpoints and integration guides', 50),
                ('Project Guides', 'project-guides', 'Project-specific documentation', 60),
                ('Tools & Resources', 'tools', 'Development tools and external resources', 70),
            ]
            
            created_count = 0
            for name, slug, description, position in categories:
                category, created = Category.objects.get_or_create(
                    slug=slug,
                    defaults={
                        'name': name,
                        'description': description,
                        'position': position
                    }
                )
                if created:
                    created_count += 1
                    self.stdout.write(f"Created category: {name}")
                else:
                    self.stdout.write(f"Category exists: {name}")
            
            self.stdout.write(
                self.style.SUCCESS(f'Successfully created {created_count} categories')
            )