from django.db import models


class LocalSettings(models.Model):
    ai_base_url = models.URLField(blank=True)
    ai_api_key = models.CharField(max_length=512, blank=True)
    text_model = models.CharField(max_length=128, blank=True)
    vision_model = models.CharField(max_length=128, blank=True)
    obsidian_vault_path = models.CharField(max_length=1024, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls):
        settings, _created = cls.objects.get_or_create(pk=1)
        return settings


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


class Paper(models.Model):
    STATUS_RECOMMENDED = "recommended"
    STATUS_SAVED = "saved"
    STATUS_PARSED = "parsed"
    STATUS_ANALYZED = "analyzed"
    STATUS_EXPORTED = "exported"

    title = models.CharField(max_length=512)
    translated_title = models.TextField(blank=True)
    authors = models.JSONField(default=list, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    abstract = models.TextField(blank=True)
    translated_abstract = models.TextField(blank=True)
    arxiv_id = models.CharField(max_length=64, blank=True, unique=True)
    doi = models.CharField(max_length=128, blank=True)
    source = models.CharField(max_length=64, default="arXiv")
    source_url = models.URLField(blank=True)
    pdf_url = models.URLField(blank=True)
    published_date = models.CharField(max_length=32, blank=True)
    version = models.CharField(max_length=32, blank=True)
    local_pdf_path = models.CharField(max_length=1024, blank=True)
    parsed_text = models.TextField(blank=True)
    topic = models.ForeignKey(ResearchTopic, null=True, blank=True, on_delete=models.SET_NULL, related_name="papers")
    status = models.CharField(max_length=32, default=STATUS_SAVED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class PaperInsight(models.Model):
    paper = models.OneToOneField(Paper, on_delete=models.CASCADE, related_name="insight")
    research_direction = models.TextField(blank=True)
    task_definition = models.TextField(blank=True)
    input_data = models.TextField(blank=True)
    output_result = models.TextField(blank=True)
    network_overview = models.TextField(blank=True)
    module_list = models.TextField(blank=True)
    information_flow = models.TextField(blank=True)
    loss_functions = models.TextField(blank=True)
    training_process = models.TextField(blank=True)
    inference_process = models.TextField(blank=True)
    innovation_points = models.TextField(blank=True)
    limitations = models.TextField(blank=True)
    reproduction_questions = models.TextField(blank=True)
    idea_hints = models.TextField(blank=True)
    keywords = models.JSONField(default=list, blank=True)
    markdown_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class PaperNote(models.Model):
    paper = models.OneToOneField(Paper, on_delete=models.CASCADE, related_name="note")
    content = models.TextField(blank=True)
    source = models.CharField(max_length=64, default="paperqa")
    target_relative_path = models.CharField(max_length=1024, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class PaperFigure(models.Model):
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="figures")
    page_number = models.PositiveIntegerField(default=1)
    figure_index = models.PositiveIntegerField(default=1)
    image_path = models.CharField(max_length=1024)
    caption = models.TextField(blank=True)
    context_text = models.TextField(blank=True)
    figure_type = models.CharField(max_length=64, default="ordinary")
    is_key_figure = models.BooleanField(default=False)
    ai_description = models.TextField(blank=True)


class DailyRecommendation(models.Model):
    topic = models.ForeignKey(ResearchTopic, on_delete=models.CASCADE, related_name="recommendations")
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="recommendations")
    recommend_date = models.DateField()
    score = models.PositiveIntegerField(default=0)
    reason = models.TextField(blank=True)
    idea_hint = models.TextField(blank=True)
    exported_to_obsidian = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["topic", "paper", "recommend_date"], name="unique_daily_recommendation")
        ]
