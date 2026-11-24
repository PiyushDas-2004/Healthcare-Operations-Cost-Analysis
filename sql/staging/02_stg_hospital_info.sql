-- 02_stg_hospital_info.sql
-- Source: CMS Provider Data Catalog "Hospital General Information" (xubh-q36u).
-- Grain : one row per facility (CCN).
-- Cleans the facility master list: CCN as 6-char text, star rating as an
-- integer 1-5 (NULL when "Not Available"), simplified ownership groups.

create or replace table stg_hospital_info as
with src as (
    select * from raw_hospital_general_info
),
cleaned as (
    select
        to_ccn("Facility ID")                                     as ccn,
        trim("Facility Name")                                     as facility_name,
        trim("City/Town")                                         as city,
        upper(trim("State"))                                      as state,
        trim("County/Parish")                                     as county,
        trim("Hospital Type")                                     as hospital_type,
        trim("Hospital Ownership")                                as ownership_detail,
        -- Collapse 12 CMS ownership categories into 4 analysis groups.
        case
            when "Hospital Ownership" like 'Voluntary non-profit%'  then 'Non-profit'
            when "Hospital Ownership" in ('Proprietary', 'Physician') then 'For-profit'
            when "Hospital Ownership" like 'Government%'
              or "Hospital Ownership" in ('Veterans Health Administration',
                                          'Department of Defense', 'Tribal') then 'Government'
            else 'Other'
        end                                                       as ownership_group,
        "Emergency Services" = 'Yes'                              as has_emergency_services,
        cast(to_num("Hospital overall rating") as integer)        as star_rating,
        nullif(trim("Hospital overall rating footnote"), '')      as star_rating_footnote,
        cast(to_num("Count of READM Measures Worse") as integer)  as readm_measures_worse
    from src
)
select * from cleaned
where ccn is not null;
