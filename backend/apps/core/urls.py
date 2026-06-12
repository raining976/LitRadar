import html
import json
import random
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date

from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt

from .models import DailyRecommendation, LocalSettings, Paper, PaperFigure, PaperInsight, ResearchTopic
from .views import health_view


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


def paper_payload(paper):
    payload = {
        "id": paper.id,
        "title": paper.title,
        "authors": paper.authors,
        "year": paper.year,
        "abstract": paper.abstract,
        "arxiv_id": paper.arxiv_id,
        "doi": paper.doi,
        "source": paper.source,
        "source_url": paper.source_url,
        "pdf_url": paper.pdf_url,
        "local_pdf_path": paper.local_pdf_path,
        "topic": paper.topic_id,
        "status": paper.status,
        "figures": [figure_payload(figure) for figure in paper.figures.all()],
        "insight": None,
    }
    if hasattr(paper, "insight"):
        payload["insight"] = insight_payload(paper.insight)
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


def tokenize(text):
    return [token for token in re.split(r"[^\w一-鿿]+", text.lower()) if len(token) > 1]


def score_text_matches(title, abstract, terms):
    title_normalized = title.lower()
    abstract_normalized = abstract.lower()
    score = 0
    matched_terms = []
    for term in terms:
        item = term.strip()
        if not item:
            continue
        item_lower = item.lower()
        term_matched = False
        if item_lower in title_normalized:
            score += 35
            term_matched = True
        elif item_lower in abstract_normalized:
            score += 22
            term_matched = True
        for token in tokenize(item):
            if token in title_normalized:
                score += 10
                matched_terms.append(token)
                term_matched = True
            elif token in abstract_normalized:
                score += 6
                matched_terms.append(token)
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
    terms = [query, *(keywords or [])]
    score, matched_terms = score_text_matches(paper.get("title", ""), paper.get("abstract", ""), terms)
    enriched["match_score"] = score
    enriched["matched_terms"] = matched_terms
    enriched["tags"] = infer_paper_tags(paper)
    return enriched


def paper_defaults(data, topic, status):
    return {
        "title": data["title"],
        "authors": data.get("authors", []),
        "year": data.get("year"),
        "abstract": data.get("abstract", ""),
        "arxiv_id": data.get("arxiv_id", ""),
        "doi": data.get("doi", ""),
        "source": data.get("source", "arXiv"),
        "source_url": data.get("source_url", ""),
        "pdf_url": data.get("pdf_url", ""),
        "local_pdf_path": data.get("local_pdf_path", ""),
        "topic": topic,
        "status": status,
    }


def rank_papers(papers, query="", keywords=None):
    enriched = [enrich_paper_metadata(paper, query, keywords) for paper in papers]
    return sorted(enriched, key=lambda paper: paper["match_score"], reverse=True)


def strip_html(value):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value))).strip()


def parse_arxiv_search_html(body):
    results = []
    for block in re.findall(r'<li class="arxiv-result">(.*?)</li>', body, flags=re.S):
        id_match = re.search(r'https://arxiv\.org/abs/([^"?#]+)', block)
        if not id_match:
            continue
        arxiv_id = id_match.group(1).strip()
        title_match = re.search(r'<p class="title[^"]*"[^>]*>(.*?)</p>', block, flags=re.S)
        abstract_match = re.search(r'<span class="abstract-full[^"]*"[^>]*>(.*?)</span>', block, flags=re.S)
        authors_block = re.search(r'<p class="authors"[^>]*>(.*?)</p>', block, flags=re.S)
        submitted_match = re.search(r'Submitted</span>\s*\d{1,2}\s+\w+,\s+(\d{4})', block, flags=re.S)
        authors = []
        if authors_block:
            authors = [strip_html(author) for author in re.findall(r'<a [^>]*>(.*?)</a>', authors_block.group(1), flags=re.S)]
        results.append(
            enrich_paper_metadata(
                {
                    "title": strip_html(title_match.group(1)) if title_match else "",
                    "authors": authors,
                    "year": int(submitted_match.group(1)) if submitted_match else None,
                    "abstract": strip_html(abstract_match.group(1)).replace("△ Less", "").strip() if abstract_match else "",
                    "arxiv_id": arxiv_id,
                    "source": "arXiv",
                    "source_url": f"https://arxiv.org/abs/{arxiv_id}",
                    "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
                }
            )
        )
    return results


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
                }
            )
        )
    return results


def search_arxiv_atom(query, categories=None, max_results=10):
    terms = [f"all:{query}" if query else ""]
    for category in categories or []:
        terms.append(f"cat:{category}")
    search_query = " AND ".join(term for term in terms if term)
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": search_query, "start": 0, "max_results": max_results, "sortBy": "submittedDate", "sortOrder": "descending"}
    )
    request = urllib.request.Request(url, headers={"User-Agent": "LitRadar/0.1 local literature tool"})
    with urllib.request.urlopen(request, timeout=12) as response:
        return parse_arxiv_atom(response.read())


def search_arxiv_html(query, categories=None, max_results=10):
    category = (categories or ["all"])[0]
    search_path = category.split(".", 1)[0] if category and category != "all" else "all"
    path = f"search/{search_path}" if search_path != "all" else "search/"
    url = f"https://arxiv.org/{path}?" + urllib.parse.urlencode(
        {"query": query, "searchtype": "all", "source": "header"}
    )
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 LitRadar/0.1 local literature tool"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return parse_arxiv_search_html(response.read().decode("utf-8", errors="replace"))[:max_results]


def search_arxiv(query, categories=None, max_results=10):
    try:
        return search_arxiv_atom(query, categories=categories, max_results=max_results)
    except (TimeoutError, urllib.error.URLError):
        pass
    except urllib.error.HTTPError as error:
        if error.code != 429:
            raise
    return search_arxiv_html(query, categories=categories, max_results=max_results)


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
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return JsonResponse({"error": "arXiv 暂时不可用，请稍后再试。"}, status=503)
    return JsonResponse(rank_papers(results, query, topic_keywords), safe=False)


@csrf_exempt
def papers_list_view(request):
    if request.method == "GET":
        return JsonResponse([paper_payload(paper) for paper in Paper.objects.select_related("topic").order_by("-created_at")], safe=False)
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
        for field in ["title", "authors", "year", "abstract", "arxiv_id", "doi", "source", "source_url", "pdf_url", "local_pdf_path", "status"]:
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


@csrf_exempt
def radar_run_view(request, topic_id):
    topic = get_object_or_404(ResearchTopic, pk=topic_id)
    data = parse_json(request)
    limit = data.get("limit", topic.daily_limit)
    try:
        limit = max(1, min(int(limit), 10))
    except (TypeError, ValueError):
        limit = topic.daily_limit
    query = " OR ".join(topic.keywords) if topic.keywords else topic.name
    try:
        scoring_terms = [topic.name, *topic.keywords, *topic.arxiv_categories]
        candidates = rank_papers(search_arxiv(query, categories=[], max_results=max(limit * 20, 50)), query, scoring_terms)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return JsonResponse({"error": "arXiv 暂时不可用，请稍后再试。"}, status=503)
    recommendations = []
    today = date.today()
    DailyRecommendation.objects.filter(topic=topic, recommend_date=today).delete()
    high_confidence = [candidate for candidate in candidates if candidate.get("match_score", 0) > 60]
    random.shuffle(high_confidence)
    fallback_candidates = [candidate for candidate in candidates if candidate not in high_confidence]
    selected_candidates = [*high_confidence, *fallback_candidates][:limit]
    for candidate in selected_candidates:
        if len(recommendations) >= limit:
            break
        lookup = {"arxiv_id": candidate.get("arxiv_id", "")} if candidate.get("arxiv_id") else {"title": candidate["title"]}
        paper, _created = Paper.objects.update_or_create(**lookup, defaults=paper_defaults(candidate, topic, Paper.STATUS_RECOMMENDED))
        score = candidate.get("match_score", 0)
        matches = candidate.get("matched_terms", [])
        reason_prefix = "" if candidate.get("match_score", 0) > 60 else "高置信候选不足，先补充展示："
        reason = f"{reason_prefix}与关键词 {', '.join(matches) if matches else topic.name} 相关，建议纳入今日阅读。"
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


def analyze_paper_with_ai(settings, paper, topic_name, source_text):
    if not settings.ai_base_url or not settings.ai_api_key or not settings.text_model:
        return None
    url = ai_chat_completions_url(settings.ai_base_url)
    prompt = (
        "你是论文精读助手。请只返回 JSON，不要 Markdown。字段必须包含："
        + ", ".join(INSIGHT_FIELDS)
        + "。task_definition 用一小段话说明论文要做什么问题、解决了前人什么痛点、做了哪些突破；"
        + "innovation_points 用数组列出论文独特创新点并简要解释；"
        + "idea_hints 用数组给出少量只贴近当前研究方向的 idea，必须由该论文创新点和当前研究方向结合得出，不要发散。"
    )
    payload = {
        "model": settings.text_model,
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": f"研究方向：{topic_name}\n标题：{paper.title}\n作者：{', '.join(paper.authors)}\n年份：{paper.year or ''}\n内容：\n{source_text}",
            },
        ],
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {settings.ai_api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = extract_json_object(content)
    except (json.JSONDecodeError, KeyError, IndexError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None
    if not isinstance(parsed, dict):
        return None
    result = {}
    for field in INSIGHT_FIELDS:
        value = parsed.get(field, [] if field in ["keywords", "innovation_points", "idea_hints"] else "")
        if field in ["keywords", "innovation_points", "idea_hints"]:
            result[field] = value if isinstance(value, list) else [str(value)] if value else []
        else:
            result[field] = str(value)
    return result


@csrf_exempt
def paper_analyze_structure_view(_request, paper_id):
    paper = get_object_or_404(Paper, pk=paper_id)
    topic_name = paper.topic.name if paper.topic else "未分类方向"
    text = f"{paper.title}\n{paper.abstract}\n{paper.parsed_text[:6000]}"
    settings = LocalSettings.current()
    ai_payload = analyze_paper_with_ai(settings, paper, topic_name, text)
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
        defaults=defaults,
    )
    paper.status = Paper.STATUS_ANALYZED
    paper.save(update_fields=["status", "updated_at"])
    insight.markdown_note = render_paper_markdown(paper, insight)
    insight.save(update_fields=["markdown_note", "updated_at"])
    return JsonResponse(insight_payload(insight))


def safe_note_name(title):
    slug = slugify(title, allow_unicode=False)
    if slug:
        return title.strip().replace(" ", "-")
    return re.sub(r"[^\w一-鿿-]+", "-", title).strip("-") or "Paper"


def render_paper_markdown(paper, insight=None):
    if insight is None and hasattr(paper, "insight"):
        insight = paper.insight
    topic_name = paper.topic.name if paper.topic else "未分类"
    authors = ", ".join(paper.authors)
    body = [
        "---",
        f'title: "{paper.title}"',
        f"authors: [{authors}]",
        f"year: {paper.year or ''}",
        f'source: "{paper.source}"',
        f'arxiv_id: "{paper.arxiv_id}"',
        f'topic: "{topic_name}"',
        'tags: [paper, litradar]',
        f'status: "{paper.status}"',
        "---",
        "",
        f"# {paper.title}",
        "",
        "## 一句话总结",
        paper.abstract[:240] or "待补充。",
        "",
        "## 研究方向",
        insight.research_direction if insight else topic_name,
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
        f"- arXiv: {paper.source_url}",
        f"- PDF: {paper.pdf_url}",
    ]
    return "\n".join(body)


def paper_obsidian_markdown_view(_request, paper_id):
    paper = get_object_or_404(Paper, pk=paper_id)
    insight = getattr(paper, "insight", None)
    folder = paper.topic.obsidian_folder if paper.topic and paper.topic.obsidian_folder else f"LitRadar/{paper.topic.name if paper.topic else 'Uncategorized'}"
    return JsonResponse({"target_relative_path": f"{folder}/Papers/{safe_note_name(paper.title)}.md", "markdown": render_paper_markdown(paper, insight)})


urlpatterns = [
    path("health/", health_view, name="health"),
    path("settings/", local_settings_view, name="local-settings"),
    path("topics/", topics_list_view, name="topics-list"),
    path("topics/<int:topic_id>/", topics_detail_view, name="topics-detail"),
    path("papers/search/", papers_search_view, name="papers-search"),
    path("papers/", papers_list_view, name="papers-list"),
    path("papers/<int:paper_id>/", papers_detail_view, name="papers-detail"),
    path("papers/<int:paper_id>/pdf/", paper_pdf_view, name="paper-pdf"),
    path("papers/<int:paper_id>/parse/", paper_parse_view, name="paper-parse"),
    path("papers/<int:paper_id>/figures/<int:figure_id>/", paper_figure_detail_view, name="paper-figure-detail"),
    path("papers/<int:paper_id>/analyze-structure/", paper_analyze_structure_view, name="paper-analyze-structure"),
    path("papers/<int:paper_id>/obsidian-markdown/", paper_obsidian_markdown_view, name="paper-obsidian-markdown"),
    path("radar/run/<int:topic_id>/", radar_run_view, name="radar-run"),
    path("radar/today/", radar_today_view, name="radar-today"),
]
