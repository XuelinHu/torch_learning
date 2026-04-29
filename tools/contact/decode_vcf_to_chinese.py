from __future__ import annotations

from pathlib import Path
import quopri
import re


QP_PATTERN = re.compile(r"^(?P<prefix>[^:]+;ENCODING=QUOTED-PRINTABLE:)(?P<value>.*)$")


def unfold_lines(text: str) -> list[str]:
    lines = text.splitlines()
    unfolded: list[str] = []
    for line in lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        elif unfolded and "ENCODING=QUOTED-PRINTABLE" in unfolded[-1] and unfolded[-1].endswith("="):
            unfolded[-1] = unfolded[-1][:-1] + line
        else:
            unfolded.append(line)
    return unfolded


def decode_qp_line(line: str) -> str:
    match = QP_PATTERN.match(line)
    if not match:
        return line

    prefix = match.group("prefix").replace(";ENCODING=QUOTED-PRINTABLE", "")
    value = match.group("value")
    try:
        decoded = quopri.decodestring(value.encode("ascii")).decode("utf-8")
    except Exception:
        return line
    return f"{prefix}{decoded}"


def main() -> None:
    source_path = Path("tools/Contacts-2026-04-29 (1).vcf")
    output_dir = Path("tools/Contacts-2026-04-29 (1)-translated")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / source_path.name

    raw_text = source_path.read_text(encoding="utf-8")
    decoded_lines = [decode_qp_line(line) for line in unfold_lines(raw_text)]
    output_path.write_text("\r\n".join(decoded_lines) + "\r\n", encoding="utf-8", newline="")
    print(f"已写入: {output_path.resolve()}")


if __name__ == "__main__":
    main()
