import base64
import io
import math
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from werkzeug.datastructures import FileStorage

import portrait_service


def image_bytes(fmt='PNG', size=(120, 180), mode='RGB'):
    buffer = io.BytesIO()
    Image.new(mode, size, (180, 40, 60) if mode == 'RGB' else (180, 40, 60, 128)).save(buffer, fmt)
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, foreground):
        self.foreground = foreground
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if 'oauth' in url:
            return FakeResponse({'access_token': 'token', 'expires_in': 3600})
        return FakeResponse({'foreground': base64.b64encode(self.foreground).decode('ascii')})


class PortraitServiceTest(unittest.TestCase):
    def test_upload_is_normalised_for_segmentation(self):
        storage = FileStorage(stream=io.BytesIO(image_bytes()), filename='portrait.png')
        normalised = portrait_service._normalise_image(portrait_service._read_upload(storage))
        image = Image.open(io.BytesIO(normalised))
        self.assertEqual(image.format, 'JPEG')
        self.assertEqual(image.size, (120, 180))

    def test_invalid_image_is_rejected(self):
        storage = FileStorage(stream=io.BytesIO(b'not-an-image'), filename='portrait.jpg')
        with self.assertRaisesRegex(portrait_service.PortraitError, '仅支持'):
            portrait_service._normalise_image(portrait_service._read_upload(storage))

    def test_oversized_dimensions_are_rejected_before_decode(self):
        with patch.object(portrait_service, 'MAX_IMAGE_PIXELS', 100):
            with self.assertRaisesRegex(portrait_service.PortraitError, '像素过大'):
                portrait_service._normalise_image(image_bytes(size=(20, 20)))

    def test_pillow_decompression_bomb_is_reported_as_validation_error(self):
        with patch.object(
            portrait_service.Image,
            'open',
            side_effect=Image.DecompressionBombError('too many pixels'),
        ):
            with self.assertRaisesRegex(portrait_service.PortraitError, '像素过大'):
                portrait_service._normalise_image(image_bytes())

    def test_saved_portrait_filename_is_content_versioned(self):
        with tempfile.TemporaryDirectory(prefix='portrait-version-test-') as storage_dir, \
                patch.object(portrait_service, 'PLAYER_PORTRAIT_STORAGE_PATH', storage_dir), \
                patch.object(portrait_service, '_segment', side_effect=[b'cutout-one', b'cutout-two']):
            first = portrait_service.save_portrait(
                'player-one',
                FileStorage(stream=io.BytesIO(image_bytes()), filename='first.png'),
            )
            second = portrait_service.save_portrait(
                'player-one',
                FileStorage(stream=io.BytesIO(image_bytes()), filename='second.png'),
            )
        self.assertNotEqual(first, second)
        self.assertTrue(first[1].endswith('-cutout.webp'))
        self.assertTrue(second[1].endswith('-cutout.webp'))

    def test_baidu_response_becomes_transparent_webp(self):
        foreground = image_bytes(mode='RGBA')
        session = FakeSession(foreground)
        with patch.object(portrait_service, 'BAIDU_BODY_API_KEY', 'key'), \
                patch.object(portrait_service, 'BAIDU_BODY_SECRET_KEY', 'secret'), \
                patch.object(portrait_service, '_token_value', ''), \
                patch.object(portrait_service, '_token_expires_at', 0):
            result = portrait_service._segment(image_bytes('JPEG'), session=session)
        image = Image.open(io.BytesIO(result))
        self.assertEqual(image.format, 'WEBP')
        self.assertEqual(image.mode, 'RGBA')
        self.assertEqual(len(session.calls), 2)

    def test_transform_values_are_bounded(self):
        self.assertEqual(
            portrait_service.clamp_transform(5, -100, 100),
            (2.2, -50.0, 50.0),
        )

    def test_non_finite_transform_is_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaisesRegex(portrait_service.PortraitError, '参数无效'):
                portrait_service.clamp_transform(value, 0, 0)


if __name__ == '__main__':
    unittest.main()
