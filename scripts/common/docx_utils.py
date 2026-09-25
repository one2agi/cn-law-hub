"""DOCX parsing and Chinese law article extraction utilities."""

import re
import subprocess
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET


def extract_paragraphs_from_docx(content: bytes) -> list:
    """Extract text paragraphs. Supports .docx (ZIP) and .doc (OLE) formats."""
    if content[:4] == b"PK\x03\x04":  # ZIP = DOCX
        with zipfile.ZipFile(BytesIO(content), "r") as z:
            with z.open("word/document.xml") as f:
                tree = ET.parse(f)
        W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        return [
            "".join(t.text for t in p.iter(f"{W}t") if t.text)
            for p in tree.iter(f"{W}p")
            if any(t.text for t in p.iter(f"{W}t"))
        ]

    # Old .doc format - try antiword or catdoc if available
    for tool in ["antiword", "catdoc"]:
        try:
            result = subprocess.run(
                [tool, "-"], input=content, capture_output=True, timeout=30
            )
            if result.returncode == 0:
                text = result.stdout.decode("utf-8", errors="replace")
                if text.strip():
                    return [line for line in text.split("\n") if line.strip()]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    # Pure-Python MS-DOC (Word 97-2004 binary OLE) extraction fallback
    doc_lines = _extract_from_doc_binary(content)
    if doc_lines:
        return doc_lines

    # Last-resort stream scanner fallback
    fallback_lines = _extract_from_doc_fallback(content)
    if fallback_lines:
        return fallback_lines

    raise RuntimeError(
        "File is in old .doc format and all extraction methods failed."
    )


def _extract_from_doc_binary(content: bytes) -> list:
    """Pure-Python extraction of text from Word 97-2004 (.doc / OLE) files via Piece Table."""
    try:
        import struct
        import olefile

        ole = olefile.OleFileIO(BytesIO(content))
        if not ole.exists("WordDocument"):
            return []
        word_doc = ole.openstream("WordDocument").read()
        if len(word_doc) < 0x01AA:
            return []

        flags = struct.unpack_from("<H", word_doc, 10)[0]
        tbl_name = "1Table" if (flags & 0x0200) else "0Table"
        if not ole.exists(tbl_name):
            tbl_name = "0Table" if ole.exists("0Table") else ("1Table" if ole.exists("1Table") else None)
        if not tbl_name:
            return []

        table = ole.openstream(tbl_name).read()
        fcClx = struct.unpack_from("<I", word_doc, 0x01A2)[0]
        lcbClx = struct.unpack_from("<I", word_doc, 0x01A6)[0]

        if fcClx + lcbClx > len(table):
            return []

        pos = fcClx
        full_text = []
        while pos < fcClx + lcbClx:
            clxt = table[pos]
            pos += 1
            if clxt == 1:
                cb = struct.unpack_from("<H", table, pos)[0]
                pos += 2 + cb
            elif clxt == 2:
                lcb = struct.unpack_from("<I", table, pos)[0]
                pos += 4
                n = (lcb - 4) // 12
                cps = [struct.unpack_from("<I", table, pos + i * 4)[0] for i in range(n + 1)]
                pcds_pos = pos + (n + 1) * 4
                for i in range(n):
                    cp_start = cps[i]
                    cp_end = cps[i + 1]
                    pcd = table[pcds_pos + i * 8 : pcds_pos + (i + 1) * 8]
                    fcValue = struct.unpack_from("<I", pcd, 2)[0]
                    fCompressed = (fcValue & 0x40000000) != 0
                    fc = fcValue & ~0x40000000
                    char_count = cp_end - cp_start
                    if fCompressed:
                        actual_fc = fc // 2
                        raw = word_doc[actual_fc : actual_fc + char_count]
                        text = raw.decode("cp936", errors="replace")
                    else:
                        raw = word_doc[fc : fc + char_count * 2]
                        text = raw.decode("utf-16le", errors="replace")
                    full_text.append(text)
                break

        all_text = "".join(full_text)
        all_text = re.sub(r"\x13[^\x15\r\n]*\x15", "", all_text)
        raw_lines = re.split(r"[\r\n\x07\x0b]+", all_text)
        lines = [l.strip("\x00\x01\x02\x03\x04\x05\x06\x0c\x13\x14\x15\t ") for l in raw_lines]
        return [l for l in lines if l]
    except Exception:
        return []


def _extract_from_doc_fallback(content: bytes) -> list:
    """Fallback scanner for UTF-16LE / CP936 text in OLE streams."""
    try:
        import olefile

        ole = olefile.OleFileIO(BytesIO(content))
        target_streams = []
        if ole.exists("WordDocument"):
            target_streams.append(["WordDocument"])
        for sname in ole.listdir():
            name = sname[0] if isinstance(sname, (list, tuple)) else str(sname)
            if name.startswith("\x05") or name.endswith("SummaryInformation") or name == "CompObj":
                continue
            if sname not in target_streams:
                target_streams.append(sname)

        best_lines = []
        best_chinese_count = 0

        for sname in target_streams:
            try:
                stream_data = ole.openstream(sname).read()
            except Exception:
                continue

            for enc in ("cp936", "utf-16le", "gb18030"):
                try:
                    t = stream_data.decode(enc, errors="ignore")
                    t = re.sub(r"\x13[^\x15\r\n]*\x15", "", t)
                    cur_lines = []
                    cur_chinese_count = 0
                    for l in re.split(r"[\r\n\x07\x0b]+", t):
                        l = l.strip("\x00\x01\x02\x03\x04\x05\x06\x0c\x13\x14\x15\t ")
                        c_count = sum(1 for c in l if "\u4e00" <= c <= "\u9fff")
                        if c_count >= 2 and len(l) >= 4:
                            cur_lines.append(l)
                            cur_chinese_count += c_count

                    if cur_chinese_count > best_chinese_count:
                        best_chinese_count = cur_chinese_count
                        best_lines = cur_lines
                except Exception:
                    pass

            if best_lines and sname in (["WordDocument"], "WordDocument"):
                break

        return best_lines
    except Exception:
        return []


def is_article_line(line: str) -> bool:
    return bool(re.match(r"^第[一二三四五六七八九十百千万零\d]+条", line.strip()))


def extract_article_number(line: str) -> str:
    m = re.match(r"(第[一二三四五六七八九十百千万零\d]+条)", line.strip())
    return m.group(1) if m else line[:20]


def split_into_articles(paragraphs: list) -> list:
    articles = []
    current_num = "题注/前言"
    current_lines = []
    for line in paragraphs:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        if is_article_line(line_stripped):
            if current_lines:
                articles.append((current_num, "\n".join(current_lines)))
            current_num = extract_article_number(line_stripped)
            current_lines = [line_stripped]
        else:
            current_lines.append(line_stripped)
    if current_lines:
        articles.append((current_num, "\n".join(current_lines)))
    return articles


def match_article_query(query: str, article_number: str) -> bool:
    from .chinese_numerals import int_to_chinese

    query = query.strip()
    if query in article_number:
        return True
    m = re.match(r"^第(\d+)条$", query)
    if m:
        n = int(m.group(1))
        return (
            f"第{int_to_chinese(n)}条" == article_number or f"第{n}条" == article_number
        )
    if re.match(r"^\d+$", query):
        n = int(query)
        return f"第{int_to_chinese(n)}条" == article_number
    if re.match(r"^[一二三四五六七八九十百千万零]+$", query):
        return f"第{query}条" == article_number
    return False
