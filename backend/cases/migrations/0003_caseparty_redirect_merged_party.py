from django.db import migrations


REDIRECT_TRIGGER = """
CREATE OR REPLACE FUNCTION cases_caseparty_redirect_merged_party()
RETURNS trigger AS $$
DECLARE
  target_id bigint := NEW.party_id;
  next_master bigint;
  existing_id bigint;
  existing_client boolean;
BEGIN
  LOOP
    SELECT merged_into_id INTO next_master
    FROM cases_party
    WHERE id = target_id;

    EXIT WHEN next_master IS NULL;
    target_id := next_master;
  END LOOP;

  IF target_id <> NEW.party_id THEN
    NEW.party_id := target_id;

    SELECT id, is_client INTO existing_id, existing_client
    FROM cases_caseparty
    WHERE case_id = NEW.case_id
      AND party_id = target_id
      AND role = NEW.role
    LIMIT 1;

    IF FOUND THEN
      UPDATE cases_caseparty
      SET is_client = (is_client OR NEW.is_client)
      WHERE id = existing_id;
      RETURN NULL;
    END IF;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER caseparty_redirect_merged_party
BEFORE INSERT OR UPDATE OF party_id, case_id, role ON cases_caseparty
FOR EACH ROW
EXECUTE FUNCTION cases_caseparty_redirect_merged_party();
"""

DROP_TRIGGER = """
DROP TRIGGER IF EXISTS caseparty_redirect_merged_party ON cases_caseparty;
DROP FUNCTION IF EXISTS cases_caseparty_redirect_merged_party();
"""


class Migration(migrations.Migration):

    dependencies = [
        ('cases', '0002_party_merged_at_party_merged_into_and_more'),
    ]

    operations = [
        migrations.RunSQL(REDIRECT_TRIGGER, DROP_TRIGGER),
    ]
