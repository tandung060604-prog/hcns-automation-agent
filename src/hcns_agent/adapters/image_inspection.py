"""Safe image verification with Pillow."""

from __future__ import annotations

from io import BytesIO

from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.ports.inspection import ImageInspection


class PillowImageInspector:
    def inspect(self, source: DocumentSource) -> ImageInspection:
        try:
            from PIL import Image

            with Image.open(BytesIO(source.content)) as image:
                width, height = image.size
                image_format = (image.format or "").upper()
                image.verify()
        except Exception:
            return ImageInspection(
                width=0,
                height=0,
                media_type="application/octet-stream",
                corrupted=True,
            )

        media_types = {
            "JPEG": "image/jpeg",
            "PNG": "image/png",
            "TIFF": "image/tiff",
            "WEBP": "image/webp",
        }
        return ImageInspection(
            width=width,
            height=height,
            media_type=media_types.get(image_format, "application/octet-stream"),
        )
