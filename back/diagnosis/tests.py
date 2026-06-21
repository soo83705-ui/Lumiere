from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from diagnosis.domain.palette_seed_data import PALETTE_SEED_DATA, validate_palette_seed_data
from diagnosis.domain.tone_keys import CANONICAL_TONE_KEYS
from diagnosis.domain.tone_key_normalizer import ToneKeyError, normalize_tone_key
from diagnosis.models import DiagnosisResult, PersonalColor, PersonalColorPalette
from diagnosis.services.makeup_generation import build_makeup_generation_prompt
from diagnosis.services.multimodal_diagnosis import validate_diagnosis_payload
from diagnosis.services.palettes import get_palette_for_tone_key, serialize_palette
from diagnosis.services.workflow import ImageQualityError


class ToneKeyNormalizerTests(TestCase):
    def test_normalizes_aliases(self):
        self.assertEqual(normalize_tone_key('fall-cool-muted'), 'autumn_cool_mute')
        self.assertEqual(normalize_tone_key('winter cool clear'), 'winter_cool_bright')

    def test_rejects_unknown_tone_key(self):
        with self.assertRaises(ToneKeyError):
            normalize_tone_key('summer_cool_true')


class DiagnosisPayloadValidationTests(TestCase):
    def test_rejects_invalid_tone_key(self):
        payload = {
            'toneKey': 'summer_cool_true',
            'toneName': 'Summer Cool True',
            'confidence': 0.8,
            'summary': 'summary',
            'analysis': {
                'temperature': 'cool',
                'brightness': 'medium',
                'chroma': 'low_to_medium',
                'contrast': 'low',
                'skinUndertone': 'pink',
                'recommendedIntensity': 'soft',
            },
            'evidence': {
                'skinToneReason': 'reason',
                'contrastReason': 'reason',
                'chromaReason': 'reason',
            },
            'cautions': ['lighting can affect the result'],
        }

        with self.assertRaises(ValidationError):
            validate_diagnosis_payload(payload)


class PaletteServiceTests(TestCase):
    @override_settings(DEBUG=True)
    def test_missing_palette_returns_preparing_fallback(self):
        palette, status = get_palette_for_tone_key('winter_cool_bright')

        self.assertEqual(status, 'preparing')
        self.assertEqual(palette['toneName'], '팔레트 준비 중')
        self.assertEqual(palette['requestedToneKey'], 'winter_cool_bright')
        self.assertGreater(len(palette['bestColors']), 0)

    @override_settings(DEBUG=False)
    def test_missing_palette_returns_missing_without_dev_fallback(self):
        palette, status = get_palette_for_tone_key('winter_cool_bright')

        self.assertEqual(status, 'missing')
        self.assertEqual(palette['toneKey'], 'winter_cool_bright')
        self.assertTrue(palette['isPlaceholder'])

    def test_seeded_palette_is_ready_for_any_canonical_tone_key(self):
        call_command('seed_personal_color_palettes', verbosity=0)

        palette, status = get_palette_for_tone_key('winter_cool_bright')

        self.assertEqual(status, 'ready')
        self.assertEqual(palette['toneKey'], 'winter_cool_bright')
        self.assertFalse(palette['isPlaceholder'])
        self.assertGreater(len(palette['palettes']['best']), 0)
        self.assertGreater(len(palette['palettes']['worst']), 0)
        self.assertEqual(set(palette['makeupColorGuide']['eye']['roles'].keys()), {'highlighter', 'base', 'shading', 'point'})


class PaletteSeedDataTests(TestCase):
    def test_seed_payload_covers_all_32_tone_keys_without_placeholders(self):
        self.assertEqual(list(PALETTE_SEED_DATA.keys()), CANONICAL_TONE_KEYS)
        self.assertEqual(validate_palette_seed_data(PALETTE_SEED_DATA), [])
        self.assertTrue(all(payload['is_placeholder'] is False for payload in PALETTE_SEED_DATA.values()))

    def test_seed_command_creates_32_complete_rows(self):
        call_command('seed_personal_color_palettes', verbosity=0)
        call_command('validate_personal_color_palettes', verbosity=0)

        self.assertEqual(PersonalColorPalette.objects.count(), 32)
        self.assertEqual(PersonalColorPalette.objects.filter(is_placeholder=False).count(), 32)
        for tone_key in CANONICAL_TONE_KEYS:
            payload = serialize_palette(PersonalColorPalette.objects.get(tone_key=tone_key))
            self.assertGreater(len(payload['palettes']['best']), 0)
            self.assertGreater(len(payload['palettes']['worst']), 0)
            self.assertEqual(set(payload['makeupColorGuide']['eye']['roles'].keys()), {'highlighter', 'base', 'shading', 'point'})


class MakeupGenerationPromptTests(TestCase):
    def test_prompt_uses_fixed_makeup_palette(self):
        user = self._user()
        personal_color = self._personal_color()
        diagnosis = DiagnosisResult.objects.create(
            user=user,
            personal_color=personal_color,
            tone_key='summer_cool_mute',
            personal_color_code='summer_cool_mute',
            confidence_score=82,
            palette_snapshot={
                'baseMakeupGuide': 'Use pink neutral base.',
                'makeupPalette': {
                    'lip': {'recommended': ['dusty rose']},
                    'cheek': {'recommended': ['lavender pink']},
                    'eye': {'recommended': ['taupe brown']},
                },
            },
        )

        prompt = build_makeup_generation_prompt(diagnosis)

        self.assertIn('summer_cool_mute', prompt)
        self.assertIn('dusty rose', prompt)
        self.assertIn('taupe brown', prompt)

    def _user(self):
        return get_user_model().objects.create_user(username='tester', email='tester@example.com', password='test1234!')

    def _personal_color(self):
        return PersonalColor.objects.create(
            type_name='여름 쿨 뮤트',
            tone_key='summer_cool_mute',
            base_temperature='cool',
            season='summer',
            tone='MUTE',
            description='desc',
            temperature_degree=82,
            brightness_degree=55,
            saturation_degree=38,
            turbidity_degree=62,
            glossiness_degree=50,
            contrast_degree=25,
        )


class DiagnosisAnalyzeApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username='api-user', email='api@example.com', password='test1234!')
        self.client.force_authenticate(self.user)
        self.personal_color = PersonalColor.objects.create(
            type_name='API 여름 쿨 뮤트',
            tone_key='summer_cool_mute',
            base_temperature='cool',
            season='summer',
            tone='MUTE',
            description='desc',
            temperature_degree=82,
            brightness_degree=55,
            saturation_degree=38,
            turbidity_degree=62,
            glossiness_degree=50,
            contrast_degree=25,
        )

    def test_analyze_endpoint_returns_created_result(self):
        diagnosis = DiagnosisResult.objects.create(
            user=self.user,
            personal_color=self.personal_color,
            tone_key='summer_cool_mute',
            personal_color_code='summer_cool_mute',
            confidence_score=82,
            palette_snapshot={'toneKey': 'summer_cool_mute', 'toneName': '여름 쿨 뮤트'},
        )
        upload = SimpleUploadedFile('face.jpg', b'fake-image', content_type='image/jpeg')

        with patch('diagnosis.views.run_personal_color_diagnosis', return_value=diagnosis):
            response = self.client.post('/api/diagnosis/analyze/', {'image': upload}, format='multipart')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['tone_key'], 'summer_cool_mute')
        self.assertEqual(response.data['palette']['toneKey'], 'summer_cool_mute')

    def test_analyze_endpoint_returns_quality_error(self):
        upload = SimpleUploadedFile('face.jpg', b'fake-image', content_type='image/jpeg')
        quality = SimpleNamespace(code='no_face', message='얼굴이 감지되지 않았습니다.', metrics={})

        with patch('diagnosis.views.run_personal_color_diagnosis', side_effect=ImageQualityError(quality)):
            response = self.client.post('/api/diagnosis/analyze/', {'image': upload}, format='multipart')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'no_face')
