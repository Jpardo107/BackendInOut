from django.contrib import admin

from .models import AnalyticsEvent, Promotion, SiteImage, SiteText, VivadentAccess

admin.site.register(VivadentAccess)
admin.site.register(Promotion)
admin.site.register(SiteImage)
admin.site.register(SiteText)
admin.site.register(AnalyticsEvent)
