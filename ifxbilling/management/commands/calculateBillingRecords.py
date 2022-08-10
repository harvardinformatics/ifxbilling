# -*- coding: utf-8 -*-

'''
Calculate billing records for the given year and month
'''
import logging
import datetime
import pytz
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.core.management.base import BaseCommand
from ifxbilling import settings
from ifxbilling.billing_record_generator import BillingRecordGenerator
from ifxbilling.models import Facility
from ifxbilling.util import get_class_from_name


logger = logging.getLogger('ifxbilling')


class Command(BaseCommand):
    '''
    Calculate billing records for the given year and month
    '''
    help = 'Calculate billing records for the given year and month.  Use --recalculate to remove existing records and recreate. Usage:\n' + \
        "./manage.py calculateBillingRecords 'Helium Recovery Service' --month 7 --year 2022"

    def add_arguments(self, parser):
        parser.add_argument(
            'facility_name',
            help='Name of the facility to calculate for.'
        )
        parser.add_argument(
            '--year',
            dest='year',
            default=(timezone.now() - relativedelta(months=1)).year,
            help='Year for calculation',
        )
        parser.add_argument(
            '--month',
            dest='month',
            default=(timezone.now() - relativedelta(months=1)).month,
            help='Month for calculation',
        )
        parser.add_argument(
            '--recalculate',
            action='store_true',
            help='Remove existing billing records and recalculate',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Report full exception for errors',
        )
        parser.add_argument(
            '--product-names',
            dest='product_names',
            help='Comma-separated list of product names.'
        )
        parser.add_argument(
            '--organizations',
            dest='organizations',
            help='Comma-separated list of organization names.'
        )

    def handle(self, *args, **kwargs):
        month = int(kwargs['month'])
        year = int(kwargs['year'])
        recalculate = kwargs['recalculate']
        verbose = kwargs['verbose']
        facility_name = kwargs.get('facility_name')
        product_name_str = kwargs.get('product_names')
        organization_str = kwargs.get('organizations')
        product_names = None
        if product_name_str:
            product_names = product_name_str.split(',')
        organizations = None
        if organization_str:
            organizations = organization_str.split(',')
        if not facility_name:
            raise Exception('Must supply a facility_name')
        else:
            try:
                facility = Facility.objects.get(name=facility_name)
            except Facility.DoesNotExist:
                raise Exception(f'Facility name {facility_name} cannot be found')
        start_date = timezone.make_aware(datetime.datetime(year=year, month=month, day=1), timezone=pytz.timezone(settings.TIME_ZONE))
        logger.info(f'Generating billing records for {facility_name} start: {start_date} recalc {recalculate} verbose {verbose} products {product_names} orgs {organizations}')
        try:
            billing_record_generator_class = get_class_from_name(facility.billing_record_generator)
        except Exception as e:
            raise Exception(f'Facility billing record generator class does not exist: {e}')
        billing_record_generator = billing_record_generator_class(facility_name, verbose)
        gen_results = billing_record_generator.generate_billing_records(start_date, None, recalculate, product_names, organizations)
        for org, results in gen_results['org_usage_results'].items():
            print(f'Organization {org} had {results["successes"]} product usages successfully processed')
            if results['errors']:
                error_str = '\n'.join(results['errors'])
                print(f'Organization {org} Errors: {error_str}')
