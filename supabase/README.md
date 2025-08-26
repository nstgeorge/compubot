# Database Migrations

This project uses Supabase for database management. Migrations are stored in SQL files in the `supabase/migrations` directory.

## Creating a New Migration

To create a new migration:

1. Run the migration script:
   ```bash
   python scripts/create_migration.py "description of changes"
   ```

2. This will create a new timestamped SQL file in `supabase/migrations/`

3. Add your SQL commands to the new migration file

## Applying Migrations

Migrations are automatically applied when deploying to Supabase using their dashboard or CLI.

To apply migrations locally during development:

1. Install the Supabase CLI
2. Link your project: `supabase link --project-ref your-project-ref`
3. Push migrations: `supabase db push`

## Migration Guidelines

1. All migrations should be reversible when possible
2. Use `IF EXISTS` / `IF NOT EXISTS` clauses for safety
3. Add appropriate indexes for query performance
4. Document complex migrations with comments
5. Test migrations in a development environment first

## Current Schema

The database currently has the following tables:

### reminders
- `id`: UUID primary key
- `user_id`: Text (Discord user ID)
- `channel_id`: Text (Discord channel ID)
- `message`: Text (reminder message)
- `reminder_time`: Timestamp with timezone
- `is_active`: Boolean
- `created_at`: Timestamp with timezone
- `updated_at`: Timestamp with timezone

### server_settings
- `id`: UUID primary key
- `server_id`: Text (Discord server ID)
- `key`: Text
- `value`: JSONB
- `created_at`: Timestamp with timezone
- `updated_at`: Timestamp with timezone
