"""MVP content validation. Archives are inspected without extracting to disk."""

from email import policy
from email.parser import BytesParser
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from PIL import Image
from pypdf import PdfReader

TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "eml": "message/rfc822",
    "msg": "application/vnd.ms-outlook",
    "zip": "application/zip",
}
MAX_SIZE = 50 * 1024 * 1024


def validate_document(filename: str, content: bytes) -> tuple[str, str]:
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension not in TYPES:
        raise ValueError("Unsupported file type")
    if not content:
        raise ValueError("Empty file")
    if len(content) > MAX_SIZE:
        raise ValueError("File exceeds 50 MiB upload limit")
    try:
        if extension == "pdf":
            reader = PdfReader(BytesIO(content), strict=True)
            if reader.is_encrypted or not len(reader.pages):
                raise ValueError("Encrypted or empty PDF")
        elif extension in {"jpg", "jpeg", "png"}:
            with Image.open(BytesIO(content)) as image:
                expected = "PNG" if extension == "png" else "JPEG"
                if image.format != expected:
                    raise ValueError("Image type does not match extension")
                image.verify()
        elif extension in {"docx", "xlsx", "zip"}:
            with ZipFile(BytesIO(content)) as archive:
                entries = archive.infolist()
                if len(entries) > 10000 or sum(i.file_size for i in entries) > 100 * 1024 * 1024:
                    raise ValueError("Archive expansion limit exceeded")
                for entry in entries:
                    path = entry.filename.replace("\\", "/")
                    if path.startswith("/") or ":" in path or ".." in path.split("/"):
                        raise ValueError("Unsafe archive path")
                if archive.testzip() is not None:
                    raise ValueError("Corrupted archive")
                if extension != "zip":
                    from defusedxml.ElementTree import fromstring

                    required = "word/document.xml" if extension == "docx" else "xl/workbook.xml"
                    fromstring(archive.read("[Content_Types].xml"))
                    fromstring(archive.read(required))
        elif extension == "eml":
            message = BytesParser(policy=policy.default).parsebytes(content)
            if any(part.defects for part in message.walk()) or not any(
                message.get(h) for h in ("From", "To", "Subject")
            ):
                raise ValueError("Invalid email message")
        elif extension == "msg":
            import olefile

            with olefile.OleFileIO(BytesIO(content)) as message:
                if not message.exists("__properties_version1.0"):
                    raise ValueError("Invalid Outlook message")
                properties = message.openstream("__properties_version1.0").read()
                if len(properties) < 32 or (len(properties) - 32) % 16:
                    raise ValueError("Corrupted Outlook properties")
    except Exception as exc:
        raise ValueError("Corrupted or unsafe document") from exc
    return extension, TYPES[extension]
