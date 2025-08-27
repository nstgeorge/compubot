-- Add interval_seconds column to reminders table
alter table reminders
add column if not exists interval_seconds integer;

-- Add index for interval_seconds to optimize queries for recurring reminders
create index if not exists idx_reminders_interval_seconds on reminders(interval_seconds);
