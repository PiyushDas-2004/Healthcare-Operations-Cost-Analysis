-- 11_int_hospital_inpatient.sql
-- Grain : one row per hospital (CCN) that appears in the inpatient file.
-- Decomposes Medicare payment per discharge into two cost components:
--
--   payment per discharge = national avg payment per discharge
--                           x case-mix index   (what kind of patients/DRGs)
--                           x price index      (how much the hospital is paid
--                                               for the same DRG: wage index,
--                                               teaching (IME), DSH, outliers)
--
--   case_mix_index = expected payment per discharge / national payment per discharge
--     where expected = sum over DRGs of (hospital discharges x national avg payment)
--   price_index    = actual payment / expected payment

create or replace table int_hospital_inpatient as
with national as (
    select sum(medicare_payment) / sum(discharges) as national_ppd
    from stg_inpatient
),
hospital as (
    select
        i.ccn,
        any_value(i.provider_name)                          as provider_name,
        any_value(i.state)                                  as state,
        any_value(i.urban_rural)                            as urban_rural,
        count(*)                                            as drgs_reported,
        sum(i.discharges)                                   as discharges,
        sum(i.medicare_payment)                             as medicare_payment,
        sum(i.total_payment)                                as total_payment,
        sum(i.discharges * d.avg_medicare_payment)          as expected_medicare_payment
    from stg_inpatient i
    join int_drg_national d using (drg_code)
    group by i.ccn
)
select
    h.*,
    h.medicare_payment / h.discharges                       as medicare_payment_per_discharge,
    h.total_payment    / h.discharges                       as total_payment_per_discharge,
    (h.expected_medicare_payment / h.discharges) / n.national_ppd as case_mix_index,
    h.medicare_payment / h.expected_medicare_payment        as price_index
from hospital h
cross join national n;
