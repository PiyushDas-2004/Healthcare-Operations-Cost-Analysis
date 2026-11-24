-- 03_dq_join_match_rates.sql
-- Join match rates between sources on CCN. The base for each line is the
-- set of hospitals in the "from" source; match_pct is the share of those
-- hospitals that were also found in the "to" source.
-- The inpatient file is the anchor for the payment analysis, so most checks
-- start from it.

with
gi  as (select distinct ccn from stg_hospital_info),
gia as (select distinct ccn from stg_hospital_info where hospital_type = 'Acute Care Hospitals'),
ip  as (select distinct ccn from stg_inpatient),
hr  as (select distinct ccn from stg_hrrp),
hrs as (select distinct ccn from stg_hrrp where excess_readmission_ratio is not null),
ms  as (select distinct ccn from stg_mspb where mspb_ratio is not null),
pairs as (
    select 'Inpatient -> General Info'         as join_path, (select count(*) from ip) as base_hospitals,
           (select count(*) from ip join gi using (ccn)) as matched
    union all select 'Inpatient -> HRRP (any row)',          (select count(*) from ip), (select count(*) from ip join hr using (ccn))
    union all select 'Inpatient -> HRRP (>=1 scored ERR)',   (select count(*) from ip), (select count(*) from ip join hrs using (ccn))
    union all select 'Inpatient -> MSPB (scored)',           (select count(*) from ip), (select count(*) from ip join ms using (ccn))
    union all select 'Inpatient -> all three others',        (select count(*) from ip),
              (select count(*) from ip join gi using (ccn) join hrs using (ccn) join ms using (ccn))
    union all select 'HRRP -> Inpatient',                    (select count(*) from hr), (select count(*) from hr join ip using (ccn))
    union all select 'MSPB (scored) -> Inpatient',           (select count(*) from ms), (select count(*) from ms join ip using (ccn))
    union all select 'General Info (acute care) -> Inpatient', (select count(*) from gia), (select count(*) from gia join ip using (ccn))
    union all select 'HRRP condition rows -> DRG payment at same hospital',
              (select count(*) from int_condition_payment),
              (select count(*) from int_condition_payment where payment_source = 'hospital')
)
select *, round(100.0 * matched / base_hospitals, 1) as match_pct
from pairs;
