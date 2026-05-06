#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

import genanki

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_APKG = BASE_DIR / "高校教师资格考试_4科整合.apkg"
OUTPUT_JSON = BASE_DIR / "anki_merged_cards.json"

QUESTION_MODEL_ID = 2026050601
CONCEPT_MODEL_ID = 2026050602
DECK_BASE_ID = 2026050600

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
    "综合案例分析": "",
}

DECK_ORDER = [
    "高等教育学",
    "高等教育心理学",
    "高等教育法规概论",
    "高等学校教师职业道德修养",
]

QUESTION_FILES = [
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


def canonical_subject(value: str, fallback: str = "") -> str:
    text = (value or fallback or "").strip()
    if text in SUBJECT_ALIASES:
        return SUBJECT_ALIASES[text]
    for alias, target in SUBJECT_ALIASES.items():
        if alias and alias in text:
            return target
    raise ValueError(f"无法识别科目: {text!r}")


def infer_subject_from_question(question: str, fallback: str = "") -> str:
    text = strip_question_number(question)
    rules = [
        (["心理", "认知", "记忆", "动机", "迁移", "气质", "人格", "最近发展区"], "高等教育心理学"),
        (["法律", "法规", "处分", "申诉", "学籍", "学位", "权利", "义务", "教师法", "高等教育法", "作弊"], "高等教育法规概论"),
        (["师德", "教师职业道德", "为人师表", "爱岗敬业", "关爱学生", "职业行为"], "高等学校教师职业道德修养"),
        (["高等教育", "高校", "课程", "教学", "科研", "学科建设", "社会服务"], "高等教育学"),
    ]
    for keywords, subject in rules:
        if any(word in text for word in keywords):
            return subject
    if fallback:
        return canonical_subject(fallback)
    raise ValueError(f"无法根据题干推断科目: {question!r}")


def normalize_text(text: str) -> str:
    text = html.unescape(str(text or ""))
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\u3000", " ").replace("&nbsp;", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_question_number(text: str) -> str:
    return re.sub(r"^\d+[\.．、]\s*", "", normalize_text(text))


def normalize_answer(answer: str) -> str:
    letters = re.findall(r"[A-Z]", str(answer or "").upper())
    if letters:
        return "".join(sorted(dict.fromkeys(letters)))
    return normalize_text(answer)


def normalize_question_type(raw: str, answer: str) -> str:
    text = normalize_text(raw).lower()
    if text in {"single", "radio", "单选题", "单项选择题"}:
        return "单选题"
    if text in {"multi", "checkbox", "多选题", "多项选择题"}:
        return "多选题"
    if text in {"judge", "判断题"}:
        return "判断题"
    letters = normalize_answer(answer)
    if letters and len(letters) > 1 and set(letters) <= set("ABCDEFGH"):
        return "多选题"
    return "单选题"


def options_to_map(raw) -> dict[str, str]:
    if not raw:
        return {}
    result: dict[str, str] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            result[str(key).strip().upper()] = normalize_text(value)
        return dict(sorted(result.items()))
    if isinstance(raw, str):
        parts = re.split(r"[\r\n]+", raw)
        for part in parts:
            line = normalize_text(part)
            if not line:
                continue
            match = re.match(r"^([A-Z])[\.\、\s]*(.+)$", line)
            if match:
                result[match.group(1)] = normalize_text(match.group(2))
            else:
                letter = chr(ord("A") + len(result))
                result[letter] = line
        return result
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                letter = str(item.get("letter", "")).strip().upper()
                text = normalize_text(item.get("text", ""))
                if letter and text:
                    result[letter] = text
            else:
                line = normalize_text(item)
                if not line:
                    continue
                match = re.match(r"^([A-Z])[\.\、\s]*(.+)$", line)
                if match:
                    result[match.group(1)] = normalize_text(match.group(2))
                else:
                    letter = chr(ord("A") + len(result))
                    result[letter] = line
        return result
    return {}


def options_to_text(options: dict[str, str]) -> str:
    return "\n".join(f"{key}. {value}" for key, value in sorted(options.items()))


def question_key(subject: str, question: str) -> str:
    return f"{subject}||{strip_question_number(question)}"


def stable_hash_int(text: str) -> int:
    return int(hashlib.md5(text.encode("utf-8")).hexdigest()[:10], 16)


def stable_guid(prefix: str, text: str) -> str:
    return hashlib.sha1(f"{prefix}::{text}".encode("utf-8")).hexdigest()[:20]


def extract_analysis(item: dict) -> str:
    return normalize_text(
        item.get("analysis")
        or item.get("解析")
        or item.get("explanation")
        or item.get("knowledge_point")
        or item.get("note")
        or ""
    )


def standardize_question(item: dict, subject_hint: str, source_file: str) -> dict | None:
    question = strip_question_number(item.get("question") or item.get("题目") or item.get("text") or "")
    if not question:
        return None
    raw_subject = (item.get("category") or item.get("类别") or subject_hint or "").strip()
    if raw_subject == "综合案例分析":
        subject = infer_subject_from_question(question, fallback=subject_hint)
    else:
        subject = canonical_subject(raw_subject, fallback=subject_hint)
    options = options_to_map(item.get("options") or item.get("选项"))
    answer = normalize_answer(item.get("answer") or item.get("答案") or item.get("correct_answer") or "")
    qtype = normalize_question_type(item.get("type") or item.get("题型") or "", answer)
    return {
        "kind": "question",
        "subject": subject,
        "question": question,
        "type": qtype,
        "options": options,
        "answer": answer,
        "analysis": extract_analysis(item),
        "sources": [source_file],
    }


def load_questions_from_file(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    subject_hint = canonical_subject(path.stem) if path.stem in SUBJECT_ALIASES else ""
    items: list[dict] = []

    if path.name == "all_questions.json":
        for subject, rows in data.items():
            for row in rows:
                std = standardize_question(row, canonical_subject(subject), path.name)
                if std:
                    items.append(std)
        return items

    if path.name == "expanded_questions.json":
        for subject, rows in data.items():
            for row in rows:
                std = standardize_question(row, canonical_subject(subject), path.name)
                if std:
                    items.append(std)
        return items

    if isinstance(data, dict) and "questions" in data:
        rows = data["questions"]
    elif isinstance(data, list):
        rows = data
    else:
        return items

    for row in rows:
        std = standardize_question(row, subject_hint, path.name)
        if std:
            items.append(std)
    return items


def merge_questions(rows: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for row in rows:
        key = question_key(row["subject"], row["question"])
        if key not in merged:
            merged[key] = row
            continue
        current = merged[key]
        if len(row["options"]) > len(current["options"]):
            current["options"] = row["options"]
        if not current["answer"] and row["answer"]:
            current["answer"] = row["answer"]
        if row["analysis"] and row["analysis"] not in current["analysis"]:
            if current["analysis"]:
                current["analysis"] += "\n\n" + row["analysis"]
            else:
                current["analysis"] = row["analysis"]
        if row["type"] == "多选题":
            current["type"] = "多选题"
        current["sources"] = sorted(set(current["sources"] + row["sources"]))
    return sorted(merged.values(), key=lambda x: (DECK_ORDER.index(x["subject"]), x["question"]))


def load_concepts() -> list[dict]:
    theory_path = BASE_DIR / "theory_knowledge.json"
    data = json.loads(theory_path.read_text(encoding="utf-8"))
    cards: list[dict] = []
    for subject, concept_map in data.items():
        canonical = canonical_subject(subject)
        for pattern, content in concept_map.items():
            content_text = normalize_text(content)
            title_match = re.search(r"【([^】]+)】", content_text)
            title = title_match.group(1) if title_match else pattern.split("|")[0]
            title = normalize_text(title)
            keywords = [normalize_text(x) for x in pattern.split("|") if normalize_text(x)]
            body = content_text
            if title_match:
                body = normalize_text(re.sub(r"^【[^】]+】", "", content_text))
            cards.append(
                {
                    "kind": "concept",
                    "subject": canonical,
                    "title": title,
                    "keywords": keywords,
                    "content": body,
                    "source": theory_path.name,
                }
            )
    return cards


def dedupe_concepts(cards: list[dict]) -> list[dict]:
    merged: dict[tuple[str, str], dict] = {}
    for card in cards:
        key = (card["subject"], card["title"])
        if key not in merged:
            merged[key] = card
            continue
        current = merged[key]
        current["keywords"] = sorted(set(current["keywords"] + card["keywords"]))
        if len(card["content"]) > len(current["content"]):
            current["content"] = card["content"]
    return sorted(merged.values(), key=lambda x: (DECK_ORDER.index(x["subject"]), x["title"]))


def create_question_model() -> genanki.Model:
    return genanki.Model(
        QUESTION_MODEL_ID,
        "高校教师资格考试-题目卡",
        fields=[
            {"name": "Question"},
            {"name": "Answer"},
            {"name": "Meta"},
        ],
        templates=[
            {
                "name": "题目卡",
                "qfmt": "{{Question}}<div class='meta'>{{Meta}}</div>",
                "afmt": "{{FrontSide}}<hr id='answer'>{{Answer}}",
            }
        ],
        css="""
            .card {
                font-family: "Microsoft YaHei", sans-serif;
                background: #f8fafc;
                color: #1f2937;
                font-size: 18px;
                line-height: 1.7;
                text-align: left;
            }
            .badge {
                display: inline-block;
                padding: 2px 10px;
                margin-bottom: 10px;
                border-radius: 999px;
                background: #1d4ed8;
                color: #fff;
                font-size: 13px;
                font-weight: 700;
            }
            .question {
                font-size: 20px;
                font-weight: 700;
                margin-bottom: 14px;
            }
            .option {
                background: #fff;
                border: 1px solid #dbeafe;
                border-radius: 8px;
                padding: 8px 12px;
                margin: 6px 0;
            }
            .answer {
                background: #ecfdf5;
                border-left: 4px solid #16a34a;
                padding: 12px;
                border-radius: 6px;
                margin-bottom: 12px;
                font-weight: 700;
            }
            .analysis {
                background: #eff6ff;
                border-left: 4px solid #2563eb;
                padding: 12px;
                border-radius: 6px;
                white-space: pre-wrap;
            }
            .meta {
                margin-top: 10px;
                color: #64748b;
                font-size: 12px;
            }
            hr {
                border: 0;
                border-top: 1px solid #cbd5e1;
                margin: 16px 0;
            }
        """,
    )


def create_concept_model() -> genanki.Model:
    return genanki.Model(
        CONCEPT_MODEL_ID,
        "高校教师资格考试-概念卡",
        fields=[
            {"name": "Front"},
            {"name": "Back"},
            {"name": "Meta"},
        ],
        templates=[
            {
                "name": "概念卡",
                "qfmt": "{{Front}}<div class='meta'>{{Meta}}</div>",
                "afmt": "{{FrontSide}}<hr id='answer'>{{Back}}",
            }
        ],
        css="""
            .card {
                font-family: "Microsoft YaHei", sans-serif;
                background: #fffdf7;
                color: #1f2937;
                font-size: 18px;
                line-height: 1.8;
                text-align: left;
            }
            .title {
                font-size: 22px;
                font-weight: 700;
                margin-bottom: 12px;
            }
            .hint {
                color: #b45309;
                background: #fef3c7;
                border-radius: 8px;
                padding: 10px 12px;
            }
            .content {
                background: #fff;
                border-left: 4px solid #d97706;
                padding: 12px;
                border-radius: 6px;
                white-space: pre-wrap;
            }
            .meta {
                margin-top: 10px;
                color: #78716c;
                font-size: 12px;
            }
            hr {
                border: 0;
                border-top: 1px solid #e7e5e4;
                margin: 16px 0;
            }
        """,
    )


def render_question_front(row: dict) -> str:
    parts = [f"<div class='badge'>{html.escape(row['type'])}</div>"]
    parts.append(f"<div class='question'>{html.escape(row['question'])}</div>")
    for key, value in sorted(row["options"].items()):
        parts.append(f"<div class='option'>{html.escape(key)}. {html.escape(value)}</div>")
    return "".join(parts)


def render_question_back(row: dict) -> str:
    parts = [f"<div class='answer'>答案：{html.escape(row['answer'] or '未标注')}</div>"]
    if row["analysis"]:
        parts.append(f"<div class='analysis'>{html.escape(row['analysis'])}</div>")
    return "".join(parts)


def render_concept_front(card: dict) -> str:
    keywords = " / ".join(card["keywords"][:6])
    return (
        f"<div class='title'>{html.escape(card['title'])}</div>"
        f"<div class='hint'>请回忆该概念的定义、要点或适用场景。"
        f"{'<br>关键词：' + html.escape(keywords) if keywords else ''}</div>"
    )


def render_concept_back(card: dict) -> str:
    return f"<div class='content'>{html.escape(card['content'])}</div>"


def save_merged_json(questions: list[dict], concepts: list[dict]) -> None:
    payload = {
        "questions": questions,
        "concepts": concepts,
        "summary": {
            "question_count": len(questions),
            "concept_count": len(concepts),
            "subjects": {
                subject: {
                    "questions": sum(1 for row in questions if row["subject"] == subject),
                    "concepts": sum(1 for row in concepts if row["subject"] == subject),
                }
                for subject in DECK_ORDER
            },
        },
    }
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    raw_questions: list[dict] = []
    for name in QUESTION_FILES:
        raw_questions.extend(load_questions_from_file(BASE_DIR / name))

    merged_questions = merge_questions(raw_questions)
    concept_cards = dedupe_concepts(load_concepts())
    save_merged_json(merged_questions, concept_cards)

    question_model = create_question_model()
    concept_model = create_concept_model()

    decks = {
        subject: genanki.Deck(DECK_BASE_ID + index + 1, f"高校教师资格考试::{subject}")
        for index, subject in enumerate(DECK_ORDER)
    }

    for row in merged_questions:
        decks[row["subject"]].add_note(
            genanki.Note(
                model=question_model,
                fields=[
                    render_question_front(row),
                    render_question_back(row),
                    f"来源：{', '.join(row['sources'])}",
                ],
                tags=["题目卡", row["subject"], row["type"]],
                guid=stable_guid("question", question_key(row["subject"], row["question"])),
            )
        )

    for card in concept_cards:
        decks[card["subject"]].add_note(
            genanki.Note(
                model=concept_model,
                fields=[
                    render_concept_front(card),
                    render_concept_back(card),
                    f"来源：{card['source']}",
                ],
                tags=["概念卡", card["subject"]],
                guid=stable_guid("concept", f"{card['subject']}::{card['title']}"),
            )
        )

    genanki.Package(list(decks.values())).write_to_file(OUTPUT_APKG)

    print(f"已生成: {OUTPUT_APKG}")
    print(f"已生成中间数据: {OUTPUT_JSON}")
    for subject in DECK_ORDER:
        q_count = sum(1 for row in merged_questions if row["subject"] == subject)
        c_count = sum(1 for row in concept_cards if row["subject"] == subject)
        print(f"{subject}: 题目 {q_count} 张, 概念 {c_count} 张, 合计 {q_count + c_count} 张")
    print(f"总题目数: {len(merged_questions)}")
    print(f"总概念数: {len(concept_cards)}")


if __name__ == "__main__":
    main()
