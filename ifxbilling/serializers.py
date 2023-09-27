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
from decimal import Decimal
from django.db import transaction
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from ifxuser.models import Organization
from ifxuser.serializers import UserSerializer
from fiine.client import API as FiineAPI
from ifxvalidcode.ec_functions import ExpenseCodeFields
from ifxbilling import models
from ifxbilling import fiine
from ifxbilling.permissions import BillingRecordUpdatePermissions


logger = logging.getLogger(__name__)

class FacilitySerializer(serializers.ModelSerializer):
    '''
    Serializer for Facility
    '''
    class Meta:
        model = models.Facility
        fields = (
            'id',
            'name',
            'application_username',
            'invoice_prefix'
        )


class FacilityViewSet(viewsets.ModelViewSet):
    '''
    Viewset for Facility
    '''
    serializer_class = FacilitySerializer

    def list(self, request):
        return super().list(self, request)

    def get_queryset(self):
        '''
        Allow query by name, application_username
        '''
        name = self.request.query_params.get('name')
        application_username = self.request.query_params.get('application_username')

        facilities = models.Facility.objects.all()

        if name:
            facilities = facilities.filter(name=name)
        elif application_username:
            facilities = facilities.filter(application_username=application_username)

        return facilities

class BillingRecordAccountSerializer(serializers.ModelSerializer):
    '''
    Read-only serializer for billing records
    '''
    organization = serializers.SlugRelatedField(slug_field='slug', queryset=Organization.objects.all())

    class Meta:
        model = models.Account
        fields = ('id', 'code', 'name', 'organization', 'account_type', 'root', 'expiration_date', 'active', 'valid_from', 'created', 'updated', 'slug')
        read_only_fields = ('id', 'code', 'name', 'organization', 'account_type', 'root', 'expiration_date', 'active', 'valid_from', 'created', 'updated', 'slug')


class SkinnyUserSerializer(serializers.ModelSerializer):
    '''
    Serializer that just provides user basics for UserAccount and UserProductAccount serializers
    '''
    class Meta:
        model = get_user_model()
        fields = (
            'id',
            'ifxid',
            'username',
            'first_name',
            'last_name',
            'full_name',
            'primary_affiliation',
            'email',
            'is_active',
        )


class UserAccountSerializer(serializers.ModelSerializer):
    '''
    Read only serializer for AccountSerializer
    '''
    user = SkinnyUserSerializer(read_only=True)

    class Meta:
        model = models.UserAccount
        fields = ('id', 'user', 'is_valid')
        read_only_fields = ('id', 'is_valid')


class UserProductAccountSerializer(serializers.ModelSerializer):
    '''
    Read only serializer for AccountSerializer
    '''
    user = SkinnyUserSerializer(read_only=True)
    product = serializers.SlugRelatedField(slug_field='product_name', read_only=True)

    class Meta:
        model = models.UserProductAccount
        fields = ('id', 'user', 'product', 'percent', 'is_valid')
        read_only_fields = ('id', 'is_valid')


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
    user_accounts = UserAccountSerializer(many=True, read_only=True, source='useraccount_set')
    user_product_accounts = UserProductAccountSerializer(many=True, read_only=True, source='userproductaccount_set')

    class Meta:
        model = models.Account
        fields = ('id', 'code', 'name', 'organization', 'account_type', 'root', 'expiration_date', 'active', 'valid_from', 'created', 'updated', 'slug', 'user_accounts', 'user_product_accounts')
        read_only_fields = ('created', 'updated', 'id', 'slug')

    @transaction.atomic
    def create(self, validated_data):
        '''
        Ensure that an improper root value is a ValidationError
        '''
        if not re.match(r'^[0-9]{5}$', validated_data['root']):
            raise serializers.ValidationError(
                detail={
                    'root': 'Root must be a 5 digit number.'
                }
            )
        if 'account_type' not in validated_data or validated_data['account_type'] == 'Expense Code':
            if not models.EXPENSE_CODE_RE.match(validated_data['code']) and not models.EXPENSE_CODE_SANS_OBJECT_RE.match(validated_data['code']):
                raise serializers.ValidationError(
                    detail={
                        'code': 'Expense codes must be dash separated and contain either 33 digits or 29 (33 sans object code)'
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
                    'root': 'Root must be a 5 digit number.'
                }
            )
        return super().update(instance, validated_data)


class AccountViewSet(viewsets.ModelViewSet):
    '''
    ViewSet for Account models

    Filter by name, active status, organization, or account_type.

    If the 'active' query param is present, it must be set to 'true' (or True or TRUE) to get active
    accounts.  Any other value will get inactive accounts.  If the param is missing both
    active and inactive accounts will be returned.

    The account_type parameter can be set to Expense Code or PO

    The organization parameter can either be a slug or a name (distinguishes using " (a")
    '''
    serializer_class = AccountSerializer

    def get_queryset(self):
        name = self.request.query_params.get('name')
        active = self.request.query_params.get('active', False)
        account_type = self.request.query_params.get('account_type')
        organizationstr = self.request.query_params.get('organization')

        queryset = models.Account.objects.all()

        if name:
            queryset = queryset.filter(name=name)
        if active:
            queryset = queryset.filter(active=active.upper() == 'TRUE')
        if account_type:
            queryset = queryset.filter(account_type=account_type)
        if organizationstr:
            try:
                if ' (a' in organizationstr:
                    organization = Organization.objects.get(slug=organizationstr)
                else:
                    organization = Organization.objects.get(name=organizationstr)
                queryset = queryset.filter(organization=organization)
            except Organization.DoesNotExist as dne:
                raise serializers.ValidationError(
                    detail=f'Cannot find organization identified by {organizationstr}'
                ) from dne
        return queryset


class RateSerializer(serializers.ModelSerializer):
    '''
    Serializer for Rates
    '''
    name = serializers.CharField(max_length=50)
    description = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    price = serializers.IntegerField()
    decimal_price = serializers.DecimalField(max_digits=19, decimal_places=4)
    units = serializers.CharField(max_length=100)
    max_qty = serializers.IntegerField()
    is_active = serializers.BooleanField(required=False)
    version = serializers.IntegerField()
    sort_order = serializers.IntegerField()

    class Meta:
        model = models.Rate
        fields = ('id', 'name', 'description', 'price', 'decimal_price', 'units', 'is_active', 'max_qty', 'created', 'updated', 'version', 'sort_order')
        read_only_fields = ('id', 'created', 'updated', 'version')


class ProductSerializer(serializers.ModelSerializer):
    '''
    Serializer for Products
    '''
    product_number = serializers.ReadOnlyField()
    product_name = serializers.CharField(max_length=50)
    product_description = serializers.CharField(max_length=200)
    facility = serializers.SlugRelatedField(slug_field='name', queryset=models.Facility.objects.all())
    billing_calculator = serializers.CharField(max_length=100, required=False)
    rates = RateSerializer(many=True, read_only=True, source='rate_set')

    class Meta:
        model = models.Product
        fields = ('id', 'product_number', 'product_name', 'product_description', 'billing_calculator', 'rates', 'facility', 'billable')
        read_only_fields = ('id',)

    @transaction.atomic
    def get_validated_data(self, validated_data):
        '''
        Create new product in fiine first, then save any rates
        '''
        kwargs = {
            'product_name': validated_data['product_name'],
            'product_description': validated_data['product_description'],
            'facility': validated_data['facility'],
            'billable': validated_data['billable'],
        }
        if 'billing_calculator' in validated_data and validated_data['billing_calculator']:
            kwargs['billing_calculator'] = validated_data['billing_calculator']
        return kwargs

    def create(self, validated_data):
        validated_data = self.get_validated_data(validated_data)
        try:
            product = fiine.create_new_product(**validated_data)
        except Exception as e:
            logger.exception(e)
            if 'Not authorized' in str(e):
                msg = 'Cannot access fiine system due to authorization failure.  Check application key.'
            else:
                msg = f'fiine system access failed: {e}'
            raise serializers.ValidationError(
                detail={
                    'product_name': msg
                }
            )
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
        try:
            product = FiineAPI.readProduct(product_number=instance.product_number)
            product.product_name = validated_data['product_name']
            product.description = validated_data['product_description']
            product.billable = validated_data['billable']
            FiineAPI.updateProduct(**product.to_dict())
        except Exception as e:
            logger.exception(e)
            if 'Not authorized' in str(e):
                msg = 'Cannot access fiine system due to authorization failure.  Check application key.'
            else:
                msg = f'fiine system access failed: {e}'
            raise serializers.ValidationError(
                detail={
                    'product_name': msg
                }
            )

        for attr in ['product_name', 'product_description', 'billable']:
            setattr(instance, attr, validated_data[attr])
        if 'billing_calculator' in validated_data and validated_data['billing_calculator']:
            instance.billing_calculator = validated_data['billing_calculator']

        instance.save()

        # Only is_active flag can be updated for a Rate and only to set from true to false; other updates are an error
        # If there is a new Rate, the version must be incremented
        if 'rates' in self.initial_data and self.initial_data['rates']:
            # Enure that rate_data is not less than current number of rates
            if len(self.initial_data['rates']) < models.Rate.objects.filter(product=instance).count():
                raise serializers.ValidationError(
                    detail={
                        'rates': 'Rates cannot be removed'
                    }
                )
            for rate_data in self.initial_data['rates']:
                logger.debug(f'Rate data {rate_data}')
                if rate_data.get('id'):
                    try:
                        rate = models.Rate.objects.get(id=rate_data['id'])
                        if rate_data.get('decimal_price') is None:
                            raise serializers.ValidationError(
                                detail={
                                    'rates': f'Rate {rate_data["name"]} needs a decimal price'
                                }
                            )
                        rate_data['decimal_price'] = Decimal(rate_data['decimal_price'])
                        for field in ['name', 'decimal_price', 'max_qty', 'price', 'units']:
                            if rate_data.get(field) != getattr(rate, field):
                                raise serializers.ValidationError(
                                    detail={
                                        'rates': f'Cannot change {field} on a Rate. Must create a new Rate and deactivate old one.'
                                    }
                                )
                        if not rate_data['is_active'] and rate.is_active:
                            rate.is_active = rate_data['is_active']
                            rate.save()
                    except models.Rate.DoesNotExist as dne:
                        raise serializers.ValidationError(
                            detail={
                                'rates': f'Cannot find rate with id {rate_data["id"]}'
                            }
                        ) from dne
                else:
                    # If there is a previous rate with the same name and product, increment the version
                    old_rates = models.Rate.objects.filter(product=instance, name=rate_data['name']).order_by('-version')
                    if old_rates:
                        rate_data['version'] = old_rates[0].version + 1
                    else:
                        rate_data['version'] = 1
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


class ProductUsageProcessingSerializer(serializers.ModelSerializer):
    '''
    Read only serializer for ProductUsageProcessing
    '''
    class Meta:
        model = models.ProductUsageProcessing
        fields = (
            'resolved',
            'error_message',
            'created',
            'updated',
        )


class ProductUsageSerializer(serializers.ModelSerializer):
    '''
    Serializer for product usages
    '''
    year = serializers.IntegerField(required=False)
    month = serializers.IntegerField(required=False)
    quantity = serializers.IntegerField(required=False)
    decimal_quantity = serializers.DecimalField(required=False, max_digits=19, decimal_places=4, allow_null=True)
    units = serializers.CharField(max_length=100, required=False)
    # The product should probably be connected by product_number, but, within a given application, names should be unique.
    product = serializers.SlugRelatedField(slug_field='product_name', queryset=models.Product.objects.all())
    product_user = UserSerializer(many=False, read_only=True)
    start_date = serializers.DateTimeField(required=False)
    end_date = serializers.DateTimeField(required=False)
    description = serializers.CharField(max_length=2000, required=False)
    created = serializers.DateTimeField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)
    logged_by = UserSerializer(many=False, read_only=True, required=False)
    organization = serializers.SlugRelatedField(slug_field='slug', queryset=Organization.objects.all())
    processing = ProductUsageProcessingSerializer(source='productusageprocessing_set', many=True, read_only=True)

    class Meta:
        model = models.ProductUsage
        fields = (
            'id',
            'product',
            'product_user',
            'year',
            'month',
            'quantity',
            'decimal_quantity',
            'units',
            'created',
            'start_date',
            'end_date',
            'description',
            'updated',
            'logged_by',
            'organization',
            'processing',
        )
        read_only_fields = ('id', 'created', 'updated')

    def get_validated_data(self, validated_data, initial_data):
        '''
        Sets product user, start date (if missing), and logged by to request.user (if missing)
        '''
        if 'product_user' not in initial_data:
            raise serializers.ValidationError(
                detail={
                    'product_user': 'product_user must be set'
                }
            )
        product_user_data = initial_data['product_user']
        try:
            product_user_ifxid = product_user_data['ifxid']
            product_user = get_user_model().objects.get(ifxid=product_user_ifxid)
            validated_data['product_user'] = product_user
        except get_user_model().DoesNotExist as dne:
            raise serializers.ValidationError(
                detail={
                    'product_user': f'Cannot find product user with ifxid {product_user_ifxid}'
                }
            ) from dne
        except get_user_model().MultipleObjectsReturned:
            # Might be multiple user records with the same ifxid
            product_user_id = product_user_data.get('id')
            try:
                product_user = get_user_model().objects.get(id=product_user_id)
                validated_data['product_user'] = product_user
            except get_user_model().DoesNotExist as dne2:
                raise serializers.ValidationError(
                    detail={
                        'product_user': f'Cannot find product user with id {product_user_id}'
                    }
                ) from dne2


        if 'start_date' not in validated_data:
            validated_data['start_date'] = timezone.now()
        validated_data['logged_by'] = self.context['request'].user
        return validated_data

    @transaction.atomic
    def create(self, validated_data):
        validated_data = self.get_validated_data(validated_data, self.initial_data)
        instance = self.Meta.model.objects.create(**validated_data)
        return instance

    @transaction.atomic
    def update(self, instance, validated_data, bulk_id=None):
        initial_data = self.initial_data
        if bulk_id is not None:
            initial_data = self.initial_data[bulk_id]

        validated_data = self.get_validated_data(validated_data, initial_data)

        for attr in ['year', 'month', 'quantity', 'decimal_quantity', 'units', 'product', 'product_user', 'start_date', 'description', 'end_date', 'organization', 'processing']:
            if attr in validated_data:
                setattr(instance, attr, validated_data[attr])

        instance.save()
        return instance


class ProductUsageViewSet(viewsets.ModelViewSet):
    '''
    ViewSet for ProductUsages
    '''
    serializer_class = ProductUsageSerializer

    def get_queryset(self):
        invoice_prefix = self.request.query_params.get('invoice_prefix')
        product_id = self.request.query_params.get('product')
        product_name = self.request.query_params.get('product_name')
        year = self.request.query_params.get('year')
        month = self.request.query_params.get('month')
        product_user_username = self.request.query_params.get('product_user')

        queryset = models.ProductUsage.objects.all()

        if year:
            queryset = queryset.filter(year=year)
        if month:
            queryset = queryset.filter(month=month)
        if product_id:
            queryset = queryset.filter(product__id=product_id)
        if product_name:
            queryset = queryset.filter(product__product_name=product_name)
        if invoice_prefix:
            queryset = queryset.filter(product__facility__invoice_prefix=invoice_prefix)
        if product_user_username:
            queryset = queryset.filter(product_user__username=product_user_username)

        return queryset.order_by('-start_date')


class TransactionSerializer(serializers.ModelSerializer):
    '''
    Serilizer for BillingRecord Transactions.
    '''
    charge = serializers.IntegerField()
    description = serializers.CharField(max_length=200)
    author = UserSerializer(read_only=True)

    class Meta:
        model = models.Transaction
        fields = ('id', 'charge', 'decimal_charge', 'description', 'created', 'author', 'rate')
        read_only_fields = ('id', 'created', 'author', 'rate')

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
    # pylint: disable=arguments-renamed
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
    decimal_charge = serializers.DecimalField(read_only=True, max_digits=19, decimal_places=4)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    year = serializers.IntegerField(required=False)
    month = serializers.IntegerField(required=False)
    account = BillingRecordAccountSerializer(many=False, read_only=True)
    transactions = TransactionSerializer(many=True, read_only=True, source='transaction_set')
    current_state = serializers.CharField(max_length=200, allow_blank=True, required=False)
    billing_record_states = BillingRecordStateSerializer(source='billingrecordstate_set', many=True, read_only=True)
    percent = serializers.IntegerField(required=False)
    author = UserSerializer(read_only=True)
    product_usage_link_text = serializers.CharField(read_only=True)
    product_usage_url = serializers.CharField(read_only=True)
    rate_obj = RateSerializer(read_only=True)
    decimal_quantity = serializers.DecimalField(read_only=True, max_digits=19, decimal_places=4)
    start_date = serializers.DateTimeField(read_only=True,)  # Read only because an empty value can't be properly validated
    end_date = serializers.DateTimeField(read_only=True,)

    class Meta:
        model = models.BillingRecord
        fields = (
            'id',
            'account',
            'product_usage',
            'charge',
            'decimal_charge',
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
            'rate',
            'product_usage_link_text',
            'product_usage_url',
            'rate_obj',
            'decimal_quantity',
            'start_date',
            'end_date',
        )
        read_only_fields = ('id', 'created', 'updated', 'rate', 'rate_obj')
        list_serializer_class = BillingRecordListSerializer

    def to_internal_value(self, data):
        if data.get('start_date') == '':
            data['start_date'] = None
        if data.get('end_date') == '':
            data['end_date'] = None
        return super().to_internal_value(data)

    def get_current_user(self):
        '''
        Return the current user
        '''
        return self.context['request'].user

    def get_billing_record_author(self, initial_data):
        '''
        Return user that should be the author or updated_by value.  If real_author_ifxid is in initial_data, get that user
        '''
        real_user_ifxid = initial_data.get('real_user_ifxid')
        if real_user_ifxid:
            current_user = self.get_current_user()
            if current_user.username == 'fiine':
                try:
                    author = get_user_model().objects.get(ifxid=real_user_ifxid)
                    return author
                except get_user_model().DoesNotExist as dne:
                    raise serializers.ValidationError(
                        detail={
                            'real_user_ifxid': f'Cannot find user with ifxid {real_user_ifxid}'
                        }
                    ) from dne
                except get_user_model().MultipleObjectsReturned:
                    try:
                        author = get_user_model().objects.get(ifxid=real_user_ifxid, groups__name=settings.GROUPS.PREFERRED_BILLING_RECORD_APPROVAL_ACCOUNT_GROUP_NAME)
                    except Exception as e:
                        raise serializers.ValidationError(
                            detail={
                                'real_user_ifxid': f'Attempting to approve billing records with user {real_user_ifxid} that has multiple logins none of which is in the {settings.GROUPS.PREFERRED_BILLING_RECORD_APPROVAL_ACCOUNT_GROUP_NAME} auth group.'
                            }
                        ) from e
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
            except get_user_model().DoesNotExist as dne:
                raise serializers.ValidationError(
                    detail={
                        'transactions': f'Cannot find transaction author with ifxid {transaction_data["author"]["ifxid"]}'
                    }
                ) from dne
            if current_user.username not in ['fiine', author.username]:
                raise serializers.ValidationError(
                    detail={
                        'transactions': f'User {current_user} cannot set transaction author to other users'
                    }
                )
        return author

    def get_state_username(self, state_data):
        '''
        Username should be from current user unless logged in user is fiine and an IFXID is set
        '''
        current_user = self.get_current_user()
        state_username = current_user.username
        if 'user' in state_data and state_data['user'] and state_data['user'] != current_user.username:
            if current_user.username == 'fiine':
                try:
                    state_username = get_user_model().objects.get(ifxid=state_data['user']).username
                except get_user_model().DoesNotExist as dne:
                    raise serializers.ValidationError(
                        detail={
                            'states': f'Unable to find user with ifxid {state_data["user"]}'
                        }
                    ) from dne
                except MultipleObjectsReturned as mor:
                    # Try the Preferred Billing Record Approval Account
                    if hasattr(settings, 'GROUPS') and hasattr(settings.GROUPS, 'PREFERRED_BILLING_RECORD_APPROVAL_ACCOUNT_GROUP_NAME'):
                        preferred_account_group_name = settings.GROUPS.PREFERRED_BILLING_RECORD_APPROVAL_ACCOUNT_GROUP_NAME
                        try:
                            state_username = get_user_model().objects.get(ifxid=state_data['user'], groups__name=preferred_account_group_name).username
                        except get_user_model().DoesNotExist as dne:
                            raise serializers.ValidationError(
                                detail={
                                    'states': f'User with ifxid {state_data["user"]} has multiple user records, but none has {preferred_account_group_name} set.'
                                }
                            ) from dne
                    else:
                        raise serializers.ValidationError(
                            detail={
                                'states': f'User with ifxid {state_data["user"]} has multiple user records and there is no way to set a preference for billing.'
                            }
                        ) from mor
            else:
                raise serializers.ValidationError(
                    detail={
                        'states': f'Current user {current_user} cannot set states with other users'
                    }
                )
        return state_username

    @transaction.atomic
    def create(self, validated_data):
        '''
        Ensure that BillingRecord is composed of transactions.
        '''
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
                    'product_usage': 'Cannot find the specific product usage record.'
                }
            )

        account_data = self.initial_data['account']
        try:
            # This can be an id since, if billing records are ever created, it should be in the facility application
            account_id = account_data['id']
            account = models.Account.objects.get(id=account_id)
            validated_data['account'] = account
        except models.Account.DoesNotExist as dne:
            raise serializers.ValidationError(
                detail={
                    'account': f'Cannot find expense code / PO with account id {account_id}'
                }
            ) from dne

        # Set the "author"
        validated_data['author'] = self.get_billing_record_author(self.initial_data)

        # If start_date and end_date are not set, get them from the product_usage
        validated_data['start_date'] = self.initial_data.get('start_date')
        if not validated_data['start_date']:
            validated_data['start_date'] = product_usage.start_date
        validated_data['end_date'] = self.initial_data.get('end_date')
        if not validated_data['end_date']:
            validated_data['end_date'] = product_usage.end_date

        # Create the billing record.  Charge will be 0
        billing_record = models.BillingRecord.objects.create(**validated_data)

        # Set any states that exist
        if 'billing_record_states' in self.initial_data:
            billing_record_states_data = self.initial_data['billing_record_states']
            for state_data in billing_record_states_data:
                state_data['user'] = self.get_state_username(state_data)
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

        initial_data = self.initial_data
        if bulk_id is not None:
            initial_data = self.initial_data[bulk_id]

        if 'billing_record_states' not in initial_data:
            raise serializers.ValidationError(
                detail={
                    'billing_record_states': 'Billing record must have at least one billing record state'
                }
            )
        billing_record_states_data = initial_data['billing_record_states']
        if instance.current_state == 'FINAL':
            # in final only certain state changes can be made
            for state_data in billing_record_states_data:
                if 'id' not in state_data and 'name' in state_data and state_data['name'] in ['FAILED_INVOICE_GENERATION']:
                    state_data['user'] = self.get_state_username(state_data)
                    logger.info(f'setting state to {state_data["name"]} even though record is FINAL')
                    instance.setState(**state_data)
                    return instance
            raise serializers.ValidationError(
                detail={
                    'current_state': 'Cannot update billing records that are in the FINAL state'
                }
            )

        if 'transactions' not in initial_data:
            raise serializers.ValidationError(
                detail={
                    'transactions': 'Billing record must have at least one transaction'
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

        # Find account for updating based on code and organization because the id may be from fiine
        account_data = initial_data['account']
        try:
            # Ensure that account string has the right object code
            if account_data['account_type'] == 'Expense Code':
                facility_object_code = product_usage.product.facility.object_code
                if not facility_object_code:
                    raise serializers.ValidationError(
                        detail={
                            'product_usage': f'Cannot find object code for {product_usage.product.facility}'
                        }
                    )
                account_data['code'] = ExpenseCodeFields.replace_field(
                    account_data['code'],
                    ExpenseCodeFields.OBJECT_CODE,
                    facility_object_code
                )
                logger.debug(f'account code being checked is {account_data["code"]}')
            # Organization may be name if coming from fiine or slug if coming from facility application
            account = models.Account.objects.get(Q(organization__name=account_data['organization']) | Q(organization__slug=account_data['organization']), code=account_data['code'])
            instance.account = account
        except models.Account.DoesNotExist as dne:
            logger.error('Could not find account with code %s and organization %s when updating billing record %d', account_data['code'], account_data['organization'], instance.id)
            raise serializers.ValidationError(
                detail={
                    'account': f'Cannot find code {account_data["code"]} to update billing record {instance}'
                }
            ) from dne

        # If start_date and end_date are not set, get them from the product_usage
        validated_data['start_date'] = initial_data.get('start_date')
        if not validated_data['start_date']:
            validated_data['start_date'] = product_usage.start_date
        validated_data['end_date'] = initial_data.get('end_date')
        if not validated_data['end_date']:
            validated_data['end_date'] = product_usage.end_date

        instance.description = validated_data['description']
        instance.updated_by = self.get_billing_record_author(initial_data)

        instance.save()

        # Only add new transactions.  Old ones cannot be removed.
        transactions_data = initial_data['transactions']
        for transaction_data in transactions_data:
            if 'id' not in transaction_data:
                transaction_data['author'] = self.get_transaction_author(transaction_data)
                models.Transaction.objects.create(**transaction_data, billing_record=instance)

        # Only add new billing record states.  Old ones cannot be removed.
        for state_data in billing_record_states_data:
            if 'id' not in state_data:
                state_data['user'] = self.get_state_username(state_data)
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
        facility = self.request.query_params.get('facility')
        root = self.request.query_params.get('root')
        invoice_prefix = self.request.query_params.get('invoice_prefix')

        queryset = models.BillingRecord.objects.all()

        if year:
            queryset = queryset.filter(year=year)
        if month:
            queryset = queryset.filter(month=month)
        if organization:
            queryset = queryset.filter(account__organization__slug=organization)
        if facility:
            queryset = queryset.filter(product_usage__product__facility__name=facility)
        if root:
            queryset = queryset.filter(account__root=root)
        if invoice_prefix:
            queryset = queryset.filter(product_usage__product__facility__invoice_prefix=invoice_prefix)

        return queryset.order_by('id')

    @action(detail=False, methods=['post'])
    def bulk_update(self, request, *args, **kwargs):
        '''
        Call serializer update on an array of billing records
        '''
        try:
            instances = [models.BillingRecord.objects.get(id=int(r['id'])) for r in request.data]
            serializer = self.get_serializer(instances, data=request.data, many=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data)
        except models.BillingRecord.DoesNotExist:
            logger.error('Unable to find one of the billing records for update.')
            return Response({'error': 'Unable to find billing record to update'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.exception(e)
            return Response({'error': f'Problem updating billing records {e}'})

class OrganizationRateSerializer(serializers.ModelSerializer):
    '''
    Not meant for stand alone use.  Should be attached to OrganizationSerializers in applications
    '''
    rate = RateSerializer()
    start_date = serializers.DateField()
    end_date = serializers.DateField()

    class Meta:
        model = models.OrganizationRate
        fields = '__all__'
