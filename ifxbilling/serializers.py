# -*- coding: utf-8 -*-

'''
Serializers and viewsets for ifxbilling.

Note that the ProductUsage serializer is unlikely to be used by client
applications.  It is setup here for testing purposes.

Likewise the *ViewSet classes should be replaced by local versions that provide
appropriate permissions.

'''
import re
import logging
from django.db import transaction
from django.contrib.auth import get_user_model
from rest_framework import serializers, viewsets
from ifxuser.models import Organization
from ifxbilling import models


logger = logging.getLogger(__name__)


class AccountSerializer(serializers.ModelSerializer):
    '''
    Serializer for accounts
    '''
    organization = serializers.SlugRelatedField(slug_field='slug', queryset=Organization.objects.all())
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    account_type = serializers.ChoiceField(choices=('Expense Code', 'PO'), required=False)
    root = serializers.CharField(max_length=5)
    active = serializers.BooleanField(required=False)
    valid_from = serializers.DateTimeField(required=False)
    expiration_date = serializers.DateTimeField(required=False)

    class Meta:
        model = models.Account
        fields = ('id', 'code', 'name', 'organization', 'account_type', 'root', 'expiration_date', 'active', 'valid_from', 'created', 'updated', 'slug')
        read_only_fields = ('created', 'updated', 'id', 'slug')

    @transaction.atomic
    def create(self, validated_data):
        '''
        Ensure that an improper root value is a ValidationError
        '''
        if not re.match(r'^[0-9]{5}$', validated_data['root']):
            raise serializers.ValidationError(
                detail={
                    'root': f'Root must be a 5 digit number.'
                }
            )
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        '''
        Ensure that an improper root value is a ValidationError
        '''
        if not re.match(r'^[0-9]{5}$', validated_data['root']):
            raise serializers.ValidationError(
                detail={
                    'root': f'Root must be a 5 digit number.'
                }
            )
        return super().update(validated_data)


class AccountViewSet(viewsets.ModelViewSet):
    '''
    ViewSet for Account models
    '''
    queryset = models.Account.objects.all()
    serializer_class = AccountSerializer


class RateSerializer(serializers.ModelSerializer):
    '''
    Serializer for Rates
    '''
    name = serializers.CharField(max_length=50)
    price = serializers.IntegerField()
    units = serializers.CharField(max_length=100)
    is_active = serializers.BooleanField(required=False)

    class Meta:
        model = models.Product
        fields = ('id', 'name', 'price', 'units', 'is_active')
        read_only_fields = ('id',)


class ProductSerializer(serializers.ModelSerializer):
    '''
    Serializer for Products
    '''
    product_number = serializers.CharField(max_length=14)
    product_name = serializers.CharField(max_length=50)
    product_description = serializers.CharField(max_length=200)
    billing_calculator = serializers.CharField(max_length=100, required=False)
    rates = RateSerializer(many=True, read_only=True, source='rate_set')

    class Meta:
        model = models.Product
        fields = ('id', 'product_number', 'product_name', 'product_description', 'billing_calculator', 'rates')
        read_only_fields = ('id',)

    @transaction.atomic
    def create(self, validated_data):
        '''
        Handle rates
        '''
        product = models.Product.objects.create(**validated_data)
        if 'rates' in self.initial_data and self.initial_data['rates']:
            for rate_data in self.initial_data['rates']:
                try:
                    models.Rate.objects.create(product=product, **rate_data)
                except Exception as e:
                    logger.exception(e)
                    raise serializers.ValidationError(
                        detail={
                            'rates': str(e)
                        }
                    )
            # Reload the object with the new rates and return
            product = models.Product.objects.get(id=product.id)
        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        '''
        Update product and rates
        '''
        for attr in ['product_number', 'product_name', 'product_description', 'billing_calculator']:
            setattr(instance, attr, validated_data[attr])

        instance.rate_set.all().delete()

        if 'rates' in self.initial_data and self.initial_data['rates']:
            for rate_data in self.initial_data['rates']:
                try:
                    models.Rate.objects.create(product=instance, **rate_data)
                except Exception as e:
                    logger.exception(e)
                    raise serializers.ValidationError(
                        detail={
                            'rates': str(e)
                        }
                    )
            # Reload the object with the new rates and return
            instance = models.Product.objects.get(id=instance.id)
        return instance


class ProductViewSet(viewsets.ModelViewSet):
    '''
    ViewSet for Product models
    '''
    queryset = models.Product.objects.all()
    serializer_class = ProductSerializer


class ProductUsageSerializer(serializers.ModelSerializer):
    '''
    Serializer for product usages
    '''
    year = serializers.IntegerField(required=False)
    month = serializers.IntegerField(required=False)
    quantity = serializers.IntegerField(required=False)
    units = serializers.CharField(max_length=100, required=False)
    product = serializers.SlugRelatedField(slug_field='product_name', queryset=models.Product.objects.all())
    product_user = serializers.SlugRelatedField(slug_field='full_name', queryset=get_user_model().objects.all())

    class Meta:
        model = models.ProductUsage
        fields = ('id', 'product', 'product_user', 'year', 'month', 'quantity', 'units', 'created')
        read_only_fields = ('id', 'created')


class ProductUsageViewSet(viewsets.ModelViewSet):
    '''
    ViewSet for ProductUsages
    '''
    queryset = models.ProductUsage.objects.all()
    serializer_class = ProductUsageSerializer


class BillingRecordSerializer(serializers.ModelSerializer):
    '''
    Serializer for billing records.  BillingRecords should mostly be created
    by BillingCalculators.  They may be created manually, but this is probably
    mostly for display of full objects.  List displays should probably be populated
    with custom SQL.
    '''
    product_usage = serializers.IntegerField(required=False)
    charge = serializers.IntegerField()
    description = serializers.CharField(max_length=200, required=False, allow_blank=True)
    year = serializers.IntegerField(required=False)
    month = serializers.IntegerField(required=False)
#    transactions = TransactionSerializer(many=True, read_only=True, source='transaction_set')

    class Meta:
        model = models.BillingRecord
        fields = ('id', 'account', 'product_usage', 'charge', 'description', 'year', 'month', 'created', 'updated')
        read_only_fields = ('id', 'created', 'updated')
