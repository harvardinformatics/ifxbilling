# -*- coding: utf-8 -*-

'''
Serializers and viewsets for ifxbilling
'''
import re
import logging
from django.db import transaction
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
        fields = ('id', 'code', 'name', 'organization', 'account_type', 'root', 'expiration_date', 'active', 'valid_from', 'created', 'updated')
        read_only_fields = ('created', 'updated', 'id')

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
    unit = serializers.CharField(max_length=100)
    is_active = serializers.BooleanField(required=False)

    class Meta:
        model = models.Product
        fields = ('id', 'name', 'price', 'unit', 'is_active')
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
