from django.core.exceptions import ValidationError
from rest_framework import generics, parsers, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response

from diagnosis.ai_clients.openai_compatible import AIClientConfigurationError, AIClientResponseError
from diagnosis.services.workflow import ImageQualityError, PaletteNotReadyError, run_personal_color_diagnosis

from .models import DiagnosisResult
from .serializers import DiagnosisResultSerializer


DIAGNOSIS_PREFETCH = (
    'representative_colors',
    'makeover_styles',
    'color_palettes',
    'recommended_products',
    'recommended_lenses',
)


class DiagnosisAnalyzeView(APIView):
    serializer_class = DiagnosisResultSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    def post(self, request):
        uploaded_image = request.FILES.get('image')
        if not uploaded_image:
            return Response(
                {'code': 'image_required', 'detail': 'image 파일을 업로드해 주세요.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = run_personal_color_diagnosis(request.user, uploaded_image)
        except ImageQualityError as exc:
            quality = exc.result
            return Response(
                {'code': quality.code, 'detail': quality.message, 'metrics': quality.metrics},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except AIClientConfigurationError as exc:
            return Response(
                {'code': 'ai_not_configured', 'detail': str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except (AIClientResponseError, ValidationError) as exc:
            return Response(
                {'code': 'invalid_ai_response', 'detail': str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except PaletteNotReadyError as exc:
            return Response(
                {'code': 'palette_not_ready', 'detail': str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        response_status = status.HTTP_202_ACCEPTED if result.status == DiagnosisResult.Status.LOW_CONFIDENCE else status.HTTP_201_CREATED
        result = self._with_related(result.pk)
        return Response(DiagnosisResultSerializer(result, context={'request': request}).data, status=response_status)

    def _with_related(self, pk):
        return (
            DiagnosisResult.objects.select_related('user', 'personal_color')
            .prefetch_related(*DIAGNOSIS_PREFETCH)
            .get(pk=pk)
        )


class DiagnosisResultListCreateView(generics.ListCreateAPIView):
    serializer_class = DiagnosisResultSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            DiagnosisResult.objects.filter(user=self.request.user)
            .select_related('user', 'personal_color')
            .prefetch_related(*DIAGNOSIS_PREFETCH)
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class DiagnosisResultDetailView(generics.RetrieveAPIView):
    serializer_class = DiagnosisResultSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            DiagnosisResult.objects.filter(user=self.request.user)
            .select_related('user', 'personal_color')
            .prefetch_related(*DIAGNOSIS_PREFETCH)
        )


class LatestDiagnosisResultView(generics.GenericAPIView):
    serializer_class = DiagnosisResultSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        result = (
            DiagnosisResult.objects.filter(user=request.user)
            .select_related('user', 'personal_color')
            .prefetch_related(*DIAGNOSIS_PREFETCH)
            .first()
        )
        if not result:
            return Response(None)
        return Response(self.get_serializer(result).data)


class DemoDiagnosisResultView(generics.GenericAPIView):
    serializer_class = DiagnosisResultSerializer
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        result = (
            DiagnosisResult.objects.filter(is_demo=True)
            .select_related('user', 'personal_color')
            .prefetch_related(*DIAGNOSIS_PREFETCH)
            .first()
        )
        if not result:
            return Response(
                {'detail': 'Demo diagnosis result does not exist. Run python manage.py seed_demo_diagnosis.'},
                status=404,
            )
        return Response(self.get_serializer(result).data)
