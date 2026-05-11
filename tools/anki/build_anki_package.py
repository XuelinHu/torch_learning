#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

import genanki
from pypdf import PdfReader

BASE_DIR = Path(__file__).resolve().parent
PDF_DIR = Path(r"D:\edu_lt\高校教资")
OUTPUT_JSON = BASE_DIR / "anki_merged_cards.json"
OUTPUT_APKG = BASE_DIR / "高校教师资格考试_4科整合.apkg"

QUESTION_MODEL_ID = 2026050901
DECK_BASE_ID = 2026050900

DECK_ORDER = [
    "高等教育学",
    "高等教育心理学",
    "高等教育法规概论",
    "高等学校教师职业道德修养",
]

SUBJECT_ALIASES = {
    "高等教育学": "高等教育学",
    "教育学": "高等教育学",
    "高等教育心理学": "高等教育心理学",
    "教育心理学": "高等教育心理学",
    "高等教育法规概论": "高等教育法规概论",
    "教育法规": "高等教育法规概论",
    "教育法律法规": "高等教育法规概论",
    "高等学校教师职业道德修养": "高等学校教师职业道德修养",
    "教师职业道德": "高等学校教师职业道德修养",
    "教师职业道德修养": "高等学校教师职业道德修养",
}

SOURCE_JSON_FILES = [
    "高等教育学.json",
    "高等教育心理学.json",
    "高等教育法规概论.json",
    "高等学校教师职业道德修养.json",
    "t1.json",
    "t2.json",
    "t3.json",
    "t4.json",
    "all_questions.json",
    "expanded_questions.json",
]

PDF_FILES = {
    "高等学校教师职业道德修养": "2026年5月《高校教师职业道德修养》师圆教育狂背三页纸.pdf",
    "高等教育学": "2026年5月《高等教育学》师圆教育狂背三张纸.pdf",
    "高等教育心理学": "2026年5月《高等教育心理学》师圆教育狂背三张纸.pdf",
    "高等教育法规概论": "2026年5月《高等教育法规概论》师圆教育狂背三页纸.pdf",
}

WEB_STYLE_REFERENCES = [
    "https://gxttc.gxnu.edu.cn/_upload/article/files/5b/d2/398fd6d74042844299b001fb3b82/22b8a0b3-fcda-4d39-b3c3-5d5a8dddd916.pdf",
    "https://k.sina.com.cn/article_7857141524_1d452771401901v7is.html",
    "https://kandian.sina.cn/article_7857141524_1d452771401901tyns.html",
]

APPLICATION_CONTEXTS = {
    "高等教育学": [
        "某高校修订人才培养方案时，要求课程、科研训练和社会实践共同服务于学生专业能力提升",
        "某大学围绕地方产业需求建设实验室和课程群，并将科研成果转化为教学案例",
        "青年教师在课程设计中把理论讲授、案例讨论和现场实践结合起来",
    ],
    "高等教育心理学": [
        "某教师发现学生在复杂任务中容易受已有经验影响，于是通过问题分解和反馈帮助其调整学习策略",
        "辅导员面对学生焦虑、拖延和学习动机不足的问题，设计了团体辅导与个别谈话方案",
        "课堂上教师根据学生认知水平设置支架，引导学生从已有经验过渡到新知识",
    ],
    "高等教育法规概论": [
        "某高校处理学生违纪事件时，先告知事实、理由和依据，再听取学生陈述申辩",
        "学校制定学籍、学位和教师管理制度时，要求所有程序都有明确法律依据",
        "学生对处分决定不服，准备通过校内申诉或法定救济途径维护自身权益",
    ],
    "高等学校教师职业道德修养": [
        "某教师在科研署名、课堂言行和师生交往中坚持公平、诚信和自律",
        "青年教师面对学生差异时，坚持尊重学生、关爱学生，并主动反思自己的教育行为",
        "教师在无人监督时仍遵守学术规范和职业规范，拒绝利益诱惑",
    ],
}

BROAD_CONCEPT_KEYWORDS = {
    "教学",
    "教师",
    "学生",
    "教育",
    "高校",
    "大学",
    "学习",
    "心理",
    "法律",
    "法规",
    "方法",
    "内容",
    "原则",
    "功能",
    "权利",
    "义务",
}

NOISE_TOKENS = [
    "微信",
    "小吴",
    "师圆教育微信群",
    "公众号",
    "免费",
    "公益答疑",
    "内部资料",
    "扫码",
]


def normalize_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\u3000", " ").replace("&nbsp;", " ")
    text = text.replace("“", "\"").replace("”", "\"")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_question_number(text: str) -> str:
    return re.sub(r"^\d+[\.．、]\s*", "", normalize_text(text))


def canonical_subject(value: str, fallback: str = "") -> str:
    text = normalize_text(value or fallback)
    if text in SUBJECT_ALIASES:
        return SUBJECT_ALIASES[text]
    for alias, subject in SUBJECT_ALIASES.items():
        if alias in text:
            return subject
    return fallback if fallback in DECK_ORDER else "高等教育学"


def normalize_answer(value: object) -> str:
    letters = re.findall(r"[A-Z]", str(value or "").upper())
    if letters:
        return "".join(sorted(dict.fromkeys(letters)))
    return normalize_text(value)


def normalize_type(value: object, answer: str) -> str:
    text = normalize_text(value).lower()
    if text in {"blank", "fill", "填空题"}:
        return "填空题"
    if text in {"multi", "checkbox", "多选题", "多项选择题"}:
        return "多选题"
    if text in {"judge", "判断题"}:
        return "判断题"
    if len(answer) > 1 and set(answer) <= set("ABCDEFGH"):
        return "多选题"
    return "单选题"


def options_to_map(raw: object) -> dict[str, str]:
    result: dict[str, str] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            letter = normalize_text(key).upper()
            text = normalize_text(value)
            if letter and text:
                result[letter] = text
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                letter = normalize_text(item.get("letter") or item.get("key")).upper()
                text = normalize_text(item.get("text") or item.get("value"))
            else:
                line = normalize_text(item)
                match = re.match(r"^([A-Z])[\.\、\s]*(.+)$", line)
                letter = match.group(1) if match else chr(ord("A") + len(result))
                text = match.group(2) if match else line
            if letter and text:
                result[letter] = normalize_text(text)
    elif isinstance(raw, str):
        for line in re.split(r"[\r\n]+", raw):
            line = normalize_text(line)
            if not line:
                continue
            match = re.match(r"^([A-Z])[\.\、\s]*(.+)$", line)
            letter = match.group(1) if match else chr(ord("A") + len(result))
            text = match.group(2) if match else line
            result[letter] = normalize_text(text)
    return dict(sorted(result.items()))


def question_key(subject: str, question: str) -> str:
    return f"{subject}||{strip_question_number(question)}"


def merge_key(row: dict) -> str:
    if row.get("concept_question_key"):
        return f"{row['subject']}||{row['concept_question_key']}"
    return question_key(row["subject"], row["question"])


def stable_guid(prefix: str, text: str) -> str:
    return hashlib.sha1(f"{prefix}::{text}".encode("utf-8")).hexdigest()[:20]


def infer_subject_from_question(question: str, fallback: str = "") -> str:
    text = normalize_text(question)
    rules = [
        ("高等教育心理学", ["心理", "认知", "记忆", "动机", "迁移", "气质", "人格", "最近发展区"]),
        ("高等教育法规概论", ["法律", "法规", "处分", "申诉", "学籍", "学位", "权利", "义务", "教师法", "作弊"]),
        ("高等学校教师职业道德修养", ["师德", "职业道德", "为人师表", "爱岗敬业", "关爱学生", "学术不端"]),
        ("高等教育学", ["高等教育", "高校", "课程", "教学", "科研", "学科建设", "社会服务"]),
    ]
    for subject, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return subject
    return canonical_subject(fallback)


def standardize_question(item: dict, subject_hint: str, source_file: str) -> dict | None:
    question = strip_question_number(item.get("question") or item.get("题目") or item.get("text") or "")
    if not question:
        return None
    raw_subject = item.get("subject") or item.get("category") or item.get("类别") or subject_hint
    subject = infer_subject_from_question(question, subject_hint) if raw_subject == "综合案例分析" else canonical_subject(raw_subject, subject_hint)
    options = options_to_map(item.get("options") or item.get("选项"))
    answer = normalize_answer(item.get("answer") or item.get("答案") or item.get("correct_answer"))
    qtype = normalize_type(item.get("type") or item.get("题型"), answer)
    analysis = normalize_text(
        item.get("analysis")
        or item.get("解析")
        or item.get("explanation")
        or item.get("knowledge_point")
        or item.get("note")
    )
    return {
        "kind": "question",
        "subject": subject,
        "question": question,
        "type": qtype,
        "options": options,
        "answer": answer,
        "analysis": analysis,
        "concept": normalize_text(item.get("concept") or item.get("knowledge_point")),
        "correct_extension": normalize_text(item.get("correct_extension")),
        "sources": [source_file],
    }


def load_questions_from_file(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict] = []
    if isinstance(data, dict) and "questions" in data:
        for item in data["questions"]:
            if item.get("kind") == "question" or "question" in item or "text" in item:
                row = standardize_question(item, canonical_subject(item.get("subject", "")), path.name)
                if row:
                    rows.append(row)
        return rows
    if path.name in {"all_questions.json", "expanded_questions.json"} and isinstance(data, dict):
        for subject, items in data.items():
            for item in items:
                row = standardize_question(item, canonical_subject(subject), path.name)
                if row:
                    rows.append(row)
        return rows
    if isinstance(data, list):
        subject_hint = canonical_subject(path.stem) if path.stem in SUBJECT_ALIASES else ""
        for item in data:
            row = standardize_question(item, subject_hint, path.name)
            if row:
                rows.append(row)
    return rows


def is_generated_question(item: dict) -> bool:
    question = normalize_text(item.get("question") or item.get("题目") or item.get("text"))
    if item.get("concept_question_key"):
        return True
    generated_patterns = [
        "根据2026年考前资料，下列属于",
        "根据2026年考前资料，请填空",
        "理解，下列哪些判断更恰当？（多选）",
        "这一做法最能体现下列哪一知识点？",
    ]
    return any(pattern in question for pattern in generated_patterns)


def load_seed_questions() -> list[dict]:
    rows: list[dict] = []
    for name in SOURCE_JSON_FILES:
        path = BASE_DIR / name
        if path.exists():
            rows.extend(load_questions_from_file(path))
    if rows:
        return rows
    if OUTPUT_JSON.exists():
        data = json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))
        for item in data.get("questions", []):
            if is_generated_question(item):
                continue
            row = standardize_question(item, item.get("subject", ""), OUTPUT_JSON.name)
            if row:
                row["sources"] = item.get("sources") or [OUTPUT_JSON.name]
                rows.append(row)
    return rows


def load_theory_concepts() -> list[dict]:
    path = BASE_DIR / "theory_knowledge.json"
    if not path.exists():
        if not OUTPUT_JSON.exists():
            return []
        data = json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))
        return [
            {
                "subject": canonical_subject(item.get("subject", "")),
                "title": normalize_text(item.get("title")),
                "content": normalize_text(item.get("content")),
                "keywords": [normalize_text(x) for x in item.get("keywords", []) if normalize_text(x)],
                "source": item.get("source", OUTPUT_JSON.name),
            }
            for item in data.get("concepts", [])
            if item.get("title") and item.get("content")
        ]
    data = json.loads(path.read_text(encoding="utf-8"))
    concepts: list[dict] = []
    for subject_name, mapping in data.items():
        subject = canonical_subject(subject_name)
        for pattern, content in mapping.items():
            content_text = normalize_text(content)
            title_match = re.search(r"【([^】]+)】", content_text)
            title = normalize_text(title_match.group(1) if title_match else pattern.split("|")[0])
            body = normalize_text(re.sub(r"^【[^】]+】", "", content_text))
            concepts.append(
                {
                    "subject": subject,
                    "title": title,
                    "content": body,
                    "keywords": [normalize_text(x) for x in pattern.split("|") if normalize_text(x)],
                    "source": path.name,
                }
            )
    return concepts


def extract_pdf_entries(subject: str, filename: str) -> list[dict]:
    path = PDF_DIR / filename
    if not path.exists():
        return []
    reader = PdfReader(str(path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    text = re.sub(r"内部资料.*?(?=\n)", "", text)
    text = re.sub(r"2026 年 5 月.*?(?=\n)", "", text)
    lines = [normalize_text(line) for line in text.splitlines()]
    entries: list[str] = []
    current = ""
    for line in lines:
        if not line:
            continue
        if re.match(r"^\d+[\.．、]", line):
            if current:
                entries.append(current)
            current = line
        elif current:
            current += " " + line
    if current:
        entries.append(current)

    concepts: list[dict] = []
    for entry in entries:
        title = derive_title(entry)
        if not title:
            continue
        content = strip_question_number(entry)
        if not is_valid_concept(title, content):
            continue
        concepts.append(
            {
                "subject": subject,
                "title": title,
                "content": content,
                "keywords": keywords_from_text(title),
                "source": filename,
            }
        )
    return concepts


def derive_title(entry: str) -> str:
    text = strip_question_number(entry)
    text = re.sub(r"^[（(]\d+[）)]", "", text).strip()
    candidates = [
        r"^(.{2,26}?)(?:包括|主要包括|有|具有|划分为|分为|是|指|：|:)",
        r"^(.{2,26}?的(?:功能|特征|原则|内容|方法|类型|关系|职责|权利|义务|要求|阶段|结构))",
    ]
    for pattern in candidates:
        match = re.search(pattern, text)
        if match:
            title = clean_concept_title(match.group(1))
            if 2 <= len(title) <= 32:
                return title
    return ""


def clean_concept_title(raw: str) -> str:
    title = normalize_text(raw).strip(" ：:")
    title = re.sub(r"^依据(.+?)，可将.+$", r"\1分类", title)
    title = re.sub(r"^按(.+?)，可将.+$", r"\1分类", title)
    title = re.sub(r"^依据(.+?)划$", r"\1分类", title)
    title = re.sub(r"可将.*$", "", title).strip(" ，,")
    title = re.sub(r"(课程|教育|研究|法规|道德|心理)$", r"\1", title)
    if title.endswith("的"):
        title = title[:-1]
    return title


def is_valid_concept(title: str, content: str) -> bool:
    text = f"{title} {content}"
    if any(token in text for token in NOISE_TOKENS):
        return False
    if len(title) < 2 or len(title) > 32:
        return False
    if "。" in title or "；" in title:
        return False
    if len(content) < 12:
        return False
    return True


def keywords_from_text(text: str) -> list[str]:
    parts = re.split(r"[，。、；：:（）()“”\"《》\s]+", normalize_text(text))
    return [part for part in parts if 2 <= len(part) <= 12][:6]


def extract_enum_items(content: str) -> list[str]:
    items = re.findall(r"[（(]\d+[）)]\s*([^；。()（）]+)", content)
    cleaned: list[str] = []
    for item in items:
        item = normalize_text(re.split(r"[，,（(]", item)[0])
        item = item.strip("；;。.")
        if 2 <= len(item) <= 28 and item not in cleaned:
            cleaned.append(item)
    if len(cleaned) >= 2:
        return cleaned[:5]
    markers = ["包括：", "包括:", "有：", "有:", "具有：", "具有:", "分为：", "分为:"]
    for marker in markers:
        if marker in content:
            tail = content.split(marker, 1)[1]
            parts = [normalize_text(x).strip("；;。.") for x in re.split(r"[；;、]", tail)]
            cleaned = [x for x in parts if 2 <= len(x) <= 28]
            if len(cleaned) >= 2:
                return cleaned[:5]
    return []


def concept_index(concepts: list[dict]) -> list[dict]:
    seen: dict[tuple[str, str], dict] = {}
    for concept in concepts:
        title = clean_concept_title(concept["title"])
        content = normalize_text(concept["content"])
        if title.endswith("划") or "可将" in title:
            title = derive_title(content) or title
        concept = {
            **concept,
            "title": title,
            "content": content,
            "keywords": keywords_from_text(title) + [kw for kw in concept.get("keywords", []) if normalize_text(kw)],
        }
        if not is_valid_concept(concept["title"], concept["content"]):
            continue
        key = (concept["subject"], concept["title"])
        if key not in seen or len(concept["content"]) > len(seen[key]["content"]):
            seen[key] = concept
    return sorted(seen.values(), key=lambda x: (DECK_ORDER.index(x["subject"]), x["title"]))


def has_single_choice_for_concept(concept: dict, questions: list[dict]) -> bool:
    title = concept["title"]
    keywords = [kw for kw in concept.get("keywords", []) if len(kw) >= 2]
    for row in questions:
        if row["subject"] != concept["subject"] or row["type"] != "单选题":
            continue
        text = row["question"] + " " + " ".join(row["options"].values())
        if title in text:
            return True
        if keywords and sum(1 for kw in keywords if kw in text) >= min(2, len(keywords)):
            return True
    return False


def make_pdf_multi_questions(concepts: list[dict], existing_questions: list[dict]) -> list[dict]:
    generated: list[dict] = []
    for concept in concepts:
        correct_items = extract_enum_items(concept["content"])
        if len(correct_items) < 2:
            continue
        if has_single_choice_for_concept(concept, existing_questions):
            continue
        subject = concept["subject"]
        options_values = correct_items[:5]
        options = {chr(ord("A") + i): value for i, value in enumerate(options_values)}
        answer = "".join(options)
        if len(answer) < 2:
            continue
        generated.append(
            {
                "kind": "question",
                "subject": subject,
                "question": f"根据2026年考前资料，下列属于“{concept['title']}”相关要点的是（多选）",
                "type": "多选题",
                "options": options,
                "answer": answer,
                "analysis": f"正确项来自原文：{concept['content']}",
                "concept": f"{concept['title']}：{concept['content']}",
                "sources": [concept["source"]],
            }
        )
    return generated


def fill_answer_for_concept(concept: dict) -> str:
    enum_items = extract_enum_items(concept["content"])
    if enum_items:
        return "；".join(enum_items)
    return concept["title"]


def make_pdf_fill_questions(concepts: list[dict]) -> list[dict]:
    generated: list[dict] = []
    for concept in concepts:
        answer = fill_answer_for_concept(concept)
        if not answer:
            continue
        enum_items = extract_enum_items(concept["content"])
        if enum_items:
            question = f"根据2026年考前资料，请填空：“{concept['title']}”的主要要点包括：____。"
        else:
            question = f"根据2026年考前资料，请填空：以下表述对应的核心概念是____。\n{concept['content']}"
        generated.append(
            {
                "kind": "question",
                "subject": concept["subject"],
                "question": question,
                "type": "填空题",
                "options": {},
                "answer": answer,
                "analysis": f"填空答案来自原文：{concept['content']}",
                "concept": f"{concept['title']}：{concept['content']}",
                "correct_extension": "",
                "sources": [concept["source"]],
                "concept_question_key": concept_question_key(concept, "blank"),
            }
        )
    return generated


def concept_question_key(concept: dict, qtype: str) -> str:
    return f"{concept['subject']}::{concept['title']}::{qtype}"


def application_context(concept: dict) -> str:
    text = concept["title"] + " " + concept["content"]
    targeted = [
        ("高等教育学", ["课程", "教学"], "某教师设计课程时，把课堂讲授、案例讨论和实践任务结合起来，并要求学生用所学知识解决真实问题"),
        ("高等教育学", ["科研", "科学研究", "研究"], "某高校鼓励教师把科研项目、学术前沿和实验平台转化为学生可参与的学习任务"),
        ("高等教育学", ["社会服务", "服务社会"], "某大学组织教师团队为地方政府和企业提供决策咨询、技术支持与文化服务"),
        ("高等教育学", ["学科", "专业"], "某高校围绕区域发展需求调整学科方向、优化专业结构，并建设稳定的教学科研团队"),
        ("高等教育学", ["人才", "培养"], "某高校修订人才培养方案时，强调知识、能力、素质协调发展"),
        ("高等教育学", ["成绩", "评价", "评定"], "某教师对学生课程表现进行考核时，综合平时表现、实践任务和期末测试结果作出评价"),
        ("高等教育心理学", ["动机", "成就", "奖励"], "教师发现学生学习动力不足，于是调整任务难度和反馈方式，激发学生持续投入"),
        ("高等教育心理学", ["迁移", "经验"], "学生把旧课程中的方法迁移到新问题解决中，教师引导其区分相同点和差异点"),
        ("高等教育心理学", ["记忆", "策略", "元认知"], "教师要求学生制定复习计划、监控理解程度，并根据测试反馈调整学习策略"),
        ("高等教育心理学", ["人格", "气质", "心理健康"], "辅导员发现学生在人际交往和情绪调适上存在困难，准备开展有针对性的心理辅导"),
        ("高等教育法规概论", ["处分", "申诉", "学生"], "某高校处理学生违纪事件时，先告知事实、理由和依据，再听取学生陈述申辩"),
        ("高等教育法规概论", ["教师法", "权利", "义务", "资格"], "某高校制定教师管理制度时，明确教师权利、义务、资格和考核程序"),
        ("高等教育法规概论", ["学位", "学籍"], "学生因学籍、成绩或学位授予问题与学校发生争议，准备查阅校规和上位法依据"),
        ("高等学校教师职业道德修养", ["师德", "职业道德", "为人师表"], "某教师在课堂教学、科研署名和师生交往中坚持以身作则、诚实守信"),
        ("高等学校教师职业道德修养", ["公正", "公平", "关爱"], "教师评价学生时坚持标准一致，并对学习困难学生给予必要支持"),
        ("高等学校教师职业道德修养", ["慎独", "自律", "良心"], "教师在无人监督时仍遵守学术规范和职业规范，拒绝不当利益诱惑"),
    ]
    for subject, keywords, context in targeted:
        if concept["subject"] == subject and any(keyword in text for keyword in keywords):
            return context
    contexts = APPLICATION_CONTEXTS.get(concept["subject"], APPLICATION_CONTEXTS["高等教育学"])
    index = int(hashlib.md5(concept["title"].encode("utf-8")).hexdigest()[:2], 16) % len(contexts)
    return contexts[index]


def make_concept_application_questions(concepts: list[dict]) -> list[dict]:
    generated: list[dict] = []
    for concept in concepts:
        if not concept["title"] or not concept["content"]:
            continue

        enum_items = extract_enum_items(concept["content"])
        context = application_context(concept)
        if len(enum_items) >= 2:
            options_values = enum_items[:5]
            options = {chr(ord("A") + index): value for index, value in enumerate(options_values)}
            answer = "".join(options)
            if len(answer) >= 2:
                generated.append(
                    {
                        "kind": "question",
                        "subject": concept["subject"],
                        "question": f"{context}。若从“{concept['title']}”理解，下列哪些判断更恰当？（多选）",
                        "type": "多选题",
                        "options": options,
                        "answer": answer,
                        "analysis": f"该题把概念放入具体情境考查。正确项来自“{concept['title']}”的关键要点：{concept['content']}",
                        "concept": f"{concept['title']}：{concept['content']}",
                        "correct_extension": "",
                        "sources": [concept.get("source", "concept")],
                        "concept_question_key": concept_question_key(concept, "multi"),
                    }
                )
                continue

        options = {"A": concept["title"]}
        generated.append(
            {
                "kind": "question",
                "subject": concept["subject"],
                "question": f"{context}。这一做法最能体现下列哪一知识点？",
                "type": "单选题",
                "options": options,
                "answer": "A",
                "analysis": f"题干情境体现的是“{concept['title']}”：{concept['content']}",
                "concept": f"{concept['title']}：{concept['content']}",
                "correct_extension": "",
                "sources": [concept.get("source", "concept")],
                "concept_question_key": concept_question_key(concept, "single"),
            }
        )
    return generated


def best_concept_for_question(row: dict, concepts: list[dict]) -> dict | None:
    haystack = row["question"] + " " + " ".join(row["options"].values()) + " " + row.get("analysis", "")
    best: tuple[int, bool, dict] | None = None
    for concept in concepts:
        if concept["subject"] != row["subject"]:
            continue
        score = 0
        title_hit = False
        if concept["title"] and concept["title"] in haystack:
            score += 5
            title_hit = True
        for keyword in concept.get("keywords", []):
            keyword = normalize_text(keyword).replace(".*", "")
            if len(keyword) < 3 or keyword in BROAD_CONCEPT_KEYWORDS:
                continue
            if keyword in haystack:
                score += 1
        if score and (best is None or score > best[0]):
            best = (score, title_hit, concept)
    if not best:
        return None
    if best[1] or best[0] >= 2:
        return best[2]
    return None


def selected_option_text(row: dict) -> str:
    values = []
    for letter in row["answer"]:
        if letter in row["options"]:
            values.append(f"{letter}.{row['options'][letter]}")
    return "、".join(values) if values else row["answer"]


def concept_from_text(subject: str, concept_text: str) -> dict | None:
    concept_text = normalize_text(concept_text)
    if not concept_text:
        return None
    if "：" in concept_text:
        title, content = concept_text.split("：", 1)
    elif ":" in concept_text:
        title, content = concept_text.split(":", 1)
    else:
        title, content = concept_text[:24], concept_text
    title = normalize_text(title).strip("“”\"")
    content = normalize_text(content)
    if not title or title.startswith("本题考查概念"):
        return None
    return {
        "subject": subject,
        "title": title,
        "content": content or concept_text,
        "keywords": keywords_from_text(title),
        "source": "question_concept",
    }


def first_sentence(text: str, max_len: int = 120) -> str:
    text = normalize_text(text)
    if not text:
        return ""
    sentence = re.split(r"[。；;]", text)[0]
    if len(sentence) > max_len:
        sentence = sentence[:max_len].rstrip() + "..."
    return sentence


def build_correct_extension(row: dict, concept: dict | None, concept_text: str) -> str:
    if row.get("correct_extension"):
        return row["correct_extension"]
    if concept:
        return f"{concept['title']}：{first_sentence(concept['content'], 220)}。"
    return ""


def is_template_text(text: str) -> bool:
    text = normalize_text(text)
    template_markers = [
        "本题考查概念",
        "题干关键词",
        "核心概念或典型表现",
        "迁移到同类案例",
        "主体、行为和结果",
        "定义、功能、构成要件或适用范围",
        "该选项与题干关键词绑定记忆",
    ]
    return any(marker in text for marker in template_markers)


def enrich_question(row: dict, concepts: list[dict]) -> dict:
    concept = best_concept_for_question(row, concepts)
    concept_text = row.get("concept") or ""
    if not concept and row.get("concept_question_key") and concept_text:
        concept = concept_from_text(row["subject"], concept_text)
    if concept and not concept_text:
        concept_text = f"{concept['title']}：{concept['content']}"
    explicit_concept = concept_from_text(row["subject"], concept_text)
    if explicit_concept:
        concept = explicit_concept

    reason = row.get("analysis") or ""
    if not reason:
        reason = f"答案选 {row['answer']}，因为该选项表述与题干关键词和对应概念一致；其他选项要么范围不符，要么不是本题考查的核心要点。"
    elif "因此本题应选" not in reason:
        reason = f"{reason} 因此本题应选 {selected_option_text(row)}。"

    row["analysis"] = reason
    extension = build_correct_extension(row, concept, concept_text)
    if is_template_text(concept_text):
        concept_text = ""
    if is_template_text(extension):
        extension = ""
    row["concept"] = concept_text
    row["correct_extension"] = extension
    return row


def merge_questions(rows: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for row in rows:
        if row["type"] != "填空题" and not row["options"]:
            continue
        key = merge_key(row)
        if key not in merged:
            merged[key] = row
            continue
        current = merged[key]
        if len(row["options"]) > len(current["options"]):
            current["options"] = row["options"]
        if row["answer"] and not current["answer"]:
            current["answer"] = row["answer"]
        if row["analysis"] and row["analysis"] not in current["analysis"]:
            current["analysis"] = (current["analysis"] + " " + row["analysis"]).strip()
        if row.get("concept") and not current.get("concept"):
            current["concept"] = row["concept"]
        if row.get("correct_extension") and not current.get("correct_extension"):
            current["correct_extension"] = row["correct_extension"]
        if row["type"] == "多选题":
            current["type"] = "多选题"
        current["sources"] = sorted(set(current["sources"] + row["sources"]))
    type_order = {"单选题": 0, "多选题": 1, "填空题": 2, "判断题": 3}
    return sorted(merged.values(), key=lambda x: (DECK_ORDER.index(x["subject"]), type_order.get(x["type"], 9), x["question"]))


def create_question_model() -> genanki.Model:
    return genanki.Model(
        QUESTION_MODEL_ID,
        "高校教师资格考试-选择题卡",
        fields=[{"name": "Question"}, {"name": "Answer"}, {"name": "Meta"}],
        templates=[
            {
                "name": "选择题",
                "qfmt": "{{Question}}<div class='meta'>{{Meta}}</div>",
                "afmt": "{{FrontSide}}<hr id='answer'>{{Answer}}",
            }
        ],
        css="""
            .card { font-family: "Microsoft YaHei", sans-serif; background: #f8fafc; color: #1f2937; font-size: 18px; line-height: 1.7; text-align: left; }
            .badge { display: inline-block; padding: 2px 10px; margin-bottom: 10px; border-radius: 999px; background: #1d4ed8; color: #fff; font-size: 13px; font-weight: 700; }
            .badge.multi { background: #c2410c; }
            .question { font-size: 20px; font-weight: 700; margin-bottom: 14px; }
            .option { background: #fff; border: 1px solid #dbeafe; border-radius: 8px; padding: 8px 12px; margin: 6px 0; }
            .answer { background: #ecfdf5; border-left: 4px solid #16a34a; padding: 12px; border-radius: 6px; margin-bottom: 12px; font-weight: 700; }
            .block { background: #fff; border-left: 4px solid #2563eb; padding: 12px; border-radius: 6px; margin: 10px 0; white-space: pre-wrap; }
            .block.extend { border-left-color: #16a34a; }
            .meta { margin-top: 10px; color: #64748b; font-size: 12px; }
            hr { border: 0; border-top: 1px solid #cbd5e1; margin: 16px 0; }
        """,
    )


def render_front(row: dict) -> str:
    badge_class = "badge multi" if row["type"] == "多选题" else "badge"
    parts = [f"<div class='{badge_class}'>{html.escape(row['type'])}</div>"]
    parts.append(f"<div class='question'>{html.escape(row['question'])}</div>")
    for key, value in sorted(row.get("options", {}).items()):
        parts.append(f"<div class='option'>{html.escape(key)}. {html.escape(value)}</div>")
    return "".join(parts)


def render_back(row: dict) -> str:
    parts = [f"<div class='answer'>答案：{html.escape(row['answer'] or '未标注')}（{html.escape(selected_option_text(row))}）</div>"]
    if row.get("correct_extension"):
        parts.append(f"<div class='block extend'><b>正确答案概念引申：</b>{html.escape(row.get('correct_extension') or '')}</div>")
    if row.get("concept"):
        parts.append(f"<div class='block'><b>对应概念：</b>{html.escape(row.get('concept') or '')}</div>")
    return "".join(parts)


def save_json(questions: list[dict], concepts: list[dict]) -> None:
    payload = {
        "questions": questions,
        "concepts": concepts,
        "summary": {
            "question_count": len(questions),
            "single_choice_count": sum(1 for row in questions if row["type"] == "单选题"),
            "multi_choice_count": sum(1 for row in questions if row["type"] == "多选题"),
            "blank_count": sum(1 for row in questions if row["type"] == "填空题"),
            "concept_count": len(concepts),
            "subjects": {
                subject: {
                    "questions": sum(1 for row in questions if row["subject"] == subject),
                    "multi_choice": sum(1 for row in questions if row["subject"] == subject and row["type"] == "多选题"),
                    "blank": sum(1 for row in questions if row["subject"] == subject and row["type"] == "填空题"),
                    "concepts": sum(1 for row in concepts if row["subject"] == subject),
                }
                for subject in DECK_ORDER
            },
        },
    }
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_package(questions: list[dict]) -> None:
    model = create_question_model()
    decks = {
        subject: genanki.Deck(DECK_BASE_ID + index + 1, f"高校教师资格考试::{subject}")
        for index, subject in enumerate(DECK_ORDER)
    }
    for row in questions:
        decks[row["subject"]].add_note(
            genanki.Note(
                model=model,
                fields=[render_front(row), render_back(row), f"来源：{', '.join(row['sources'])}"],
                tags=["题目卡", row["subject"], row["type"]],
                guid=stable_guid("question", merge_key(row)),
            )
        )
    genanki.Package(list(decks.values())).write_to_file(OUTPUT_APKG)


def main() -> None:
    seed_questions = load_seed_questions()
    pdf_concepts = []
    for subject, filename in PDF_FILES.items():
        pdf_concepts.extend(extract_pdf_entries(subject, filename))
    concepts = concept_index(load_theory_concepts() + pdf_concepts)
    generated_questions = make_pdf_fill_questions(pdf_concepts)
    questions = merge_questions(seed_questions + generated_questions)
    questions = [enrich_question(row, concepts) for row in questions]
    save_json(questions, concepts)
    build_package(questions)

    print(f"已生成: {OUTPUT_JSON}")
    print(f"已生成: {OUTPUT_APKG}")
    print(f"题目: {len(questions)}，其中单选 {sum(1 for row in questions if row['type'] == '单选题')}，多选 {sum(1 for row in questions if row['type'] == '多选题')}，填空 {sum(1 for row in questions if row['type'] == '填空题')}")
    for subject in DECK_ORDER:
        count = sum(1 for row in questions if row["subject"] == subject)
        multi = sum(1 for row in questions if row["subject"] == subject and row["type"] == "多选题")
        blank = sum(1 for row in questions if row["subject"] == subject and row["type"] == "填空题")
        print(f"{subject}: {count} 题，多选 {multi} 题，填空 {blank} 题")


if __name__ == "__main__":
    main()
