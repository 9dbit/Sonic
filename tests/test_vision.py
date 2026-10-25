import base64
import pytest
from sonic.vision import MAX_IMAGE_BYTES, validate_image


def to_b64(data):
    return base64.b64encode(data).decode()


@pytest.mark.parametrize("mime,prefix", [
    ("image/jpeg", b"\xff\xd8\xff\x00"),
    ("image/png", b"\x89PNG\r\n\x1a\n"),
    ("image/webp", b"RIFF1234WEBP")
])
def test_accepted_bounded_image_mime(mime, prefix):
    data = prefix + b"abcdef" * 4
    output = validate_image(mime, to_b64(data))
    assert output.startswith("data:" + mime + ";base64,")


def test_mime_mismatch_rejected():
    with pytest.raises(ValueError, match="MISMATCH"):
        validate_image("image/png", to_b64(b"\xff\xd8\xff" + b"a" * 20))


def test_image_size_is_bounded():
    with pytest.raises(ValueError, match="LARGE"):
        validate_image("image/jpeg", to_b64(b"\xff\xd8\xff" + b"a" * MAX_IMAGE_BYTES))


def test_garbage_and_unsupported_format_rejected():
    with pytest.raises(ValueError):
        validate_image("image/png", "THIS!IS!INVALID")
    with pytest.raises(ValueError):
        validate_image("image/svg+xml", to_b64(b"<svg>"))
