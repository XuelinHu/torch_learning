#!/usr/bin/env python3
"""
Robust scraper for 4 papers in PaperTestOnce mode.
Flow: Click answer → wait → dismiss modal → extract answer → next.
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


def get_answer_from_page(page) -> str:
    """Extract correct answer from the right-side answer panel."""
    try:
        # The answer is in .answerSheet label.form-control
        ans_label = page.locator('.answerSheet label.form-control')
        if ans_label.count() > 0:
            text = ans_label.first.inner_text().strip()
            if text and re.match(r'^[A-Za-z,]+$', text):
                return text.upper()
    except:
        pass
    # Fallback: read body text
    try:
        body = page.locator('body').inner_text()
        for line in body.split('\n'):
            if '正确答案' in line:
                m = re.search(r'正确答案[：:\s]*([A-Za-z,]+)', line)
                if m:
                    return m.group(1).upper()
    except:
        pass
    return ''


def get_kp_from_page(page) -> str:
    """Extract knowledge point using Playwright locators."""
    try:
        kp_label = page.locator('label[for$="_KnowledgePoint"]')
        if kp_label.count() > 0:
            text = kp_label.first.inner_text()
            return text.replace('知识点：', '').replace('知识点:', '').strip()
    except:
        pass
    return ''


def dismiss_modal(page):
    """Close any bootbox modal by pressing Escape or clicking OK."""
    try:
        ok_btn = page.locator('.bootbox .btn-primary')
        if ok_btn.count() > 0:
            ok_btn.first.click(timeout=3000)
            page.wait_for_timeout(500)
            return
        any_btn = page.locator('.bootbox .btn')
        if any_btn.count() > 0:
            any_btn.first.click(timeout=3000)
            page.wait_for_timeout(500)
            return
    except:
        pass
    try:
        page.keyboard.press('Escape')
    except:
        pass


def process_paper(browser, paper_name: str, paper_url: str, reuse_page=None):
    print(f"\n{'='*60}")
    print(f"[{paper_name}] {paper_url}")

    # Try to reuse an existing logged-in page, or find one on pchome
    page = reuse_page
    if not page:
        # Look for existing logged-in page
        for ctx in browser.contexts:
            for p in ctx.pages:
                if "pchome" in p.url and "msg=" not in p.url:
                    page = p
                    break
        if not page:
            page = browser.contexts[0].new_page()

    if page.url != paper_url and "GqpxExamTest" not in page.url:
        try:
            page.goto(paper_url, wait_until="load", timeout=15000)
        except:
            page.goto(paper_url, timeout=15000)
    page.wait_for_timeout(3000)

    if "msg=" in page.url or "请登录" in page.url:
        print(f"  [!] Login required, trying home page first...")
        # Try navigating via home page
        try:
            page.goto("http://gxgspxpt.gspxonline.com/pchome", wait_until="load", timeout=10000)
            page.wait_for_timeout(2000)
            page.goto(paper_url, wait_until="load", timeout=15000)
            page.wait_for_timeout(3000)
        except:
            pass
        if "msg=" in page.url:
            print(f"  [!] Still needs login, skipping paper")
            return []

    print(f"  Title: {page.title()}")
    try:
        h2 = page.locator('.test_content_title h2').first
        if h2.count() > 0:
            print(f"  Info: {h2.inner_text()}")
    except:
        pass

    all_qs = []
    seen_ids = set()

    for step in range(200):
        try:
            # Check if still on exam page
            if "GqpxExamTest" not in page.url:
                print(f"  Step {step}: Navigated away, done")
                break

            # Get current question via Playwright locator
            qu_el = page.locator('li[id^="qu_"]').first
            if qu_el.count() == 0:
                print(f"  Step {step}: No question element, done")
                break

            qid = qu_el.get_attribute('id')

            if qid in seen_ids:
                # Try clicking next
                try:
                    nb = page.locator('input[value="下一题"]')
                    if nb.count() > 0:
                        nb.first.click(timeout=5000)
                        page.wait_for_timeout(1500)
                except:
                    pass
                # Check again
                new_qid_el = page.locator('li[id^="qu_"]').first
                if new_qid_el.count() > 0:
                    new_qid = new_qid_el.get_attribute('id')
                    if new_qid == qid:
                        print(f"  Step {step}: Stuck on {qid}, done")
                        break
                continue

            seen_ids.add(qid)

            # Get full HTML for BS4 parsing
            html = page.content()
            soup = BeautifulSoup(html, 'lxml')
            qu_lis = soup.find_all('li', id=re.compile(r'^qu_\d+$'))
            if not qu_lis:
                continue
            li = qu_lis[0]

            # --- Extract question ---
            font = li.find('font')
            qtext = font.get_text(strip=True) if font else ''

            # --- Determine type ---
            first_input = li.find('input', class_='radioOrCheck')
            inp_type = first_input.get('type', 'radio') if first_input else 'radio'
            qtype = '多选题' if inp_type == 'checkbox' else '单选题'

            # --- Extract options ---
            options = []
            for opt_li in li.find_all('li', class_=re.compile(r'option')):
                label = opt_li.find('label')
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

            # --- Click answer by clicking the input element directly ---
            if options:
                qid_num = re.search(r'(\d+)$', qid).group(1)
                if qtype == '单选题':
                    chosen = random.choice(options)
                    letter = chosen['letter']
                    # Click the input radio
                    inp_sel = 'input#answer_%s_option_%s' % (qid_num, letter)
                    try:
                        page.locator(inp_sel).first.click(timeout=5000)
                    except:
                        try:
                            page.locator('label[for="answer_%s_option_%s"]' % (qid_num, letter)).first.click(timeout=5000)
                        except:
                            pass
                else:
                    chosen_opts = random.sample(options, min(2, len(options)))
                    for co in chosen_opts:
                        l = co['letter']
                        try:
                            page.locator('input#answer_%s_option_%s' % (qid_num, l)).first.click(timeout=5000)
                            page.wait_for_timeout(400)
                        except:
                            try:
                                page.locator('label[for="answer_%s_option_%s"]' % (qid_num, l)).first.click(timeout=5000)
                            except:
                                pass

            # --- Wait for answer to appear in right panel ---
            max_wait = 15  # seconds
            for _ in range(max_wait):
                page.wait_for_timeout(1000)
                ans_text = get_answer_from_page(page)
                if ans_text:
                    break

            # Dismiss any modal
            dismiss_modal(page)
            page.wait_for_timeout(500)

            # --- Extract answer ---
            correct_answer = get_answer_from_page(page)
            knowledge_point = get_kp_from_page(page)

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
            ans_str = correct_answer or '?'
            if not correct_answer:
                print(f"  [{qnum}] {qtype} | A:{ans_str} | {qtext[:50]}... [NO ANSWER]")
            else:
                print(f"  [{qnum}] {qtype} | A:{ans_str} | {qtext[:50]}...")

            # --- Next question: call JS nextQuestion function directly ---
            try:
                # Extract the next question ID from the button's onclick
                next_btn = page.locator('input[value="下一题"]')
                if next_btn.count() > 0:
                    onclick = next_btn.first.get_attribute('onclick')
                    if onclick:
                        # Execute the onclick directly
                        page.evaluate(f"() => {{ {onclick} }}")
                    else:
                        next_btn.first.click(force=True, timeout=5000)
                else:
                    print(f"    No next button, done")
                    break
            except Exception as e:
                print(f"    Next err: {e}")
                break

            # Wait for next question to load
            page.wait_for_timeout(2000)

            # Verify we moved
            try:
                new_qid_el = page.locator('li[id^="qu_"]').first
                if new_qid_el.count() > 0:
                    new_qid = new_qid_el.get_attribute('id')
                    if new_qid == qid:
                        # Force next via JS
                        try:
                            page.evaluate("""
                                () => {
                                    const btn = document.querySelector('input[value="下一题"]');
                                    if (btn) { const fn = btn.getAttribute('onclick');
                                        if (fn) eval(fn);
                                    }
                                }
                            """)
                            page.wait_for_timeout(2000)
                        except:
                            pass
            except:
                pass

        except Exception as e:
            print(f"  Step {step} ERROR: {e}")
            break

    # Save
    paper_path = OUTPUT_DIR / f"{paper_name}_questions.json"
    paper_path.write_text(json.dumps(all_qs, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"  => {len(all_qs)} questions saved to {paper_path.name}")
    page.close()
    return all_qs


def main():
    print("Connecting to Chrome CDP...")
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")

        # Find the existing exam page or home page with login
        existing_page = None
        for ctx in browser.contexts:
            for p in ctx.pages:
                if "GqpxExamTest" in p.url and "msg=" not in p.url:
                    existing_page = p
                    print(f"Reusing exam page: {p.title()}")
                    break

        total = 0
        for paper_name, paper_url in PAPERS:
            qs = process_paper(browser, paper_name, paper_url, reuse_page=existing_page)
            total += len(qs)
            existing_page = None  # Don't reuse after first (page was navigated)

        # Merge
        all_data = {}
        for paper_name, _ in PAPERS:
            fpath = OUTPUT_DIR / f"{paper_name}_questions.json"
            if fpath.exists():
                all_data[paper_name] = json.loads(fpath.read_text(encoding='utf-8'))

        merged = OUTPUT_DIR / "all_papers_questions.json"
        merged.write_text(json.dumps(all_data, ensure_ascii=False, indent=2), encoding='utf-8')

        print(f"\n{'='*60}")
        print(f"DONE! {total} questions total")


if __name__ == '__main__':
    main()
