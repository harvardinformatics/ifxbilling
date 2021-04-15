Setup
=====

This document describes how the ifxbilling module is setup.

Add ifxbilling to Django applications after ifxuser
---------------------------------------------------
This library depends on Organization from ifxuser

ProductUsage may need to be linked to another model
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
A hypothetical InstrumentUsage model, for example, may contain the details of the instrument used and the start / end time
of the usage.  The InstrumentUsage could either be implemented as a ProductUsage subclass or a OneToOne foreign
key relationship could be used (especially if the InstrumentUsage is already a subclass of something else)
