-- Create reminders table
create table if not exists reminders (
    id uuid default gen_random_uuid() primary key,
    user_id text not null,
    channel_id text not null,
    message text not null,
    reminder_time timestamp with time zone not null,
    is_active boolean default true,
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now()
);

-- Create server_settings table
create table if not exists server_settings (
    id uuid default gen_random_uuid() primary key,
    server_id text not null,
    key text not null,
    value jsonb not null,
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now(),
    unique(server_id, key)
);

-- Create updated_at trigger function
create or replace function update_updated_at_column()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

-- Add triggers for updated_at
create trigger update_reminders_updated_at
    before update on reminders
    for each row
    execute function update_updated_at_column();

create trigger update_server_settings_updated_at
    before update on server_settings
    for each row
    execute function update_updated_at_column();

-- Add indexes
create index if not exists idx_reminders_is_active on reminders(is_active);
create index if not exists idx_reminders_reminder_time on reminders(reminder_time);
create index if not exists idx_server_settings_lookup on server_settings(server_id, key);
