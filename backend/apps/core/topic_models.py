from django.db import models


class ResearchTopic(models.Model):
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    keywords = models.JSONField(default=list, blank=True)
    arxiv_categories = models.JSONField(default=list, blank=True)
    daily_limit = models.PositiveIntegerField(default=3)
    obsidian_folder = models.CharField(max_length=512, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
