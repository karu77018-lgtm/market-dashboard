-- Jev Phase 1 / Stage 2
-- Apply ONLY after:
-- 1) Stage 1 is live,
-- 2) hardened API is deployed,
-- 3) smoke/dedupe/summary tests pass.
--
-- Stage 2 closes the nullable migration window and freezes audit-critical rows.

ALTER TABLE jev_evaluations
  ALTER COLUMN evaluation_kind SET NOT NULL;

CREATE OR REPLACE FUNCTION protect_jev_attempts_final()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'jev_attempts rows are append/finalize only; delete is forbidden';
  END IF;

  IF OLD.completed_at IS NOT NULL OR OLD.status <> 'started' THEN
    RAISE EXCEPTION 'completed jev_attempts rows are immutable';
  END IF;

  IF NEW.ticker IS DISTINCT FROM OLD.ticker
     OR NEW.asof_timestamp IS DISTINCT FROM OLD.asof_timestamp
     OR NEW.question_set_id IS DISTINCT FROM OLD.question_set_id
     OR NEW.evaluation_kind IS DISTINCT FROM OLD.evaluation_kind
     OR NEW.source_document_id IS DISTINCT FROM OLD.source_document_id
     OR NEW.state_text_hash IS DISTINCT FROM OLD.state_text_hash
     OR NEW.dedupe_key IS DISTINCT FROM OLD.dedupe_key
     OR NEW.run_count IS DISTINCT FROM OLD.run_count
     OR NEW.started_at IS DISTINCT FROM OLD.started_at THEN
    RAISE EXCEPTION 'attempt identity fields are immutable';
  END IF;

  IF NEW.status = 'started' OR NEW.completed_at IS NULL THEN
    RAISE EXCEPTION 'attempt finalization must set terminal status and completed_at';
  END IF;

  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_jev_attempts_final_immutable
BEFORE UPDATE OR DELETE ON jev_attempts
FOR EACH ROW
EXECUTE FUNCTION protect_jev_attempts_final();

CREATE OR REPLACE FUNCTION block_jev_truncate()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'TRUNCATE is forbidden on protected Jev tables';
END;
$$;

CREATE TRIGGER trg_jev_attempts_no_truncate
BEFORE TRUNCATE ON jev_attempts
FOR EACH STATEMENT
EXECUTE FUNCTION block_jev_truncate();

CREATE OR REPLACE FUNCTION protect_questions_by_set_status()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  old_status text;
  new_status text;
BEGIN
  IF TG_OP = 'INSERT' THEN
    SELECT status INTO new_status FROM question_sets WHERE id = NEW.question_set_id;
    IF new_status IS DISTINCT FROM 'draft' THEN
      RAISE EXCEPTION 'questions may only be inserted into draft question sets';
    END IF;
    RETURN NEW;
  END IF;

  SELECT status INTO old_status FROM question_sets WHERE id = OLD.question_set_id;

  IF TG_OP = 'DELETE' THEN
    IF old_status IS DISTINCT FROM 'draft' THEN
      RAISE EXCEPTION 'questions in non-draft question sets are immutable';
    END IF;
    RETURN OLD;
  END IF;

  SELECT status INTO new_status FROM question_sets WHERE id = NEW.question_set_id;
  IF old_status IS DISTINCT FROM 'draft' OR new_status IS DISTINCT FROM 'draft' THEN
    RAISE EXCEPTION 'questions in non-draft question sets are immutable';
  END IF;

  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_questions_frozen_after_draft
BEFORE INSERT OR UPDATE OR DELETE ON questions
FOR EACH ROW
EXECUTE FUNCTION protect_questions_by_set_status();

CREATE TRIGGER trg_questions_no_truncate
BEFORE TRUNCATE ON questions
FOR EACH STATEMENT
EXECUTE FUNCTION block_jev_truncate();

CREATE OR REPLACE FUNCTION protect_question_set_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  old_rank integer;
  new_rank integer;
BEGIN
  old_rank := CASE OLD.status
    WHEN 'draft' THEN 0 WHEN 'shadow' THEN 1 WHEN 'validation' THEN 2
    WHEN 'production' THEN 3 WHEN 'retired' THEN 4 ELSE -1 END;
  new_rank := CASE NEW.status
    WHEN 'draft' THEN 0 WHEN 'shadow' THEN 1 WHEN 'validation' THEN 2
    WHEN 'production' THEN 3 WHEN 'retired' THEN 4 ELSE -1 END;

  IF new_rank < old_rank THEN
    RAISE EXCEPTION 'question set status cannot move backward';
  END IF;

  IF OLD.activated_at IS NOT NULL AND NEW.activated_at IS DISTINCT FROM OLD.activated_at THEN
    RAISE EXCEPTION 'activated_at can only be set once';
  END IF;

  IF OLD.retired_at IS NOT NULL AND NEW.retired_at IS DISTINCT FROM OLD.retired_at THEN
    RAISE EXCEPTION 'retired_at can only be set once';
  END IF;

  IF OLD.status <> 'draft' THEN
    IF NEW.version IS DISTINCT FROM OLD.version
       OR NEW.requested_model IS DISTINCT FROM OLD.requested_model
       OR NEW.model_revision IS DISTINCT FROM OLD.model_revision
       OR NEW.default_runs IS DISTINCT FROM OLD.default_runs
       OR NEW.schema_version IS DISTINCT FROM OLD.schema_version
       OR NEW.hash_canonicalization_version IS DISTINCT FROM OLD.hash_canonicalization_version
       OR NEW.question_set_hash IS DISTINCT FROM OLD.question_set_hash
       OR NEW.notes IS DISTINCT FROM OLD.notes
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
      RAISE EXCEPTION 'non-draft question set definition is immutable';
    END IF;
  END IF;

  IF NEW.status = 'retired' AND NEW.retired_at IS NULL THEN
    NEW.retired_at := now();
  END IF;

  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_question_sets_update_guard
BEFORE UPDATE ON question_sets
FOR EACH ROW
EXECUTE FUNCTION protect_question_set_update();

-- The following is part of the intended production policy.
-- It was not executable through the current ChatGPT Neon safety wrapper during staging,
-- but it is standard PostgreSQL syntax and should be applied/verified during Stage 2.
CREATE TRIGGER trg_question_sets_no_truncate
BEFORE TRUNCATE ON question_sets
FOR EACH STATEMENT
EXECUTE FUNCTION block_jev_truncate();
