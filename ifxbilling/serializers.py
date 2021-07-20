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
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from ifxuser.models import Organization
from ifxuser.serializers import UserSerializer
from fiine.client import API as FiineAPI
from ifxbilling import models
from ifxbilling import fiine
from ifxbilling.permissions import BillingRecordUpdatePermissions


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
    valid_from = serializers.DateField(required=False)
    expiration_date = serializers.DateField(required=False)

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
        if 'account_type' not in validated_data or validated_data['account_type'] == 'Expense Code':
            if not models.EXPENSE_CODE_RE.match(validated_data['code']) and not models.EXPENSE_CODE_SANS_OBJECT_RE.match(validated_data['code']):
                raise serializers.ValidationError(
                    detail={
                        'code': f'Expense codes must be dash separated and contain either 33 digits or 29 (33 sans object code)'
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
    product_number = serializers.ReadOnlyField()
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
        Create new product in fiine first, then save any rates
        '''
        kwargs = {
            'product_name': validated_data['product_name'],
            'product_description': validated_data['product_description'],
        }
        if 'billing_calculator' in validated_data and validated_data['billing_calculator']:
            kwargs['billing_calculator'] = validated_data['billing_calculator']

        product = fiine.createNewProduct(**kwargs)

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
        Update product and rates.  Ensure updated in Fiine as well.
        '''
        product = FiineAPI.readProduct(product_number=instance.product_number)
        product.product_name = validated_data['product_name']
        product.description = validated_data['product_description']
        FiineAPI.updateProduct(**product.to_dict())

        for attr in ['product_name', 'product_description', 'billing_calculator']:
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
    # The product should probably be connected by product_number, but, within a given application, names should be unique.
    product = serializers.SlugRelatedField(slug_field='product_name', queryset=models.Product.objects.all())
    product_user = UserSerializer(many=False, read_only=True)
    start_date = serializers.DateTimeField(required=False)
    description = serializers.CharField(max_length=2000, required=False)

    class Meta:
        model = models.ProductUsage
        fields = ('id', 'product', 'product_user', 'year', 'month', 'quantity', 'units', 'created', 'start_date', 'description')
        read_only_fields = ('id', 'created')

    @transaction.atomic
    def create(self, validated_data):
        # Pop the user
        if 'product_user' not in self.initial_data:
            raise serializers.ValidationError(
                detail={
                    'product_user': 'product_user must be set'
                }
            )
        product_user_data = self.initial_data['product_user']
        try:
            product_user_ifxid = product_user_data['ifxid']
            product_user = get_user_model().objects.get(ifxid=product_user_ifxid)
            validated_data['product_user'] = product_user
        except get_user_model().DoesNotExist:
            raise serializers.ValidationError(
                detail={
                    'product_user': f'Cannot find product user with ifxid {product_user_ifxid}'
                }
            )
        if 'start_date' not in validated_data:
            validated_data['start_date'] = timezone.now()
        product_usage = models.ProductUsage.objects.create(**validated_data)
        return product_usage

    @transaction.atomic
    def update(self, instance, validated_data):
        if 'product_user' not in self.initial_data:
            raise serializers.ValidationError(
                detail={
                    'product_user': 'product_user must be set'
                }
            )
        product_user_data = self.initial_data['product_user']
        try:
            product_user_ifxid = product_user_data['ifxid']
            product_user = get_user_model().objects.get(ifxid=product_user_ifxid)
            validated_data['product_user'] = product_user
        except get_user_model().DoesNotExist:
            raise serializers.ValidationError(
                detail={
                    'product_user': f'Cannot find product user with ifxid {product_user_ifxid}'
                }
            )

        for attr in ['year', 'month', 'quantity', 'units', 'product', 'product_user', 'start_date', 'description']:
            if attr in validated_data:
                setattr(instance, attr, validated_data[attr])

        instance.save()
        return instance


class ProductUsageViewSet(viewsets.ModelViewSet):
    '''
    ViewSet for ProductUsages
    '''
    queryset = models.ProductUsage.objects.all()
    serializer_class = ProductUsageSerializer


class TransactionSerializer(serializers.ModelSerializer):
    '''
    Serilizer for BillingRecord Transactions.
    '''
    charge = serializers.IntegerField()
    description = serializers.CharField(max_length=200)
    author = UserSerializer(read_only=True)

    class Meta:
        model = models.Transaction
        fields = ('id', 'charge', 'description', 'created', 'author')
        read_only_fields = ('id', 'created', 'author')

class BillingRecordStateSerializer(serializers.ModelSerializer):
    '''
    Serializer for billing record state
    '''
    name = serializers.CharField(max_length=100)
    user = serializers.SlugRelatedField(slug_field='full_name', queryset=get_user_model().objects.all())
    approvers = serializers.SlugRelatedField(slug_field='full_name', queryset=get_user_model().objects.all(), many=True)
    comment = serializers.CharField(max_length=1000, required=False)

    class Meta:
        model = models.BillingRecordState
        fields = ('id', 'name', 'user', 'approvers', 'comment', 'created', 'updated')
        read_only_fields = ('id', 'created', 'updated')

class BillingRecordListSerializer(serializers.ListSerializer):
    '''
    Serializer for list of billing records for bulk update.
    '''
    def update(self, instances, validated_data):
        results = []
        for i, instance in enumerate(instances):
            results.append(self.child.update(instance, validated_data[i], i))
        return results

class BillingRecordSerializer(serializers.ModelSerializer):
    '''
    Serializer for billing records.  BillingRecords should mostly be created
    by BillingCalculators.  They may be created manually, but this is probably
    mostly for display of full objects.  List displays should probably be populated
    with custom SQL.

    If real_user_ifxid is in the initial_data dict and the logged in user is fiine,
    the ifxid will be used to set the 'author' or 'updated_by' value
    '''
    product_usage = ProductUsageSerializer(read_only=True)
    charge = serializers.IntegerField(read_only=True)
    description = serializers.CharField(max_length=200, required=False, allow_blank=True)
    year = serializers.IntegerField(required=False)
    month = serializers.IntegerField(required=False)
    account = AccountSerializer(many=False, read_only=True)
    transactions = TransactionSerializer(many=True, read_only=True, source='transaction_set')
    current_state = serializers.CharField(max_length=200, allow_blank=True, required=False)
    billing_record_states = BillingRecordStateSerializer(source='billingrecordstate_set', many=True, read_only=True)
    percent = serializers.IntegerField(required=False)
    author = UserSerializer(read_only=True)

    class Meta:
        model = models.BillingRecord
        fields = (
            'id',
            'account',
            'product_usage',
            'charge',
            'description',
            'year',
            'month',
            'transactions',
            'current_state',
            'billing_record_states',
            'created',
            'updated',
            'percent',
            'author',
        )
        read_only_fields = ('id', 'created', 'updated')
        list_serializer_class = BillingRecordListSerializer

    def get_current_user(self):
        '''
        Return the current user
        '''
        return self.context['request'].user

    def get_billing_record_author(self):
        '''
        Return user that should be the author or updated_by value.  If real_author_ifxid is in initial_data, get that user
        '''
        real_user_ifxid = self.initial_data.get('real_user_ifxid')
        if real_user_ifxid:
            current_user = self.get_current_user()
            if current_user.username == 'fiine':
                try:
                    author = get_user_model().objects.get(ifxid=real_user_ifxid)
                    return author
                except get_user_model().DoesNotExist:
                    raise serializers.ValidationError(
                        detail={
                            'real_user_ifxid': f'Cannot find user with ifxid {real_user_ifxid}'
                        }
                    )
            else:
                raise serializers.ValidationError(
                    detail={
                        'real_user_ifxid': f'User {current_user} cannot set a different author'
                    }
                )
        else:
            return self.get_current_user()

    def get_transaction_author(self, transaction_data):
        '''
        Determine author for a transaction
        '''
        current_user = self.get_current_user()
        author = current_user
        if 'author' in transaction_data and transaction_data['author'] and 'ifxid' in transaction_data['author'] and transaction_data['author']['ifxid']:
            try:
                author = get_user_model().objects.get(ifxid=transaction_data['author']['ifxid'])
            except get_user_model().DoesNotExist:
                raise serializers.ValidationError(
                    detail={
                        'transactions': f'Cannot find transaction author with ifxid {transaction_data["author"]["ifxid"]}'
                    }
                )
            if current_user.username not in ['fiine', author.username]:
                raise serializers.ValidationError(
                    detail={
                        'transactions': f'User {current_user} cannot set transaction author to other users'
                    }
                )
        return author

    @transaction.atomic
    def create(self, validated_data):
        '''
        Ensure that BillingRecord is composed of transactions.
        '''
        current_username = self.get_current_user().username

        # Fail if transactions are missing
        if 'transactions' not in self.initial_data:
            raise serializers.ValidationError(
                detail={
                    'transactions': 'Billing record must have at least one transaction'
                }
            )

        if 'account' not in self.initial_data:
            raise serializers.ValidationError(
                detail={
                    'account': 'Billing record requires an account'
                }
            )

        # Check for product_usage, fetch and add to validated_data
        if 'product_usage' not in self.initial_data \
            or not self.initial_data['product_usage'] \
            or not 'id' in self.initial_data['product_usage'] \
            or not self.initial_data['product_usage']['id']:
            raise serializers.ValidationError(
                detail={
                    'product_usage': 'An existing product usage must be defined.'
                }
            )
        product_usage_id = self.initial_data['product_usage']['id']
        try:
            product_usage = models.ProductUsage.objects.get(id=int(product_usage_id))
            validated_data['product_usage'] = product_usage
        except Exception as e:
            logger.exception(e)
            raise serializers.ValidationError(
                detail={
                    'product_usage': 'Cannot find the specifiec product usage record.'
                }
            )

        account_data = self.initial_data['account']
        try:
            account_id = account_data['id']
            account = models.Account.objects.get(id=account_id)
            validated_data['account'] = account
        except models.Account.DoesNotExist:
            raise serializers.ValidationError(
                detail={
                    'account': f'Cannot find expense code / PO with account id {account_id}'
                }
            )

        # Set the "author"
        validated_data['author'] = self.get_billing_record_author()

        # Create the billing record.  Charge will be 0
        billing_record = models.BillingRecord.objects.create(**validated_data)

        # Set any states that exist
        if 'billing_record_states' in self.initial_data:
            billing_record_states_data = self.initial_data['billing_record_states']
            for state_data in billing_record_states_data:
                if 'user' not in state_data or not state_data['user']:
                    state_data['user'] = current_username
                if current_username not in ['fiine', state_data['user']]:
                    raise serializers.ValidationError(
                        detail={
                            'billing_record_states': 'BillingRecord state cannot be set by another user'
                        }
                    )
                billing_record.setState(**state_data)

        # Set the transactions to get the actual charge
        transactions_data = self.initial_data['transactions']
        for transaction_data in transactions_data:
            transaction_data['author'] = self.get_transaction_author(transaction_data)
            models.Transaction.objects.create(**transaction_data, billing_record=billing_record)
        return billing_record

    @transaction.atomic
    def update(self, instance, validated_data, bulk_id=None):
        '''
        Ensure the BillingRecord is composed of transactions.
        Only the account and description may be modified.  Transactions and billing record states may be added.
        Added billing record states will be used to call setState
        '''
        current_username = self.get_current_user().username
        initial_data = self.initial_data
        if bulk_id is not None:
            initial_data = self.initial_data[bulk_id]
        if 'transactions' not in initial_data:
            raise serializers.ValidationError(
                detail={
                    'transactions': 'Billing record must have at least one transaction'
                }
            )

        if 'billing_record_states' not in initial_data:
            raise serializers.ValidationError(
                detail={
                    'billing_record_states': 'Billing record must have at least one billing record state'
                }
            )
        # Check for product_usage, fetch and add to validated_data
        if 'product_usage' not in initial_data \
            or not initial_data['product_usage'] \
            or not initial_data['product_usage']['id']:
            raise serializers.ValidationError(
                detail={
                    'product_usage': 'An existing product usage must be defined.'
                }
            )
        product_usage_id = initial_data['product_usage']['id']
        try:
            product_usage = models.ProductUsage.objects.get(id=int(product_usage_id))
            validated_data['product_usage'] = product_usage
        except Exception as e:
            logger.exception(e)
            raise serializers.ValidationError(
                detail={
                    'product_usage': 'Cannot find the specific product usage record.'
                }
            )

        for attr in ['account', 'description']:
            if attr in validated_data:
                setattr(instance, attr, validated_data[attr])

        validated_data['updated_by'] = self.get_billing_record_author()

        instance.save()

        # Only add new transactions.  Old ones cannot be removed.
        transactions_data = initial_data['transactions']
        for transaction_data in transactions_data:
            if 'id' not in transaction_data:
                transaction_data['author'] = self.get_transaction_author(transaction_data)
                models.Transaction.objects.create(**transaction_data, billing_record=instance)

        # Only add new billing record states.  Old ones cannot be removed.
        billing_record_states_data = initial_data['billing_record_states']
        for state_data in billing_record_states_data:
            if 'id' not in state_data:
                if 'user' not in state_data or not state_data['user']:
                    state_data['user'] = current_username
                if current_username not in ['fiine', state_data['user']]:
                    raise serializers.ValidationError(
                        detail={
                            'billing_record_states': f'User {current_username} cannot set billing record state for other users'
                        }
                    )
                instance.setState(**state_data)

        return instance


class BillingRecordViewSet(viewsets.ModelViewSet):
    '''
    ViewSet for BillingRecords
    '''
    serializer_class = BillingRecordSerializer
    permission_classes = [BillingRecordUpdatePermissions]

    def get_queryset(self):
        year = self.request.query_params.get('year')
        month = self.request.query_params.get('month')
        organization = self.request.query_params.get('organization')
        root = self.request.query_params.get('root')

        queryset = models.BillingRecord.objects.all()

        if year:
            queryset = queryset.filter(year=year)
        if month:
            queryset = queryset.filter(month=month)
        if organization:
            queryset = queryset.filter(account__organization__slug=organization)
        if root:
            queryset = queryset.filter(account__root=root)

        return queryset.order_by('id')

    @action(detail=False, methods=['post'])
    def bulk_update(self, request, *args, **kwargs):
        '''
        Call serializer update on an array of billing records
        '''
        ids = [int(r['id']) for r in request.data]
        instances = models.BillingRecord.objects.filter(id__in=ids)
        serializer = self.get_serializer(instances, data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)
