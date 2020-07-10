Products
========

Anything that can be billed needs a product number
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Because billing will be done across a wide range of items,
each will need a unique identifier to ensure that what is billed
is unambiguous.

The product number will be a nonsense identifier that must be
associated with the billable entity before any billing can occur.
The identifier cannot be transferred to another entity or reused.

The product number will be obtained from the billing system and
stored with the entity in the facility application.

Products are related to invoice line items, billing rates
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Anything that is likely to appear as an invoice line item will
need a product number.  In addition to usage of an individual
instrument, things like Helium dewars, training courses, facility
assistance, etc. can be products.

Similar items that may be charged at different rates should be different
products.  An example might be Group Training on Electron Microscope vs.
One on One Training on Electron Microscope.

Similarly, if there is a different baseline rate for commercial
customers than there is for internal customers, this should be a
separate product.

Discounts or other adjustments do not need product numbers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Invoices will display a line item with a summary charge associated
with a product.  A breakdown of component charges will also be
displayed indicating the main billing rate, plus lines for any
adjustments / discounts, etc.

For example, if flat discount of $100 is applied to instrument usage
over 100 hours, this would

"Credit" products will be supported??
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
For the Helium system, returned helium is credited to the user
account.  This isn't really an adjustment to a charge, right?????
