from __future__ import annotations

from pathlib import Path


GROUP_NAME = "2026年4月工学交替班"
ORG_NAME = GROUP_NAME
NOTE_TEXT = GROUP_NAME


def read_text_with_fallback(path: Path) -> str:
    for encoding in ("utf-8", "gbk", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"无法解码文件: {path}")


def encode_qp(value: str) -> str:
    return "".join(f"={byte:02X}" for byte in value.encode("utf-8"))


def build_qp_field(field: str, value: str) -> str:
    encoded = encode_qp(value)
    return f"{field};CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE:{encoded}"


def normalize_phone(value: str) -> str:
    return str(value).strip().replace(" ", "")


def parse_contact_lines(text: str) -> list[dict[str, str]]:
    rows = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parts = [part.strip() for part in line.split("\t")]
        if len(parts) < 8:
            continue
        if parts[0] == "姓名":
            continue

        rows.append(
            {
                "student_name": parts[0],
                "student_phone": normalize_phone(parts[5]),
                "guardian_name": parts[6],
                "guardian_phone": normalize_phone(parts[7]),
            }
        )
    return rows


def build_vcard(contact: dict[str, str]) -> str:
    student_name = contact["student_name"]
    display_name = f"{student_name}同学"

    lines = [
        "BEGIN:VCARD",
        "VERSION:2.1",
        build_qp_field("N", student_name),
        build_qp_field("FN", display_name),
        f"TEL;CELL:{contact['student_phone']}",
        f"TEL;HOME:{contact['guardian_phone']}",
        build_qp_field("ORG", ORG_NAME),
        build_qp_field("NOTE", NOTE_TEXT),
        build_qp_field("X-OPPO-GROUP", GROUP_NAME),
        "END:VCARD",
    ]
    return "\r\n".join(lines)


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    source_path = base_dir / "contact.txt"
    output_path = base_dir / "contact.vcf"

    text = read_text_with_fallback(source_path)
    contacts = parse_contact_lines(text)
    if not contacts:
        raise ValueError(f"未从 {source_path} 解析到联系人数据")

    vcards = "\r\n\r\n".join(build_vcard(contact) for contact in contacts) + "\r\n"
    output_path.write_text(vcards, encoding="utf-8", newline="")
    print(f"已生成 {len(contacts)} 条联系人到: {output_path}")


if __name__ == "__main__":
    main()
