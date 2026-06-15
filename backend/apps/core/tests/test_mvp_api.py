import json
import urllib.error
from datetime import date

import pytest
from django.urls import reverse

from apps.core.urls import arxiv_api_url, build_arxiv_search_query, enrich_paper_metadata, paper_within_recent_years, parse_arxiv_atom, rank_papers, translate_search_results_with_ai, weighted_random_candidates


def test_parse_arxiv_atom_extracts_paper_metadata():
    body = b"""
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2605.10789v1</id>
        <published>2026-05-20T00:00:00Z</published>
        <title>Rapid Forest Fuel Load Estimation via Virtual Remote Sensing</title>
        <summary>Accurate quantification for remote sensing classification.</summary>
        <author><name>Jane Doe</name></author>
        <author><name>Alan Smith</name></author>
        <link title="pdf" href="https://arxiv.org/pdf/2605.10789v1" />
      </entry>
    </feed>
    """

    papers = parse_arxiv_atom(body)

    assert papers[0] == {
        "title": "Rapid Forest Fuel Load Estimation via Virtual Remote Sensing",
        "authors": ["Jane Doe", "Alan Smith"],
        "year": 2026,
        "abstract": "Accurate quantification for remote sensing classification.",
        "arxiv_id": "2605.10789v1",
        "source": "arXiv",
        "source_url": "https://arxiv.org/abs/2605.10789v1",
        "pdf_url": "https://arxiv.org/pdf/2605.10789v1",
        "google_scholar_url": "https://scholar.google.com/scholar?q=Rapid%20Forest%20Fuel%20Load%20Estimation%20via%20Virtual%20Remote%20Sensing",
        "published_date": "2026-05-20",
        "version": "v1",
        "match_score": 0,
        "matched_terms": [],
        "tags": ["图像分类"],
    }


def test_rank_papers_prioritizes_query_and_topic_keyword_matches():
    papers = [
        {
            "title": "Quantum Optical Neuron for Image Classification",
            "abstract": "A generic image classification method.",
            "authors": [],
            "year": 2026,
            "arxiv_id": "1",
            "source": "arXiv",
            "source_url": "",
            "pdf_url": "",
        },
        {
            "title": "Mamba Backbone for Remote Sensing Image Fusion",
            "abstract": "A state space model for multimodal hyperspectral and SAR image fusion.",
            "authors": [],
            "year": 2026,
            "arxiv_id": "2",
            "source": "arXiv",
            "source_url": "",
            "pdf_url": "",
        },
    ]

    ranked = rank_papers(papers, "remote sensing image fusion", ["hyperspectral", "SAR"])

    assert ranked[0]["arxiv_id"] == "2"
    assert ranked[0]["match_score"] > ranked[1]["match_score"]


def test_enrich_paper_metadata_adds_model_and_task_tags():
    paper = {
        "title": "Mamba Backbone for Multimodal Hyperspectral Image Fusion",
        "abstract": "We propose a state space model for SAR optical fusion and hyperspectral classification.",
        "authors": [],
        "year": 2026,
        "arxiv_id": "2",
        "source": "arXiv",
        "source_url": "",
        "pdf_url": "",
    }

    enriched = enrich_paper_metadata(paper, "remote sensing", ["hyperspectral"])

    assert "Mamba" in enriched["tags"]
    assert "图像融合" in enriched["tags"]
    assert "高光谱分类" in enriched["tags"]
    assert enriched["match_score"] > 0


def test_build_arxiv_search_query_formats_semicolon_terms_as_required_keywords():
    query = build_arxiv_search_query("HSI；classify", ["cs.CV", "CVPR"])

    assert query == "((all:HSI) AND (all:classify)) AND cat:cs.CV"


def test_build_arxiv_search_query_handles_empty_query():
    assert build_arxiv_search_query("") == "all:*"


def test_arxiv_api_url_uses_export_atom_endpoint():
    url = arxiv_api_url("all:electron", 10)

    assert url == "http://export.arxiv.org/api/query?search_query=all%3Aelectron&start=0&max_results=10&sortBy=submittedDate&sortOrder=descending"


@pytest.mark.django_db
def test_search_result_translation_accepts_fenced_ai_json(client, monkeypatch):
    client.patch(
        reverse("local-settings"),
        data={"ai_base_url": "https://relay.example/v1", "ai_api_key": "secret-key", "text_model": "text-model"},
        content_type="application/json",
    )

    seen = {}

    class FakeMessage:
        content = """```json
        {"results":[{"arxiv_id":"2601.1","translated_title":"高光谱图像分类","translated_abstract":"本文提出一种高光谱图像分类方法，提升了复杂场景表现。"}]}
        ```"""

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            seen["payload"] = kwargs
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            seen["client"] = kwargs
            self.chat = FakeChat()

    monkeypatch.setattr("apps.core.urls.OpenAI", FakeOpenAI)

    papers = translate_search_results_with_ai([
        {"arxiv_id": "2601.1", "title": "HSI Classification", "abstract": "A hyperspectral image classification method."}
    ])

    assert papers[0]["translated_title"] == "高光谱图像分类"
    assert papers[0]["translated_abstract"] == "本文提出一种高光谱图像分类方法，提升了复杂场景表现。"
    assert seen["client"]["base_url"] == "https://relay.example/v1"
    assert seen["payload"]["reasoning_effort"] == "high"
    assert seen["payload"]["extra_body"] == {"thinking": {"type": "enabled"}}
    assert "不要总结" in seen["payload"]["messages"][0]["content"]


@pytest.mark.django_db
def test_local_settings_can_be_saved_and_fetched(client):
    response = client.patch(
        reverse("local-settings"),
        data={
            "ai_base_url": "https://relay.example/v1",
            "ai_api_key": "secret-key",
            "text_model": "claude-sonnet-4-6",
            "vision_model": "claude-opus-4-7",
            "obsidian_vault_path": "/tmp/LitRadarVault",
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json() == {
        "ai_base_url": "https://relay.example/v1",
        "has_ai_api_key": True,
        "text_model": "claude-sonnet-4-6",
        "vision_model": "claude-opus-4-7",
        "obsidian_vault_path": "/tmp/LitRadarVault",
    }

    fetch_response = client.get(reverse("local-settings"))

    assert fetch_response.status_code == 200
    assert fetch_response.json()["has_ai_api_key"] is True
    assert "ai_api_key" not in fetch_response.json()


@pytest.mark.django_db
def test_topic_crud_api(client):
    create_response = client.post(
        reverse("topics-list"),
        data={
            "name": "遥感变化检测",
            "description": "Remote sensing change detection papers",
            "keywords": ["remote sensing change detection", "SAR change detection"],
            "arxiv_categories": ["cs.CV", "eess.IV"],
            "daily_limit": 3,
            "obsidian_folder": "LitRadar/遥感变化检测",
            "enabled": True,
        },
        content_type="application/json",
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "遥感变化检测"
    assert created["keywords"] == ["remote sensing change detection", "SAR change detection"]
    assert created["daily_limit"] == 3

    list_response = client.get(reverse("topics-list"))

    assert list_response.status_code == 200
    assert list_response.json()[0]["name"] == "遥感变化检测"

    patch_response = client.patch(
        reverse("topics-detail", args=[created["id"]]),
        data={"daily_limit": 2, "enabled": False},
        content_type="application/json",
    )

    assert patch_response.status_code == 200
    assert patch_response.json()["daily_limit"] == 2
    assert patch_response.json()["enabled"] is False


@pytest.mark.django_db
def test_paper_search_returns_error_payload_when_arxiv_rate_limits(client, monkeypatch):
    def fake_search(_query, categories=None, max_results=10):
        raise urllib.error.HTTPError("https://export.arxiv.org/api/query", 429, "Too Many Requests", {}, None)

    monkeypatch.setattr("apps.core.urls.search_arxiv", fake_search)

    response = client.get(reverse("papers-search"), {"query": "remote sensing classify"})

    assert response.status_code == 503
    assert response.json() == {"error": "arXiv API 返回 429，请稍后再试或调整关键词。"}


@pytest.mark.django_db
def test_paper_search_returns_clear_error_for_non_arxiv_query(client):
    response = client.get(reverse("papers-search"), {"query": "遥感变化检测"})

    assert response.status_code == 400
    assert response.json() == {"error": "arXiv 只支持英文或 arXiv 可解析的检索词，请输入英文关键词。"}


@pytest.mark.django_db
def test_paper_save_and_detail_api(client):
    topic_response = client.post(
        reverse("topics-list"),
        data={"name": "Foundation Models", "keywords": ["remote sensing foundation model"]},
        content_type="application/json",
    )
    topic_id = topic_response.json()["id"]

    response = client.post(
        reverse("papers-list"),
        data={
            "title": "A Remote Sensing Foundation Model",
            "authors": ["Ada Lovelace", "Grace Hopper"],
            "year": 2026,
            "abstract": "A model for multimodal remote sensing.",
            "arxiv_id": "2601.00001",
            "source": "arXiv",
            "source_url": "https://arxiv.org/abs/2601.00001",
            "pdf_url": "https://arxiv.org/pdf/2601.00001",
            "topic": topic_id,
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    paper = response.json()
    assert paper["title"] == "A Remote Sensing Foundation Model"
    assert paper["authors"] == ["Ada Lovelace", "Grace Hopper"]
    assert paper["topic"] == topic_id

    detail_response = client.get(reverse("papers-detail", args=[paper["id"]]))

    assert detail_response.status_code == 200
    assert detail_response.json()["arxiv_id"] == "2601.00001"


@pytest.mark.django_db
def test_radar_run_uses_keyword_fallback_without_ai(client, monkeypatch):
    topic_response = client.post(
        reverse("topics-list"),
        data={
            "name": "变化检测",
            "keywords": ["change detection"],
            "daily_limit": 1,
            "enabled": True,
        },
        content_type="application/json",
    )
    topic_id = topic_response.json()["id"]

    def fake_search(query, categories=None, max_results=10):
        return [
            {
                "title": "Change Detection with Transformers",
                "authors": ["Researcher A"],
                "year": 2026,
                "abstract": "Transformer based change detection for remote sensing.",
                "arxiv_id": "2601.00002",
                "source": "arXiv",
                "source_url": "https://arxiv.org/abs/2601.00002",
                "pdf_url": "https://arxiv.org/pdf/2601.00002",
            }
        ]

    monkeypatch.setattr("apps.core.urls.search_arxiv", fake_search)

    response = client.post(reverse("radar-run", args=[topic_id]))

    assert response.status_code == 200
    payload = response.json()
    assert payload["topic"]["name"] == "变化检测"
    assert len(payload["recommendations"]) == 1
    assert payload["recommendations"][0]["score"] > 0
    assert "来源：arXiv" in payload["recommendations"][0]["reason"]


@pytest.mark.django_db
def test_radar_run_uses_and_query_before_keyword_backfill(client, monkeypatch):
    topic_response = client.post(
        reverse("topics-list"),
        data={"name": "HSI", "keywords": ["HSI OR classify"], "daily_limit": 2, "enabled": True},
        content_type="application/json",
    )
    topic_id = topic_response.json()["id"]
    seen_queries = []

    def fake_search(query, categories=None, max_results=10):
        seen_queries.append(query)
        return [
            {
                "title": f"{query} Paper",
                "authors": ["Researcher A"],
                "year": 2026,
                "abstract": f"A paper about {query}.",
                "arxiv_id": f"2601.{len(seen_queries)}",
                "source": "arXiv",
                "source_url": "",
                "pdf_url": "",
            }
        ]

    monkeypatch.setattr("apps.core.urls.search_arxiv", fake_search)

    response = client.post(reverse("radar-run", args=[topic_id]), data={"limit": 2}, content_type="application/json")

    assert response.status_code == 200
    assert "HSI OR classify" not in seen_queries
    assert "OR" not in seen_queries
    assert "HSI;classify" in seen_queries
    assert {"HSI", "classify"}.issubset(set(seen_queries))


@pytest.mark.django_db
def test_radar_run_returns_error_payload_when_arxiv_rate_limits(client, monkeypatch):
    topic_response = client.post(
        reverse("topics-list"),
        data={"name": "变化检测", "keywords": ["change detection"], "daily_limit": 1, "enabled": True},
        content_type="application/json",
    )
    topic_id = topic_response.json()["id"]

    def fake_search(_query, categories=None, max_results=10):
        raise urllib.error.HTTPError("https://export.arxiv.org/api/query", 429, "Too Many Requests", {}, None)

    monkeypatch.setattr("apps.core.urls.search_arxiv", fake_search)

    response = client.post(reverse("radar-run", args=[topic_id]))

    assert response.status_code == 503
    assert response.json() == {"error": "arXiv API 返回 429，请稍后再试或调整关键词。"}


@pytest.mark.django_db
def test_paper_markdown_preview_contains_structured_sections(client, tmp_path):
    client.patch(
        reverse("local-settings"),
        data={"obsidian_vault_path": str(tmp_path)},
        content_type="application/json",
    )
    topic_response = client.post(
        reverse("topics-list"),
        data={"name": "遥感变化检测", "keywords": ["change detection"]},
        content_type="application/json",
    )
    topic_id = topic_response.json()["id"]
    paper_response = client.post(
        reverse("papers-list"),
        data={
            "title": "Change Detection with Transformers",
            "authors": ["Researcher A"],
            "year": 2026,
            "abstract": "Transformer based change detection.",
            "arxiv_id": "2601.00002",
            "topic": topic_id,
        },
        content_type="application/json",
    )
    paper_id = paper_response.json()["id"]

    analyze_response = client.post(reverse("paper-analyze-structure", args=[paper_id]))

    assert analyze_response.status_code == 200

    markdown_response = client.get(reverse("paper-obsidian-markdown", args=[paper_id]))

    assert markdown_response.status_code == 200
    payload = markdown_response.json()
    assert payload["target_relative_path"].endswith("Papers/Change-Detection-with-Transformers.md")
    assert "# Change Detection with Transformers" in payload["markdown"]
    assert "## 输入与输出" not in payload["markdown"]
    assert "## 整体网络框架" not in payload["markdown"]
    assert "## 信息流向" not in payload["markdown"]
    assert "## 创新点" in payload["markdown"]
    assert (tmp_path / payload["target_relative_path"]).exists()
    assert (tmp_path / "LitRadar/遥感变化检测/Graph/Change-Detection-with-Transformers-知识图谱.md").exists()


@pytest.mark.django_db
def test_paper_note_generation_persists_and_exports_to_obsidian(client, tmp_path, monkeypatch):
    client.patch(
        reverse("local-settings"),
        data={"ai_base_url": "https://api.deepseek.com", "ai_api_key": "secret-key", "text_model": "deepseek-v4-pro", "obsidian_vault_path": str(tmp_path)},
        content_type="application/json",
    )
    paper_response = client.post(
        reverse("papers-list"),
        data={
            "title": "PaperQA Note Paper",
            "authors": ["Researcher A"],
            "year": 2026,
            "abstract": "A paper for deep note generation.",
            "arxiv_id": "2601.99001",
            "pdf_url": "https://arxiv.org/pdf/2601.99001",
        },
        content_type="application/json",
    )
    paper_id = paper_response.json()["id"]
    monkeypatch.setattr("apps.core.urls.local_pdf_for_note", lambda paper: tmp_path / "paper.pdf")
    monkeypatch.setattr("apps.core.urls.generate_note_with_paperqa", lambda settings, paper, pdf_path, topic_name: "## 深度讲解\n带引文的论文笔记。")

    response = client.post(reverse("paper-note", args=[paper_id]), data={"force": True}, content_type="application/json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "paperqa"
    assert "深度讲解" in payload["content"]
    exported = tmp_path / payload["target_relative_path"]
    assert exported.exists()
    assert "带引文的论文笔记" in exported.read_text()


@pytest.mark.django_db
def test_paper_note_generation_can_use_paperqa_env_file(client, tmp_path, monkeypatch):
    env_path = tmp_path / ".env.paperqa"
    env_path.write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=env-key",
                "DEEPSEEK_API_BASE=https://api.deepseek.com",
                "DEEPSEEK_MODEL=deepseek-v4-pro",
                "PAPERQA_LLM=openai/deepseek-v4-pro",
                "PAPERQA_SUMMARY_LLM=openai/deepseek-v4-pro",
            ]
        )
    )
    monkeypatch.setattr("apps.core.urls.django_settings.BASE_DIR", tmp_path)
    paper_response = client.post(
        reverse("papers-list"),
        data={"title": "Env Note Paper", "authors": [], "year": 2026, "abstract": "Env based note.", "arxiv_id": "2601.99002"},
        content_type="application/json",
    )
    paper_id = paper_response.json()["id"]
    monkeypatch.setattr("apps.core.urls.local_pdf_for_note", lambda paper: tmp_path / "paper.pdf")

    seen = {}

    def fake_generate(settings, paper, pdf_path, topic_name):
        from apps.core.urls import effective_ai_base, effective_ai_key

        seen["key"] = effective_ai_key(settings)
        seen["base"] = effective_ai_base(settings)
        return "env note"

    monkeypatch.setattr("apps.core.urls.generate_note_with_paperqa", fake_generate)

    response = client.post(reverse("paper-note", args=[paper_id]), data={"force": True}, content_type="application/json")

    assert response.status_code == 200
    assert seen == {"key": "env-key", "base": "https://api.deepseek.com"}
    assert response.json()["content"] == "env note"


@pytest.mark.django_db
def test_pdf_association_parse_and_key_figure_update(client, tmp_path):
    paper_response = client.post(
        reverse("papers-list"),
        data={
            "title": "Architecture Paper",
            "authors": ["Researcher A"],
            "year": 2026,
            "abstract": "A paper with a framework figure.",
            "arxiv_id": "2601.00003",
        },
        content_type="application/json",
    )
    paper_id = paper_response.json()["id"]
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"not a real pdf")

    pdf_response = client.post(
        reverse("paper-pdf", args=[paper_id]),
        data={"local_pdf_path": str(pdf_path)},
        content_type="application/json",
    )

    assert pdf_response.status_code == 200
    assert pdf_response.json()["local_pdf_path"] == str(pdf_path)

    parse_response = client.post(reverse("paper-parse", args=[paper_id]))

    assert parse_response.status_code == 200
    figure = parse_response.json()["figures"][0]
    assert figure["caption"] == "待从 PDF 解析中提取 caption"
    assert figure["figure_type"] == "architecture"

    patch_response = client.patch(
        reverse("paper-figure-detail", args=[paper_id, figure["id"]]),
        data={"is_key_figure": True, "ai_description": "关键框架图"},
        content_type="application/json",
    )

    assert patch_response.status_code == 200
    assert patch_response.json()["is_key_figure"] is True
    assert patch_response.json()["ai_description"] == "关键框架图"


@pytest.mark.django_db
def test_topic_can_be_updated_and_deleted(client):
    create_response = client.post(
        reverse("topics-list"),
        data={"name": "待编辑方向", "keywords": ["change detection"], "daily_limit": 5},
        content_type="application/json",
    )
    topic_id = create_response.json()["id"]

    patch_response = client.patch(
        reverse("topics-detail", args=[topic_id]),
        data={"name": "当前方向", "keywords": ["remote sensing"]},
        content_type="application/json",
    )

    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "当前方向"
    assert patch_response.json()["keywords"] == ["remote sensing"]

    delete_response = client.delete(reverse("topics-detail", args=[topic_id]))

    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}
    assert client.get(reverse("topics-detail", args=[topic_id])).status_code == 404


@pytest.mark.django_db
def test_paper_can_be_updated_and_deleted(client):
    paper_response = client.post(
        reverse("papers-list"),
        data={
            "title": "Original Paper Title",
            "authors": ["Researcher A"],
            "year": 2026,
            "abstract": "A paper abstract.",
            "arxiv_id": "2601.99999",
            "source": "arXiv",
            "source_url": "https://arxiv.org/abs/2601.99999",
            "pdf_url": "https://arxiv.org/pdf/2601.99999",
        },
        content_type="application/json",
    )
    paper_id = paper_response.json()["id"]

    patch_response = client.patch(
        reverse("papers-detail", args=[paper_id]),
        data={"title": "Edited Paper Title", "status": "analyzed"},
        content_type="application/json",
    )

    assert patch_response.status_code == 200
    assert patch_response.json()["title"] == "Edited Paper Title"
    assert patch_response.json()["status"] == "analyzed"

    delete_response = client.delete(reverse("papers-detail", args=[paper_id]))

    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}
    assert client.get(reverse("papers-detail", args=[paper_id])).status_code == 404


@pytest.mark.django_db
def test_radar_run_uses_request_limit_instead_of_topic_daily_limit(client, monkeypatch):
    topic_response = client.post(
        reverse("topics-list"),
        data={"name": "变化检测", "keywords": ["change detection"], "daily_limit": 3, "enabled": True},
        content_type="application/json",
    )
    topic_id = topic_response.json()["id"]

    def fake_search(query, categories=None, max_results=10):
        return [
            {
                "title": f"Change Detection Paper {index}",
                "authors": ["Researcher A"],
                "year": 2026,
                "abstract": "Transformer based change detection for remote sensing.",
                "arxiv_id": f"2601.1000{index}",
                "source": "arXiv",
                "source_url": f"https://arxiv.org/abs/2601.1000{index}",
                "pdf_url": f"https://arxiv.org/pdf/2601.1000{index}",
            }
            for index in range(3)
        ]

    monkeypatch.setattr("apps.core.urls.search_arxiv", fake_search)

    response = client.post(
        reverse("radar-run", args=[topic_id]),
        data={"limit": 1},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert len(response.json()["recommendations"]) == 1


def test_enrich_paper_metadata_scores_and_reports_matched_terms():
    paper = {
        "title": "Mamba Network for Hyperspectral Image Fusion",
        "abstract": "A remote sensing method accepted at CVPR for SAR optical fusion.",
        "authors": [],
        "year": 2026,
        "arxiv_id": "2601.12345",
        "source": "arXiv",
        "source_url": "",
        "pdf_url": "",
    }

    enriched = enrich_paper_metadata(paper, "remote sensing image fusion", ["hyperspectral", "CVPR"])

    assert enriched["match_score"] > 0
    assert "hyperspectral" in enriched["matched_terms"]
    assert "CVPR" in enriched["matched_terms"]


def test_weighted_random_candidates_only_randomizes_high_score_pool():
    candidates = [
        {"arxiv_id": f"high-{index}", "match_score": 80 - index, "published_date": "2026-06-10"}
        for index in range(6)
    ] + [
        {"arxiv_id": f"low-{index}", "match_score": 12, "published_date": "2026-06-10"}
        for index in range(6)
    ]

    selected = weighted_random_candidates(candidates, 3)

    assert len(selected) == 3
    assert all(item["match_score"] >= 65 for item in selected)


def test_paper_within_recent_years_filters_old_radar_candidates():
    assert paper_within_recent_years({"published_date": "2025-01-01"}, today=date(2026, 6, 14))
    assert paper_within_recent_years({"year": 2024}, today=date(2026, 6, 14))
    assert not paper_within_recent_years({"published_date": "2023-12-31"}, today=date(2026, 6, 14))
    assert not paper_within_recent_years({"year": 2023}, today=date(2026, 6, 14))


@pytest.mark.django_db
def test_radar_run_replaces_today_recommendations_and_requires_score_above_60(client, monkeypatch):
    topic_response = client.post(
        reverse("topics-list"),
        data={"name": "视觉方向", "keywords": ["hyperspectral fusion", "CVPR"], "daily_limit": 3, "enabled": True},
        content_type="application/json",
    )
    topic_id = topic_response.json()["id"]
    calls = {"count": 0}

    def fake_search(query, categories=None, max_results=10):
        calls["count"] += 1
        suffix = calls["count"]
        return [
            {
                "title": f"Hyperspectral Fusion CVPR Paper {suffix}-{index}",
                "authors": ["Researcher A"],
                "year": 2026,
                "abstract": "remote sensing hyperspectral fusion with CVPR experiments",
                "arxiv_id": f"2601.200{suffix}{index}",
                "source": "arXiv",
                "source_url": f"https://arxiv.org/abs/2601.200{suffix}{index}",
                "pdf_url": f"https://arxiv.org/pdf/2601.200{suffix}{index}",
            }
            for index in range(5)
        ] + [
            {
                "title": "Unrelated Paper",
                "authors": [],
                "year": 2026,
                "abstract": "quantum chemistry",
                "arxiv_id": f"2601.low{suffix}",
                "source": "arXiv",
                "source_url": "",
                "pdf_url": "",
            }
        ]

    monkeypatch.setattr("apps.core.urls.search_arxiv", fake_search)

    first = client.post(reverse("radar-run", args=[topic_id]), data={"limit": 3}, content_type="application/json").json()
    second = client.post(reverse("radar-run", args=[topic_id]), data={"limit": 3}, content_type="application/json").json()

    assert len(first["recommendations"]) == 3
    assert len(second["recommendations"]) == 3
    assert {item["paper"]["arxiv_id"] for item in first["recommendations"]} != {item["paper"]["arxiv_id"] for item in second["recommendations"]}
    assert all(item["score"] > 0 for item in second["recommendations"])


@pytest.mark.django_db
def test_paper_search_scores_venue_names_without_using_them_as_arxiv_categories(client, monkeypatch):
    topic_response = client.post(
        reverse("topics-list"),
        data={"name": "视觉方向", "keywords": ["hyperspectral fusion"], "arxiv_categories": ["CVPR", "ICLR"]},
        content_type="application/json",
    )
    topic_id = topic_response.json()["id"]
    seen = {}

    def fake_search(query, categories=None, max_results=10):
        seen["query"] = query
        seen["categories"] = categories
        return [
            {
                "title": "Hyperspectral Fusion Paper",
                "authors": ["Researcher A"],
                "year": 2026,
                "abstract": "Remote sensing fusion accepted at CVPR.",
                "arxiv_id": "2601.30001",
                "source": "arXiv",
                "source_url": "https://arxiv.org/abs/2601.30001",
                "pdf_url": "https://arxiv.org/pdf/2601.30001",
            }
        ]

    monkeypatch.setattr("apps.core.urls.search_arxiv", fake_search)

    response = client.get(reverse("papers-search"), {"query": "hyperspectral fusion", "topic_id": topic_id})

    assert response.status_code == 200
    assert seen["categories"] == []
    result = response.json()[0]
    assert "CVPR" in result["matched_terms"]
    assert result["match_score"] > 0


@pytest.mark.django_db
def test_radar_run_scores_venue_names_without_using_them_as_arxiv_categories(client, monkeypatch):
    topic_response = client.post(
        reverse("topics-list"),
        data={"name": "视觉方向", "keywords": ["hyperspectral fusion"], "arxiv_categories": ["CVPR"], "daily_limit": 3, "enabled": True},
        content_type="application/json",
    )
    topic_id = topic_response.json()["id"]
    seen = {}

    def fake_search(query, categories=None, max_results=10):
        seen["categories"] = categories
        return [
            {
                "title": "Hyperspectral Fusion CVPR Paper",
                "authors": ["Researcher A"],
                "year": 2026,
                "abstract": "Remote sensing hyperspectral fusion with CVPR experiments.",
                "arxiv_id": "2601.30002",
                "source": "arXiv",
                "source_url": "https://arxiv.org/abs/2601.30002",
                "pdf_url": "https://arxiv.org/pdf/2601.30002",
            }
        ]

    monkeypatch.setattr("apps.core.urls.search_arxiv", fake_search)

    response = client.post(reverse("radar-run", args=[topic_id]), data={"limit": 1}, content_type="application/json")

    assert response.status_code == 200
    assert seen["categories"] == []
    recommendation = response.json()["recommendations"][0]
    assert recommendation["score"] > 0
    assert "来源：arXiv" in recommendation["reason"]


@pytest.mark.django_db
def test_enrich_paper_metadata_returns_clean_model_task_and_venue_year_tags():
    paper = {
        "title": "Mamba Network for Hyperspectral Image Fusion",
        "abstract": "A remote sensing method accepted at CVPR for SAR optical fusion.",
        "authors": [],
        "year": 2026,
        "arxiv_id": "2601.40001",
        "source": "arXiv",
        "source_url": "",
        "pdf_url": "",
    }

    enriched = enrich_paper_metadata(paper, "remote sensing image fusion", ["hyperspectral", "CVPR"])

    assert "Mamba" in enriched["tags"]
    assert "图像融合" in enriched["tags"]
    assert "CVPR2026" in enriched["tags"]
    assert all("backbone:" not in tag and "task:" not in tag for tag in enriched["tags"])


@pytest.mark.django_db
def test_radar_run_backfills_with_best_candidates_when_score_threshold_is_too_strict(client, monkeypatch):
    topic_response = client.post(
        reverse("topics-list"),
        data={"name": "视觉方向", "keywords": ["hyperspectral fusion"], "arxiv_categories": ["CVPR"], "daily_limit": 3, "enabled": True},
        content_type="application/json",
    )
    topic_id = topic_response.json()["id"]
    seen = {}

    def fake_search(query, categories=None, max_results=10):
        seen["max_results"] = max_results
        return [
            {
                "title": f"Hyperspectral Candidate {index}",
                "authors": ["Researcher A"],
                "year": 2026,
                "abstract": "A candidate for fusion.",
                "arxiv_id": f"2601.4100{index}",
                "source": "arXiv",
                "source_url": f"https://arxiv.org/abs/2601.4100{index}",
                "pdf_url": f"https://arxiv.org/pdf/2601.4100{index}",
            }
            for index in range(3)
        ]

    monkeypatch.setattr("apps.core.urls.search_arxiv", fake_search)

    response = client.post(reverse("radar-run", args=[topic_id]), data={"limit": 3}, content_type="application/json")

    assert response.status_code == 200
    assert seen["max_results"] >= 20
    payload = response.json()
    assert len(payload["recommendations"]) == 3
    assert all("来源：arXiv" in item["reason"] for item in payload["recommendations"])


@pytest.mark.django_db
def test_paper_analyze_structure_uses_configured_ai_relay(client, monkeypatch):
    settings_response = client.patch(
        reverse("local-settings"),
        data={"ai_base_url": "https://relay.example/v1", "ai_api_key": "secret-key", "text_model": "claude-sonnet-4-6"},
        content_type="application/json",
    )
    assert settings_response.status_code == 200
    paper_response = client.post(
        reverse("papers-list"),
        data={
            "title": "AI Analysis Paper",
            "authors": ["Researcher A"],
            "year": 2026,
            "abstract": "A method with a Mamba encoder for hyperspectral fusion.",
            "arxiv_id": "2601.42001",
        },
        content_type="application/json",
    )
    paper_id = paper_response.json()["id"]
    seen = {}

    class FakeMessage:
        content = json.dumps(
            {
                "translated_title": "AI 分析论文",
                "translated_abstract": "本文提出一种用于高光谱融合的 Mamba 编码方法。",
                "research_direction": "遥感高光谱融合",
                "task_definition": "这篇文章要解决高光谱与辅助模态结合的多源分类问题，缓解传统方法跨模态信息融合不足的痛点，并通过状态空间建模提升长程依赖表达。",
                "input_data": "高光谱与遥感影像。",
                "output_result": "融合后的分类结果。",
                "network_overview": "Mamba encoder with fusion head.",
                "module_list": "| 模块 | 作用 |\n|---|---|\n| Mamba | 编码 |",
                "information_flow": "输入经过编码器后融合。",
                "loss_functions": "交叉熵。",
                "training_process": "监督训练。",
                "inference_process": "单次前向推理。",
                "innovation_points": ["Mamba 编码器用于跨模态特征建模", "融合头统一高光谱与遥感影像表征"],
                "limitations": "需要更多数据验证。",
                "reproduction_questions": "数据集划分是什么？",
                "idea_hints": ["结合当前遥感高光谱方向，可以尝试把 Mamba 编码器迁移到多源分类。"],
                "keywords": ["Mamba", "hyperspectral"],
            }
        )

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            seen["payload"] = kwargs
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            seen["client"] = kwargs
            self.chat = FakeChat()

    monkeypatch.setattr("apps.core.urls.OpenAI", FakeOpenAI)

    response = client.post(reverse("paper-analyze-structure", args=[paper_id]))

    assert response.status_code == 200
    assert seen["client"]["api_key"] == "secret-key"
    assert seen["client"]["base_url"] == "https://relay.example/v1"
    assert seen["payload"]["model"] == "claude-sonnet-4-6"
    assert seen["payload"]["reasoning_effort"] == "high"
    assert seen["payload"]["stream"] is False
    assert seen["payload"]["extra_body"] == {"thinking": {"type": "enabled"}}
    assert "研究动机" in seen["payload"]["messages"][0]["content"]
    assert "不要总结、扩写或评价" in seen["payload"]["messages"][0]["content"]
    payload = response.json()
    assert payload["research_direction"] == "遥感高光谱融合"
    assert payload["task_definition"] == "这篇文章要解决高光谱与辅助模态结合的多源分类问题，缓解传统方法跨模态信息融合不足的痛点，并通过状态空间建模提升长程依赖表达。"
    assert payload["innovation_points"] == "Mamba 编码器用于跨模态特征建模\n融合头统一高光谱与遥感影像表征"
    assert payload["idea_hints"] == "结合当前遥感高光谱方向，可以尝试把 Mamba 编码器迁移到多源分类。"
    saved_paper = client.get(reverse("papers-detail", args=[paper_id])).json()
    assert saved_paper["translated_title"] == "AI 分析论文"
    assert saved_paper["translated_abstract"] == "本文提出一种用于高光谱融合的 Mamba 编码方法。"
    assert "input_data" not in payload
    assert "output_result" not in payload
    assert "network_overview" not in payload
    assert "information_flow" not in payload


@pytest.mark.django_db
def test_paper_analyze_structure_uses_configured_sdk_base_url(client, monkeypatch):
    client.patch(
        reverse("local-settings"),
        data={"ai_base_url": "https://relay.example", "ai_api_key": "secret-key", "text_model": "claude-sonnet-4-6"},
        content_type="application/json",
    )
    paper_response = client.post(
        reverse("papers-list"),
        data={
            "title": "AI Relay URL Paper",
            "authors": ["Researcher A"],
            "year": 2026,
            "abstract": "A method with a Mamba encoder for hyperspectral fusion.",
            "arxiv_id": "2601.44001",
        },
        content_type="application/json",
    )
    paper_id = paper_response.json()["id"]
    seen = {}

    class FakeMessage:
        content = json.dumps({"research_direction": "AI relay", "task_definition": "这篇文章解决多源分类中的跨模态融合不足问题。", "innovation_points": ["Real AI result."], "idea_hints": ["贴近当前方向继续验证该创新点。"]})

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            seen["payload"] = kwargs
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            seen["client"] = kwargs
            self.chat = FakeChat()

    monkeypatch.setattr("apps.core.urls.OpenAI", FakeOpenAI)

    response = client.post(reverse("paper-analyze-structure", args=[paper_id]))

    assert response.status_code == 200
    assert seen["client"]["base_url"] == "https://relay.example"
    assert seen["client"]["timeout"] == 180
    assert seen["payload"]["extra_body"] == {"thinking": {"type": "enabled"}}
    assert response.json()["innovation_points"] == "Real AI result."


@pytest.mark.django_db
def test_paper_analyze_structure_falls_back_when_ai_relay_returns_non_json(client, monkeypatch):
    client.patch(
        reverse("local-settings"),
        data={"ai_base_url": "https://relay.example/v1", "ai_api_key": "secret-key", "text_model": "claude-sonnet-4-6"},
        content_type="application/json",
    )
    paper_response = client.post(
        reverse("papers-list"),
        data={
            "title": "Fallback Analysis Paper",
            "authors": ["Researcher A"],
            "year": 2026,
            "abstract": "A fallback abstract.",
            "arxiv_id": "2601.43001",
        },
        content_type="application/json",
    )
    paper_id = paper_response.json()["id"]

    class FakeMessage:
        content = "not json"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **_kwargs):
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = FakeChat()

    monkeypatch.setattr("apps.core.urls.OpenAI", FakeOpenAI)

    response = client.post(reverse("paper-analyze-structure", args=[paper_id]))

    assert response.status_code == 200
    assert response.json()["research_direction"] == "未分类方向"
