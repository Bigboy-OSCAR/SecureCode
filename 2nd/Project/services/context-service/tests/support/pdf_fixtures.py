"""[시험 전용] 텍스트 PDF fixture 생성기(4.9).

외부 도구 없이 PDF 1.7 객체를 직접 쓴다. 글꼴은 Identity-H Type0(CID = UTF-16 코드 단위)이고
ToUnicode CMap으로 한글을 되돌린다. 페이지 내용은 FlateDecode로 압축하고, Kids 순서를 객체 번호와
다르게 줄 수 있다. 스캔 페이지(이미지만), 빈 페이지, 암호화 표시(/Encrypt), 손상 파일을 만들 수 있다.
"""

import zlib
from dataclasses import dataclass


@dataclass(frozen=True)
class PageSpec:
    """
    클래스 이름: PageSpec
    기능: 페이지 하나의 줄 목록과 이미지(스캔) 여부.
    작성 날짜: 2026/11/10
    """

    lines: tuple[str, ...] = ()
    image: bool = False


def _hex(text: str) -> str:
    """
    함수 이름: _hex()
    기능: 문자열을 UTF-16BE 코드 단위 hex 문자열로 만든다(Identity-H CID).
    인자: text -> 본문
    반환값: <...> hex 문자열
    작성 날짜: 2026/11/10
    """
    return "<" + text.encode("utf-16-be").hex().upper() + ">"


def _cmap(chars: set[str]) -> bytes:
    """
    함수 이름: _cmap()
    기능: 쓴 문자마다 bfchar 항목이 있는 ToUnicode CMap을 만든다.
    인자: chars -> BMP 문자 집합
    반환값: CMap 바이트
    작성 날짜: 2026/11/10
    """
    entries = sorted(ord(c) for c in chars)
    body = []
    for index in range(0, len(entries), 100):
        chunk = entries[index : index + 100]
        body.append(f"{len(chunk)} beginbfchar")
        body += [f"<{code:04X}> <{code:04X}>" for code in chunk]
        body.append("endbfchar")
    head = (
        "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
        "/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n"
        "1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
    )
    tail = "\nendcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n"
    return (head + "\n".join(body) + tail).encode("ascii")


def _stream(data: bytes, extra: str = "", compress: bool = True) -> bytes:
    """
    함수 이름: _stream()
    기능: stream 객체 본문을 만든다(기본 FlateDecode).
    인자: data -> 원본, extra -> 사전 추가 항목, compress -> 압축 여부
    반환값: 객체 본문 바이트
    작성 날짜: 2026/11/10
    """
    payload = zlib.compress(data) if compress else data
    flt = " /Filter /FlateDecode" if compress else ""
    head = f"<< /Length {len(payload)}{flt}{extra} >>\nstream\n".encode("ascii")
    return head + payload + b"\nendstream"


def build_pdf(pages: list[PageSpec], reverse_kids: bool = False, encrypted: bool = False) -> bytes:
    """
    함수 이름: build_pdf()
    기능: 페이지 명세로 PDF 바이트를 만든다.
    인자: pages -> 페이지 목록, reverse_kids -> 페이지 객체를 거꾸로 만들고 Kids는 올바른 순서로 둔다,
        encrypted -> trailer에 Standard /Encrypt 사전을 넣는다
    반환값: PDF 바이트
    작성 날짜: 2026/11/10
    """
    chars = {c for page in pages for line in page.lines for c in line} | {" "}
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type0 /BaseFont /SecureCodeTest /Encoding /Identity-H "
        b"/DescendantFonts [4 0 R] /ToUnicode 6 0 R >>",
        4: b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /SecureCodeTest "
        b"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
        b"/FontDescriptor 5 0 R /DW 1000 /CIDToGIDMap /Identity >>",
        5: b"<< /Type /FontDescriptor /FontName /SecureCodeTest /Flags 4 "
        b"/FontBBox [0 -200 1000 900] /ItalicAngle 0 /Ascent 900 /Descent -200 "
        b"/CapHeight 700 /StemV 80 >>",
        6: _stream(_cmap(chars)),
        7: _stream(
            b"\xff\x00\x00" * 4,
            " /Type /XObject /Subtype /Image /Width 2 /Height 2 "
            "/ColorSpace /DeviceRGB /BitsPerComponent 8",
        ),
    }
    order = list(range(len(pages)))
    build_order = list(reversed(order)) if reverse_kids else order
    page_ids: dict[int, int] = {}
    next_id = 8
    for index in build_order:
        page_ids[index] = next_id
        next_id += 2
    for index, page in enumerate(pages):
        page_id = page_ids[index]
        ops = ["BT /F1 12 Tf 72 760 Td 14 TL"]
        ops += [f"{_hex(line)} Tj T*" for line in page.lines]
        ops.append("ET")
        if page.image:
            ops.append("q 100 0 0 100 72 72 cm /Im1 Do Q")
        content = "\n".join(ops).encode("ascii") if page.lines or page.image else b""
        objects[page_id + 1] = _stream(content)
        xobject = " /XObject << /Im1 7 0 R >>" if page.image else ""
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {page_id + 1} 0 R "
            f"/Resources << /Font << /F1 3 0 R >>{xobject} >> >>"
        ).encode("ascii")
    kids = " ".join(f"{page_ids[i]} 0 R" for i in order)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii")
    trailer_extra = ""
    if encrypted:
        objects[next_id] = (
            b"<< /Filter /Standard /V 1 /R 2 /P -4 /O <"
            + b"00" * 32
            + b"> /U <"
            + b"00" * 32
            + b"> >>"
        )
        trailer_extra = f" /Encrypt {next_id} 0 R /ID [<{'11' * 16}> <{'11' * 16}>]"
    return _serialize(objects, trailer_extra)


def _serialize(objects: dict[int, bytes], trailer_extra: str) -> bytes:
    """
    함수 이름: _serialize()
    기능: 객체를 번호 순으로 쓰고 정확한 xref·trailer를 붙인다.
    인자: objects -> 객체 번호별 본문, trailer_extra -> trailer 추가 항목
    반환값: PDF 바이트
    작성 날짜: 2026/11/10
    """
    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    size = max(objects) + 1
    offsets = [0] * size
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode("ascii") + objects[number] + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {size}\n0000000000 65535 f \n".encode("ascii")
    for number in range(1, size):
        flag = "n" if number in objects else "f"
        out += f"{offsets[number]:010d} 00000 {flag} \n".encode("ascii")
    out += f"trailer\n<< /Size {size} /Root 1 0 R{trailer_extra} >>\nstartxref\n{xref}\n%%EOF\n".encode(
        "ascii"
    )
    return bytes(out)
