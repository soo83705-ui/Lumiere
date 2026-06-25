import logging

from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.db.models import Avg, Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from diagnosis.ai_clients.openai_compatible import (
    AIClientConfigurationError,
)
from diagnosis.domain.tone_profiles import build_tone_result_payload
from diagnosis.services.primary import get_primary_diagnosis_for_user
from engagements.models import LikedProductOption
from Lumiere.api_pagination import list_response
from products.models import (
    Product,
    ProductImageAnalysis,
    ProductOffer,
    ProductOption,
    ProductOptionToneScore,
    Review,
)
from products.serializers import (
    ProductImageAnalysisRequestSerializer,
    ProductImageAnalysisSummarySerializer,
    ProductImageAnalysisUpdateSerializer,
    ProductSerializer,
    ReviewSerializer,
)
from products.services.catalog_color_analysis import build_product_color_analysis_payload
from products.services.image_color_analysis import (
    NoColorCandidatesFoundError,
    ProductImageAnalysisPipeline,
    build_product_image_analysis_payload,
    confirm_analysis,
    update_analysis_from_review,
)
from products.services.recommendation import build_user_tone_profile, calculate_option_match


logger = logging.getLogger(__name__)
IMAGE_ANALYSIS_SAVE_FAILED_MESSAGE = 'The uploaded image could not be saved for analysis.'
IMAGE_ANALYSIS_FAILED_MESSAGE = 'Product image analysis failed unexpectedly.'

HYBRID_SCORE_WEIGHTS = {
    'personal_color_score': 0.45,
    'preference_score': 0.20,
    'similar_user_score': 0.20,
    'review_bookmark_score': 0.15,
}

CATEGORY_BEAUTY_LABELS = {
    Product.Category.LIP: '립 컬러',
    Product.Category.EYE: '아이 메이크업',
    Product.Category.CHEEK: '치크 컬러',
    Product.Category.BASE: '베이스 메이크업',
    Product.Category.LENS: '렌즈 컬러',
    Product.Category.ETC: '뷰티 아이템',
}

COLOR_FAMILY_BEAUTY_LABELS = {
    Product.ColorFamily.PINK: '핑크',
    Product.ColorFamily.ROSE: '로즈',
    Product.ColorFamily.CORAL: '코랄',
    Product.ColorFamily.RED: '레드',
    Product.ColorFamily.BERRY: '베리',
    Product.ColorFamily.LAVENDER: '라벤더',
    Product.ColorFamily.BEIGE: '베이지',
    Product.ColorFamily.BROWN: '브라운',
    Product.ColorFamily.GRAY: '소프트 그레이',
    Product.ColorFamily.IVORY: '아이보리',
    Product.ColorFamily.ETC: '균형감 있는',
}

COLOR_FAMILY_REASON_FRAGMENTS = {
    Product.ColorFamily.ROSE: '차분한 로즈빛과 부드러운 혈색으로',
    Product.ColorFamily.PINK: '맑은 생기와 깨끗한 인상으로',
    Product.ColorFamily.CORAL: '따뜻한 생기와 화사한 분위기로',
    Product.ColorFamily.BROWN: '차분한 음영과 깊이감으로',
    Product.ColorFamily.BERRY: '또렷한 포인트와 분위기 있는 컬러감으로',
    Product.ColorFamily.BEIGE: '부담 없는 데일리감과 정돈된 인상으로',
    Product.ColorFamily.RED: '선명한 포인트 컬러감으로',
    Product.ColorFamily.LAVENDER: '맑고 차분한 포인트로',
    Product.ColorFamily.GRAY: '소프트한 그림자감으로',
    Product.ColorFamily.IVORY: '깨끗한 피부 표현으로',
    Product.ColorFamily.ETC: '균형감 있는 컬러감으로',
}

CATEGORY_REASON_FRAGMENTS = {
    Product.Category.LIP: {
        'BEST': '혈색을 채우고 데일리 립 포인트를 깔끔하게 남겨요.',
        'GOOD': '입술 포인트로 쓰기 좋고 분위기 전환도 부담 없습니다.',
        'CAUTION': '입술 중앙에 얇게 올리면 혈색만 가볍게 더해요.',
        'default': '데일리 립으로 쓰기 쉽고 입술 포인트를 편하게 만들어요.',
    },
    Product.Category.CHEEK: {
        'BEST': '피부 위 발색이 은은하고 립과의 연결감이 부드러워요.',
        'GOOD': '은은한 생기를 더하면서 립 컬러와 자연스럽게 이어져요.',
        'CAUTION': '소량만 올리면 피부 위 발색과 립 연결감이 과하지 않아요.',
        'default': '피부 위에 은은한 생기를 얹고 립과의 연결감을 맞추기 좋아요.',
    },
    Product.Category.EYE: {
        'BEST': '눈매를 정리하고 음영감과 대비감을 또렷하게 잡아줘요.',
        'GOOD': '포인트 컬러로 쓰기 좋고 눈매에 필요한 대비감만 더해요.',
        'CAUTION': '넓게 쓰기보다 포인트 컬러로 얹으면 눈매가 정돈돼요.',
        'default': '음영감과 포인트 컬러감을 더해 눈매를 깔끔하게 정리해요.',
    },
    Product.Category.BASE: {
        'BEST': '피부톤 연결이 좋아 목과 얼굴 차이를 부드럽게 낮춰요.',
        'GOOD': '자연스러운 피부 표현에 맞고 얼굴과 목 경계가 덜 도드라져요.',
        'CAUTION': '얇게 올리면 피부톤 연결을 도와 목과 얼굴 차이를 완화해요.',
        'default': '피부톤 연결과 자연스러운 피부 표현을 함께 맞추기 좋아요.',
    },
    Product.Category.LENS: {
        'default': '눈빛의 대비감을 정리하고 전체 메이크업 무드를 맞추기 좋아요.',
    },
    Product.Category.ETC: {
        'default': '전체 메이크업 무드를 정돈하는 포인트로 활용하기 좋아요.',
    },
}

PICK_FIT_PHRASES = {
    'BEST': '가장 먼저 집어볼 만한 픽',
    'GOOD': '데일리로 쓰기 좋은 픽',
    'CAUTION': '양을 조절해 시도하기 좋은 픽',
    'default': '톤에 맞춰 보기 좋은 픽',
}


def validation_error_message(exc):
    if hasattr(exc, 'message'):
        return exc.message
    if hasattr(exc, 'messages') and exc.messages:
        return exc.messages[0]
    return str(exc)


def mark_product_image_analysis_failed(analysis, *, code, message, exc=None):
    """Persist analysis failure metadata without deleting the uploaded analysis row."""
    if not analysis or not analysis.pk:
        return None

    raw_payload = analysis.raw_ai_response if isinstance(analysis.raw_ai_response, dict) else {}
    raw_meta = raw_payload.get('analysis_meta') if isinstance(raw_payload.get('analysis_meta'), dict) else {}

    error_message = message or (str(exc) if exc else '')

    raw_payload['analysis_meta'] = {
        **raw_meta,
        'success': False,
        'code': code,
        'error_type': exc.__class__.__name__ if exc else '',
        'error_message': str(exc) if exc else error_message,
        'message': error_message,
    }

    analysis.raw_ai_response = raw_payload
    try:
        analysis.save(update_fields=['raw_ai_response', 'updated_at'])
    except Exception:
        logger.exception(
            'Failed to persist product image analysis failure metadata. analysis_id=%s code=%s',
            analysis.pk,
            code,
        )
    return analysis.pk


def product_image_analysis_error_response(analysis, *, code, message, http_status, exc=None, detail=None):
    analysis_id = mark_product_image_analysis_failed(
        analysis,
        code=code,
        message=message,
        exc=exc,
    )
    body = {
        'success': False,
        'analysis_id': analysis_id,
        'code': code,
        'message': message,
    }
    if detail is not None:
        body['detail'] = detail
    elif exc is not None:
        body['detail'] = str(exc)
    return Response(body, status=http_status)


class IsAuthorOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.author == request.user


def product_queryset(request, apply_filters=True):
    offer_queryset = ProductOffer.objects.order_by('price', 'id')
    tone_score_queryset = ProductOptionToneScore.objects.order_by('-match_score', 'target_tone', 'id')
    option_queryset = (
        ProductOption.objects.select_related('product')
        .prefetch_related(
            Prefetch('offers', queryset=offer_queryset),
            Prefetch('tone_scores', queryset=tone_score_queryset),
        )
        .order_by('option_no', 'option_name', 'id')
    )
    queryset = (
        Product.objects.all()
        .annotate(
            review_count=Count('reviews', distinct=True),
            average_rating=Avg('reviews__rating'),
            bookmark_count=Count('liked_by_users', distinct=True),
        )
        .prefetch_related(Prefetch('options', queryset=option_queryset))
    )
    if not apply_filters:
        return queryset

    category = request.query_params.get('category')
    keyword = request.query_params.get('q')

    if category:
        queryset = queryset.filter(category=category)
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(brand__icontains=keyword))
    return queryset


def user_tone_profile_from_request(request):
    tone_key = request.query_params.get('tone_key')
    second_tone_key = request.query_params.get('second_tone_key')
    axis_profile = None
    range_profile = None

    if not tone_key and request.user.is_authenticated:
        try:
            diagnosis = get_primary_diagnosis_for_user(request.user)
        except Exception:
            diagnosis = None
        if diagnosis:
            profile_payload = build_tone_result_payload(
                diagnosis.tone_key or diagnosis.personal_color_code,
                (diagnosis.diagnosis_json or {}).get('second_tone_key'),
            )
            tone_key = profile_payload['tone_key']
            second_tone_key = profile_payload['second_tone_key']
            axis_profile = profile_payload['axis_profile']
            range_profile = profile_payload['range_profile']

    return build_user_tone_profile(
        tone_key=tone_key,
        second_tone_key=second_tone_key,
        axis_profile=axis_profile,
        range_profile=range_profile,
    )


def sort_products_by_best_option(products, user_profile):
    def best_score(product):
        options = list(getattr(product, '_prefetched_objects_cache', {}).get('options', []) or [])
        if not options:
            return getattr(product, 'match_score', 0) or 0
        return max(
            calculate_option_match(option, user_profile, product.category)['match_score']
            for option in options
        )

    return sorted(products, key=best_score, reverse=True)


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        return product_queryset(self.request)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['user_tone_profile'] = user_tone_profile_from_request(self.request)
        context['option_match_cache'] = {}
        return context

    def list(self, request, *args, **kwargs):
        user_profile = user_tone_profile_from_request(request)
        products = sort_products_by_best_option(list(self.get_queryset()), user_profile)
        serializer = self.get_serializer(
            products,
            many=True,
            context={**self.get_serializer_context(), 'user_tone_profile': user_profile},
        )
        return Response(serializer.data)


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsAuthorOrReadOnly]

    def get_queryset(self):
        queryset = Review.objects.select_related('product', 'author')
        product_id = self.request.query_params.get('product')
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        return queryset


@api_view(['GET'])
def product_list(request):
    user_profile = user_tone_profile_from_request(request)
    products = sort_products_by_best_option(list(product_queryset(request)), user_profile)
    serializer = ProductSerializer(
        products,
        many=True,
        context={'request': request, 'user_tone_profile': user_profile, 'option_match_cache': {}},
    )
    return Response(serializer.data)


@api_view(['GET'])
def product_detail(request, product_id):
    user_profile = user_tone_profile_from_request(request)
    product = get_object_or_404(product_queryset(request, apply_filters=False), pk=product_id)
    serializer = ProductSerializer(
        product,
        context={'request': request, 'user_tone_profile': user_profile, 'option_match_cache': {}},
    )
    return Response(serializer.data)


@api_view(['GET'])
def product_catalog_color_analysis(request, product_id):
    product = get_object_or_404(product_queryset(request, apply_filters=False), pk=product_id)
    return Response(build_product_color_analysis_payload(product, request=request))


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticatedOrReadOnly])
def personalized_recommendation_products(request):
    limit = _positive_int(request.query_params.get('limit'), 12)
    per_category = _positive_int(request.query_params.get('per_category'), 2)
    user_profile = user_tone_profile_from_request(request)
    hybrid_context = _hybrid_recommendation_context(request, user_profile)
    queryset = product_queryset(request, apply_filters=False).filter(options__isnull=False).distinct()
    sorted_products = sort_products_by_best_option(list(queryset), user_profile)
    sorted_products = [
        product
        for product in sorted_products
        if _product_recommendation_status(product, user_profile) != 'AVOID'
    ]
    selected_products, balance = _balanced_recommendation_products(
        sorted_products,
        limit=limit,
        per_category=per_category,
    )
    results = [_recommendation_summary(product, request, hybrid_context=hybrid_context) for product in selected_products]
    return Response(
        {
            'count': len(results),
            'results': results,
            'category_balance': balance,
        },
        status=status.HTTP_200_OK,
    )


def _product_recommendation_status(product, user_profile):
    options = list(getattr(product, '_prefetched_objects_cache', {}).get('options', []) or product.options.all())
    if not options:
        return _recommendation_status(getattr(product, 'match_score', None))
    best_score = max(
        calculate_option_match(option, user_profile, product.category)['match_score']
        for option in options
    )
    return _recommendation_status(best_score)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticatedOrReadOnly])
def recommendation_color_matching(request, product_id):
    product = get_object_or_404(
        product_queryset(request, apply_filters=False).filter(options__isnull=False).distinct(),
        pk=product_id,
    )
    payload = build_product_color_analysis_payload(product, request=request)
    best_option = _enrich_recommendation_option(payload.get('best_option'))
    options = [_enrich_recommendation_option(option) for option in payload.get('options', [])]
    payload['product'] = {
        **payload.get('product', {}),
        'brand': product.brand,
        'name': product.name,
        'image_url': product.display_image_url,
        'product_url': product.product_url,
    }
    payload['options'] = options
    payload['best_option'] = best_option
    payload['match_status'] = best_option.get('match_status') if best_option else ''
    payload['summary_reason'] = _friendly_recommendation_reason(best_option)
    payload['comparison_metrics'] = _comparison_metrics(payload.get('user_tone'), best_option)
    return Response(payload, status=status.HTTP_200_OK)


def _balanced_recommendation_products(products, *, limit, per_category):
    target_categories = [Product.Category.LIP, Product.Category.EYE, Product.Category.BASE, Product.Category.CHEEK]
    selected = []
    selected_ids = set()
    actual = {category: 0 for category in target_categories}

    for category in target_categories:
        category_products = [product for product in products if product.category == category]
        for product in category_products[:per_category]:
            selected.append(product)
            selected_ids.add(product.id)
            actual[category] += 1

    for product in products:
        if len(selected) >= limit:
            break
        if product.id in selected_ids:
            continue
        selected.append(product)
        selected_ids.add(product.id)
        if product.category in actual:
            actual[product.category] += 1

    return selected[:limit], {
        'requested_total': limit,
        'requested_per_category': per_category,
        'actual': actual,
        'filled_with_alternatives': max(0, len(selected[:limit]) - sum(min(per_category, actual[category]) for category in target_categories)),
    }


def _recommendation_summary(product, request, *, hybrid_context=None):
    payload = build_product_color_analysis_payload(product, request=request)
    best_option = _enrich_recommendation_option(payload.get('best_option'))
    options = [_enrich_recommendation_option(option) for option in payload.get('options', [])]
    representative_offer = best_option.get('representative_offer') if best_option else None
    hybrid_scores = _hybrid_recommendation_score(product, best_option, hybrid_context or {})
    display_fields = _recommendation_display_fields(
        product,
        best_option,
        user_tone=payload.get('user_tone'),
        hybrid_scores=hybrid_scores,
    )
    return {
        'id': product.id,
        'brand': product.brand,
        'name': product.name,
        'category': product.category,
        'image_url': best_option.get('image_url') if best_option else product.display_image_url,
        'product_url': (representative_offer or {}).get('product_url') or product.product_url,
        'best_option': best_option,
        'options': options,
        'match_status': best_option.get('match_status') if best_option else '',
        'match_score': best_option.get('match_score') if best_option else None,
        'short_reason': _friendly_recommendation_reason(best_option),
        'detail_reason': best_option.get('detail_reason') if best_option else '',
        'usage_tip': best_option.get('usage_tip') if best_option else '',
        'personalized': payload.get('personalized', False),
        **hybrid_scores,
        **display_fields,
    }


def _hybrid_recommendation_context(request, user_profile):
    context = {
        'liked_product_ids': set(),
        'liked_option_ids': set(),
        'liked_categories': set(),
        'liked_color_families': set(),
        'liked_tone_tags': set(),
        'product_bookmark_counts': {},
        'option_bookmark_counts': {},
        'similar_product_counts': {},
        'similar_option_counts': {},
        'max_bookmark_count': 0,
        'max_similar_count': 0,
    }

    try:
        product_bookmarks = (
            LikedProductOption.objects.values('product_id')
            .annotate(total=Count('id', distinct=True))
        )
        option_bookmarks = (
            LikedProductOption.objects.exclude(product_option_id__isnull=True)
            .values('product_option_id')
            .annotate(total=Count('id', distinct=True))
        )
        context['product_bookmark_counts'] = {
            item['product_id']: item['total'] for item in product_bookmarks if item['product_id']
        }
        context['option_bookmark_counts'] = {
            item['product_option_id']: item['total'] for item in option_bookmarks if item['product_option_id']
        }
        context['max_bookmark_count'] = max(context['product_bookmark_counts'].values() or [0])

        if request.user.is_authenticated:
            liked_items = (
                LikedProductOption.objects.filter(user=request.user)
                .select_related('product', 'product_option')
            )
            for item in liked_items:
                context['liked_product_ids'].add(item.product_id)
                if item.product_option_id:
                    context['liked_option_ids'].add(item.product_option_id)
                if item.product:
                    context['liked_categories'].add(item.product.category)
                if item.product_option:
                    context['liked_color_families'].add(item.product_option.color_family)
                    context['liked_tone_tags'].add(item.product_option.analyzed_tone_tag)

        tone_key = (user_profile or {}).get('tone_key')
        if tone_key:
            similar_likes = (
                LikedProductOption.objects.filter(
                    Q(user__diagnosis_results__is_primary=True),
                    Q(user__diagnosis_results__tone_key=tone_key)
                    | Q(user__diagnosis_results__personal_color_code=tone_key),
                )
                .exclude(user=request.user if request.user.is_authenticated else None)
            )
            similar_products = similar_likes.values('product_id').annotate(total=Count('id', distinct=True))
            similar_options = (
                similar_likes.exclude(product_option_id__isnull=True)
                .values('product_option_id')
                .annotate(total=Count('id', distinct=True))
            )
            context['similar_product_counts'] = {
                item['product_id']: item['total'] for item in similar_products if item['product_id']
            }
            context['similar_option_counts'] = {
                item['product_option_id']: item['total'] for item in similar_options if item['product_option_id']
            }
            context['max_similar_count'] = max(
                list(context['similar_product_counts'].values())
                + list(context['similar_option_counts'].values())
                or [0]
            )
    except DatabaseError:
        logger.warning('Hybrid recommendation signal lookup failed.', exc_info=True)

    return context


def _hybrid_recommendation_score(product, option, context):
    personal_color_score = _score_value((option or {}).get('match_score'), 0)
    preference_score, preference_source = _preference_score(product, option, context, personal_color_score)
    similar_user_score, similar_source = _similar_user_score(product, option, context, personal_color_score)
    review_bookmark_score, review_source = _review_bookmark_score(product, option, context, personal_color_score)
    final_score = round(
        personal_color_score * HYBRID_SCORE_WEIGHTS['personal_color_score']
        + preference_score * HYBRID_SCORE_WEIGHTS['preference_score']
        + similar_user_score * HYBRID_SCORE_WEIGHTS['similar_user_score']
        + review_bookmark_score * HYBRID_SCORE_WEIGHTS['review_bookmark_score']
    )

    return {
        'personal_color_score': personal_color_score,
        'preference_score': preference_score,
        'similar_user_score': similar_user_score,
        'review_bookmark_score': review_bookmark_score,
        'hybrid_score': final_score,
        'final_score': final_score,
        'hybrid_score_weights': HYBRID_SCORE_WEIGHTS,
        'hybrid_score_sources': {
            'ranking': 'match_score',
            'preference_score': preference_source,
            'similar_user_score': similar_source,
            'review_bookmark_score': review_source,
        },
    }


def _preference_score(product, option, context, fallback_score):
    if not context.get('liked_product_ids') and not context.get('liked_option_ids'):
        return fallback_score, 'fallback_personal_color'

    option_id = (option or {}).get('id')
    if option_id and option_id in context['liked_option_ids']:
        return 100, 'liked_option'
    if product.id in context['liked_product_ids']:
        return 95, 'liked_product'

    score = 50
    if product.category in context['liked_categories']:
        score += 20
    if (option or {}).get('color_family') in context['liked_color_families']:
        score += 20
    if (option or {}).get('analyzed_tone_tag') in context['liked_tone_tags']:
        score += 10
    return min(100, score), 'liked_pattern'


def _similar_user_score(product, option, context, fallback_score):
    option_count = context.get('similar_option_counts', {}).get((option or {}).get('id'), 0)
    product_count = context.get('similar_product_counts', {}).get(product.id, 0)
    count = max(option_count, product_count)
    max_count = context.get('max_similar_count') or 0
    if not count or not max_count:
        return fallback_score, 'fallback_personal_color'
    return round(55 + 45 * count / max_count), 'same_tone_bookmarks'


def _review_bookmark_score(product, option, context, fallback_score):
    signals = []
    review_count = _score_value(getattr(product, 'review_count', 0), 0)
    average_rating = getattr(product, 'average_rating', None)
    if review_count and average_rating:
        signals.append(_score_value(float(average_rating) * 20, 0))

    bookmark_count = max(
        context.get('product_bookmark_counts', {}).get(product.id, 0),
        context.get('option_bookmark_counts', {}).get((option or {}).get('id'), 0),
        getattr(product, 'bookmark_count', 0) or 0,
    )
    max_bookmark_count = context.get('max_bookmark_count') or bookmark_count
    if bookmark_count and max_bookmark_count:
        signals.append(round(55 + 45 * bookmark_count / max_bookmark_count))

    if not signals:
        return fallback_score, 'fallback_personal_color'
    return round(sum(signals) / len(signals)), 'reviews_bookmarks'


def _recommendation_display_fields(product, option, *, user_tone, hybrid_scores):
    option = option or {}
    tone_label = (user_tone or {}).get('tone_label') or '내 톤'
    category_label = CATEGORY_BEAUTY_LABELS.get(product.category, '뷰티 아이템')
    family_label = COLOR_FAMILY_BEAUTY_LABELS.get(option.get('color_family'), '균형감 있는')
    option_name = ' '.join(part for part in [option.get('option_no'), option.get('option_name')] if part)
    status_label = option.get('match_status') or _recommendation_status(option.get('match_score'))
    family_fragment = _color_family_reason_fragment(option.get('color_family'))
    category_fragment = _category_reason_fragment(product.category, status_label)
    pick_phrase = _pick_fit_phrase(status_label, hybrid_scores.get('final_score', 0))

    reason_title = 'AI 톤 맞춤 픽'
    if status_label == 'BEST':
        reason_title = '오늘의 베스트 톤 매치'
    elif status_label == 'GOOD':
        reason_title = '매일 쓰기 좋은 컬러'
    elif status_label == 'CAUTION':
        reason_title = '양 조절 추천 컬러'

    label = option_name or family_label
    reason_text = (
        f'{label}은 {tone_label}에 {pick_phrase}이에요. '
        f'{family_fragment} {category_fragment}'
    )

    return {
        'ai_pick_label': "AI's Pick",
        'reason_title': reason_title,
        'reason_text': reason_text,
        'reason_tags': _compact_tags([tone_label, category_label, family_label, status_label]),
    }


def _color_family_reason_fragment(color_family):
    return COLOR_FAMILY_REASON_FRAGMENTS.get(
        color_family,
        COLOR_FAMILY_REASON_FRAGMENTS[Product.ColorFamily.ETC],
    )


def _category_reason_fragment(category, status_label):
    category_copy = CATEGORY_REASON_FRAGMENTS.get(category, CATEGORY_REASON_FRAGMENTS[Product.Category.ETC])
    return category_copy.get(status_label) or category_copy.get('default') or CATEGORY_REASON_FRAGMENTS[Product.Category.ETC]['default']


def _pick_fit_phrase(status_label, final_score):
    if final_score >= 85:
        return PICK_FIT_PHRASES['BEST']
    return PICK_FIT_PHRASES.get(status_label) or PICK_FIT_PHRASES['default']


def _compact_tags(values):
    tags = []
    for value in values:
        tag = str(value or '').strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:4]


def _score_value(value, default=0):
    try:
        number = round(float(value))
    except (TypeError, ValueError):
        number = default
    return max(0, min(100, number))


def _enrich_recommendation_option(option):
    if not option:
        return {}
    status_label = _recommendation_status(option.get('match_score'))
    return {
        **option,
        'match_status': status_label,
        'is_precise_color': _has_complete_color_metrics(option),
    }


def _recommendation_status(score):
    try:
        number = float(score)
    except (TypeError, ValueError):
        return ''
    if number >= 85:
        return 'BEST'
    if number >= 70:
        return 'GOOD'
    if number >= 40:
        return 'CAUTION'
    return 'AVOID'


def _friendly_recommendation_reason(option):
    if not option:
        return '아직 추천할 수 있는 색상 옵션 정보가 충분하지 않아요.'
    status_label = option.get('match_status') or _recommendation_status(option.get('match_score'))
    brightness = _metric_value(option, 'brightness')
    saturation = _metric_value(option, 'saturation')
    coolness = _metric_value(option, 'coolness')
    option_name = ' '.join(part for part in [option.get('option_no'), option.get('option_name')] if part) or '이 옵션'
    light_word = '밝고 맑은' if brightness >= 65 else '차분한' if brightness >= 45 else '깊이 있는'
    chroma_word = '생기 있는' if saturation >= 55 else '부드러운'
    temp_word = '쿨한' if coolness >= 60 else '따뜻한' if coolness <= 40 else '중립적인'

    if status_label == 'BEST':
        return f'{option_name}은 {light_word} {temp_word} 톤이라 피부가 맑아 보이기 쉬운 추천 옵션이에요.'
    if status_label == 'GOOD':
        return f'{option_name}은 {chroma_word} 색감이 부담 없이 어울려 데일리로 쓰기 좋은 편이에요.'
    if status_label == 'MIX':
        return f'{option_name}은 단독보다 비슷한 계열의 밝은 색과 섞으면 더 자연스럽게 어울려요.'
    if status_label == 'CAUTION':
        return f'{option_name}은 살짝 튀어 보일 수 있어 양을 줄이거나 포인트로 쓰는 편이 좋아요.'
    if status_label == 'AVOID':
        return f'{option_name}은 현재 퍼스널 컬러 기준과 차이가 커서 신중하게 테스트해보는 편이 좋아요.'
    return '퍼스널 컬러 진단을 설정하면 더 정확한 추천 이유를 볼 수 있어요.'


def _comparison_metrics(user_tone, option):
    if not option:
        return []
    axis = (user_tone or {}).get('axis_profile') or {}
    metric_specs = [
        ('brightness', '명도'),
        ('saturation', '채도'),
        ('coolness', '쿨 경향'),
        ('warmth', '웜 경향'),
        ('softness', '부드러움'),
        ('contrast', '대비'),
    ]
    rows = []
    for key, label in metric_specs:
        user_value = _metric_value(axis, key)
        product_value = _metric_value(option, key)
        diff = abs(user_value - product_value)
        rows.append(
            {
                'key': key,
                'label': label,
                'user_value': user_value,
                'product_value': product_value,
                'diff': diff,
                'explanation': _metric_explanation(label, diff),
            }
        )
    return rows


def _metric_explanation(label, diff):
    if diff <= 8:
        return f'{label} 차이가 작아 자연스럽게 이어지는 편이에요.'
    if diff <= 20:
        return f'{label} 차이가 있어 발색 강도를 조절하면 좋아요.'
    return f'{label} 차이가 커서 포인트 사용을 권장해요.'


def _has_complete_color_metrics(option):
    required = ['hex_code', 'brightness', 'saturation', 'coolness', 'warmth']
    return all(option.get(key) not in [None, ''] for key in required)


def _metric_value(source, key):
    try:
        return round(float(source.get(key, 0)))
    except (AttributeError, TypeError, ValueError):
        return 0


def _positive_int(value, default):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, number)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def product_image_analysis(request):
    if not request.FILES.get('image'):
        return Response(
            {
                'success': False,
                'analysis_id': None,
                'code': 'IMAGE_REQUIRED',
                'message': 'An image file is required for product image analysis.',
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = ProductImageAnalysisRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    validated = serializer.validated_data

    analysis = None
    try:
        analysis = ProductImageAnalysis.objects.create(
            user=request.user,
            product_name=validated.get('product_name', ''),
            brand_name=validated.get('brand_name', ''),
            category=validated.get('category') or Product.Category.ETC,
            uploaded_image=validated['image'],
        )
        logger.info(
            'Product image analysis request saved. analysis_id=%s user_id=%s category=%s image_name=%s image_path=%s',
            analysis.id,
            request.user.id,
            analysis.category,
            analysis.uploaded_image.name,
            getattr(analysis.uploaded_image, 'path', ''),
        )

        pipeline = ProductImageAnalysisPipeline(analysis)
        payload = pipeline.run()

    except NoColorCandidatesFoundError as exc:
        logger.warning(
            'Product image analysis found no color candidates. analysis_id=%s error=%s',
            analysis.id if analysis else None,
            exc,
        )
        return product_image_analysis_error_response(
            analysis,
            code='NO_COLOR_CANDIDATES_FOUND',
            message=str(exc),
            detail=str(exc),
            exc=exc,
            http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    except AIClientConfigurationError as exc:
        logger.exception(
            'Product image analysis AI configuration failed. analysis_id=%s error=%s',
            analysis.id if analysis else None,
            exc,
        )
        return product_image_analysis_error_response(
            analysis,
            code='IMAGE_ANALYSIS_UNAVAILABLE',
            message=str(exc),
            detail=str(exc),
            exc=exc,
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    except ValidationError as exc:
        message = validation_error_message(exc)
        logger.exception(
            'Product image analysis validation failed. analysis_id=%s error=%s',
            analysis.id if analysis else None,
            message,
        )
        return product_image_analysis_error_response(
            analysis,
            code='INVALID_IMAGE',
            message=message,
            detail=message,
            exc=exc,
            http_status=status.HTTP_400_BAD_REQUEST,
        )

    except (DatabaseError, OSError, ValueError) as exc:
        logger.exception(
            'Product image analysis persistence or processing failed. analysis_id=%s error=%s',
            analysis.id if analysis else None,
            exc,
        )
        return product_image_analysis_error_response(
            analysis,
            code='IMAGE_ANALYSIS_SAVE_FAILED',
            message=IMAGE_ANALYSIS_SAVE_FAILED_MESSAGE,
            detail=str(exc),
            exc=exc,
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    except Exception as exc:
        logger.exception(
            'Unexpected product image analysis failure. analysis_id=%s error=%s',
            analysis.id if analysis else None,
            exc,
        )
        return product_image_analysis_error_response(
            analysis,
            code='IMAGE_ANALYSIS_FAILED',
            message=IMAGE_ANALYSIS_FAILED_MESSAGE,
            detail=str(exc),
            exc=exc,
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(payload, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def product_image_analysis_list(request):
    queryset = ProductImageAnalysis.objects.filter(user=request.user).prefetch_related('options')
    return list_response(request, queryset, ProductImageAnalysisSummarySerializer, context={'request': request})


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def product_image_analysis_detail(request, analysis_id):
    analysis = get_object_or_404(
        ProductImageAnalysis.objects.filter(user=request.user).prefetch_related('options'),
        pk=analysis_id,
    )
    if request.method == 'GET':
        return Response(build_product_image_analysis_payload(analysis), status=status.HTTP_200_OK)
    if request.method == 'DELETE':
        analysis.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = ProductImageAnalysisUpdateSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    try:
        payload = update_analysis_from_review(analysis, serializer.validated_data)
    except ValidationError as exc:
        return Response(
            {
                'success': False,
                'code': 'INVALID_REVIEW_UPDATE',
                'detail': exc.message if hasattr(exc, 'message') else exc.messages[0],
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(payload, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def product_image_analysis_confirm(request, analysis_id):
    analysis = get_object_or_404(
        ProductImageAnalysis.objects.filter(user=request.user).prefetch_related('options'),
        pk=analysis_id,
    )
    payload = confirm_analysis(analysis)
    return Response(payload, status=status.HTTP_200_OK)
