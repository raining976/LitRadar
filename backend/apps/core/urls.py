import asyncio
import json
import logging
import os
import random
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from django.conf import settings as django_settings
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from openai import OpenAI

from .models import DailyRecommendation, LocalSettings, Paper, PaperFigure, PaperInsight, PaperNote, ResearchTopic
from .views import health_view

logger = logging.getLogger(__name__)


def parse_json(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return {}


def topic_payload(topic):
    return {
        "id": topic.id,
        "name": topic.name,
        "description": topic.description,
        "keywords": topic.keywords,
        "arxiv_categories": topic.arxiv_categories,
        "daily_limit": topic.daily_limit,
        "obsidian_folder": topic.obsidian_folder,
        "enabled": topic.enabled,
    }


def format_note_list(value):
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value if item) or "待分析。"
    return value or "待分析。"


def insight_payload(insight):
    return {
        "research_direction": insight.research_direction,
        "task_definition": insight.task_definition,
        "module_list": insight.module_list,
        "loss_functions": insight.loss_functions,
        "training_process": insight.training_process,
        "inference_process": insight.inference_process,
        "innovation_points": insight.innovation_points,
        "limitations": insight.limitations,
        "reproduction_questions": insight.reproduction_questions,
        "idea_hints": insight.idea_hints,
        "keywords": insight.keywords,
        "markdown_note": insight.markdown_note,
    }


def note_payload(note):
    return {
        "content": note.content,
        "source": note.source,
        "target_relative_path": note.target_relative_path,
        "updated_at": note.updated_at.isoformat() if note.updated_at else "",
    }


def paper_payload(paper):
    payload = {
        "id": paper.id,
        "title": paper.title,
        "translated_title": paper.translated_title,
        "authors": paper.authors,
        "year": paper.year,
        "abstract": paper.abstract,
        "translated_abstract": paper.translated_abstract,
        "arxiv_id": paper.arxiv_id,
        "doi": paper.doi,
        "source": paper.source,
        "source_url": paper.source_url,
        "pdf_url": paper.pdf_url,
        "google_scholar_url": google_scholar_url(paper.title),
        "published_date": paper.published_date,
        "version": paper.version,
        "local_pdf_path": paper.local_pdf_path,
        "topic": paper.topic_id,
        "status": paper.status,
        "figures": [figure_payload(figure) for figure in paper.figures.all()],
        "insight": None,
        "note": None,
    }
    if hasattr(paper, "insight"):
        payload["insight"] = insight_payload(paper.insight)
    if hasattr(paper, "note"):
        payload["note"] = note_payload(paper.note)
    return payload


def figure_payload(figure):
    return {
        "id": figure.id,
        "paper": figure.paper_id,
        "page_number": figure.page_number,
        "figure_index": figure.figure_index,
        "image_path": figure.image_path,
        "caption": figure.caption,
        "context_text": figure.context_text,
        "figure_type": figure.figure_type,
        "is_key_figure": figure.is_key_figure,
        "ai_description": figure.ai_description,
    }


def recommendation_payload(recommendation):
    return {
        "id": recommendation.id,
        "topic": topic_payload(recommendation.topic),
        "paper": paper_payload(recommendation.paper),
        "recommend_date": recommendation.recommend_date.isoformat(),
        "score": recommendation.score,
        "reason": recommendation.reason,
        "idea_hint": recommendation.idea_hint,
        "exported_to_obsidian": recommendation.exported_to_obsidian,
    }


def settings_payload(settings):
    return {
        "ai_base_url": settings.ai_base_url,
        "has_ai_api_key": bool(settings.ai_api_key),
        "text_model": settings.text_model,
        "vision_model": settings.vision_model,
        "obsidian_vault_path": settings.obsidian_vault_path,
    }


@csrf_exempt
def local_settings_view(request):
    settings = LocalSettings.current()
    if request.method == "GET":
        return JsonResponse(settings_payload(settings))
    if request.method == "PATCH":
        data = parse_json(request)
        for field in ["ai_base_url", "ai_api_key", "text_model", "vision_model", "obsidian_vault_path"]:
            if field in data:
                setattr(settings, field, data[field])
        settings.save()
        return JsonResponse(settings_payload(settings))
    return JsonResponse({"error": "Method not allowed"}, status=405)


@csrf_exempt
def topics_list_view(request):
    if request.method == "GET":
        return JsonResponse([topic_payload(topic) for topic in ResearchTopic.objects.order_by("name")], safe=False)
    if request.method == "POST":
        data = parse_json(request)
        topic = ResearchTopic.objects.create(
            name=data["name"],
            description=data.get("description", ""),
            keywords=data.get("keywords", []),
            arxiv_categories=data.get("arxiv_categories", []),
            daily_limit=data.get("daily_limit", 3),
            obsidian_folder=data.get("obsidian_folder", ""),
            enabled=data.get("enabled", True),
        )
        return JsonResponse(topic_payload(topic), status=201)
    return JsonResponse({"error": "Method not allowed"}, status=405)


@csrf_exempt
def topics_detail_view(request, topic_id):
    topic = get_object_or_404(ResearchTopic, pk=topic_id)
    if request.method == "GET":
        return JsonResponse(topic_payload(topic))
    if request.method == "PATCH":
        data = parse_json(request)
        for field in ["name", "description", "keywords", "arxiv_categories", "daily_limit", "obsidian_folder", "enabled"]:
            if field in data:
                setattr(topic, field, data[field])
        topic.save()
        return JsonResponse(topic_payload(topic))
    if request.method == "DELETE":
        topic.delete()
        return JsonResponse({"deleted": True})
    return JsonResponse({"error": "Method not allowed"}, status=405)


MODEL_TAGS = [
    ("mamba", "Mamba"),
    ("transformer", "Transformer"),
    ("diffusion", "Diffusion"),
    ("cnn", "CNN"),
    ("state space", "State Space Model"),
]

TASK_TAGS = [
    (["image fusion", "fusion", "sar optical", "多模态融合"], "图像融合"),
    (["hyperspectral", "高光谱"], "高光谱分类"),
    (["change detection", "变化检测"], "变化检测"),
    (["classification", "classify", "分类"], "图像分类"),
    (["segmentation", "分割"], "语义分割"),
    (["detection", "目标检测"], "目标检测"),
]

VENUE_TAGS = ["CVPR", "ICCV", "ECCV", "NeurIPS", "ICML", "ICLR", "AAAI", "IJCAI", "TPAMI", "ACM MM", "TNNLS", "Pattern Recognition"]


def google_scholar_url(title):
    return "https://scholar.google.com/scholar?q=" + urllib.parse.quote(title or "")


def tokenize(text):
    return [token for token in re.split(r"[^\w一-鿿]+", text.lower()) if len(token) > 1]


def similarity_ratio(left, right):
    left = left.lower().strip()
    right = right.lower().strip()
    if not left or not right:
        return 0
    if left in right or right in left:
        return 100
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[right_index] + 1,
                    current[right_index - 1] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    distance = previous[-1]
    return int((1 - distance / max(len(left), len(right))) * 100)


def best_fuzzy_ratio(term, text):
    normalized_text = " ".join(tokenize(text))
    normalized_term = " ".join(tokenize(term))
    if not normalized_text or not normalized_term:
        return 0
    if normalized_term in normalized_text:
        return 100
    text_tokens = normalized_text.split()
    term_tokens = normalized_term.split()
    window_size = max(1, len(term_tokens))
    ratios = [similarity_ratio(normalized_term, " ".join(text_tokens[index : index + window_size])) for index in range(len(text_tokens))]
    if window_size > 1:
        ratios.extend(
            similarity_ratio(normalized_term, " ".join(text_tokens[index : index + window_size + 1]))
            for index in range(len(text_tokens))
        )
    return max(ratios or [0])


def split_search_terms(query):
    terms = []
    for item in re.split(r"\s+(?:OR|or)\s+|[;；\n]+", query or ""):
        cleaned = re.sub(r"\s+", " ", item).strip()
        if cleaned and cleaned.lower() not in [term.lower() for term in terms]:
            terms.append(cleaned)
    return terms


def has_partial_keyword_match(term, text):
    text_tokens = tokenize(text)
    for token in tokenize(term):
        prefix = token[:5] if len(token) >= 5 else token
        if any(token == candidate or (len(prefix) >= 5 and (candidate.startswith(prefix) or token.startswith(candidate[:5]))) for candidate in text_tokens):
            return True
    return False


def score_text_matches(title, abstract, terms):
    score = 0
    matched_terms = []
    deduped_terms = split_search_terms(";".join(terms or []))
    normalized_title = " ".join(tokenize(title))
    normalized_abstract = " ".join(tokenize(abstract))
    for item in deduped_terms:
        normalized_item = " ".join(tokenize(item))
        if not normalized_item:
            continue
        term_matched = False
        if normalized_item in normalized_title:
            score += 20
            term_matched = True
        elif has_partial_keyword_match(item, title):
            score += 10
            term_matched = True
        if normalized_item in normalized_abstract or has_partial_keyword_match(item, abstract):
            score += 5
            term_matched = True
        if term_matched:
            matched_terms.append(item)
    deduped_matches = []
    for term in matched_terms:
        if term and term not in deduped_matches:
            deduped_matches.append(term)
    return min(score, 100), deduped_matches


def fuzzy_match_score(text, terms):
    score, _matches = score_text_matches(text, "", terms)
    return score


def infer_paper_tags(paper):
    text = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
    tags = []
    for needle, label in MODEL_TAGS:
        if needle in text and label not in tags:
            tags.append(label)
    for needles, label in TASK_TAGS:
        if any(needle in text for needle in needles) and label not in tags:
            tags.append(label)
    year = paper.get("year")
    if year:
        for venue in VENUE_TAGS:
            if venue.lower() in text:
                tags.append(f"{venue.replace(' ', '')}{year}")
                break
    return tags[:5]


def enrich_paper_metadata(paper, query="", keywords=None):
    enriched = dict(paper)
    terms = [*split_search_terms(query), *(keywords or [])]
    score, matched_terms = score_text_matches(paper.get("title", ""), paper.get("abstract", ""), terms)
    enriched["match_score"] = score
    enriched["matched_terms"] = matched_terms
    enriched["tags"] = infer_paper_tags(paper)
    enriched["google_scholar_url"] = google_scholar_url(paper.get("title", ""))
    return enriched


def paper_defaults(data, topic, status):
    return {
        "title": data["title"],
        "translated_title": data.get("translated_title", ""),
        "authors": data.get("authors", []),
        "year": data.get("year"),
        "abstract": data.get("abstract", ""),
        "translated_abstract": data.get("translated_abstract", ""),
        "arxiv_id": data.get("arxiv_id", ""),
        "doi": data.get("doi", ""),
        "source": data.get("source", "arXiv"),
        "source_url": data.get("source_url", ""),
        "pdf_url": data.get("pdf_url", ""),
        "published_date": data.get("published_date", ""),
        "version": data.get("version", ""),
        "local_pdf_path": data.get("local_pdf_path", ""),
        "topic": topic,
        "status": status,
    }


def rank_papers(papers, query="", keywords=None):
    enriched = [enrich_paper_metadata(paper, query, keywords) for paper in papers]
    return sorted(enriched, key=lambda paper: paper["match_score"], reverse=True)


def parse_arxiv_atom(body):
    root = ET.fromstring(body)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    results = []
    for entry in root.findall("atom:entry", ns):
        arxiv_id = entry.findtext("atom:id", default="", namespaces=ns).rstrip("/").split("/")[-1]
        pdf_url = ""
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("title") == "pdf":
                pdf_url = link.attrib.get("href", "")
        published = entry.findtext("atom:published", default="", namespaces=ns)
        version_match = re.search(r"(v\d+)$", arxiv_id)
        results.append(
            enrich_paper_metadata(
                {
                    "title": re.sub(r"\s+", " ", entry.findtext("atom:title", default="", namespaces=ns)).strip(),
                    "authors": [author.findtext("atom:name", default="", namespaces=ns) for author in entry.findall("atom:author", ns)],
                    "year": int(published[:4]) if published[:4].isdigit() else None,
                    "abstract": re.sub(r"\s+", " ", entry.findtext("atom:summary", default="", namespaces=ns)).strip(),
                    "arxiv_id": arxiv_id,
                    "source": "arXiv",
                    "source_url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
                    "pdf_url": pdf_url,
                    "published_date": published[:10] if published else "",
                    "version": version_match.group(1) if version_match else "",
                }
            )
        )
    return results


def normalize_arxiv_terms(query):
    terms = []
    for item in re.split(r"\s+(?:OR|or)\s+|[;；\n]+", query or ""):
        cleaned = re.sub(r"\s+", " ", item).strip()
        if cleaned and cleaned.lower() not in [term.lower() for term in terms]:
            terms.append(cleaned)
    return terms


def normalize_arxiv_token(token):
    return re.sub(r"[^A-Za-z0-9_.:-]+", "", token)


def format_arxiv_all_terms(term):
    tokens = [normalize_arxiv_token(token) for token in re.split(r"\s+", term.strip())]
    tokens = [token for token in tokens if token]
    return " AND ".join(f"all:{token}" for token in tokens)


def build_arxiv_search_query(query, categories=None):
    query_terms = normalize_arxiv_terms(query)
    parts = []
    formatted_terms = [format_arxiv_all_terms(term) for term in query_terms]
    formatted_terms = [term for term in formatted_terms if term]
    if formatted_terms:
        parts.append("(" + " AND ".join(f"({term})" for term in formatted_terms) + ")")
    for category in categories or []:
        if re.fullmatch(r"[a-z-]+(?:\.[A-Z]{2})?", category):
            parts.append(f"cat:{category}")
    return " AND ".join(parts) if parts else "all:*"


def arxiv_api_url(search_query, max_results):
    return "http://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": search_query, "start": 0, "max_results": max_results, "sortBy": "submittedDate", "sortOrder": "descending"}
    )


def search_arxiv_atom(query, categories=None, max_results=10):
    search_query = build_arxiv_search_query(query, categories)
    if search_query == "all:*" and (query or "").strip():
        raise ValueError("arXiv 只支持英文或 arXiv 可解析的检索词，请输入英文关键词。")
    url = arxiv_api_url(search_query, max_results)
    request = urllib.request.Request(url, headers={"User-Agent": "LitRadar/0.1 local literature tool"})
    # macOS framework Python can miss system CA roots; arXiv redirects HTTP to HTTPS.
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=12, context=context) as response:
        return parse_arxiv_atom(response.read())


def search_arxiv(query, categories=None, max_results=10):
    return search_arxiv_atom(query, categories=categories, max_results=max_results)


def extract_ai_json_value(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        for pattern in [r"\[.*\]", r"\{.*\}"]:
            match = re.search(pattern, text, flags=re.S)
            if match:
                return json.loads(match.group(0))
    return None


def translate_search_results_with_ai(papers):
    settings = LocalSettings.current()
    if not settings.ai_base_url or not settings.ai_api_key or not settings.text_model or not papers:
        return papers
    source_items = [
        {
            "arxiv_id": paper.get("arxiv_id", ""),
            "title": paper.get("title", ""),
            "abstract": paper.get("abstract", "")[:1200],
        }
        for paper in papers[:10]
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "你是论文搜索结果翻译助手。只返回 JSON 数组，不要 Markdown。"
                "每个元素包含 arxiv_id、translated_title、translated_abstract。"
                "translated_title 将英文论文题目忠实翻译成中文；"
                "translated_abstract 只翻译原文摘要内容，不要总结、不要扩写、不要加入评价。"
            ),
        },
        {"role": "user", "content": json.dumps(source_items, ensure_ascii=False)},
    ]
    try:
        content = ai_message_content(ai_chat_completion(settings, messages, timeout=90))
        parsed = extract_ai_json_value(content)
    except Exception as error:
        logger.exception("AI search-result translation failed: %s", type(error).__name__)
        return papers
    if isinstance(parsed, dict):
        for key in ["results", "items", "papers", "translations"]:
            if isinstance(parsed.get(key), list):
                parsed = parsed[key]
                break
    if not isinstance(parsed, list):
        return papers
    translations = {
        str(item.get("arxiv_id", "")): item
        for item in parsed
        if isinstance(item, dict)
    }
    translated = []
    for paper in papers:
        enriched = dict(paper)
        translation = translations.get(str(paper.get("arxiv_id", "")))
        if translation:
            enriched["translated_title"] = str(translation.get("translated_title", "")).strip()
            enriched["translated_abstract"] = str(translation.get("translated_abstract", "")).strip()
        translated.append(enriched)
    return translated


def log_arxiv_error(error, query, categories=None, max_results=10):
    search_query = build_arxiv_search_query(query, categories)
    url = arxiv_api_url(search_query, max_results)
    detail = {
        "query": query,
        "categories": categories or [],
        "search_query": search_query,
        "url": url,
        "error_type": type(error).__name__,
    }
    if isinstance(error, urllib.error.HTTPError):
        detail["code"] = error.code
        detail["reason"] = str(error.reason)
        try:
            detail["body"] = error.read().decode("utf-8", errors="replace")[:1200]
        except Exception as body_error:
            detail["body_error"] = repr(body_error)
    elif isinstance(error, urllib.error.URLError):
        detail["reason"] = str(error.reason)
    else:
        detail["message"] = str(error)
    logger.exception("arXiv API request failed: %s", detail)


def reconstruct_abstract_from_inverted_index(inverted_index):
    """Reconstruct plain text from OpenAlex abstract_inverted_index dict."""
    if not inverted_index or not isinstance(inverted_index, dict):
        return ""
    positioned = []
    for word, positions in inverted_index.items():
        for pos in positions:
            positioned.append((pos, word))
    positioned.sort(key=lambda pair: pair[0])
    return " ".join(word for _pos, word in positioned)


def parse_openalex_work(work, query="", keywords=None):
    """Map an OpenAlex work dict to the internal paper dict, with enrichment."""
    abstract = reconstruct_abstract_from_inverted_index(work.get("abstract_inverted_index"))
    authors = [
        authorship.get("author", {}).get("display_name", "")
        for authorship in work.get("authorships", [])
        if authorship.get("author", {}).get("display_name")
    ]
    primary = work.get("primary_location") or {}
    source_info = primary.get("source") or {}
    published_date = work.get("publication_date", "") or ""
    year = int(published_date[:4]) if published_date[:4].isdigit() else (work.get("publication_year") or None)
    openalex_id = work.get("id", "")

    raw = {
        "title": (work.get("title") or work.get("display_name") or "").strip(),
        "authors": authors,
        "year": year,
        "abstract": abstract,
        "arxiv_id": openalex_id,
        "doi": (work.get("doi") or "").replace("https://doi.org/", ""),
        "source": source_info.get("display_name") or "OpenAlex",
        "source_url": primary.get("landing_page_url", ""),
        "pdf_url": primary.get("pdf_url") or "",
        "published_date": published_date,
        "version": "",
        "openalex_id": openalex_id,
        "openalex_relevance": work.get("relevance_score", None),
    }
    enriched = enrich_paper_metadata(raw, query, keywords)
    enriched["openalex_id"] = openalex_id
    enriched["openalex_relevance"] = work.get("relevance_score", None)
    return enriched


def fetch_openalex_works(query, per_page=50):
    """Fetch works from the OpenAlex semantic search API."""
    cutoff_year = date.today().year - 2
    params = urllib.parse.urlencode({
        "search": query,
        "per_page": str(per_page),
    })
    url = f"https://api.openalex.org/works?{params}&filter=from_publication_date:{cutoff_year}-01-01"
    request = urllib.request.Request(url, headers={"User-Agent": "LitRadar/0.1 local literature tool"})
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=15, context=context) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("results", [])


@csrf_exempt
def papers_search_view(request):
    query = request.GET.get("query", "")
    topic_id = request.GET.get("topic_id")
    topic_keywords = []
    if topic_id:
        topic = get_object_or_404(ResearchTopic, pk=topic_id)
        topic_keywords = [*topic.keywords, *topic.arxiv_categories]
    try:
        results = search_arxiv(query, categories=[])
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)
    except urllib.error.HTTPError as error:
        log_arxiv_error(error, query, categories=[], max_results=10)
        return JsonResponse({"error": f"arXiv API 返回 {error.code}，请稍后再试或调整关键词。"}, status=503)
    except (urllib.error.URLError, TimeoutError) as error:
        log_arxiv_error(error, query, categories=[], max_results=10)
        return JsonResponse({"error": "arXiv 暂时不可用，请稍后再试。"}, status=503)
    ranked = rank_papers(results, query, topic_keywords)
    return JsonResponse(translate_search_results_with_ai(ranked), safe=False)


@csrf_exempt
def papers_list_view(request):
    if request.method == "GET":
        papers = Paper.objects.exclude(status=Paper.STATUS_RECOMMENDED).select_related("topic").order_by("-created_at")
        return JsonResponse([paper_payload(paper) for paper in papers], safe=False)
    if request.method == "POST":
        data = parse_json(request)
        topic = ResearchTopic.objects.filter(pk=data.get("topic")).first() if data.get("topic") else None
        lookup = {"arxiv_id": data.get("arxiv_id", "")} if data.get("arxiv_id") else {"title": data["title"]}
        paper, _created = Paper.objects.update_or_create(
            **lookup,
            defaults=paper_defaults(data, topic, data.get("status", Paper.STATUS_SAVED)),
        )
        return JsonResponse(paper_payload(paper), status=201)
    return JsonResponse({"error": "Method not allowed"}, status=405)


@csrf_exempt
def papers_detail_view(request, paper_id):
    paper = get_object_or_404(Paper, pk=paper_id)
    if request.method == "GET":
        return JsonResponse(paper_payload(paper))
    if request.method == "PATCH":
        data = parse_json(request)
        for field in [
            "title",
            "translated_title",
            "authors",
            "year",
            "abstract",
            "translated_abstract",
            "arxiv_id",
            "doi",
            "source",
            "source_url",
            "pdf_url",
            "published_date",
            "version",
            "local_pdf_path",
            "status",
        ]:
            if field in data:
                setattr(paper, field, data[field])
        if "topic" in data:
            paper.topic = ResearchTopic.objects.filter(pk=data.get("topic")).first() if data.get("topic") else None
        paper.save()
        return JsonResponse(paper_payload(paper))
    if request.method == "DELETE":
        paper.delete()
        return JsonResponse({"deleted": True})
    return JsonResponse({"error": "Method not allowed"}, status=405)


def keyword_score(topic, paper_data):
    text = f"{paper_data.get('title', '')} {paper_data.get('abstract', '')}".lower()
    matches = [keyword for keyword in topic.keywords if keyword.lower() in text]
    return min(95, 50 + len(matches) * 20), matches


def radar_search_terms(topic):
    terms = []
    for value in [topic.name, *topic.keywords]:
        for term in split_search_terms(value):
            if format_arxiv_all_terms(term) and term.lower() not in [existing.lower() for existing in terms]:
                terms.append(term)
    return terms[:8]


def combined_radar_query(terms):
    return ";".join(terms[:4])


def paper_recency_score(paper, today=None):
    today = today or date.today()
    published = paper.get("published_date", "")
    try:
        days = (today - date.fromisoformat(published)).days
    except (TypeError, ValueError):
        year = paper.get("year")
        return 5 if year == today.year else 0
    if days <= 7:
        return 25
    if days <= 30:
        return 18
    if days <= 180:
        return 10
    if days <= 365:
        return 5
    return 0


def paper_within_recent_years(paper, years=2, today=None):
    today = today or date.today()
    cutoff_year = today.year - years
    published = paper.get("published_date", "")
    try:
        return date.fromisoformat(published) >= date(cutoff_year, 1, 1)
    except (TypeError, ValueError):
        year = paper.get("year")
        return bool(year and year >= cutoff_year)


def weighted_random_candidates(candidates, limit):
    ranked = sorted(
        candidates,
        key=lambda paper: (paper.get("match_score", 0), paper_recency_score(paper)),
        reverse=True,
    )
    threshold = max(25, ranked[0].get("match_score", 0) - 15) if ranked else 0
    pool = [paper for paper in ranked if paper.get("match_score", 0) >= threshold][: max(limit * 5, 12)]
    if len(pool) < limit:
        pool = ranked[: max(limit * 5, 12)]
    selected = []
    while pool and len(selected) < limit:
        weights = [max(1, paper.get("match_score", 0) * 3 + paper_recency_score(paper) + random.randint(0, 8)) for paper in pool]
        chosen = random.choices(pool, weights=weights, k=1)[0]
        selected.append(chosen)
        pool.remove(chosen)
    return selected


def radar_candidates(topic, limit):
    terms = radar_search_terms(topic)
    if not terms:
        raise ValueError("请至少配置一个英文关键词，arXiv 不支持直接使用中文研究方向检索。")
    per_query_limit = max(20, limit * 10)
    merged = {}
    last_error = None
    queries = []
    for query in [combined_radar_query(terms), *terms]:
        if query and query.lower() not in [existing.lower() for existing in queries]:
            queries.append(query)
    for term in queries:
        try:
            for paper in search_arxiv(term, categories=[], max_results=per_query_limit):
                key = paper.get("arxiv_id") or paper.get("title")
                if key:
                    merged[key] = paper
        except ValueError:
            continue
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            last_error = error
            logger.warning("arXiv radar term failed: %s", term, exc_info=True)
    if not merged and last_error:
        raise last_error
    scoring_terms = [topic.name, *topic.keywords, *topic.arxiv_categories]
    recent = [paper for paper in merged.values() if paper_within_recent_years(paper, years=2)]
    return rank_papers(recent, ";".join(terms), scoring_terms)


@csrf_exempt
def radar_run_view(request, topic_id):
    topic = get_object_or_404(ResearchTopic, pk=topic_id)
    data = parse_json(request)
    limit = data.get("limit", topic.daily_limit)
    try:
        limit = max(1, min(int(limit), 10))
    except (TypeError, ValueError):
        limit = topic.daily_limit
    max_results = max(limit * 20, 50)
    try:
        candidates = radar_candidates(topic, limit)
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)
    except urllib.error.HTTPError as error:
        log_arxiv_error(error, ";".join(radar_search_terms(topic)), categories=[], max_results=max_results)
        return JsonResponse({"error": f"arXiv API 返回 {error.code}，请稍后再试或调整关键词。"}, status=503)
    except (urllib.error.URLError, TimeoutError) as error:
        log_arxiv_error(error, ";".join(radar_search_terms(topic)), categories=[], max_results=max_results)
        return JsonResponse({"error": "arXiv 暂时不可用，请稍后再试。"}, status=503)
    recommendations = []
    today = date.today()
    DailyRecommendation.objects.filter(topic=topic, recommend_date=today).delete()
    selected_candidates = weighted_random_candidates(candidates, limit)
    selected_candidates = translate_search_results_with_ai(selected_candidates)
    for candidate in selected_candidates:
        if len(recommendations) >= limit:
            break
        lookup = {"arxiv_id": candidate.get("arxiv_id", "")} if candidate.get("arxiv_id") else {"title": candidate["title"]}
        paper, _created = Paper.objects.update_or_create(**lookup, defaults=paper_defaults(candidate, topic, Paper.STATUS_RECOMMENDED))
        score = candidate.get("match_score", 0)
        matches = candidate.get("matched_terms", [])
        reason = f"发表：{candidate.get('published_date') or candidate.get('year') or '未知时间'} · 来源：{candidate.get('source') or 'arXiv'}"
        idea_hint = f"可关注 {topic.name} 中的方法设计、数据流和实验设置。"
        try:
            recommendation = DailyRecommendation.objects.create(
                topic=topic,
                paper=paper,
                recommend_date=today,
                score=score,
                reason=reason,
                idea_hint=idea_hint,
            )
        except IntegrityError:
            continue
        recommendations.append(recommendation)
    return JsonResponse({"topic": topic_payload(topic), "date": today.isoformat(), "recommendations": [recommendation_payload(item) for item in recommendations]})


def radar_today_view(_request):
    today = date.today()
    return JsonResponse([recommendation_payload(item) for item in DailyRecommendation.objects.filter(recommend_date=today).select_related("topic", "paper")], safe=False)


@csrf_exempt
def paper_pdf_view(request, paper_id):
    paper = get_object_or_404(Paper, pk=paper_id)
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    data = parse_json(request)
    paper.local_pdf_path = data.get("local_pdf_path", "")
    paper.save(update_fields=["local_pdf_path", "updated_at"])
    return JsonResponse(paper_payload(paper))


@csrf_exempt
def paper_parse_view(request, paper_id):
    paper = get_object_or_404(Paper, pk=paper_id)
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    parsed_text = ""
    if paper.local_pdf_path:
        try:
            import fitz

            document = fitz.open(paper.local_pdf_path)
            parsed_text = "\n".join(page.get_text() for page in document)
        except Exception:
            parsed_text = "PDF 文本解析失败，请确认文件是否为有效 PDF。"
    paper.parsed_text = parsed_text
    paper.status = Paper.STATUS_PARSED
    paper.save(update_fields=["parsed_text", "status", "updated_at"])
    figure, _created = PaperFigure.objects.get_or_create(
        paper=paper,
        figure_index=1,
        defaults={
            "page_number": 1,
            "image_path": "",
            "caption": "待从 PDF 解析中提取 caption",
            "context_text": parsed_text[:800],
            "figure_type": "architecture",
            "is_key_figure": False,
        },
    )
    return JsonResponse({"paper": paper_payload(paper), "figures": [figure_payload(figure)]})


@csrf_exempt
def paper_figure_detail_view(request, paper_id, figure_id):
    figure = get_object_or_404(PaperFigure, pk=figure_id, paper_id=paper_id)
    if request.method != "PATCH":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    data = parse_json(request)
    for field in ["is_key_figure", "figure_type", "caption", "context_text", "ai_description"]:
        if field in data:
            setattr(figure, field, data[field])
    figure.save()
    return JsonResponse(figure_payload(figure))


INSIGHT_FIELDS = [
    "research_direction",
    "task_definition",
    "module_list",
    "loss_functions",
    "training_process",
    "inference_process",
    "innovation_points",
    "limitations",
    "reproduction_questions",
    "idea_hints",
    "keywords",
]

PAPER_TRANSLATION_FIELDS = ["translated_title", "translated_abstract"]


def load_paperqa_env():
    env_path = Path(django_settings.BASE_DIR) / ".env.paperqa"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def effective_ai_key(settings):
    load_paperqa_env()
    return settings.ai_api_key or os.environ.get("DEEPSEEK_API_KEY", "")


def effective_ai_base(settings):
    load_paperqa_env()
    return (settings.ai_base_url or os.environ.get("DEEPSEEK_API_BASE", "")).rstrip("/")


def effective_text_model(settings):
    load_paperqa_env()
    return settings.text_model or os.environ.get("DEEPSEEK_MODEL", "")


def has_effective_ai_config(settings):
    return bool(effective_ai_key(settings) and effective_ai_base(settings) and effective_text_model(settings))


def extract_json_object(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return None
        return json.loads(match.group(0))


def ai_chat_completions_url(base_url):
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def ai_chat_completion(settings, messages, timeout=180):
    client = OpenAI(api_key=effective_ai_key(settings), base_url=effective_ai_base(settings), timeout=timeout)
    return client.chat.completions.create(
        model=effective_text_model(settings),
        messages=messages,
        stream=False,
        reasoning_effort="high",
        extra_body={"thinking": {"type": "enabled"}},
    )


def ai_message_content(response):
    try:
        return response.choices[0].message.content or ""
    except (AttributeError, IndexError):
        return ""


def analyze_paper_with_ai(settings, paper, topic_name, source_text):
    if not has_effective_ai_config(settings):
        return None
    prompt = (
        "你是论文精读助手。请只返回 JSON，不要 Markdown、不要解释。字段必须包含："
        + ", ".join([*PAPER_TRANSLATION_FIELDS, *INSIGHT_FIELDS])
        + "。translated_title 忠实翻译论文题目；translated_abstract 只翻译原文摘要内容，不要总结、扩写或评价。"
        + "research_direction 用一个短语概括论文所属主题。"
        + "task_definition 写研究动机：精炼说明该论文解决了什么问题、为什么要解决，不超过120字。"
        + "innovation_points 用数组列出论文原文提到的创新点；每项尽量不用原文英文缩写作名字，而是说明这是一个什么作用的模块/机制，使用什么方法做了什么事。"
        + "idea_hints 用数组列出2到3个可参考 idea，必须结合上述创新点和用户的雷达研究方向。"
        + "module_list、loss_functions、training_process、inference_process、limitations、reproduction_questions 可以返回空字符串；keywords 返回少量关键词数组。"
    )
    messages = [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": f"研究方向：{topic_name}\n标题：{paper.title}\n作者：{', '.join(paper.authors)}\n年份：{paper.year or ''}\n内容：\n{source_text}",
        },
    ]
    try:
        content = ai_message_content(ai_chat_completion(settings, messages, timeout=180))
        parsed = extract_json_object(content)
    except Exception as error:
        logger.exception("AI paper analysis failed: %s", type(error).__name__)
        return None
    if not isinstance(parsed, dict):
        return None
    result = {}
    for field in PAPER_TRANSLATION_FIELDS:
        result[field] = str(parsed.get(field, ""))
    for field in INSIGHT_FIELDS:
        value = parsed.get(field, [] if field in ["keywords", "innovation_points", "idea_hints"] else "")
        if field == "keywords":
            result[field] = value if isinstance(value, list) else [str(value)] if value else []
        elif field in ["innovation_points", "idea_hints"]:
            if isinstance(value, list):
                result[field] = "\n".join(str(item).strip() for item in value if str(item).strip())
            else:
                result[field] = str(value)
        else:
            result[field] = str(value)
    return result


def normalize_insight_defaults(defaults):
    normalized = dict(defaults)
    for field in ["innovation_points", "idea_hints"]:
        value = normalized.get(field)
        if isinstance(value, list):
            normalized[field] = "\n".join(str(item).strip() for item in value if str(item).strip())
    return normalized


@csrf_exempt
def paper_analyze_structure_view(_request, paper_id):
    paper = get_object_or_404(Paper, pk=paper_id)
    topic_name = paper.topic.name if paper.topic else "未分类方向"
    text = f"{paper.title}\n{paper.abstract}\n{paper.parsed_text[:6000]}"
    settings = LocalSettings.current()
    ai_payload = analyze_paper_with_ai(settings, paper, topic_name, text)
    if ai_payload:
        paper.translated_title = ai_payload.pop("translated_title", "") or paper.translated_title
        paper.translated_abstract = ai_payload.pop("translated_abstract", "") or paper.translated_abstract
    defaults = ai_payload or {
        "research_direction": topic_name,
        "task_definition": paper.abstract or f"这篇文章围绕 {topic_name} 展开，但当前材料不足以稳定判断它解决的具体痛点和突破，需要补充摘要或正文后再分析。",
        "module_list": "不确定：需要结合论文 Method 或关键图确认模块设计。",
        "loss_functions": "不确定：当前材料未稳定提取损失函数。",
        "training_process": "不确定：当前材料未稳定提取训练流程。",
        "inference_process": "不确定：当前材料未稳定提取推理流程。",
        "innovation_points": ["需要结合论文摘要、方法章节和关键图进一步确认创新点。"],
        "limitations": "不确定：需要阅读实验和局限性段落。",
        "reproduction_questions": "需要确认数据集、输入尺寸、训练配置、损失函数和代码可用性。",
        "idea_hints": [f"围绕 {topic_name}，先确认论文独特创新点，再思考其是否能迁移到当前研究方向。"],
        "keywords": paper.topic.keywords if paper.topic else [],
    }
    insight, _created = PaperInsight.objects.update_or_create(
        paper=paper,
        defaults=normalize_insight_defaults(defaults),
    )
    paper.status = Paper.STATUS_ANALYZED
    paper.save(update_fields=["translated_title", "translated_abstract", "status", "updated_at"])
    insight.markdown_note = render_paper_markdown(paper, insight)
    insight.save(update_fields=["markdown_note", "updated_at"])
    write_paper_to_obsidian(settings, paper, insight)
    return JsonResponse(insight_payload(insight))


def safe_note_name(title):
    slug = slugify(title, allow_unicode=False)
    if slug:
        return title.strip().replace(" ", "-")
    return re.sub(r"[^\w一-鿿-]+", "-", title).strip("-") or "Paper"


def obsidian_folder_for_paper(paper):
    return paper.topic.obsidian_folder if paper.topic and paper.topic.obsidian_folder else f"LitRadar/{paper.topic.name if paper.topic else 'Uncategorized'}"


def note_relative_path(paper):
    return f"{obsidian_folder_for_paper(paper)}/Papers/{safe_note_name(paper.title)}.md"


def graph_relative_path(paper):
    return f"{obsidian_folder_for_paper(paper)}/Graph/{safe_note_name(paper.title)}-知识图谱.md"


def paper_note_relative_path(paper):
    return f"{obsidian_folder_for_paper(paper)}/Notes/{safe_note_name(paper.title)}-深度笔记.md"


def wiki_link(label):
    cleaned = re.sub(r"[\[\]\n\r]+", " ", str(label)).strip()
    return f"[[{cleaned}]]" if cleaned else ""


def insight_items(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not value:
        return []
    return [item.replace("- ", "", 1).strip() for item in str(value).splitlines() if item.replace("- ", "", 1).strip()]


def render_paper_markdown(paper, insight=None):
    if insight is None and hasattr(paper, "insight"):
        insight = paper.insight
    topic_name = paper.topic.name if paper.topic else "未分类"
    authors = ", ".join(paper.authors)
    direction = insight.research_direction if insight else topic_name
    graph_name = safe_note_name(paper.title) + "-知识图谱"
    translated_title = paper.translated_title or paper.title
    body = [
        "---",
        f'title: "{paper.title}"',
        f'translated_title: "{translated_title}"',
        f"authors: [{authors}]",
        f"year: {paper.year or ''}",
        f'source: "{paper.source}"',
        f'arxiv_id: "{paper.arxiv_id}"',
        f'topic: "{topic_name}"',
        'tags: [paper, litradar]',
        f'status: "{paper.status}"',
        "---",
        "",
        f"# {translated_title}",
        "",
        f"英文题目：{paper.title}",
        "",
        "## 中文摘要",
        paper.translated_abstract or "待 AI 翻译。",
        "",
        "## 英文摘要",
        paper.abstract or "待补充。",
        "",
        "## 研究方向",
        wiki_link(direction) or direction,
        "",
        "## 论文要解决的问题",
        insight.task_definition if insight else "待分析。",
        "",
        "## 模块拆解",
        insight.module_list if insight else "待分析。",
        "",
        "## 实验与结果",
        "待补充。",
        "",
        "## 创新点",
        format_note_list(insight.innovation_points if insight else None),
        "",
        "## Obsidian 知识图谱",
        f"- 图谱入口：[[{graph_name}]]",
        f"- 主题节点：{wiki_link(direction) or '待分析。'}",
        *[f"- 创新点节点：{wiki_link(item)}" for item in insight_items(insight.innovation_points if insight else None)[:6]],
        "",
        "## 局限性",
        insight.limitations if insight else "待分析。",
        "",
        "## 可复现疑点",
        insight.reproduction_questions if insight else "待分析。",
        "",
        "## 可以启发的新 idea",
        format_note_list(insight.idea_hints if insight else None),
        "",
        "## 原文信息",
        f"- Google Scholar: {google_scholar_url(paper.title)}",
        f"- arXiv: {paper.source_url}",
        f"- PDF: {paper.pdf_url}",
    ]
    return "\n".join(body)


def render_graph_markdown(paper, insight):
    direction = insight.research_direction or (paper.topic.name if paper.topic else "未分类")
    paper_node = safe_note_name(paper.title)
    lines = [
        f"# {paper.translated_title or paper.title} 知识图谱",
        "",
        f"- 论文：[[{paper_node}]]",
        f"- 主题节点：{wiki_link(direction)}",
        f"- 核心关系：{insight.task_definition or '待分析。'}",
        "",
        "## 创新点节点",
        format_note_list(insight.innovation_points),
        "",
        "## Idea 节点",
        format_note_list(insight.idea_hints),
        "",
        "## 关键词",
        "\n".join(f"- {wiki_link(keyword)}" for keyword in insight.keywords) or "待分析。",
    ]
    return "\n".join(lines)


def render_note_markdown(paper, note):
    return "\n".join(
        [
            "---",
            f'title: "{paper.title} 深度笔记"',
            f'source: "{note.source}"',
            f'arxiv_id: "{paper.arxiv_id}"',
            "tags: [paper-note, litradar]",
            "---",
            "",
            f"# {paper.translated_title or paper.title} 深度笔记",
            "",
            f"- 原文：{paper.source_url}",
            f"- PDF：{paper.pdf_url}",
            "",
            note.content or "待生成。",
        ]
    )


def write_paper_to_obsidian(settings, paper, insight):
    if not settings.obsidian_vault_path:
        return None
    try:
        vault = Path(settings.obsidian_vault_path).expanduser()
        paper_path = vault / note_relative_path(paper)
        graph_path = vault / graph_relative_path(paper)
        paper_path.parent.mkdir(parents=True, exist_ok=True)
        graph_path.parent.mkdir(parents=True, exist_ok=True)
        paper_path.write_text(render_paper_markdown(paper, insight), encoding="utf-8")
        graph_path.write_text(render_graph_markdown(paper, insight), encoding="utf-8")
        return paper_path
    except OSError as error:
        logger.exception("Obsidian export failed: %s", error)
        return None


def write_note_to_obsidian(settings, paper, note):
    if not settings.obsidian_vault_path:
        return None
    try:
        vault = Path(settings.obsidian_vault_path).expanduser()
        note_path = vault / note.target_relative_path
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(render_note_markdown(paper, note), encoding="utf-8")
        return note_path
    except OSError as error:
        logger.exception("Obsidian note export failed: %s", error)
        return None


def paper_cache_dir(paper):
    key = paper.arxiv_id or str(paper.id)
    safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "-", key).strip("-") or str(paper.id)
    path = Path(django_settings.BASE_DIR) / ".cache" / "papers" / safe_key
    path.mkdir(parents=True, exist_ok=True)
    return path


def local_pdf_for_note(paper):
    if paper.local_pdf_path and Path(paper.local_pdf_path).expanduser().exists():
        return Path(paper.local_pdf_path).expanduser()
    if not paper.pdf_url:
        return None
    target = paper_cache_dir(paper) / "paper.pdf"
    if target.exists() and target.stat().st_size > 0:
        return target
    request = urllib.request.Request(paper.pdf_url, headers={"User-Agent": "LitRadar/0.1 local literature tool"})
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=45, context=context) as response:
        target.write_bytes(response.read())
    return target


def parsed_paper_text(paper, pdf_path=None, limit=16000):
    if paper.parsed_text:
        return paper.parsed_text[:limit]
    if pdf_path and Path(pdf_path).exists():
        try:
            import fitz

            document = fitz.open(pdf_path)
            return "\n".join(page.get_text() for page in document)[:limit]
        except Exception as error:
            logger.exception("PDF text extraction for note failed: %s", type(error).__name__)
    return f"{paper.title}\n{paper.abstract}"[:limit]


def paper_note_question(paper, topic_name):
    return (
        "请用中文深度讲解这篇论文，要求简约但信息密度高，并保留必要的页码/引文线索。"
        "输出 Markdown，包含：1. 论文试图解决的问题；2. 核心方法与关键模块；"
        "3. 主要创新点，逐条展开解释；4. 实验结论和适用边界；"
        f"5. 结合我的雷达研究方向“{topic_name}”给出可借鉴的研究思路。"
    )


def generate_note_with_paperqa(settings, paper, pdf_path, topic_name):
    load_paperqa_env()
    os.environ.setdefault("PQA_HOME", str(Path(django_settings.BASE_DIR) / ".pqa"))
    from paperqa import Settings, ask

    paper_dir = Path(pdf_path).parent
    api_key = effective_ai_key(settings)
    api_base = effective_ai_base(settings)
    llm = os.environ.get("PAPERQA_LLM") or f"openai/{effective_text_model(settings)}"
    summary_llm = os.environ.get("PAPERQA_SUMMARY_LLM") or llm
    pqa_settings = Settings(
        temperature=0.2,
        llm=llm,
        summary_llm=summary_llm,
        llm_config={"api_key": api_key, "api_base": api_base},
        summary_llm_config={"api_key": api_key, "api_base": api_base},
        embedding="st-multi-qa-MiniLM-L6-cos-v1",
        agent={"index": {"paper_directory": paper_dir, "index_directory": paper_dir / ".pqa-index"}},
    )
    response = ask(paper_note_question(paper, topic_name), settings=pqa_settings)
    if asyncio.isfuture(response) or hasattr(response, "__await__"):
        response = asyncio.run(response)
    return getattr(response, "formatted_answer", None) or getattr(response, "answer", None) or str(response)


def generate_note_with_deepseek(settings, paper, topic_name, source_text):
    messages = [
        {
            "role": "system",
            "content": (
                "你是论文精读讲解助手。请用中文输出 Markdown，不要 JSON。"
                "内容要详细但有结构，解释论文动机、方法、关键模块、创新点、实验结论、局限，以及与用户研究方向相关的可借鉴 idea。"
            ),
        },
        {"role": "user", "content": f"研究方向：{topic_name}\n论文：{paper.title}\n摘要：{paper.abstract}\n正文摘录：\n{source_text}"},
    ]
    return ai_message_content(ai_chat_completion(settings, messages, timeout=240))


def generate_paper_note(settings, paper, force=False):
    if hasattr(paper, "note") and paper.note.content and not force:
        return paper.note
    topic_name = paper.topic.name if paper.topic else "未分类方向"
    pdf_path = None
    source = "deepseek"
    content = ""
    try:
        pdf_path = local_pdf_for_note(paper)
        if pdf_path:
            content = generate_note_with_paperqa(settings, paper, pdf_path, topic_name)
            source = "paperqa"
    except Exception as error:
        logger.exception("paper-qa note generation failed, falling back to DeepSeek: %s", type(error).__name__)
    if not content:
        content = generate_note_with_deepseek(settings, paper, topic_name, parsed_paper_text(paper, pdf_path))
        source = "deepseek"
    note, _created = PaperNote.objects.update_or_create(
        paper=paper,
        defaults={
            "content": content or "论文笔记生成失败，请检查 AI 配置或 PDF 可访问性。",
            "source": source,
            "target_relative_path": paper_note_relative_path(paper),
        },
    )
    write_note_to_obsidian(settings, paper, note)
    return note


def paper_obsidian_markdown_view(_request, paper_id):
    paper = get_object_or_404(Paper, pk=paper_id)
    insight = getattr(paper, "insight", None)
    return JsonResponse({"target_relative_path": note_relative_path(paper), "markdown": render_paper_markdown(paper, insight)})


@csrf_exempt
def paper_note_view(request, paper_id):
    paper = get_object_or_404(Paper, pk=paper_id)
    if request.method == "GET":
        note = getattr(paper, "note", None)
        return JsonResponse(note_payload(note) if note else {"content": "", "source": "", "target_relative_path": paper_note_relative_path(paper), "updated_at": ""})
    if request.method == "POST":
        settings = LocalSettings.current()
        if not has_effective_ai_config(settings):
            return JsonResponse({"error": "请先在本地设置中配置 DeepSeek，或创建 backend/.env.paperqa。"}, status=400)
        data = parse_json(request)
        note = generate_paper_note(settings, paper, force=bool(data.get("force")))
        return JsonResponse(note_payload(note))
    return JsonResponse({"error": "Method not allowed"}, status=405)


@csrf_exempt
def papers_openalex_discover_view(request):
    topic_id = request.GET.get("topic_id")
    if not topic_id:
        return JsonResponse({"error": "请提供 topic_id 参数。"}, status=400)
    topic = get_object_or_404(ResearchTopic, pk=topic_id)
    keywords = [kw for kw in (topic.keywords or []) if kw and isinstance(kw, str) and kw.strip()]
    if not keywords:
        return JsonResponse({"error": "当前研究方向未配置关键词，请先在今日雷达中添加英文关键词。"}, status=400)
    query = " ".join(keywords)
    try:
        works = fetch_openalex_works(query, per_page=50)
    except urllib.error.HTTPError as error:
        logger.exception("OpenAlex API HTTP error: %s", error.code)
        return JsonResponse({"error": f"OpenAlex API 返回 {error.code}，请稍后再试。"}, status=503)
    except (urllib.error.URLError, TimeoutError) as error:
        logger.exception("OpenAlex API request failed: %s", type(error).__name__)
        return JsonResponse({"error": "OpenAlex 暂时不可用，请稍后再试。"}, status=503)
    if not works:
        return JsonResponse([], safe=False)
    papers = [parse_openalex_work(work, query, keywords) for work in works]
    today = date.today()
    for paper in papers:
        paper["_combined"] = paper.get("match_score", 0) * 3 + paper_recency_score(paper, today)
    papers.sort(key=lambda p: p["_combined"], reverse=True)
    pool = papers[:20]
    if len(pool) <= 6:
        selected = pool
    else:
        selected = random.sample(pool, 6)
    for paper in selected:
        paper.pop("_combined", None)
        paper["arxiv_id"] = paper.get("openalex_id", "")
    translated = translate_search_results_with_ai(selected)
    for paper in translated:
        paper["arxiv_id"] = ""
    return JsonResponse(translated, safe=False)


urlpatterns = [
    path("health/", health_view, name="health"),
    path("settings/", local_settings_view, name="local-settings"),
    path("topics/", topics_list_view, name="topics-list"),
    path("topics/<int:topic_id>/", topics_detail_view, name="topics-detail"),
    path("papers/search/", papers_search_view, name="papers-search"),
    path("papers/openalex/discover/", papers_openalex_discover_view, name="papers-openalex-discover"),
    path("papers/", papers_list_view, name="papers-list"),
    path("papers/<int:paper_id>/", papers_detail_view, name="papers-detail"),
    path("papers/<int:paper_id>/pdf/", paper_pdf_view, name="paper-pdf"),
    path("papers/<int:paper_id>/parse/", paper_parse_view, name="paper-parse"),
    path("papers/<int:paper_id>/figures/<int:figure_id>/", paper_figure_detail_view, name="paper-figure-detail"),
    path("papers/<int:paper_id>/analyze-structure/", paper_analyze_structure_view, name="paper-analyze-structure"),
    path("papers/<int:paper_id>/obsidian-markdown/", paper_obsidian_markdown_view, name="paper-obsidian-markdown"),
    path("papers/<int:paper_id>/note/", paper_note_view, name="paper-note"),
    path("radar/run/<int:topic_id>/", radar_run_view, name="radar-run"),
    path("radar/today/", radar_today_view, name="radar-today"),
]
