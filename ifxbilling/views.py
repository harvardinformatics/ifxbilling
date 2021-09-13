# -*- coding: utf-8 -*-

'''
Common views for expense codes
'''

import logging
import json
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.http import urlencode
from django.http import HttpResponseBadRequest
from django.core.validators import validate_email, ValidationError
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view
from ifxmail.client import send, FieldErrorsException
from ifxurls.urls import FIINE_URL_BASE
from ifxbilling.fiine import updateUserAccounts
from ifxbilling import models, settings


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
