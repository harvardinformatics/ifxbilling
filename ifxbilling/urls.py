"""ifxbilling URL Configuration

This is just for testing purposes
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework import routers
from drf_yasg import openapi
from ifxbilling import serializers
from ifxbilling import views

# Setup the Swagger API view
API_INFO = openapi.Info(
    title="IfxBilling API",
    default_version='v1',
    description="Library for billing stuff",
    terms_of_service="https://www.google.com/policies/terms/",
    contact=openapi.Contact(email="ifx@fas.harvard.edu"),
    license=openapi.License(name="GNU GPL version 2"),
)

# routers provide an easy way of automatically determining the URL conf.
router = routers.DefaultRouter()
router.register(r'accounts', serializers.AccountViewSet, 'account')
router.register(r'products', serializers.ProductViewSet, 'product')
router.register(r'facilities', serializers.FacilityViewSet, 'facility')
router.register(r'product-usages', serializers.ProductUsageViewSet, 'product-usages')
router.register(r'billing-records', serializers.BillingRecordViewSet, 'billing-record')

urlpatterns = [
    path(r'ifxbilling/djadmin/', admin.site.urls),
    path(r'ifxbilling/api/obtain-auth-token/', views.get_remote_user_auth_token),
    path(r'ifxbilling/api/update-user-accounts/', views.update_user_accounts_view, name='update-user-accounts'),
    path(r'ifxbilling/api/expense-code-request/', views.expense_code_request, name='expense-code-request'),
    path(r'ifxbilling/api/send-billing-record-review-notification/<str:invoice_prefix>/<int:year>/<int:month>/', views.send_billing_record_review_notification, name='send-billing-record-review-notification'),
    path(r'ifxbilling/api/unauthorized/', views.unauthorized, name='unauthorized'),
    path(r'ifxbilling/api/finalize-billing-month/', views.finalize_billing_month, name='finalize-billing-month'),
    path(r'ifxbilling/api/', include(router.urls)),
]
