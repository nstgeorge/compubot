-- Add target_id column to reminders table
alter table reminders
add column if not exists target_id text not null default '';

-- Add index for target_id to optimize queries
create index if not exists idx_reminders_target_id on reminders(target_id);

-- Update existing reminders to set target_id same as user_id for backwards compatibility
update reminders
set target_id = user_id
where target_id = '';
