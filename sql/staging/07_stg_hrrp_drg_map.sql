-- 07_stg_hrrp_drg_map.sql
-- Reference table: which MS-DRGs represent each HRRP condition.
-- Used to attach a dollar value to an excess readmission:
--   cost of one readmission ~= average Medicare payment for that condition's DRGs.
-- Choices (see docs/DECISIONS.md):
--   AMI      280-282  AMI discharged alive (w MCC / w CC / w/o CC-MCC)
--   HF       291-293  Heart failure and shock
--   PN       193-195  Simple pneumonia; 177-179 respiratory infections
--                     (covers aspiration pneumonia, which is in the HRRP cohort)
--   COPD     190-192
--   CABG     231-236  Coronary bypass
--   HIP-KNEE 469-470  Major hip and knee joint replacement (elective THA/TKA)

create or replace table stg_hrrp_drg_map as
select * from (
    values
    ('AMI','280'),('AMI','281'),('AMI','282'),
    ('HF','291'),('HF','292'),('HF','293'),
    ('PN','177'),('PN','178'),('PN','179'),('PN','193'),('PN','194'),('PN','195'),
    ('COPD','190'),('COPD','191'),('COPD','192'),
    ('CABG','231'),('CABG','232'),('CABG','233'),('CABG','234'),('CABG','235'),('CABG','236'),
    ('HIP-KNEE','469'),('HIP-KNEE','470')
) as t(condition_code, drg_code);
