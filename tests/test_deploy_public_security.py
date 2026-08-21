from pathlib import Path


def test_quick_tunnel_does_not_publish_camunda() -> None:
    source = (Path(__file__).parents[1] / "deploy_public.py").read_text(encoding="utf-8")

    assert 'start_tunnel("camunda"' not in source


def test_dashboard_does_not_send_extracted_fields_to_camunda() -> None:
    source = (
        Path(__file__).parents[1]
        / "apps"
        / "ocr_lab"
        / "api"
        / "serve_dashboard_api.py"
    ).read_text(encoding="utf-8")

    assert "templateFieldsJson" not in source
