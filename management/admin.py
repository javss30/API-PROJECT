
from django.contrib import admin
from .models import Athlete, TrainingSession, Payment, PerformanceRecord, GameRecord, BasketballStat

admin.site.register(Athlete)
admin.site.register(TrainingSession)
admin.site.register(Payment)
admin.site.register(PerformanceRecord)
admin.site.register(GameRecord)
admin.site.register(BasketballStat)
