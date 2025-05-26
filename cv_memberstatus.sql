CREATE OR REPLACE VIEW member_status AS
SELECT
  m.member_id,
  m.surname,
  m.name,
  m.email,
  m.street_address,
  m.year_joined,
  m.sex,
  CASE
    WHEN NOT EXISTS (
      SELECT 1 FROM subscriptions s
      WHERE s.member_id = m.member_id
        AND s.year >= 2023
        AND LOWER(TRIM(s.fee_paid)) = 'no'
    ) THEN 'regolare'
    WHEN m.year_joined < 2022 AND NOT EXISTS (
      SELECT 1 FROM subscriptions s
      WHERE s.member_id = m.member_id AND s.year = 2023 AND LOWER(TRIM(s.fee_paid)) = 'yes'
    ) THEN 'decaduto'
    ELSE 'moroso'
  END AS stato
FROM members m;
