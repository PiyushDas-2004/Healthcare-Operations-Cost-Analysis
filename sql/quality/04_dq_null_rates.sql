-- 04_dq_null_rates.sql
-- Null (missing) rates for the key analysis columns. Most nulls here are
-- structural (CMS suppression or a hospital not participating in a program),
-- not data errors - see docs/DECISIONS.md.

with scope as (select * from mart_hospital where in_inpatient),
h as (
    select 'mart_hospital (inpatient hospitals)' as table_name, count(*) as n_rows,
        avg((facility_name is null)::int)                  as facility_name,
        avg((state is null)::int)                          as state,
        avg((ownership_group is null)::int)                as ownership_group,
        avg((star_rating is null)::int)                    as star_rating,
        avg((medicare_payment_per_discharge is null)::int) as payment_per_discharge,
        avg((mspb_ratio is null)::int)                     as mspb_ratio,
        avg((err_weighted is null)::int)                   as err_weighted,
        avg((err_hf is null)::int)                         as err_hf,
        avg((err_pn is null)::int)                         as err_pn
    from scope
)
unpivot h on columns(* exclude (table_name, n_rows)) into name column_name value null_rate
union all
select * from (
    with c as (
        select 'mart_hospital_condition' as table_name, count(*) as n_rows,
            avg((excess_readmission_ratio is null)::int) as excess_readmission_ratio,
            avg((discharges_3yr is null)::int)           as discharges_3yr,
            avg((readmissions_3yr is null)::int)         as readmissions_3yr,
            avg((excess_readmissions_annual is null)::int) as excess_readmissions_annual,
            avg((cost_per_readmission_base is null)::int)  as cost_per_readmission_base
        from mart_hospital_condition
    )
    unpivot c on columns(* exclude (table_name, n_rows)) into name column_name value null_rate
);
