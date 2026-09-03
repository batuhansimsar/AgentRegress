import app as target


def test_download_does_not_escape_upload_directory(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (tmp_path / "secret.txt").write_text("do-not-disclose", encoding="utf-8")
    monkeypatch.setattr(target, "UPLOAD_DIR", str(upload_dir))
    response = target.app.test_client().get("/files/../secret.txt")
    assert response.status_code in (400, 404)
    assert b"do-not-disclose" not in response.data
