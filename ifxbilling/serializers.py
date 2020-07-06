from rest_framework import serializers, viewsets
from ifxbilling.models import *

class ExpenseCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCode
        fields  = ( 'id', 'fullcode', 'name', 'root', 'expiration_date', 'active', 'valid_from', 'created', 'updated')
        read_only_fields = ('created', 'updated')

class ExpenseCodeViewSet(viewsets.ModelViewSet):
    '''
    ViewSet for Expense Code models
    '''
    queryset = ExpenseCode.objects.all()
    serializer_class = ExpenseCodeSerializer
