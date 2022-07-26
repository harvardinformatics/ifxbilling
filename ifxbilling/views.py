# -*- coding: utf-8 -*-

'''
Common views for expense codes
'''

import logging
import json
from django.db import connection
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone
from django.utils.http import urlencode
from django.template.loader import render_to_string
from django.http import HttpResponseBadRequest
from django.core.validators import validate_email, ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view
from ifxmail.client import send, FieldErrorsException
from ifxurls.urls import FIINE_URL_BASE
from ifxbilling.fiine import updateUserAccounts
from ifxbilling import models, settings, permissions
from ifxbilling.calculator import calculateBillingMonth


logger = logging.getLogger(__name__)


def get_remote_user_auth_token(request):
    '''
    Get the token
    '''
    try:
        token = Token.objects.get(user=request.user)
    except Token.DoesNotExist:
        return Response({'error': 'User record for %s is not complete- missing token.' % str(request.user)}, status=401)

    if not request.user.is_active:
        logger.info('User %s is not active', request.user.username)
        return Response({'error': 'User is inactive.'}, status=401)

    return Response({
        'token': str(token),
        'is_staff': request.user.is_staff is True,
        'username': request.user.username,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
        'groups': [g.name for g in request.user.groups.all()]
    })


@api_view(('POST',))
def update_user_accounts(request):
    '''
    Take a list of ifxids and update data from fiine.  Body should be of the form:
    {
        'ifxids': [
            'IFXID0001',
            'IFXID0002',
        ]
    }
    If no data is specified, all accounts will be updated
    '''

    try:
        data = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError as e:
        logger.exception(e)
        return Response(data={'error': 'Cannot parse request body'}, status=status.HTTP_400_BAD_REQUEST)

    if not data:
        queryset = get_user_model().objects.filter(ifxid__isnull=False)
    else:
        queryset = get_user_model().objects.filter(ifxid__in=data['ifxids'])

    successes = 0
    errors = []
    for user in queryset:
        try:
            updateUserAccounts(user)
            successes += 1
        except Exception as e:
            logger.exception(e)
            errors.append(f'Error updating {user}: {e}')

    if errors:
        return Response(data={'successes': successes, 'errors': errors}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    else:
        return Response(data={'successes': successes})



@api_view(('GET',))
def unauthorized(request):
    '''
    Return a list of product usages for which there is no expense code authorized
    '''
    year = request.GET.get('year', timezone.now().year)
    month = request.GET.get('month', timezone.now().month)

    results = []

    for pu in models.ProductUsage.objects.filter(year=year, month=month):
        valid_account_exists = False

        # Check that both the account is valid and the user's use of the account is valid
        for ua in pu.product_user.useraccount_set.filter(is_valid=True):
            if ua.account.active:
                valid_account_exists = True
        for upa in pu.product_user.userproductaccount_set.filter(is_valid=True, product=pu.product):
            if upa.account.active:
                valid_account_exists = True

        if not valid_account_exists:
            results.append(
                {
                    'user': {
                        'ifxid': pu.product_user.ifxid,
                        'full_name': pu.product_user.full_name,
                        'primary_email': pu.product_user.email,
                        'primary_affiliation': pu.product_user.primary_affiliation.slug if pu.product_user.primary_affiliation else '',
                        'user_accounts': [str(ua.account) for ua in pu.product_user.useraccount_set.all()],
                        'user_product_accounts': [str(ua.account) for ua in pu.product_user.userproductaccount_set.all()]
                    },
                    'product': {
                        'product_name': pu.product.product_name,
                        'product_description': pu.product.product_description,
                    },
                    'quantity': pu.quantity,
                    'units': pu.units,
                    'description': pu.description,
                }
            )

    return Response(data=results)


@api_view(('POST',))
def expense_code_request(request):
    '''
    email an expense code request
    '''
    user = request.user
    organization_name = request.data.get('organization')
    facility_name = request.data.get('facility')
    product_name = request.data.get('product')
    emails = request.data.get('emails')

    # ensure there is atleast one valid email
    email_list = [e.strip() for e in emails.split(',')]
    valid_emails = []
    for email in email_list:
        try:
            validate_email(email)
            valid_emails.append(email)
        except ValidationError:
            pass
    if not valid_emails:
        msg = f'None of the emails supplied were valid: {emails}.'
        logger.error(msg)
        return Response(data={'emails': msg}, status=status.HTTP_400_BAD_REQUEST)

    # ensure all parameters are passed in
    param_errors = {}
    if organization_name is None:
        msg = f'A required parameter is missing from data: organization_name - {organization_name}.'
        logger.error(msg)
        param_errors['organization'] = msg
    if facility_name is None:
        msg = f'A required parameter is missing from data: facility_name - {facility_name}'
        logger.error(msg)
        param_errors['facility'] = msg
    if product_name is None:
        msg = f'A required parameter is missing from data: product_name - {product_name}'
        logger.error(msg)
        param_errors['product'] = msg
    if param_errors:
        return Response(data=param_errors, status=status.HTTP_400_BAD_REQUEST)

    logger.info(f'Formatting message for {facility_name} {organization_name} request from {user.full_name} for {product_name}.')

    try:
        org = models.Organization.objects.get(slug=organization_name)
        facility = models.Facility.objects.get(name=facility_name)
        qparams = {'facility': facility_name, 'product':product_name}
        url = f'{FIINE_URL_BASE}/labs/{org.ifxorg}/member/{user.ifxid}/?{urlencode(qparams)}'
    except models.Organization.DoesNotExist:
        msg = f'Organization not found: {organization_name}.'
        logger.error(msg)
        return Response(data={'organization': f'Error {msg}'}, status=status.HTTP_400_BAD_REQUEST)
    except models.Facility.DoesNotExist:
        msg = f'Facility not found: {facility_name}.'
        logger.error(msg)
        return Response(data={'facility': f'Error {msg}'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception(e)
        return Response(data={'error': f'Error gathering information to create expense code request for {facility_name} {organization_name} by {user.full_name} for {product_name}.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    fromstr = settings.EMAILS.DEFAULT_EMAIL_FROM_ADDRESS
    tostr = ','.join(valid_emails)
    ccstr = user.email
    ifxmessage = settings.IFXMESSAGES.EXPENSE_CODE_REQUEST_MESSAGE_NAME
    data = {
        'user': user.full_name,
        'facility': facility_name,
        'product': product_name,
        'organization': organization_name,
        'link': url
    }

    logger.debug(f'Attempting to send message to {tostr} from {fromstr} with {ifxmessage} with {json.dumps(data)}.')
    try:
        send(
            to=tostr,
            fromaddr=fromstr,
            ifxmessage=ifxmessage,
            field_errors=True,
            cclist=ccstr.split(','),
            data=data
        )
        msg = 'Successfully sent mailing.'
        msg_status = status.HTTP_200_OK
        data = {'message': msg}
    except FieldErrorsException as e:
        logger.exception(e)
        data = e.field_errors
        msg_status = e.status
    return Response(data=data, status=msg_status)


@permission_classes((permissions.AdminPermissions, ))
@api_view(('POST',))
def calculate_billing_month(request, invoice_prefix, year, month):
    '''
    Calculate billing for the given invoice_prefix, year, and month
    '''
    recalculate = False
    try:
        data = json.loads(request.body.decode('utf-8'))
        if data and 'recalculate' in data:
            recalculate = data['recalculate']
    except json.JSONDecodeError as e:
        logger.exception(e)
        return Response(data={'error': 'Cannot parse request body'}, status=status.HTTP_400_BAD_REQUEST)

    logger.debug('Calculating billing records with invoice_prefix %s for month %d of year %d, with recalculate flag %s', invoice_prefix, month, year, str(recalculate))

    try:
        facility = models.Facility.objects.get(invoice_prefix=invoice_prefix)
    except models.Facility.DoesNotExist:
        return Response(data={ 'error': f'Facility cannot be found using invoice_prefix {invoice_prefix}' }, status=status.HTTP_400_BAD_REQUEST)

    try:
        (successes, errors) = calculateBillingMonth(month, year, facility, recalculate)
        return Response(data={ 'successes': successes, 'errors': errors }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception(e)
        return Response(data={ 'error': f'Billing calculation failed {e}' }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@permission_classes((permissions.AdminPermissions, ))
@api_view(('POST',))
def billing_record_summary(request, invoice_prefix, year, month):
    '''
    return a billing record summary from template for the facility
    '''
    try:
        data = json.loads(request.body.decode('utf-8'))
        if data and 'organization' in data:
            organization = data['organization']
    except json.JSONDecodeError as e:
        logger.exception(e)
        return Response(data={'error': 'Cannot parse request body'}, status=status.HTTP_400_BAD_REQUEST)
    logger.debug('Summarizing billing records with invoice_prefix %s for month %d of year %d, with organization %s', invoice_prefix, month, year, organization)

    try:
        facility = models.Facility.objects.get(invoice_prefix=invoice_prefix)
    except models.Facility.DoesNotExist:
        return Response(data={ 'error': f'Facility cannot be found using invoice_prefix {invoice_prefix}' }, status=status.HTTP_400_BAD_REQUEST)

    try:
        template = facility.billing_record_template or settings.DEFAULT_BILLING_RECORD_TEMPLATE
        billing_records = models.BillingRecord.objects.filter(year=year, month=month, product_usage__product__facility__id=facility.id, product_usage__organization__name=organization).select_related('product_usage').all()
        total = billing_records.aggregate(Sum('charge'))['charge__sum']
        context = {'year': year, 'month': month, 'billing_records': billing_records, 'total': total}
        summary = render_to_string(template, context)
        return Response(data={ 'summary': summary }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception(e)
        return Response(data={ 'error': f'Billing record summary failed {str(e)}' }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def make_transaction_from_query_result(row_dict):
    '''
    Return a transaction dict from the row
    '''
    return {
        'description': row_dict['transaction_description'],
        'id': row_dict['transaction_id'],
        'charge': row_dict['transaction_charge'],
        'rate': row_dict['transaction_rate'],
        'author': {
            'ifxid': row_dict['transaction_user_ifxid'],
            'full_name': row_dict['transaction_user_full_name']
        }
    }

@api_view(('GET', ))
def get_billing_record_list(request):
    '''
    Return trimmed down listing for billing record displays
    '''
    year = request.GET.get('year', None)
    month = request.GET.get('month', None)
    invoice_prefix = request.GET.get('invoice_prefix', None)
    facility = request.GET.get('facility', None)
    organization = request.GET.get('organization', None)
    root = request.GET.get('root', None)
    results = {}
    sql = '''
        select
            br.id as billing_record_id,
            br.charge as billing_record_charge,
            br.percent as billing_record_percent,
            br.current_state as billing_record_current_state,
            br.description as billing_record_description,
            br.year,
            br.month,
            product_user.full_name as product_user_full_name,
            product_user.ifxid as product_user_ifxid,
            product_user_organization.slug as product_user_primary_affiliation,
            acct.id as account_id,
            acct.code as account_code,
            acct.name as account_name,
            acct.slug as account_slug,
            o.slug as account_organization,
            p.product_name,
            p.product_number,
            pu.id as product_usage_id,
            txn.id as transaction_id,
            txn.description as transaction_description,
            txn.charge as transaction_charge,
            txn.rate as transaction_rate,
            txn_user.full_name as transaction_user_full_name,
            txn_user.ifxid as transaction_user_ifxid
        from
            billing_record br
            inner join product_usage pu on pu.id = br.product_usage_id
            inner join product p on p.id = pu.product_id
            inner join ifxuser product_user on pu.product_user_id = product_user.id
            inner join nanites_organization product_user_organization on product_user.primary_affiliation_id = product_user_organization.id
            inner join account acct on acct.id = br.account_id
            inner join nanites_organization o on o.id = acct.organization_id
            inner join transaction txn on txn.billing_record_id = br.id
            inner join ifxuser txn_user on txn_user.id = txn.author_id
            inner join facility f on f.id = p.facility_id
    '''
    where_clauses = []
    query_args = []
    if year:
        try:
            year = int(year)
        except ValueError:
            return Response('year must be an integer', status=status.HTTP_400_BAD_REQUEST)
        where_clauses.append('br.year = %s')
        query_args.append(year)

    if month:
        try:
            month = int(month)
        except ValueError:
            return Response('month must be an integer', status=status.HTTP_400_BAD_REQUEST)
        where_clauses.append('br.month = %s')
        query_args.append(month)

    if invoice_prefix:
        where_clauses.append('f.invoice_prefix = %s')
        query_args.append(invoice_prefix)
    if organization:
        where_clauses.append('o.slug = %s')
        query_args.append(organization)
    if facility:
        where_clauses.append('f.name = %s')
        query_args.append(facility)
    if root:
        where_clauses.append('acct.root = %s')
        query_args.append(root)

    if where_clauses:
        sql += ' where '
        sql += ' and '.join(where_clauses)

    try:

        cursor = connection.cursor()
        cursor.execute(sql, query_args)

        desc = cursor.description

        for row in cursor.fetchall():
            # Make a dictionary labeled by column name
            row_dict = dict(zip([col[0] for col in desc], row))
            billing_record_id = row_dict['billing_record_id']
            if billing_record_id in results:
                # Additional transaction
                results[billing_record_id]['transactions'].append(
                    make_transaction_from_query_result(row_dict)
                )
            else:
                results[billing_record_id] = {
                    'id': billing_record_id,
                    'charge': row_dict['billing_record_charge'],
                    'description': row_dict['billing_record_description'],
                    'percent': row_dict['billing_record_percent'],
                    'current_state': row_dict['billing_record_current_state'],
                    'year': row_dict['year'],
                    'month': row_dict['month'],
                    'account': {
                        'id': row_dict['account_id'],
                        'code': row_dict['account_code'],
                        'name': row_dict['account_name'],
                        'slug': row_dict['account_slug'],
                        'organization': row_dict['account_organization'],
                    },
                    'product_usage': {
                        'id': row_dict['product_usage_id'],
                        'product': row_dict['product_name'],
                        'product_user': {
                            'ifxid': row_dict['product_user_ifxid'],
                            'primary_affiliation': row_dict['product_user_primary_affiliation'],
                            'full_name': row_dict['product_user_full_name']
                        }
                    },
                    'transactions': [
                        make_transaction_from_query_result(row_dict)
                    ]
                }
    except Exception as e:
        logger.exception(e)
        return Response(f'Error getting billing records {e}', status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(
        data=list(results.values())
    )
