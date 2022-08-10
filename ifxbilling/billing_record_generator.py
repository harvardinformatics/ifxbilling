# -*- coding: utf-8 -*-

'''
Billing Record Generator

Created on  2022-08-09

@author: Meghan Correa <mportermahoney@g.harvard.edu>
@copyright: 2022 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
import logging
import json
from collections import defaultdict
from datetime import datetime
from dateutil.relativedelta import relativedelta
from django.db import transaction
from ifxbilling import settings
from ifxbilling.models import BillingRecord, ProductUsage, Product, Facility, Organization
from ifxbilling.util import get_class_from_name

logger = logging.getLogger('ifxbilling')

class BillingRecordGenerator():

    def __init__(self, facility_name, verbose = False):
        '''
        Initialize generator with facility name.
        '''
        try:
            facility = Facility.objects.get(name=facility_name)
        except Facility.DoesNotExist:
            raise Exception(f'Facility name {facility_name} cannot be found')
        self.facility = facility
        self.facility_name = facility_name
        self.verbose = verbose
        # keep calculator classes available by product
        self.calculators = defaultdict()

    def get_product_usages(self, start_date, end_date, organizations=None, product_names=None):
        # only billable usages will be billed
        product_usages = ProductUsage.objects.filter(start_date__gte=start_date, start_date__lte=end_date, product__facility=self.facility, product__billable=True)

        # Filter by product if needed
        products = []
        if product_names is not None:
            for product_name in product_names:
                try:
                    products.append(Product.objects.get(product_name=product_name))
                except Product.DoesNotExist:
                    raise Exception(f'Cannot filter by {product_name}: Product does not exist.')
            if products:
                product_usages = product_usages.filter(product__in=products)

        # Filter by organization if needed
        org_filter = []
        if organizations is not None:
            for org_name in organizations:
                try:
                    org_filter.append(Organization.objects.get(name=org_name))
                except Organization.DoesNotExist:
                    raise Exception(f'Cannot filter by {org_name}: Organization does not exist.')
            if organizations:
                product_usages = product_usages.filter(organization__in=org_filter)
        product_usages.order_by('organization')
        return product_usages

    def get_usages_grouped_by_organization(self, start_date, end_date, organizations=None, product_names=None):
        product_usages = self.get_product_usages(start_date, end_date, organizations, product_names)
        org_usages = defaultdict(list)
        for product_usage in product_usages:
            org_usages[product_usage.organization.name].append(product_usage)
        return org_usages

    def generate_billing_records(self, start_date, end_date=None, recalculate=False, organizations=None, product_names=None):
        '''
        generates billing records for a single facility, start date
        must be the first of the month, if a diffent day is passed it will be
        an exception.  If end date is not passed in then end is considered to be
        the first day of the month after the start.  If end month is set then
        it must be the first day of a month after the starting month.

        List of organization names or product names can be passed in to only
        generate records that match those lists.
        '''
        # set start and end date for full months
        if start_date.day != 1 or (start_date.hour + start_date.minute + start_date.second + start_date.microsecond) != 0 or str(start_date.tzinfo) != settings.TIME_ZONE:
            raise Exception(f'Start start date should be a date beginning on the first of the month and have time of 00:00:00:00 and be in EST instead of {start_date}.')
        months = [(start_date.month, start_date.year)]
        if end_date:
            if end_date <= start_date:
                raise Exception(f'End date: {end_date} is not greater than start date {start_date}')
            if end_date.day != 1:
                raise Exception(f'End date should be a date beginning on the first of the date instead of {end_date}.')
            curr = start_date + relativedelta(months=1)
            while curr < end_date:
                months.append(curr.month, curr.year)
                curr += relativedelta(months=1)
        else: # default to the first of the next month
            end_date = start_date + relativedelta(months=1)
        logger.info(f'Billing Record Generator is generating records for these parameters: {self.facility.name} start: {start_date} end: {end_date} recalc {recalculate} verbose {self.verbose} products {product_names} orgs {organizations}')
        organization_usages = self.get_usages_grouped_by_organization(start_date, end_date, product_names, organizations)
        if not organization_usages:
            logger.info(f'No usages were found for the parameters specified')
            return organization_usages
        org_results= {} # store success and error by organization
        for org, product_usages in organization_usages.items():
            org_results[org] = self.generate_organization_billing_records(org, product_usages, recalculate)
            if org_results[org]['successes'] < len(product_usages):
                logger.info(f'Organization {org} had {len(product_usages)} product usages but {org_results[org]["skipped"]} were skipped because they already had billing records and {org_results[org]["successes"]} billing records were created')
        calc_errors = []
        for product_name, calculator in self.calculators.items():
            for (month, year) in months:
                try:
                    with transaction.atomic():
                            calculator.finalize(month, year, facility, recalculate=False, verbose=False)
                except Exception as e:
                    if self.verbose:
                        logger.exception(e)
                    calc_errors.append(f'Finalization failed for calculator for {product_name} {self.facility.name} month {month} year {year}: {e}')
        return {'calculator_errors': calc_errors, 'org_usage_results': org_results}

    def generate_organization_billing_records(self, org, product_usages, recalculate):
        logger.info(f'Generating billing records for {org} with {len(product_usages)} product usages')
        successes = 0
        errors = []
        skipped = 0
        for product_usage in product_usages:
            if BillingRecord.objects.filter(product_usage=product_usage).exists():
                if recalculate:
                    BillingRecord.objects.filter(product_usage=product_usage).delete()
                else:
                    skipped += 1
                    logger.info(f'Skipping, billing record exists for product_usage {product_usage} and recalculate is false')
                    continue
            try:
                if product_usage.product.product_name not in self.calculators:
                    billing_calculator_name = product_usage.product.billing_calculator
                    billing_calculator_class = get_class_from_name(billing_calculator_name)
                    self.calculators[product_usage.product.product_name] = billing_calculator_class()
                billing_calculator = self.calculators[product_usage.product.product_name]
                billing_calculator.createBillingRecordsForUsage(product_usage, usage_data=product_usage)
                successes += 1
            except Exception as e:
                if self.verbose:
                    logger.exception(e)
                errors.append(f'Unable to create billing record for {product_usage}: {e}')
        return {'successes': successes, 'errors': errors, 'skipped': skipped}

