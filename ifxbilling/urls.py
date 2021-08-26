"""ifxbilling URL Configuration

This is just for testing purposes
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework import routers
from ifxbilling import serializers
from ifxbilling.views import get_remote_user_auth_token, update_user_accounts, unauthorized


# routers provide an easy way of automatically determining the URL conf.
router = routers.DefaultRouter()
router.register(r'accounts', serializers.AccountViewSet)
router.register(r'products', serializers.ProductViewSet)
router.register(r'facilities', serializers.FacilityViewSet, 'facility')
router.register(r'product-usages', serializers.ProductUsageViewSet)
router.register(r'billing-records', serializers.BillingRecordViewSet, 'billing-record')

urlpatterns = [
    path(r'ifxbilling/djadmin/', admin.site.urls),
    path(r'ifxbilling/api/obtain-auth-token/', get_remote_user_auth_token),
    path(r'ifxbilling/api/update-user-accounts/', update_user_accounts, name='update-user-accounts'),
    path(r'ifxbilling/api/unauthorized/', unauthorized, name='unauthorized'),
    path(r'ifxbilling/api/', include(router.urls)),
]
