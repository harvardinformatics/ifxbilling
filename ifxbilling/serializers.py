# -*- coding: utf-8 -*-

'''
Serializers and viewsets for ifxbilling
'''
from rest_framework import serializers, viewsets
from ifxuser.models import Organization
from ifxbilling import models


class AccountSerializer(serializers.ModelSerializer):
    '''
    Serializer for accounts
    '''
    organization = serializers.SlugRelatedField(slug_field='slug', queryset=Organization.objects.all())
    class Meta:
        model = models.Account
        fields = ('id', 'code', 'name', 'organization', 'account_type', 'root', 'expiration_date', 'active', 'valid_from', 'created', 'updated')
        read_only_fields = ('created', 'updated', 'id')


class AccountViewSet(viewsets.ModelViewSet):
    '''
    ViewSet for Account models
    '''
    queryset = models.Account.objects.all()
    serializer_class = AccountSerializer


class ProductSerializer(serializers.ModelSerializer):
    '''
    Serializer for Products
    '''
    class Meta:
        model = models.Product
        fields = ('id', 'code', 'name', 'account_type', 'root', 'expiration_date', 'active', 'valid_from', 'created', 'updated')
        read_only_fields = ('created', 'updated', 'id')


class ProductViewSet(viewsets.ModelViewSet):
    '''
    ViewSet for Product models
    '''
    queryset = models.Product.objects.all()
    serializer_class = ProductSerializer
