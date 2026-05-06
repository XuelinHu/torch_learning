#!/usr/bin/env python3
"""
数据清洗与整合脚本。
读取当前目录下所有JSON文件 → 字段标准化 → 分类映射 → 去重 → 生成Anki apkg。
"""

import re
import json
import html
import random
from pathlib import Path
import genanki

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_APKG = BASE_DIR / "高校教资_整合版.apkg"

# === 标准类别 ===
VALID_CATEGORIES = {"教师职业道德", "教育学", "教育心理学", "教育法规"}

# 类别映射
CATEGORY_MAP = {
    "高等教育学": "教育学",
    "教育法律法规": "教育法规",
    "综合案例分析": None,  # 需根据内容分类
}

# Anki IDs
MODEL_ID = 2025050101
DECK_BASE_ID = 2025050100


def normalize_category(cat: str, question_text: str = "") -> str:
    """标准化类别名称"""
    cat = cat.strip()
    if cat in VALID_CATEGORIES:
        return cat
    if cat in CATEGORY_MAP:
        mapped = CATEGORY_MAP[cat]
        if mapped:
            return mapped
    # 根据题目内容推断
    text_lower = question_text
    if any(kw in text_lower for kw in ["师德", "教师职业", "教师道德", "为人师表", "关爱学生", "爱岗敬业", "教书育人"]):
        return "教师职业道德"
    if any(kw in text_lower for kw in ["教育法", "教师法", "高等教育法", "权利", "义务", "法律责任", "处分", "申诉", "学位"]):
        return "教育法规"
    if any(kw in text_lower for kw in ["心理学", "气质", "人格", "动机", "学习理论", "记忆", "认知", "皮亚杰", "维果"]):
        return "教育心理学"
    return "教育学"


def extract_options_text(options_raw) -> str:
    """统一选项格式为字符串 'A. xxx\nB. xxx\nC. xxx\nD. xxx'"""
    if isinstance(options_raw, str):
        return options_raw

    if isinstance(options_raw, list):
        parts = []
        for item in options_raw:
            if isinstance(item, str):
                # 可能是 "A. xxx" 或 "xxx"
                match = re.match(r'^([A-Z])[\.\、]\s*(.+)', item)
                if match:
                    parts.append(f"{match.group(1)}. {match.group(2)}")
                else:
                    # 按顺序分配字母
                    letter = chr(ord('A') + len(parts))
                    parts.append(f"{letter}. {item}")
            elif isinstance(item, dict):
                letter = item.get('letter', chr(ord('A') + len(parts)))
                text = item.get('text', '')
                parts.append(f"{letter}. {text}")
        return "\n".join(parts)

    if isinstance(options_raw, dict):
        parts = []
        for letter in sorted(options_raw.keys()):
            text = options_raw[letter]
            parts.append(f"{letter}. {text}")
        return "\n".join(parts)

    return str(options_raw)


def standardize_item(item: dict, source_file: str) -> dict | None:
    """将任意格式的题目标准化为统一格式，返回 None 表示跳过"""
    q = {}

    # --- 分类 ---
    cat = item.get("category") or item.get("类别") or ""
    q_text = item.get("question") or item.get("题目") or item.get("text") or ""
    q['category'] = normalize_category(cat, q_text)

    # --- 题目 ---
    q['question'] = q_text.strip()
    if not q['question'] or len(q['question']) < 3:
        return None

    # --- 题型 ---
    qtype = item.get("type") or item.get("题型") or ""
    if qtype in ["single", "radio", "单选题", "单项选择题"]:
        q['type'] = "单选题"
    elif qtype in ["multi", "checkbox", "多选题", "多项选择题"]:
        q['type'] = "多选题"
    elif qtype in ["judge", "判断题"]:
        q['type'] = "判断题"
    else:
        # 根据选项数量或答案推断
        answer_raw = str(item.get("answer") or item.get("答案") or item.get("correct_answer") or "")
        if len(answer_raw.replace(" ", "")) > 1 and all(c in "ABCDEFGH" for c in answer_raw.replace(" ", "")):
            q['type'] = "多选题"
        else:
            q['type'] = "单选题"

    # --- 选项 ---
    options_raw = (
        item.get("options") or item.get("选项")
        or item.get("选择") or []
    )
    # all_questions.json 结构特殊：options是dict数组 {letter, text}
    if isinstance(options_raw, list) and options_raw and isinstance(options_raw[0], dict):
        q['options'] = extract_options_text(options_raw)
    else:
        q['options'] = extract_options_text(options_raw)

    # --- 答案 ---
    answer = (
        item.get("answer") or item.get("答案")
        or item.get("correct_answer") or ""
    )
    q['answer'] = str(answer).strip()

    # --- 解析 ---
    analysis = (
        item.get("analysis") or item.get("解析")
        or item.get("explanation") or item.get("note")
        or item.get("knowledge_point") or ""
    )
    q['analysis'] = str(analysis).strip()

    # --- 来源 ---
    q['source'] = source_file

    return q


def load_all_questions_json(filepath: Path) -> list[dict]:
    """专门处理 all_questions.json 格式（dict by subject）"""
    data = json.loads(filepath.read_text(encoding='utf-8'))
    items = []
    for subject, qlist in data.items():
        cat = normalize_category(subject, "")
        for qitem in qlist:
            items.append({
                'category': cat,
                'question': qitem.get('text', '').strip(),
                'type': qitem.get('type', '单选题'),
                'options': extract_options_text(qitem.get('options', [])),
                'answer': qitem.get('correct_answer', ''),
                'analysis': qitem.get('knowledge_point', ''),
                'source': filepath.name,
            })
    return items


def load_expanded_questions_json(filepath: Path) -> list[dict]:
    """专门处理 expanded_questions.json 格式"""
    data = json.loads(filepath.read_text(encoding='utf-8'))
    items = []
    for subject, qlist in data.items():
        cat = normalize_category(subject, "")
        for qitem in qlist:
            items.append({
                'category': cat,
                'question': qitem.get('text', '').strip(),
                'type': qitem.get('type', '单选题'),
                'options': extract_options_text(qitem.get('options', {})),
                'answer': qitem.get('correct_answer', ''),
                'analysis': qitem.get('note', ''),
                'source': filepath.name,
            })
    return items


def load_all_json_files(base_dir: Path) -> list[dict]:
    """读取所有JSON文件并标准化"""
    all_items = []

    json_files = [
        f for f in base_dir.glob("*.json")
        if f.name != "theory_knowledge.json"
    ]

    for fp in json_files:
        print(f"Reading: {fp.name}...", end=" ")
        try:
            data = json.loads(fp.read_text(encoding='utf-8'))

            # 特殊格式：all_questions.json
            if fp.name == "all_questions.json":
                items = load_all_questions_json(fp)
                print(f"{len(items)} items")
                all_items.extend(items)
                continue

            # 特殊格式：expanded_questions.json
            if fp.name == "expanded_questions.json":
                items = load_expanded_questions_json(fp)
                print(f"{len(items)} items")
                all_items.extend(items)
                continue

            # 通用格式处理
            if isinstance(data, list):
                raw_items = data
            elif isinstance(data, dict) and "questions" in data:
                raw_items = data["questions"]
            else:
                print("SKIP (unknown format)")
                continue

            count = 0
            for item in raw_items:
                std = standardize_item(item, fp.name)
                if std:
                    all_items.append(std)
                    count += 1
            print(f"{count} items")

        except Exception as e:
            print(f"ERROR: {e}")

    return all_items


def deduplicate(items: list[dict]) -> list[dict]:
    """根据 question 字段去重，完全相同的题目只保留一条"""
    seen = {}
    unique = []
    for item in items:
        key = item['question'].strip()
        if key not in seen:
            seen[key] = True
            unique.append(item)
    return unique


def format_card_front(item: dict) -> str:
    """生成Anki卡片正面"""
    qtype = item.get('type', '单选题')
    badge_colors = {
        "单选题": "#4A90D9",
        "多选题": "#E67E22",
        "判断题": "#2ECC71",
    }
    color = badge_colors.get(qtype, "#4A90D9")

    lines = [
        f'<div class="q-header">',
        f'<span class="q-badge" style="background:{color};">{html.escape(qtype)}</span>',
        f'<span class="q-cat">{html.escape(item["category"])}</span>',
        f'</div>',
        f'<div class="q-text">{html.escape(item["question"])}</div>',
        f'<div class="q-options">',
    ]
    for opt_line in item.get('options', '').split('\n'):
        opt_line = opt_line.strip()
        if opt_line:
            lines.append(f'<div class="opt-item">{html.escape(opt_line)}</div>')
    lines.append('</div>')
    return "\n".join(lines)


def format_card_back(item: dict) -> str:
    """生成Anki卡片背面"""
    lines = [
        f'<div class="answer-bar">',
        f'<b>正确答案：{html.escape(item["answer"])}</b>',
        f'</div>',
    ]
    if item.get('analysis'):
        lines.append(
            f'<div class="analysis-box">'
            f'<b>📖 解析：</b>{html.escape(item["analysis"])}'
            f'</div>'
        )
    return "\n".join(lines)


def create_anki_model():
    """创建Anki模型"""
    return genanki.Model(
        MODEL_ID,
        '高校教资整合模型',
        fields=[
            {'name': 'Question'},
            {'name': 'Answer'},
        ],
        templates=[{
            'name': 'Card 1',
            'qfmt': '{{Question}}',
            'afmt': '{{FrontSide}}<hr id="answer">{{Answer}}',
        }],
        css='''
            .card {
                font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
                font-size: 17px; color: #2c3e50;
                background-color: #fafbfc; padding: 0; line-height: 1.8;
            }
            .q-header {
                display: flex; align-items: center; gap: 12px;
                padding: 10px 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-radius: 0 0 12px 12px; margin-bottom: 16px;
            }
            .q-badge {
                padding: 3px 12px; border-radius: 12px;
                font-size: 13px; font-weight: bold; color: #fff;
            }
            .q-cat {
                color: rgba(255,255,255,0.8); font-size: 14px;
            }
            .q-text {
                padding: 0 20px; font-size: 18px; font-weight: 600;
                color: #1a1a2e; margin-bottom: 16px;
            }
            .q-options { padding: 0 20px 16px; }
            .opt-item {
                padding: 8px 14px; margin-bottom: 6px;
                background: #fff; border-radius: 6px;
                border: 1px solid #e8ecf0;
            }
            .answer-bar {
                margin: 12px 16px; padding: 12px 16px;
                background: #eafaf1; border-radius: 6px;
                border-left: 4px solid #27ae60; font-size: 17px;
            }
            .analysis-box {
                margin: 8px 16px 16px; padding: 14px 16px;
                background: #eaf2f8; border-radius: 8px;
                border-left: 4px solid #2980b9; font-size: 15px;
            }
            hr { margin: 16px 0; border: none; border-top: 2px solid #e0e0e0; }
        ''',
    )


def main():
    # 1. 读取所有JSON
    all_items = load_all_json_files(BASE_DIR)
    print(f"\nTotal raw items: {len(all_items)}")

    # 2. 分类统计
    cat_counts = {}
    for item in all_items:
        cat = item['category']
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    for cat, cnt in sorted(cat_counts.items()):
        print(f"  {cat}: {cnt}")

    # 3. 去重
    unique_items = deduplicate(all_items)
    dup_count = len(all_items) - len(unique_items)
    print(f"\nAfter dedup: {len(unique_items)} (removed {dup_count} duplicates)")

    # 4. 生成Anki
    model = create_anki_model()
    decks = {}

    for item in unique_items:
        cat = item['category']
        deck_name = f"高校教资::{cat}"
        if deck_name not in decks:
            deck_id = DECK_BASE_ID + hash(cat) % 1000
            decks[deck_name] = genanki.Deck(deck_id, deck_name)

        tags = [item.get('type', ''), cat, item.get('source', '')]
        note = genanki.Note(
            model=model,
            fields=[format_card_front(item), format_card_back(item)],
            tags=tags,
        )
        decks[deck_name].add_note(note)

    package = genanki.Package(list(decks.values()))
    package.write_to_file(OUTPUT_APKG)

    print(f"\nDecks:")
    for name, deck in sorted(decks.items()):
        cnt = len(deck.notes) if hasattr(deck, 'notes') else 0
        print(f"  {name}: {cnt} cards")

    print(f"\nAPKG saved: {OUTPUT_APKG}")
    print(f"Total cards: {len(unique_items)}")


if __name__ == '__main__':
    main()
