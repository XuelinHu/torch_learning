#!/usr/bin/env python3
"""
Anki题库增强版生成脚本 v2.
优化：
  1. 美化卡片格式（3字段模型 + 增强CSS）
  2. 每题添加理论知识备注
  3. 联网扩展真题

4个主题：高等教育学 / 教育心理学 / 教育法规 / 教师职业道德
"""

import re
import json
import html
from pathlib import Path
from bs4 import BeautifulSoup
import genanki

# === 路径配置 ===
BASE_DIR = Path(__file__).resolve().parent
DESKTOP = Path("C:/Users/De/Desktop")
OUTPUT_APKG = BASE_DIR / "高校教师资格考试_增强版.apkg"
QUESTIONS_JSON = BASE_DIR / "all_questions.json"

# === 主题名称 ===
PAPER_NAMES = {
    "练习回顾1.html": "高等教育学",
    "练习回顾2.html": "教育心理学",
    "练习回顾3.html": "教育法规",
    "练习回顾4.html": "教师职业道德",
}

# Anki IDs (固定)
MODEL_ID = 2025010201
DECK_BASE_ID = 2025010200

# === 理论知识库（从JSON文件加载） ===
def load_theory_knowledge():
    theory_file = Path(__file__).resolve().parent / "theory_knowledge.json"
    if theory_file.exists():
        return json.loads(theory_file.read_text(encoding='utf-8'))
    return {}

THEORY_KNOWLEDGE = load_theory_knowledge()


def match_theory(text: str, subject: str, correct_answer: str = "", options: list = None) -> str:
    """根据题目文本+选项内容匹配理论知识，使用评分制"""
    if subject not in THEORY_KNOWLEDGE:
        return ""

    # 构建搜索文本：题目+正确答案+全部选项文本
    search_text = text
    if correct_answer:
        search_text += " " + correct_answer
    if options:
        for opt in options:
            search_text += " " + opt.get('text', '')

    best_match = None
    best_score = 0

    for pattern, theory in THEORY_KNOWLEDGE[subject].items():
        keywords = pattern.split("|")
        total = len(keywords)
        hits = sum(1 for kw in keywords if re.search(kw, search_text))
        score = hits / total if total > 0 else 0
        # 至少需要命中一半的关键词
        if score >= 0.5 and score > best_score:
            best_score = score
            best_match = theory

    return best_match or ""


# === HTML解析（同v1） ===
def parse_html_file(filepath: Path) -> list[dict]:
    soup = BeautifulSoup(filepath.read_text(encoding='utf-8'), 'lxml')
    questions = []

    all_test_titles = soup.find_all('div', class_='test_content_title')
    type_order = []
    for title_div in all_test_titles:
        h2 = title_div.find('h2')
        if h2:
            section_name = h2.get_text(strip=True)
            count_tag = title_div.find('i', class_='content_lit')
            count = int(count_tag.get_text(strip=True)) if count_tag else 0
            if count > 0:
                type_order.append(section_name)

    if not type_order:
        type_order = ['单选题']

    all_nr_divs = soup.find_all('div', class_='test_content_nr')
    real_nr_divs = [d for d in all_nr_divs
                    if d.find_parent('div', class_='rt_content') is None]

    type_idx = 0
    for nr_div in real_nr_divs:
        if type_idx < len(type_order):
            current_type = type_order[type_idx]
            type_idx += 1

        qu_lis = nr_div.find_all('li', id=re.compile(r'^qu_\d+$'))
        for li in qu_lis:
            qu_id = li['id']
            num_tag = li.find('i')
            qu_num = num_tag.get_text(strip=True) if num_tag else ''

            font_tag = li.find('font')
            qu_text = ''
            if font_tag:
                for btn in font_tag.find_all('input'):
                    btn.decompose()
                qu_text = font_tag.get_text(strip=True)

            options = []
            option_lis = li.find_all('li', class_=re.compile(r'option'))
            for opt_li in option_lis:
                label = opt_li.find('label')
                if not label:
                    continue
                raw_parts = []
                for child in label.children:
                    if isinstance(child, str):
                        raw_parts.append(child.strip())
                    elif child.name == 'p':
                        raw_parts.append(child.get_text(strip=True))
                    else:
                        raw_parts.append(child.get_text(strip=True) if hasattr(child, 'get_text') else str(child))
                full_text = ''.join(raw_parts)
                match = re.match(r'([A-Z]+)\.?\s*(.*)', full_text)
                if not match:
                    continue
                opt_letter = match.group(1)
                opt_content = match.group(2).strip()
                input_tag = opt_li.find('input')
                is_checked = input_tag and input_tag.get('checked') is not None
                classes = opt_li.get('class', [])
                is_correct = any(c in ['correctBeenAnswer', 'correctBeenAnswerA'] for c in classes)
                options.append({
                    'letter': opt_letter,
                    'text': opt_content,
                    'checked': is_checked,
                    'is_correct': is_correct,
                })

            answer_label = li.find('label', attrs={'for': re.compile(r'answer_.*_Answer')})
            correct_answer = ''
            if answer_label:
                answer_p = answer_label.find('p')
                if answer_p:
                    correct_answer = answer_p.get_text(strip=True)

            kp_label = li.find('label', attrs={'for': re.compile(r'answer_.*_KnowledgePoint')})
            knowledge_point = ''
            if kp_label:
                kp_p = kp_label.find('p')
                if kp_p:
                    knowledge_point = kp_p.get_text(strip=True)

            checked_opts = [o['letter'] for o in options if o['checked']]
            user_answer = ','.join(checked_opts) if checked_opts else ''

            if options:
                first_input = option_lis[0].find('input', type='checkbox') if option_lis else None
                if first_input:
                    current_type = '多选题'

            questions.append({
                'id': qu_id,
                'num': qu_num,
                'type': current_type,
                'text': qu_text,
                'options': options,
                'correct_answer': correct_answer,
                'user_answer': user_answer,
                'knowledge_point': knowledge_point,
            })

    return questions


# === 格式化函数（增强版） ===
def format_question_front(q: dict) -> str:
    """正面：精美格式的题目 + 选项"""
    qtype = q['type']
    badge_color = "#4A90D9" if qtype == "单选题" else "#E67E22" if qtype == "多选题" else "#2ECC71"
    badge_text = qtype

    lines = []
    lines.append(f'<div class="q-header">')
    lines.append(f'<span class="q-badge" style="background:{badge_color};">{badge_text}</span>')
    lines.append(f'<span class="q-num">第{q["num"]}题</span>')
    lines.append(f'</div>')
    lines.append(f'<div class="q-text">{html.escape(q["text"])}</div>')
    lines.append(f'<div class="q-options">')

    for opt in q['options']:
        label_map = {'A': 'A', 'B': 'B', 'C': 'C', 'D': 'D', 'E': 'E', 'F': 'F'}
        lines.append(
            f'<div class="opt-item">'
            f'<span class="opt-badge">{label_map.get(opt["letter"], opt["letter"])}</span>'
            f'<span class="opt-text">{html.escape(opt["text"])}</span>'
            f'</div>'
        )

    lines.append(f'</div>')
    return "\n".join(lines)


def format_question_back(q: dict) -> str:
    """背面：答案 + 选项分析 + 知识点 + 理论扩展"""
    correct_letters = set(q['correct_answer'].replace(' ', ''))
    user_letters = set(q['user_answer'].replace(',', '').replace(' ', '')) if q['user_answer'] else set()

    lines = []

    # 答案标题栏
    is_correct_user = user_letters == correct_letters and correct_letters
    result_color = "#27ae60" if is_correct_user else "#e74c3c"
    result_icon = "✓" if is_correct_user else "✗"
    lines.append(f'<div class="answer-bar" style="border-left:4px solid {result_color};">')
    lines.append(f'<span class="result-icon" style="color:{result_color};">{result_icon}</span> ')
    lines.append(f'<b>正确答案：{q["correct_answer"]}</b>')
    if not is_correct_user and q['user_answer']:
        lines.append(f' <span class="your-answer">（你的答案：{q["user_answer"]}）</span>')
    lines.append(f'</div>')

    # 选项分析
    lines.append(f'<div class="option-analysis">')
    for opt in q['options']:
        in_correct = opt['letter'] in correct_letters
        in_user = opt['letter'] in user_letters

        if in_correct:
            cls = "opt-correct"
            mark = "✓"
        elif in_user and not in_correct:
            cls = "opt-wrong"
            mark = "✗"
        else:
            cls = "opt-neutral"
            mark = ""

        label_map = {'A': 'A', 'B': 'B', 'C': 'C', 'D': 'D'}
        lines.append(
            f'<div class="opt-result {cls}">'
            f'<span class="opt-badge-sm">{label_map.get(opt["letter"], opt["letter"])}</span>'
            f'<span>{html.escape(opt["text"])}</span>'
            f'{"<span class=\"mark\">" + mark + "</span>" if mark else ""}'
            f'</div>'
        )
    lines.append(f'</div>')

    # 知识点
    if q.get('knowledge_point'):
        lines.append(f'<div class="kp-box"><b>📖 知识点：</b>{q["knowledge_point"]}</div>')

    # 理论扩展
    if q.get('theory_notes'):
        lines.append(f'<div class="theory-box"><b>📚 相关理论：</b>{q["theory_notes"]}</div>')

    return "\n".join(lines)


# === Anki模型（增强版 v2） ===
def create_anki_model_v2():
    return genanki.Model(
        MODEL_ID,
        '高校教师资格考试模型 v2',
        fields=[
            {'name': 'Question'},
            {'name': 'Answer'},
            {'name': 'TheoryNotes'},
        ],
        templates=[
            {
                'name': 'Card 1',
                'qfmt': '{{Question}}',
                'afmt': (
                    '{{FrontSide}}'
                    '<hr id="answer">'
                    '{{Answer}}'
                ),
            },
        ],
        css='''
            .card {
                font-family: "Microsoft YaHei", "PingFang SC", "SimHei", sans-serif;
                font-size: 17px;
                text-align: left;
                color: #2c3e50;
                background-color: #fafbfc;
                padding: 0;
                margin: 0;
                line-height: 1.8;
            }

            /* === 正面样式 === */
            .q-header {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 10px 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-radius: 0 0 12px 12px;
                margin: 0 0 16px 0;
            }
            .q-badge {
                display: inline-block;
                padding: 3px 12px;
                border-radius: 12px;
                font-size: 13px;
                font-weight: bold;
                color: #fff;
                letter-spacing: 1px;
            }
            .q-num {
                color: rgba(255,255,255,0.85);
                font-size: 14px;
            }
            .q-text {
                padding: 0 20px;
                font-size: 18px;
                font-weight: 600;
                color: #1a1a2e;
                margin-bottom: 20px;
                line-height: 1.7;
            }
            .q-options {
                padding: 0 20px 16px 20px;
            }
            .opt-item {
                display: flex;
                align-items: baseline;
                padding: 10px 14px;
                margin-bottom: 8px;
                background: #fff;
                border-radius: 8px;
                border: 1px solid #e8ecf0;
                transition: background 0.2s;
            }
            .opt-badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 28px;
                height: 28px;
                border-radius: 50%;
                background: #eef2ff;
                color: #5b6abf;
                font-weight: 700;
                font-size: 14px;
                margin-right: 12px;
                flex-shrink: 0;
            }
            .opt-text {
                flex: 1;
            }

            /* === 背面样式 === */
            .answer-bar {
                margin: 12px 16px;
                padding: 12px 16px;
                background: #fff;
                border-radius: 6px;
                font-size: 17px;
            }
            .result-icon {
                font-size: 20px;
                font-weight: bold;
            }
            .your-answer {
                color: #999;
                font-size: 14px;
            }
            .option-analysis {
                padding: 0 16px;
            }
            .opt-result {
                display: flex;
                align-items: baseline;
                padding: 8px 12px;
                margin-bottom: 4px;
                border-radius: 6px;
                font-size: 16px;
            }
            .opt-correct {
                background: #eafaf1;
                border-left: 3px solid #27ae60;
            }
            .opt-wrong {
                background: #fdedec;
                border-left: 3px solid #e74c3c;
            }
            .opt-neutral {
                background: transparent;
                border-left: 3px solid transparent;
            }
            .opt-badge-sm {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 24px;
                height: 24px;
                border-radius: 50%;
                background: #eef2ff;
                color: #5b6abf;
                font-weight: 700;
                font-size: 13px;
                margin-right: 10px;
                flex-shrink: 0;
            }
            .mark {
                margin-left: auto;
                font-weight: bold;
                font-size: 16px;
            }
            .opt-correct .mark { color: #27ae60; }
            .opt-wrong .mark { color: #e74c3c; }

            .kp-box {
                margin: 16px 16px 8px 16px;
                padding: 12px 16px;
                background: #fef9e7;
                border-radius: 8px;
                border-left: 4px solid #f39c12;
                font-size: 15px;
            }
            .theory-box {
                margin: 8px 16px 16px 16px;
                padding: 14px 16px;
                background: #eaf2f8;
                border-radius: 8px;
                border-left: 4px solid #2980b9;
                font-size: 15px;
                line-height: 1.7;
            }
            hr {
                margin: 16px 0;
                border: none;
                border-top: 2px solid #e0e0e0;
            }
        ''',
    )


def main():
    html_files = [
        DESKTOP / "练习回顾1.html",
        DESKTOP / "练习回顾2.html",
        DESKTOP / "练习回顾3.html",
        DESKTOP / "练习回顾4.html",
    ]

    model = create_anki_model_v2()
    all_decks = []
    total_questions = 0
    theory_hits = 0

    for idx, html_file in enumerate(html_files):
        filename = html_file.name
        paper_name = PAPER_NAMES.get(filename, filename)

        questions = parse_html_file(html_file)

        deck_id = DECK_BASE_ID + idx + 1
        deck_name = f"高校教资::{paper_name}"
        deck = genanki.Deck(deck_id, deck_name)

        q_count = {'单选题': 0, '多选题': 0, '判断题': 0}
        for q in questions:
            q_count[q['type']] = q_count.get(q['type'], 0) + 1

            # 匹配理论知识（基于题目文本+选项+正确答案综合匹配）
            theory = match_theory(
                q['text'],
                paper_name,
                correct_answer=q.get('correct_answer', ''),
                options=q.get('options', [])
            )
            q['theory_notes'] = theory
            if theory:
                theory_hits += 1

            tags = [q['type'], paper_name]

            note = genanki.Note(
                model=model,
                fields=[
                    format_question_front(q),
                    format_question_back(q),
                    "",  # TheoryNotes 已嵌入 Answer 背面
                ],
                tags=tags,
            )
            deck.add_note(note)

        all_decks.append(deck)
        total_questions += len(questions)

        print(f"{paper_name}: {len(questions)} 题", end='')
        for t, c in sorted(q_count.items()):
            print(f" [{t}: {c}]", end='')
        print()

    # === 加载扩展题目 ===
    expanded_json = BASE_DIR / "expanded_questions.json"
    if expanded_json.exists():
        expanded_data = json.loads(expanded_json.read_text(encoding='utf-8'))
        expand_count = 0
        for subject, eq_list in expanded_data.items():
            deck_id = DECK_BASE_ID + 10 + hash(subject) % 100
            deck_name = f"高校教资::{subject}（扩展）"
            deck = genanki.Deck(deck_id, deck_name)
            for eq in eq_list:
                note = genanki.Note(
                    model=model,
                    fields=[
                        format_expanded_front(eq),
                        format_expanded_back(eq),
                        "",
                    ],
                    tags=[eq.get('type', '单选题'), subject, '扩展'],
                )
                deck.add_note(note)
                expand_count += 1
            all_decks.append(deck)
        print(f"\n扩展题目: {expand_count} 题")

    # 生成apkg
    package = genanki.Package(all_decks)
    package.write_to_file(OUTPUT_APKG)
    print(f"\n总计: {total_questions} 题 (理论覆盖: {theory_hits})")
    if expanded_json.exists():
        print(f"扩展: {expand_count} 题")
    print(f"增强版 Anki 文件: {OUTPUT_APKG}")


def format_expanded_front(eq: dict) -> str:
    qtype = eq.get('type', '单选题')
    badge_color = "#4A90D9" if qtype == "单选题" else "#E67E22"
    lines = []
    lines.append(f'<div class="q-header">')
    lines.append(f'<span class="q-badge" style="background:{badge_color};">{qtype}</span>')
    lines.append(f'<span class="q-num">扩展题</span>')
    lines.append(f'</div>')
    lines.append(f'<div class="q-text">{html.escape(eq["text"])}</div>')
    lines.append(f'<div class="q-options">')
    for letter, text in eq.get('options', {}).items():
        lines.append(
            f'<div class="opt-item">'
            f'<span class="opt-badge">{letter}</span>'
            f'<span class="opt-text">{html.escape(text)}</span>'
            f'</div>'
        )
    lines.append(f'</div>')
    return "\n".join(lines)


def format_expanded_back(eq: dict) -> str:
    lines = []
    lines.append(f'<div class="answer-bar" style="border-left:4px solid #27ae60;">')
    lines.append(f'<b>正确答案：{eq["correct_answer"]}</b>')
    lines.append(f'</div>')
    lines.append(f'<div class="option-analysis">')
    correct_letters = set(eq['correct_answer'].replace(' ', ''))
    for letter, text in eq.get('options', {}).items():
        if letter in correct_letters:
            lines.append(
                f'<div class="opt-result opt-correct">'
                f'<span class="opt-badge-sm">{letter}</span><span>{text}</span>'
                f'<span class="mark">✓</span></div>'
            )
        else:
            lines.append(
                f'<div class="opt-result opt-neutral">'
                f'<span class="opt-badge-sm">{letter}</span><span>{text}</span></div>'
            )
    lines.append(f'</div>')
    if eq.get('note'):
        lines.append(f'<div class="theory-box"><b>📚 解析：</b>{eq["note"]}</div>')
    return "\n".join(lines)


if __name__ == '__main__':
    main()
