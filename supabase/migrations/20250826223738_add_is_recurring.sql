-- Add is_recurring column to reminders table
alter table reminders
add column if not exists is_recurring boolean default false;

-- Add index for is_recurring to optimize queries for recurring reminders
create index if not exists idx_reminders_is_recurring on reminders(is_recurring) where is_recurring = true;
