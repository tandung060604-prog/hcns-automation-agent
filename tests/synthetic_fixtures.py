"""PII-free synthetic documents for parser and safety contract tests."""

from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile


def administrative_image_bytes() -> bytes:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (640, 240), "white")
    ImageDraw.Draw(image).text(
        (24, 40),
        "BIEU MAU HANH CHINH SYNTHETIC",
        fill="black",
    )
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def administrative_jpeg_bytes() -> bytes:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (640, 240), "white")
    ImageDraw.Draw(image).text(
        (24, 40),
        "BIEU MAU HANH CHINH SYNTHETIC",
        fill="black",
    )
    output = BytesIO()
    image.save(output, format="JPEG", quality=90)
    return output.getvalue()


def synthetic_text_pdf_bytes(lines: list[str]) -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    for index, line in enumerate(lines):
        page.insert_text((72, 72 + index * 20), line)
    payload = document.tobytes()
    document.close()
    return payload


def synthetic_cv_pdf_bytes() -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "CV SYNTHETIC")
    page.insert_text((72, 92), "HO TEN: NHAN_VIEN_SYNTHETIC_A")
    page.insert_text((72, 112), "KY NANG: KIEM THU TAI LIEU")
    page.insert_text((72, 132), "HOC VAN: CHUONG TRINH SYNTHETIC")
    payload = document.tobytes()
    document.close()
    return payload


def scanned_pdf_bytes() -> bytes:
    import fitz

    image = administrative_image_bytes()
    document = fitz.open()
    page = document.new_page(width=640, height=240)
    page.insert_image(page.rect, stream=image)
    payload = document.tobytes()
    document.close()
    return payload


def mixed_pdf_bytes() -> bytes:
    import fitz

    image = administrative_image_bytes()
    document = fitz.open()
    text_page = document.new_page(width=640, height=240)
    text_page.insert_text((24, 72), "MIXED PDF NATIVE PAGE")
    scan_page = document.new_page(width=640, height=240)
    scan_page.insert_image(scan_page.rect, stream=image)
    payload = document.tobytes()
    document.close()
    return payload


def encrypted_pdf_bytes() -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "SYNTHETIC ENCRYPTED DOCUMENT")
    payload = document.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="synthetic-owner",
        user_pw="synthetic-user",
    )
    document.close()
    return payload


def synthetic_contract_docx_bytes() -> bytes:
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>HOP DONG SYNTHETIC</w:t></w:r></w:p>
    <w:p><w:r><w:t>Dieu khoan kiem thu khong chua PII.</w:t></w:r></w:p>
    <w:p><w:r><w:t>SO HOP DONG: HD-SYNTHETIC-001</w:t></w:r></w:p>
    <w:p><w:r><w:t>HO TEN: NHAN_VIEN_SYNTHETIC_A</w:t></w:r></w:p>
    <w:p><w:r><w:t>NGAY BAT DAU: 2099-01-01</w:t></w:r></w:p>
    <w:p><w:r><w:t>NGAY KET THUC: 2099-12-31</w:t></w:r></w:p>
    <w:p><w:r><w:t>LUONG: 1000000</w:t></w:r></w:p>
    <w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>
      <w:r><w:t>Muc synthetic thu nhat</w:t></w:r>
    </w:p>
    <w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>
      <w:r><w:t>Muc synthetic thu hai</w:t></w:r>
    </w:p>
    <w:tbl>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Truong</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Gia tri</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Loai</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>SYNTHETIC</w:t></w:r></w:p></w:tc>
      </w:tr>
    </w:tbl>
    <w:sectPr/>
  </w:body>
</w:document>"""
    return make_ooxml_zip(
        {
            "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
            "word/document.xml": document_xml,
        }
    )


def synthetic_leave_request_docx_bytes() -> bytes:
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>DON NGHI PHEP SYNTHETIC</w:t></w:r></w:p>
    <w:p><w:r><w:t>HO TEN: NHAN_VIEN_SYNTHETIC_B</w:t></w:r></w:p>
    <w:p><w:r><w:t>TU NGAY: 2099-02-01</w:t></w:r></w:p>
    <w:p><w:r><w:t>DEN NGAY: 2099-02-02</w:t></w:r></w:p>
    <w:p><w:r><w:t>LY DO: KIEM THU QUY TRINH SYNTHETIC</w:t></w:r></w:p>
    <w:sectPr/>
  </w:body>
</w:document>"""
    return make_ooxml_zip(
        {
            "[Content_Types].xml": (
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
            ),
            "word/document.xml": document_xml,
        }
    )


def synthetic_xlsx_bytes() -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "SyntheticSheet"
    worksheet.append(["MA_SYNTHETIC", "GioSang", "GioChieu", "TongGio"])
    worksheet.append(["EMP_SYNTHETIC_A", 4, 4, "=SUM(B2:C2)"])
    worksheet.merge_cells("A4:D4")
    worksheet["A4"] = "SYNTHETIC DATA"
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def synthetic_pptx_bytes() -> bytes:
    slide_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:sp><p:txBody><a:bodyPr/><a:lstStyle/>
    <a:p><a:r><a:t>THONG BAO SYNTHETIC</a:t></a:r></a:p>
  </p:txBody></p:sp></p:spTree></p:cSld>
</p:sld>"""
    return make_ooxml_zip(
        {
            "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
            "ppt/slides/slide1.xml": slide_xml,
        }
    )


def make_ooxml_zip(entries: dict[str, str | bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, mode="w", compression=ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return output.getvalue()
