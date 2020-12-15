# -*- coding: utf-8 -*-

'''
Serializers and viewsets for ifxbilling
'''

from rest_framework import serializers, viewsets
from ifxbilling import models


class AccountSerializer(serializers.ModelSerializer):
    '''
    Serializer for accounts
    '''
    class Meta:
        model = models.Account
        fields = ('id', 'code', 'name', 'account_type', 'root', 'expiration_date', 'active', 'valid_from', 'created', 'updated')
        read_only_fields = ('created', 'updated')


class AccountViewSet(viewsets.ModelViewSet):
    '''
    ViewSet for Account models
    '''
    queryset = models.Account.objects.all()
    serializer_class = AccountSerializer
