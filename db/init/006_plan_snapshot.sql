-- Freeze current input data for existing plans. Earlier edits cannot be recovered.
ALTER TABLE plan ADD COLUMN IF NOT EXISTS input_snapshot JSONB;
UPDATE plan p SET input_snapshot = jsonb_build_object(
 'requests', COALESCE((SELECT jsonb_object_agg(r.id::text, to_jsonb(r))
   FROM request r WHERE EXISTS (SELECT 1 FROM assignment a WHERE a.plan_id=p.id AND a.request_id=r.id)), '{}'::jsonb),
 'engineers', COALESCE((SELECT jsonb_object_agg(e.id::text, to_jsonb(e) || jsonb_build_object('skill_ids',
   (SELECT jsonb_agg(es.skill_id) FROM engineer_skill es WHERE es.engineer_id=e.id)))
   FROM engineer e WHERE EXISTS (SELECT 1 FROM assignment a WHERE a.plan_id=p.id AND a.engineer_id=e.id)), '{}'::jsonb)
) WHERE input_snapshot IS NULL;
