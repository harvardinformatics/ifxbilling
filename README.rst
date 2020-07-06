=====
IfxBilling
=====

IfxBilling is a Django app with models and api for billing to be used by ifx applications.


Installation
------------

1. Add ifxbilling to your requirements or Dockerfile (using direct installation from git with commit hashes forces rebuild of the docker image when the package is updated)::

     RUN pip install git+https://github.com/harvardinformatics/ifxbilling.git


2. Add "ifxbilling" to your INSTALLED_APPS before the contrib.django.admin setting

    INSTALLED_APPS = [
        'ifxbilling',
        ...
    ]
