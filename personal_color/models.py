from django.db import models
from django_conf import settings

# Create your models here.
# 진단 결과의 기준 상품&사용자를 있는 매개체 -> 하나의 퍼컬에는 여러개의 상품 option
class PerSonalColor(models.Model):
    id = 
    name  = models.CharField(max_length=50 unique=True)
    base_type = 

    class SeasonChoice(models.TextChoices):
        spring = 'spring', '봄(spring)'
        summer = 'summer', '여름(summer)'
        fall = 'fall', '가을(fall)'
        winter = 'winter', '겨울(winter)'
    season =  models.CharField(max_length=10, choices=SeasonChoice.choices)
    # 봄 여름 가을 겨울 
    class ToneChoices(models.TextChoices):
        BRIGHT = 'BRIGHT', '브라이트(Bright)'
        LIGHT = 'LIGHT', '라이트(Light)'
        MUTE = 'MUTE', '뮤트(Mute)'
        DEEP = 'DEEP', '딥(Deep)'
    tone = models.CharField(max_length=10, choices=ToneChoices.choices)
    # 브라이트  뮤트 딥 
    
    description = models.TextField() 
    # 짧은 설명 