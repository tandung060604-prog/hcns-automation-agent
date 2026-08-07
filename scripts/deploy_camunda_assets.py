"""Deploy the Camunda BPMN and DMN assets to a running Camunda 7 engine.

Uses the standard REST deployment endpoint with multipart/form-data and only
stdlib modules, so it works without installing extra dependencies.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

_BOUNDARY = "----hcns-agent-asset-deploy"
_DEFAULT_ASSETS = (
    ROOT / "camunda" / "HR_DOCUMENT_AGENT_MVP_V2.bpmn",
    ROOT / "camunda" / "HR_DOCUMENT_QUALITY_ROUTING.dmn",
)


def _multipart_body(deployment_name: str, assets: tuple[Path, ...]) -> bytes:
    chunks: list[bytes] = []
    for field, value in (
        ("deployment-name", deployment_name),
        ("enable-duplicate-filtering", "true"),
        ("deploy-changed-only", "true"),
    ):
        chunks.append(f"--{_BOUNDARY}\r\n".encode())
        chunks.append(
            f'Content-Disposition: form-data; name="{field}"\r\n\r\n'.encode()
        )
        chunks.append(f"{value}\r\n".encode())
    for asset in assets:
        chunks.append(f"--{_BOUNDARY}\r\n".encode())
        chunks.append(
            (
                f'Content-Disposition: form-data; name="data"; '
                f'filename="{asset.name}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode()
        )
        chunks.append(asset.read_bytes())
        chunks.append(b"\r\n")
    chunks.append(f"--{_BOUNDARY}--\r\n".encode())
    return b"".join(chunks)


def deploy(
    *,
    base_url: str,
    assets: tuple[Path, ...],
    deployment_name: str,
    timeout_seconds: float = 30.0,
) -> dict[str, object]:
    for asset in assets:
        if not asset.is_file():
            raise FileNotFoundError(f"Asset does not exist: {asset}")
    payload = _multipart_body(deployment_name, assets)
    request = Request(
        base_url.rstrip("/") + "/deployment/create",
        data=payload,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={_BOUNDARY}",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            content = response.read()
    except HTTPError as error:
        raise RuntimeError(f"Camunda deployment returned HTTP {error.code}") from error
    except URLError as error:
        raise RuntimeError("Camunda engine is unavailable") from error
    return dict(json.loads(content.decode("utf-8")))


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine-rest-url",
        default="http://localhost:8080/engine-rest",
        help="Camunda engine-rest base URL (default: http://localhost:8080/engine-rest)",
    )
    args = parser.parse_args()
    deployment_name = f"hr-document-agent-mvp-v2-{uuid.uuid4().hex[:12]}"
    try:
        result = deploy(
            base_url=args.engine_rest_url,
            assets=_DEFAULT_ASSETS,
            deployment_name=deployment_name,
        )
    except (OSError, RuntimeError, json.JSONDecodeError) as error:
        print(f"Deploy failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
