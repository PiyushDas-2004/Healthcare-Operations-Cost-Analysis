-- 00_macros.sql
-- Reusable cleaning helpers shared by every staging model.
--
-- CMS files encode missing values as text placeholders instead of blanks:
--   "Not Available", "N/A", "Too Few to Report", "Not Applicable", "--", "".
-- to_num() turns any of these (or anything else that is not a number) into NULL
-- and strips thousands separators / percent signs before casting.
-- to_ccn() standardises a CMS Certification Number (CCN / "Facility ID") as
-- 6-character text with leading zeros preserved (e.g. 10001 -> '010001').

create or replace macro to_num(x) as
    try_cast(
        nullif(
            replace(replace(trim(cast(x as varchar)), ',', ''), '%', ''),
            ''
        ) as double
    );

create or replace macro is_missing_token(x) as
    x is null
    or trim(cast(x as varchar)) in ('', 'N/A', 'Not Available', 'Too Few to Report', 'Not Applicable', '--');

create or replace macro to_ccn(x) as
    case
        when x is null or trim(cast(x as varchar)) = '' then null
        else lpad(upper(trim(cast(x as varchar))), 6, '0')
    end;
