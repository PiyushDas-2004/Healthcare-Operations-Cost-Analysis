-- 04_stg_inpatient.sql
-- Source: "Medicare Inpatient Hospitals - by Provider and Service", data year
--         2024 (Original Medicare / fee-for-service IPPS claims).
-- Grain : one row per hospital (CCN) per MS-DRG.
--
-- CMS only publishes a hospital x DRG cell when it has 11+ discharges, so
-- hospital totals built from this file undercount small hospitals.
-- Payments are averages per discharge; we multiply back out to totals.

create or replace table stg_inpatient as
with src as (
    select * from raw_inpatient_by_provider_service
)
select
    to_ccn(Rndrng_Prvdr_CCN)                         as ccn,
    trim(Rndrng_Prvdr_Org_Name)                      as provider_name,
    upper(trim(Rndrng_Prvdr_State_Abrvtn))           as state,
    to_num(Rndrng_Prvdr_RUCA)                        as ruca_code,
    -- RUCA 1-3 = metropolitan, 4-10 = micropolitan / small town / rural, 99 = not coded
    case
        when to_num(Rndrng_Prvdr_RUCA) < 4  then 'Urban'
        when to_num(Rndrng_Prvdr_RUCA) < 99 then 'Rural'
    end                                              as urban_rural,
    lpad(trim(DRG_Cd), 3, '0')                       as drg_code,
    trim(DRG_Desc)                                   as drg_desc,
    cast(to_num(Tot_Dschrgs) as integer)             as discharges,
    to_num(Avg_Submtd_Cvrd_Chrg)                     as avg_covered_charges,
    to_num(Avg_Tot_Pymt_Amt)                         as avg_total_payment,
    to_num(Avg_Mdcr_Pymt_Amt)                        as avg_medicare_payment,
    to_num(Tot_Dschrgs) * to_num(Avg_Tot_Pymt_Amt)   as total_payment,
    to_num(Tot_Dschrgs) * to_num(Avg_Mdcr_Pymt_Amt)  as medicare_payment
from src
where Rndrng_Prvdr_CCN is not null;
