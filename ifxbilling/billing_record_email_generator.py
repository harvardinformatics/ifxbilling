# -*- coding: utf-8 -*-

'''
Billing Record Email Generator

Created on  2022-07-26

@author: Meghan Correa <mportermahoney@g.harvard.edu>
@copyright: 2022 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
import logging
import json
from django.core import serializers
from django.template.loader import render_to_string
from ifxurls.urls import getIfxUrl
from ifxuser.models import OrganizationContact
from ifxuser.user_functions import get_contactables, contacts_by_org
from ifxmail.client import send, FieldErrorsException
from ifxbilling import models

logger = logging.getLogger('ifxbilling')

class BillingRecordEmailGenerator():
    '''
    Looks at Billing Records for the month, year,
    facility and optional organization list and prepares and sends an email for all organizations.

    '''
    FACILITY_INVOICE_CONTACT_ROLE = 'Facility Invoice'
    LAB_MANAGER_CONTACT_ROLE = 'Lab Manager'
    DEFAULT_BILLING_RECORD_TEMPLATE = 'billing_record_summary_base.html'
    IFXMESSAGE_NAME = 'lab_manager_billing_record_notification'
    HUMAN_TIME_FORMAT = '%Y-%m-%d %I:%m%p'

    def __init__(self, invoice_prefix, month=None, year=None, ifxorg_ids=None):
        '''
        Initialize generator with invoice_prefix.  If month / year are not specified, current month year are used.
        '''
        self.invoice_prefix = invoice_prefix
        self.facility = models.Facility.objects.get(invoice_prefix=invoice_prefix)
        self.ifxorg_ids = ifxorg_ids
        # default to current month and year
        if not month or not year:
            today = datetime.datetime.today()
            logger.info(f'Month and/ or year not given, setting to current month {today.month} and current year {today.year}')
            self.month = today.month
            self.year = today.year
        else:
            self.year = year
            self.month = month

        self.template = self.facility.billing_record_template or self.DEFAULT_BILLING_RECORD_TEMPLATE
        # Setup facility contact
        self.facility_contact = None
        try:
            oc = OrganizationContact.objects.get(role=self.FACILITY_INVOICE_CONTACT_ROLE, organization__name=self.facility.name)
            self.facility_contact = oc.contact
        except OrganizationContact.DoesNotExist as dne:
            raise Exception(f'There is no facility invoice contact record for organization {facility_name}')
        self.ifxmessage_name = self.get_ifxmessage_name()

        self.review_link = getIfxUrl(f'{self.facility.application_username.upper()}_BILLING_RECORD_LISTING')

    def get_ifxmessage_name(self):
        # TODO: is this the naming convention? why two invoice prefixes?
        return f'{self.facility.invoice_prefix}_{self.facility.invoice_prefix}_{self.IFXMESSAGE_NAME}'

    def send_billing_record_emails(self):
        sent = []
        org_data, errors = self.prepare_org_data()
        for org, data in org_data.items():
            if org not in errors: # already errored, skip
                logger.info(f'Sending message for {org} with {org_data}')
                success, msg = self.send_email(data)
                if success:
                    sent.append(org)
                    logger.info('Successfully sent message for {org}')
                else:
                    errors[org] = msg
                    logger.warn(msg)
        logger.info(f'Successfully sent messagse to {len(sent)} labs: {" ,".join(sent)}')
        logger.info(f'Billing record email errors: {errors}')
        return sent, errors

    def send_email(self, org_data):
        try:
            # to, fromaddr, cclist=[], bcclist=[], replyto=None, ifxmessage=None, data=None, timeout=5
            logger.info(org_data['msg_data'])
            data = {
                'to': [c['detail'] for c in org_data['contact']],
                'fromaddr': self.facility_contact.detail,
                'replyto': self.facility_contact.detail,
                'data': org_data['msg_data'],
                'ifxmessage': self.ifxmessage_name,
                'field_errors': True
            }
            success = send(**data)
            logger.info(success)
            msg = 'Successfully sent mailing.'
            sent = True
        except FieldErrorsException as e:
            logger.exception(e)
            msg = str(e)
            sent = False
        return sent, msg


    def prepare_org_data(self):
        '''
        get data for an email to each org
        '''
        billing_records = models.BillingRecord.objects.filter(year=self.year, month=self.month, product_usage__product__facility__id=self.facility.id).select_related('product_usage').order_by('product_usage__organization').all()
        if self.ifxorg_ids:
            billing_records = billing_records.filter(product_usage__organization__ifxorg__in=self.ifxorg_ids)
        if not billing_records:
            raise Exception(f'No billing records found for year {self.year} month {self.month} facility {self.facility.name} ifxorg_ids {self.ifxorg_ids}')
        org_data = {}
        org_slug_list = []
        total = 0
        last_org = None
        for rec in billing_records:
            org = rec.product_usage.organization
            if org.slug not in org_data:
                org_slug_list.append(org.slug)
                org_data[org.slug] = {'recs': [], 'msg_data': {
                      'lab_name': org.name,
                      'facility_contact': self.facility_contact.name,
                      'facility_name': self.facility.name,
                      'year': self.year,
                      'month': self.month,
                      'link': self.review_link
                }}
                # set total for last org
                if last_org:
                    org_data[last_org]['total'] = total
                total = 0 # reset total
                last_org = org.slug # reset last org
            total += rec.charge
            org_data[org.slug]['recs'].append(self.format_summary(rec))
        if last_org:
            org_data[last_org]['total'] = total
        org_data, errors = self.add_contacts_to_org_data(org_slug_list, org_data)
        org_data, errors = self.add_html_to_org_data(org_data, errors)
        return org_data, errors

    def format_summary(self, rec):
        summary = {
          'start_date': rec.product_usage.start_date.strftime(self.HUMAN_TIME_FORMAT),
          'end_date': rec.product_usage.end_date.strftime(self.HUMAN_TIME_FORMAT),
          'product': rec.product_usage.product.product_name,
          'user': rec.product_usage.product_user.full_name,
          'quantity': rec.product_usage.quantity,
          'rate': rec.rate,
          'account': rec.account.code,
          'charge': rec.charge
        }
        return summary

    def format_html_context(self, data):
        return {
                    'year': self.year,
                    'month': self.month,
                    'billing_records': data['recs'],
                    'total': data['total']
                }

    def add_html_to_org_data(self, org_data, errors):
        '''
        Add summary html to each org
        '''
        for org, data in org_data.items():
            if not 'error' in data:
                context = self.format_html_context(data)
                try:
                    summary = render_to_string(self.template, context)
                    org_data[org]['msg_data']['summary'] = summary
                except Exception as e:
                    errors[org] = str(e)
                    logger.warn(str(e))
        return org_data, errors

    def add_contacts_to_org_data(self, org_slug_list, org_data):
        '''
        Add contact data to each org
        '''
        contacts = contacts_by_org(get_contactables(self.LAB_MANAGER_CONTACT_ROLE, org_slug_list))
        errors = {}
        for org, data in org_data.items():
            if org in contacts:
                org_data[org]['contact'] = contacts[org]
            else:
                msg = f'No contact found for organization: {org} with role {self.LAB_MANAGER_CONTACT_ROLE}'
                logger.warn(msg)
                errors[org] = msg
        return org_data, errors
