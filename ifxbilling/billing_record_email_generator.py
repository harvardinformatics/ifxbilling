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
from django.template.loader import render_to_string
from django.db.models import Sum
from ifxuser.models import OrganizationContact, Organization
from ifxuser.contacts import get_contactables
from ifxmail.client import send
from ifxbilling import models

logger = logging.getLogger('ifxbilling')

class BillingRecordEmailGenerator():
    '''
    Looks at Billing Records for the month, year,
    facility and optional organization list and prepares and sends an email for all organizations.

    '''
    FACILITY_INVOICE_CONTACT_ROLE = 'Facility Invoice'
    LAB_MANAGER_CONTACT_ROLE = 'Lab Manager'
    BILLING_RECORD_REVIEW_CONTACT_ROLE = 'Billing Record Review'
    PI_CONTACT_ROLE = 'PI'
    DEFAULT_BILLING_RECORD_TEMPLATE = 'billing/billing_record_summary.html'
    IFXMESSAGE_NAME = 'lab_manager_billing_record_notification'
    HUMAN_TIME_FORMAT = '%Y-%m-%d %I:%m%p'
    PENDING_LAB_APPROVAL_STATE = 'PENDING_LAB_APPROVAL'

    def __init__(self, facility, month=None, year=None, organizations=None, test=None):
        '''
        Initialize generator with invoice_prefix.  If month / year are not specified, current month year are used.
        If test is set to a list of email addresses, they will be used instead of the normal contacts
        '''
        self.facility = facility
        self.organizations = organizations
        self.year = year
        self.month = month
        self.test = test

        self.billing_record_template_name = self.get_billing_record_template_name(facility)
        self.facility_contact = self.get_facility_contact(facility)
        self.review_link = self.get_review_link(facility)

    def get_billing_record_template_name(self, facility):
        '''
        Return the billing record summary template name.  Either the facility specific template or the default one
        '''
        return facility.billing_record_template or self.DEFAULT_BILLING_RECORD_TEMPLATE

    def get_review_link(self, facility):
        '''
        Link in email for reviewing charges
        '''
        return f'https://fiine.rc.fas.harvard.edu/fiine/billing/billing-records/list/?year={self.year}&month={self.month}&facility={facility.name}'

    def get_facility_contact(self, facility):
        '''
        Setup the facility contact
        '''
        try:
            oc = OrganizationContact.objects.get(
                role=self.FACILITY_INVOICE_CONTACT_ROLE,
                organization__name=facility.name,
                organization__org_tree='Harvard'
            )
            return oc.contact
        except OrganizationContact.DoesNotExist as dne:
            raise Exception(f'There is no facility invoice contact record for organization {facility.name}')

    def get_ifxmessage_name(self, org=None):
        '''
        Return the name for the ifxmessage.  Combines facility application name, invoice prefix and IFXMESSAGE_NAME
        '''
        return f'{self.facility.application_username}_{self.facility.invoice_prefix}_{self.IFXMESSAGE_NAME}'

    def send_billing_record_emails(self):
        '''
        Iterate through organizations and send email via ifxmail if there are billing records.
        Returns a tuple that includes a list of organizations that were successfully sent emails,
        a dict of errors keyed by org name, and a list of organizations that had no billing records.
        '''
        sent = []
        nobrs = []
        errors = {}
        for org in self.get_organizations():
            try:
                brs = self.get_billing_records_for_org(org)
                if brs:
                    email_data = {
                        'to': self.get_to_list(org),
                        'fromaddr': self.get_fromaddr(org),
                        'replyto': self.get_replyto_email(org),
                        'ifxmessage': self.get_ifxmessage_name(org),
                        'field_errors': True,
                        'data': self.get_message_data(org, brs)
                    }
                    self.send_email(email_data)
                    sent.append(org)
                    logger.info(f'Successfully sent message for {org}')
                else:
                    nobrs.append(org)
            except Exception as e:
                logger.exception(e)
                errors[org.name] = [str(e)]
        logger.debug(f'Successfully sent messages to {len(sent)} labs: {" ,".join([s.name for s in sent])}')
        logger.debug(f'Billing record email errors: {errors}')
        return sent, errors, nobrs

    def get_fromaddr(self, org=None):
        '''
        Return the from: email address, using self.facility_contact
        '''
        return self.facility_contact.detail

    def get_replyto_email(self, org=None):
        '''
        Return the replyto: email address, using self.facility_contact
        '''
        return self.facility_contact.detail

    def get_to_list(self, org):
        '''
        Return the list of to: email addresses for an organization
        '''
        tolist = []
        if self.test:
            tolist = self.test
        else:
            contacts = self.get_organization_contacts(org)
            if not contacts:
                raise Exception(f'Organization {org} has no appropriate contacts')
            tolist = [c['detail'] for c in contacts]
        return tolist

    def send_email(self, data):
        '''
        Use ifxmail send() to send the email
        '''
        # to, fromaddr, cclist=[], bcclist=[], replyto=None, ifxmessage=None, data=None, timeout=5
        logger.debug(f'Sending {data}')
        send(**data)

    def get_billing_records_for_org(self, org):
        '''
        Get billing record queryset for an organization based on the account org
        Ordered by product name, product user name
        '''
        return models.BillingRecord.objects.filter(
            year=self.year,
            month=self.month,
            product_usage__product__facility=self.facility,
            account__organization=org,
            current_state=self.PENDING_LAB_APPROVAL_STATE,
        ).order_by('product_usage__product__product_name', 'product_usage__product_user__full_name')

    def get_message_data(self, org, brs):
        '''
        Get the msg_data portion of the email (except for total and summary)
        '''
        msg_data = {
            'lab_name': org.name,
            'facility_contact': self.facility_contact.name,
            'facility_name': self.facility.name,
            'year': self.year,
            'month': self.month,
            'link': self.review_link,
        }
        msg_data['summary'] = self.get_billing_record_html_summary(org, brs)
        return msg_data

    def get_organizations(self):
        '''
        Return the list (or queryset) of organizations to be processed
        '''
        if self.organizations:
            orgs = self.organizations
        else:
            orgs = Organization.objects.all()
        return orgs

    def get_organization_contacts(self, org):
        '''
        Return the organization contacts to be emailed
        '''
        contactables = None
        for role in [
            self.BILLING_RECORD_REVIEW_CONTACT_ROLE,
            self.LAB_MANAGER_CONTACT_ROLE,
            self.PI_CONTACT_ROLE,
        ]:
            contactables = get_contactables(role, [org])
            if contactables:
                return contactables
        return contactables

    def get_billing_record_dict(self, rec):
        '''
        Compose data dict from billing record
        '''
        return {
          'start_date': rec.product_usage.start_date,
          'end_date': rec.product_usage.end_date if rec.product_usage.end_date else None,
          'product': rec.product_usage.product.product_name,
          'user': rec.product_usage.product_user.full_name,
          'quantity': rec.product_usage.quantity,
          'rate': rec.rate,
          'account': rec.account.code,
          'charge': rec.charge,
          'decimal_charge': rec.decimal_charge,
          'transaction_descriptions': [txn.description for txn in rec.transaction_set.all()],
        }

    def get_billing_record_html_summary(self, org, brs):
        '''
        Create billing data summary by rendering Django template
        '''
        context = {
            'year': self.year,
            'month': self.month,
            'billing_records': [self.get_billing_record_dict(br) for br in brs],
            'total': brs.aggregate(Sum('charge'))['charge__sum'],
            'decimal_total': brs.aggregate(Sum('decimal_charge'))['decimal_charge__sum'],
        }
        return render_to_string(self.billing_record_template_name, context)
