#!/usr/bin/env python3
"""
按顺序抓取4张试卷 (PaperTestOnce模式)
每题：随机选答案 → 等5秒 → 提取正确答案 → 下一题
"""

import json, re, time, random, sys
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path(__file__).resolve().parent

PAPERS = [
    ("paper_38", "http://gxgspxpt.gspxonline.com/GqpxExamTest/PaperTestOnce?paperId=38&tab=vtab1"),
    ("paper_35", "http://gxgspxpt.gspxonline.com/GqpxExamTest/PaperTestOnce?paperId=35&tab=vtab1"),
    ("paper_41", "http://gxgspxpt.gspxonline.com/GqpxExamTest/PaperTestOnce?paperId=41&tab=vtab1"),
    ("paper_43", "http://gxgspxpt.gspxonline.com/GqpxExamTest/PaperTestOnce?paperId=43&tab=vtab1"),
]


def extract_correct_answer_from_page(page) -> str:
    """从页面提取正确答案"""
    html = page.content()
    soup = BeautifulSoup(html, 'lxml')
    for label in soup.find_all('label', attrs={'for': re.compile(r'answer_.*_Answer')}):
        p = label.find('p')
        if p:
            ans = p.get_text(strip=True)
            if ans:
                return ans.upper()
    return ''


def extract_knowledge_point(page) -> str:
    """从页面提取知识点"""
    html = page.content()
    soup = BeautifulSoup(html, 'lxml')
    for label in soup.find_all('label', attrs={'for': re.compile(r'answer_.*_KnowledgePoint')}):
        p = label.find('p')
        if p:
            return p.get_text(strip=True)
    return ''


def process_paper(browser, paper_name: str, paper_url: str):
    print(f"\n{'=' * 60}")
    print(f"Paper: {paper_name}")
    print(f"URL: {paper_url}")

    page = browser.contexts[0].new_page()
    page.goto(paper_url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3000)

    if "msg=" in page.url or "请登录" in page.url:
        print(f"[!] Login required! URL: {page.url}")
        page.close()
        return []

    print(f"Title: {page.title()}")

    all_qs = []
    seen_ids = set()

    for step in range(150):
        try:
            html = page.content()
            soup = BeautifulSoup(html, 'lxml')
            qu_lis = soup.find_all('li', id=re.compile(r'^qu_\d+$'))

            if not qu_lis:
                print(f"  Step {step}: No question, finished?")
                break

            li = qu_lis[0]
            qid = li['id']

            if qid in seen_ids:
                next_btn = page.locator('input[value="下一题"]')
                if next_btn.count() > 0:
                    next_btn.first.click()
                    page.wait_for_timeout(1000)
                    continue
                else:
                    print(f"  Step {step}: Repeated question, no next btn, done")
                    break

            seen_ids.add(qid)

            # --- Extract question text ---
            font = li.find('font')
            qtext = ''
            if font:
                for btn in font.find_all('input'):
                    btn.decompose()
                qtext = font.get_text(strip=True)

            # --- Determine type ---
            qtype = '单选题'
            section = li.find_parent('div', class_='test_content_nr')
            if section:
                prev = section.find_previous_sibling('div', class_='test_content')
                if prev:
                    h2 = prev.find('h2')
                    if h2:
                        qtype = h2.get_text(strip=True)

            # --- Extract options ---
            options = []
            option_lis = li.find_all('li', class_=re.compile(r'option'))
            for opt_li in option_lis:
                label = opt_li.find('label')
                input_tag = opt_li.find('input')
                if label:
                    raw = ''
                    for child in label.children:
                        if isinstance(child, str):
                            raw += child.strip()
                        elif child.name == 'p':
                            raw += child.get_text(strip=True)
                    m = re.match(r'([A-Z]+)\.?\s*(.*)', raw)
                    if m:
                        options.append({'letter': m.group(1), 'text': m.group(2)})
                if input_tag and input_tag.get('type') == 'checkbox':
                    qtype = '多选题'

            # --- Randomly click an answer ---
            if options:
                chosen = random.choice(options)
                letter = chosen['letter']
                try:
                    # Click the label for this option
                    opt_label = page.locator(f'label[for$="option_{letter}"]')
                    if opt_label.count() > 0:
                        opt_label.first.click()
                    else:
                        opt_input = page.locator(f'input[id$="option_{letter}"]')
                        if opt_input.count() > 0:
                            opt_input.first.click()
                except Exception as e:
                    print(f"  Click error: {e}")

            # --- Wait for modal to appear ---
            page.wait_for_timeout(3000)

            # --- Dismiss the answer result modal ---
            # Try various ways to close the bootbox modal
            try:
                # Try clicking "确定" button in modal
                ok_btn = page.locator('.bootbox .btn-primary')
                if ok_btn.count() > 0:
                    ok_btn.first.click()
                    page.wait_for_timeout(500)
                else:
                    # Try clicking any button in the modal
                    modal_btn = page.locator('.bootbox .btn')
                    if modal_btn.count() > 0:
                        modal_btn.first.click()
                        page.wait_for_timeout(500)
                    else:
                        # Try pressing Escape
                        page.keyboard.press('Escape')
                        page.wait_for_timeout(500)
            except:
                page.keyboard.press('Escape')
                page.wait_for_timeout(500)

            # --- Extract correct answer ---
            correct_answer = extract_correct_answer_from_page(page)
            knowledge_point = extract_knowledge_point(page)

            all_qs.append({
                'id': qid,
                'num': len(all_qs) + 1,
                'type': qtype,
                'text': qtext,
                'options': options,
                'correctAnswer': correct_answer,
                'knowledgePoint': knowledge_point,
            })

            qnum = len(all_qs)
            print(f"  [{qnum}] {qtype} | Ans: {correct_answer} | {qtext[:55]}...")

            # --- Click next (use keyboard or direct JS to avoid modal blocking) ---
            try:
                # Try clicking via JS to bypass modal
                page.evaluate("""
                    () => {
                        const btns = document.querySelectorAll('input[value="下一题"]');
                        if (btns.length > 0) btns[0].click();
                    }
                """)
                page.wait_for_timeout(1000)
            except:
                pass

            # Check if still on same question
            new_html = page.content()
            if f'id="{qid}"' in new_html:
                # Still stuck, try force click
                try:
                    next_btn = page.locator('input[value="下一题"]').first
                    next_btn.click(force=True, timeout=5000)
                    page.wait_for_timeout(1000)
                except:
                    print(f"    Cannot proceed, breaking")
                    break

        except Exception as e:
            print(f"  Step {step} ERROR: {e}")
            import traceback
            traceback.print_exc()
            break

    paper_path = OUTPUT_DIR / f"{paper_name}_questions.json"
    paper_path.write_text(json.dumps(all_qs, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"  => Saved: {len(all_qs)} questions to {paper_path.name}")

    page.close()
    return all_qs


def main():
    print("Connecting to Chrome CDP...")
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")

        total = 0
        for paper_name, paper_url in PAPERS:
            qs = process_paper(browser, paper_name, paper_url)
            total += len(qs)

        # Merge all into one file
        all_data = {}
        for paper_name, _ in PAPERS:
            fpath = OUTPUT_DIR / f"{paper_name}_questions.json"
            if fpath.exists():
                all_data[paper_name] = json.loads(fpath.read_text(encoding='utf-8'))

        merged_path = OUTPUT_DIR / "all_papers_questions.json"
        merged_path.write_text(json.dumps(all_data, ensure_ascii=False, indent=2), encoding='utf-8')

        print(f"\n{'=' * 60}")
        print(f"DONE! Total: {total} questions across 4 papers")
        print(f"Merged: {merged_path}")


if __name__ == '__main__':
    main()
