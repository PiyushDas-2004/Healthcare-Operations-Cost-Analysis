-- 23_mart_cost_drivers.sql
-- Grain : one row per cost bucket.
-- Puts excess readmissions in context against the other places Medicare
-- inpatient money goes, so we can say whether readmissions are the top driver.
-- Buckets: top 10 DRGs by spend (from int_drg_national) + HRRP condition DRG
-- families + the annual excess readmission cost estimate.

create or replace table mart_cost_drivers as
with total as (
    select sum(medicare_payment) as total_medicare from int_drg_national
),
top_drgs as (
    select 'DRG ' || drg_code || ': ' || drg_desc as bucket, 'Top-10 DRG by spend' as bucket_type,
           medicare_payment as annual_medicare_dollars, discharges
    from int_drg_national
    where spend_rank <= 10
),
hrrp_families as (
    select 'HRRP condition DRGs: ' || m.condition_code as bucket, 'HRRP condition (index stays)' as bucket_type,
           sum(d.medicare_payment), sum(d.discharges)
    from int_drg_national d join stg_hrrp_drg_map m using (drg_code)
    group by m.condition_code
),
excess as (
    select 'Excess readmissions, all 6 HRRP conditions (est.)', 'Excess readmissions (estimate)',
           sum(excess_cost_annual_base), sum(positive_excess_annual)
    from mart_hospital_condition
)
select
    b.*,
    b.annual_medicare_dollars / t.total_medicare  as share_of_medicare_inpatient,
    rank() over (order by b.annual_medicare_dollars desc) as dollar_rank
from (select * from top_drgs union all select * from hrrp_families union all select * from excess) b
cross join total t
order by dollar_rank;
