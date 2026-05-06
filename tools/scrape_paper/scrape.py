#!/usr/bin/env python3
"""
爬取 gxgspxpt.gspxonline.com 试卷内容。
通过 Chrome DevTools Protocol 连接本地已登录的 Chrome 浏览器。
"""

import json
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

TARGET_URL = "http://gxgspxpt.gspxonline.com/GqpxExamTest/PaperTestOnce?paperId=38&tab=vtab1"
OUTPUT_DIR = Path(__file__).resolve().parent

# Chrome 用户数据目录（Windows默认路径，使用后请关闭Chrome）
CHROME_USER_DATA = Path.home() / "AppData/Local/Google/Chrome/User Data"

# CDP 连接端口
CDP_PORT = 9222


def scrape_via_cdp():
    """通过 CDP 连接已打开的 Chrome（需提前以 --remote-debugging-port=9222 启动Chrome）"""
    print(f"尝试通过 CDP 连接 Chrome (端口 {CDP_PORT})...")

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
            print("CDP 连接成功!")
            do_scrape(browser)
            return True
        except Exception as e:
            print(f"CDP 连接失败: {e}")
            return False


def scrape_via_persistent_context():
    """通过持久化用户目录启动 Chrome"""
    import shutil
    import tempfile

    # 复制用户数据到临时目录（避免锁定冲突）
    temp_dir = Path(tempfile.gettempdir()) / "chrome_scrape_profile"

    print(f"准备 Chrome 用户数据...")
    print(f"  源目录: {CHROME_USER_DATA}")
    print(f"  临时目录: {temp_dir}")

    # 只复制关键的会话数据，跳过缓存
    key_dirs = ["Default", "Local State"]
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    for d in key_dirs:
        src = CHROME_USER_DATA / d
        dst = temp_dir / d
        if src.exists():
            try:
                if src.is_dir():
                    shutil.copytree(
                        src, dst,
                        ignore=shutil.ignore_patterns(
                            "Cache", "Code Cache", "GPUCache", "Service Worker",
                            "Storage", "history*", "*.bak", "Bookmarks*"
                        ),
                        dirs_exist_ok=True,
                    )
                else:
                    shutil.copy2(src, dst)
            except Exception as e:
                print(f"  复制 {d} 时出错: {e}")

    print("Chrome 用户数据准备完成")

    with sync_playwright() as p:
        try:
            browser_context = p.chromium.launch_persistent_context(
                user_data_dir=str(temp_dir),
                channel="chrome",
                headless=False,
                accept_downloads=False,
                args=[
                    "--disable-extensions",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            print("Chrome 启动成功!")

            page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
            do_scrape_with_context(browser_context, page)
            browser_context.close()
            return True
        except Exception as e:
            print(f"Chrome 启动失败: {e}")
            return False


def do_scrape(browser):
    """执行爬取（Browser 对象 - CDP模式）"""
    # 检查已有页面或创建新页面
    if browser.contexts:
        context = browser.contexts[0]
        if context.pages:
            page = context.pages[0]
        else:
            page = context.new_page()
    else:
        context = browser.new_context()
        page = context.new_page()

    do_scrape_with_context(context, page)


def do_scrape_with_context(context, page):
    """执行爬取（BrowserContext + Page 对象）"""
    print(f"\n导航到: {TARGET_URL}")
    page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)

    # 等待页面加载
    page.wait_for_timeout(3000)

    current_url = page.url
    print(f"当前URL: {current_url}")

    # 检查是否被重定向到登录页
    if "msg=" in current_url or "login" in current_url.lower():
        print("[!] 被重定向到登录页！Chrome 中可能没有登录态。")
        print("请在可见的 Chrome 窗口中手动登录，然后按回车继续...")
        input()
        page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

    # 获取页面标题
    title = page.title()
    print(f"页面标题: {title}")

    # 保存完整HTML
    html_path = OUTPUT_DIR / "paper_raw.html"
    html_content = page.content()
    html_path.write_text(html_content, encoding='utf-8')
    print(f"HTML已保存: {html_path} ({len(html_content)} 字符)")

    # 截图
    screenshot_path = OUTPUT_DIR / "paper_screenshot.png"
    page.screenshot(path=str(screenshot_path), full_page=True)
    print(f"截图已保存: {screenshot_path}")

    # 尝试提取题目数据
    extract_questions(page)

    print("\n[OK] 爬取完成!")


def extract_questions(page):
    """从页面提取题目结构化数据"""
    questions = page.evaluate("""
        () => {
            const result = [];
            // 尝试多种选择器
            const quItems = document.querySelectorAll('li[id^="qu_"]');

            quItems.forEach(li => {
                const id = li.id;
                const font = li.querySelector('.test_content_nr_tt font');
                const numTag = li.querySelector('.test_content_nr_tt i');

                let questionText = '';
                if (font) {
                    const btn = font.querySelector('input');
                    if (btn) btn.remove();
                    questionText = font.textContent.trim();
                }

                const options = [];
                const optionLis = li.querySelectorAll('li.option');
                optionLis.forEach(optLi => {
                    const label = optLi.querySelector('label');
                    const input = optLi.querySelector('input');
                    if (label) {
                        const p = label.querySelector('p');
                        const text = p ? p.textContent.trim() : label.textContent.trim();
                        // 提取字母
                        const match = text.match(/^([A-Z])\\.?\\s*(.+)/) || text.match(/^([A-Z])\\s+(.+)/);
                        if (match) {
                            options.push({
                                letter: match[1],
                                text: match[2],
                                checked: input ? input.checked : false
                            });
                        }
                    }
                });

                // 正确答案
                const answerLabel = li.querySelector('label[for*="_Answer"]');
                let correctAnswer = '';
                if (answerLabel) {
                    const p = answerLabel.querySelector('p');
                    if (p) correctAnswer = p.textContent.trim();
                }

                // 知识点
                const kpLabel = li.querySelector('label[for*="_KnowledgePoint"]');
                let knowledgePoint = '';
                if (kpLabel) {
                    const p = kpLabel.querySelector('p');
                    if (p) knowledgePoint = p.textContent.trim();
                }

                result.push({
                    id: id,
                    num: numTag ? numTag.textContent.trim() : '',
                    question: questionText,
                    options: options,
                    correctAnswer: correctAnswer,
                    knowledgePoint: knowledgePoint
                });
            });
            return result;
        }
    """)

    if questions:
        print(f"\n提取到 {len(questions)} 道题目")
        qs_path = OUTPUT_DIR / "paper_questions.json"
        qs_path.write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"题目数据已保存: {qs_path}")
    else:
        print("\n未提取到题目（可能需要调整解析逻辑）")
        # 保存页面文本用于手动分析
        text = page.evaluate("() => document.body.innerText")
        text_path = OUTPUT_DIR / "paper_text.txt"
        text_path.write_text(text, encoding='utf-8')
        print(f"页面文本已保存: {text_path}")


def main():
    print("=" * 60)
    print("  高校教资试卷爬虫")
    print("=" * 60)

    # 方式1: CDP连接（Chrome已开启调试端口）
    if scrape_via_cdp():
        return

    print("\n" + "-" * 40)

    # 方式2: 持久化用户目录
    if scrape_via_persistent_context():
        return

    print("\n[FAIL] 两种方式都失败了。")
    print("\n请手动操作:")
    print("1. 关闭所有Chrome窗口")
    print("2. 按 Win+R，输入:")
    print('   chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\\temp\\chrome_debug"')
    print("3. 在新Chrome中打开目标网站并登录")
    print("4. 重新运行本脚本")


if __name__ == "__main__":
    main()
