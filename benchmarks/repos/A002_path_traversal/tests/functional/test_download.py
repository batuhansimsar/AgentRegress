import app as target


def test_downloads_a_file_inside_the_upload_directory(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / "public.txt").write_text("public document", encoding="utf-8")
    monkeypatch.setattr(target, "UPLOAD_DIR", str(upload_dir))
    response = target.app.test_client().get("/files/public.txt")
    assert response.status_code == 200
    assert response.data == b"public document"
