Invoicing
=========

This document describes the details of the FAS invoicing system.

Internal billing invoices are generated monthly
-----------------------------------------------
Both CNS and FAS Core facilities generate invoices each month.  CNS attempts to generate
them in time for the next month's "listings" (July billing for August listings),
which is up to 4 days after the end of the next month.  FAS Cores generate invoices
(Maria Lopez does this) on the second Monday after the month.

The billing period is always one month as that is best for grant processing.

Invoices may potentially be generated at any time after the end of the month
due to delays in processing, etc.

Invoices are generated when ready by designated staff
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Invoices are only generated when facilities are "ready" to do so.  An automated process that
generates them at a set time would not work.

Currently, CNS invoices are generated after a thorough, 3 week process of examining charges for
discrepancies.  FAS Core invoices are generated the second Monday of the month, but only
after facility managers clear up any outstanding issues.

Only a limited set of Science Operations or CNS staff are allowed to generate invoices.

An entire months worth of invoices should be generated at once
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
It should be easy to generate an entire month of invoice records.  Currently "single button"
operations make invoices available.

Must be able to generate one invoice at a time
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
One-at-a-time is also valuable.

Invoice generation must be tracked
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The login and timestamp of the staff member generating invoices must be tracked.

Invoice data must be generated with a copy of original data
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Many aspects of a billing system change over time; algorithms to calculate charges, data
presentation layer, etc.  However, once an invoice is made, the data used to generate
that invoice should be immutable.  This ensures that subsequent auditing will be accurate.

Software revision should be recorded with invoice data to ensure reproducibility
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
At the very least, the revision number for software used to calculate charges should be
recorded with the invoicing data.  The revision number should be as specific as possible; a
git commit hash, for example.

Ideally, this would include a container reference so that not just the version of the
software, but the environment as well can be reproduced.

Prior to invoice generation, revisions may need to occur
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Designated staff may need to arbitrarily change:

    * Expense code assignments
    * Expense code assignment proportions (percentages for split codes)
    * Billing rate
    * Amount expensed

The login and timestamp of the individual changing the expenses must be recorded.

It should be possible to add an arbitrary line item.

It should also be possible to create an entire invoice of any thing.

Invoices may need to be reissued
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Errors can occur after an invoice has been generated, so a new invoice may need to
be issued.  If this is the case, as is done with Spinal, the old invoice should be
retained when the new one is active.

If a new invoice is generated, again, the current data should be made immutable and
old data should remain with the old invoice.

Invoice must have a section for instructions that may be modified by staff
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Currently in Spinal, handling instructions and contact information is provided
in the invoice.  These instructions may change and should be editable by
staff.

Invoice must have a unique number
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Number must uniquely identify the invoice and it's associated data once the invoice is
"issued".  Any modifications to invoice data (changes to charges, etc.) should
require the creation of a new "invoice" and invoice number.

Invoice must indicate the dates covered
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
An invoice for April 2020 charges should indicate this.

Invoice must indicate the invoice date
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
This should be the date the invoice was generated.

Invoice must include itemized charges
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Itemized listing should include expense code charged, item used, date of the charge,
the total charge, and a text description of the item.  User that instigated the
charge should be included if appropriate.

If the item is an hourly charge, the number of hours and the rate should be included.

Invoice must include a total charge
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
In addition to itemized charges, a total must be provided.  All elements that
are used to produce the total should be indicated on the invoice.

Must be able to provide free text notes on an individual invoice
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Like CNS does

Must be able to add user and expense code summaries
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Like Spinal and MiniLIMS do

Lab administrators must be notified when invoices are ready
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
An email must be sent out to lab administrators when invoice records have been prepared.

Facility administrators should be able to see invoice listings that are identical to those seen by lab administrators
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The monthly invoicing view that is seen by lab administrators should also be accessible to facility
administrators to help with possible areas of confusion.