ifxbilling package
==================

A ProductUsage associates a product with a user, 'how much' they used, and when
-------------------------------------------------------------------------------
The ProductUsage base model associates a Product with a "quantity" of that product
used by a user.  This table can be used directly, but it may also be used
as a "base model" for another model.  For example, if "InstrumentUsage" is a
model that tracks instrument reservations and actual usage via start and
end dates, it could be implemented as a subclass of the ProductUsage model.

Models that cannot have a base class (ie, they already have one), can us a
subclass with a OneToOne foreign key reference.

BillingRecords apply a charge to an Account for a ProductUsage
--------------------------------------------------------------
BillingRecord applies a charge to an Account for a (single) ProductUsage.
It is not a many-to-many relationship- you cannot apply a single BillingRecord
to a group of ProductUsages.  However, multiple BillingRecords can be applied to
a single ProductUsage to support expense code splits, for example.

BillingRecord charges are a sum of Transaction charges
------------------------------------------------------
The 'charge' field on BillingRecord should not be manually set.  BillingRecord
charges are the sum of all the charges from related Transactions.  Each time a
Transaction is associated with a BillingRecord, the charge field is recalculated.

Charges are signed integers in pennies
--------------------------------------
Rather than mess with storing Decimal numbers, all charges are integer values in
pennies.  Displays should adjust accordingly.

Charges are signed integers to that credits and discounts can be applied easily




.. automodule:: ifxbilling
   :members:
   :undoc-members:
   :show-inheritance:

Subpackages
-----------

.. toctree::
   :maxdepth: 4

   ifxbilling.management
   ifxbilling.migrations

Submodules
----------

.. toctree::
   :maxdepth: 4

   ifxbilling.admin
   ifxbilling.init
   ifxbilling.initDev
   ifxbilling.models
   ifxbilling.serializers
   ifxbilling.settings
   ifxbilling.urls
   ifxbilling.views
