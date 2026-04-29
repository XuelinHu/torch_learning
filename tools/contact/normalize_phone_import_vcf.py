from __future__ import annotations

from pathlib import Path
import re


SOURCE_PATH = Path("tools/Contacts-2026-04-29 (1)-translated/Contacts-2026-04-29 (1).vcf")
OUTPUT_DIR = Path("tools/Contacts-2026-04-29 (1)-phone-import")

TEXT_FIELDS = {"ORG", "NOTE", "X-OPPO-GROUP", "X-ANDROID-CUSTOM"}
XJ_SOFT_PATTERN = re.compile(r"^新疆大学\d+软件工程硕士$")
SHAOYANG_PREFIX_PATTERN = re.compile(r"^(?:\d+计本|\d+通信|\d+级|\d+物联网|\d+网本)$")


def normalize_text_value(value: str) -> str:
    if XJ_SOFT_PATTERN.fullmatch(value):
        return "新疆大学软件学院"
    if SHAOYANG_PREFIX_PATTERN.fullmatch(value):
        return f"邵阳学院{value}"
    return value


def normalize_android_custom(value: str) -> str:
    parts = value.split(";")
    if len(parts) >= 2:
        parts[1] = normalize_text_value(parts[1])
    return ";".join(parts)


def normalize_line(line: str) -> str:
    if ":" not in line:
        return line

    prefix, value = line.split(":", 1)
    field = prefix.split(";", 1)[0]
    if field not in TEXT_FIELDS:
        return line

    if field == "X-ANDROID-CUSTOM":
        return f"{prefix}:{normalize_android_custom(value)}"
    return f"{prefix}:{normalize_text_value(value)}"


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / SOURCE_PATH.name

    text = SOURCE_PATH.read_text(encoding="utf-8")
    normalized_lines = [normalize_line(line) for line in text.splitlines()]
    output_path.write_text("\r\n".join(normalized_lines) + "\r\n", encoding="utf-8", newline="")
    print(f"已写入: {output_path.resolve()}")


if __name__ == "__main__":
    main()
