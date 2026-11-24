-- 01_stg_state_region.sql
-- Reference table: US state / territory -> US Census Bureau region and division.
-- Used to group 50+ states into 4 regions so the regression does not need a
-- dummy variable per state (which would eat degrees of freedom and overfit).
-- Territories (PR, GU, VI, MP, AS) are kept as their own "Territory" region.

create or replace table stg_state_region as
with mapping(state, region, division) as (
    values
    ('CT','Northeast','New England'),('ME','Northeast','New England'),('MA','Northeast','New England'),
    ('NH','Northeast','New England'),('RI','Northeast','New England'),('VT','Northeast','New England'),
    ('NJ','Northeast','Middle Atlantic'),('NY','Northeast','Middle Atlantic'),('PA','Northeast','Middle Atlantic'),
    ('IL','Midwest','East North Central'),('IN','Midwest','East North Central'),('MI','Midwest','East North Central'),
    ('OH','Midwest','East North Central'),('WI','Midwest','East North Central'),
    ('IA','Midwest','West North Central'),('KS','Midwest','West North Central'),('MN','Midwest','West North Central'),
    ('MO','Midwest','West North Central'),('NE','Midwest','West North Central'),('ND','Midwest','West North Central'),
    ('SD','Midwest','West North Central'),
    ('DE','South','South Atlantic'),('DC','South','South Atlantic'),('FL','South','South Atlantic'),
    ('GA','South','South Atlantic'),('MD','South','South Atlantic'),('NC','South','South Atlantic'),
    ('SC','South','South Atlantic'),('VA','South','South Atlantic'),('WV','South','South Atlantic'),
    ('AL','South','East South Central'),('KY','South','East South Central'),('MS','South','East South Central'),
    ('TN','South','East South Central'),
    ('AR','South','West South Central'),('LA','South','West South Central'),('OK','South','West South Central'),
    ('TX','South','West South Central'),
    ('AZ','West','Mountain'),('CO','West','Mountain'),('ID','West','Mountain'),('MT','West','Mountain'),
    ('NV','West','Mountain'),('NM','West','Mountain'),('UT','West','Mountain'),('WY','West','Mountain'),
    ('AK','West','Pacific'),('CA','West','Pacific'),('HI','West','Pacific'),('OR','West','Pacific'),
    ('WA','West','Pacific'),
    ('PR','Territory','Territory'),('GU','Territory','Territory'),('VI','Territory','Territory'),
    ('MP','Territory','Territory'),('AS','Territory','Territory')
)
select * from mapping;
