import asyncio
import datetime
import logging
from typing import Dict, Union

from dotenv import load_dotenv
from interactions import (Client, Extension, Member, OptionType, Role,
                          SlashContext, User, slash_command, slash_option)

from src.database.supabase_client import get_client

LOGGER = logging.getLogger(__name__)
load_dotenv()

class Remind(Extension):
  def __init__(self, client: Client):
    LOGGER.debug("Initialized /remind shard")
    self.client = client
    self.db = get_client()
    self.reminders: Dict[str, asyncio.Task] = {}  # Store active reminder tasks
    self.ready = False

  async def extension_load(self):
    """Called when the extension is loaded"""
    await self._load_active_reminders()
    self.ready = True

  def __get_output_channel(self, ctx):
    return ctx.channel_id

  @slash_command(
    name="remind",
    description="remind someone about something",
    sub_cmd_name="on",
    sub_cmd_description="remind at a certain time"
  )
  @slash_option(
    name="who",
    description="who to remind",
    required=True,
    opt_type=OptionType.MENTIONABLE
  )
  @slash_option(
    name="when",
    description="when to remind",
    required=True,
    opt_type=OptionType.STRING
  )
  @slash_option(
    name="description",
    description="what to remind about",
    required=True,
    opt_type=OptionType.STRING
  )
  async def remind_on(self, ctx: SlashContext, who: Union[Member, User, Role], when: str, description: str):
    try:
      now = datetime.datetime.now()
      
      # First try parsing as ISO format
      try:
        reminder_time = datetime.datetime.fromisoformat(when)
        delay = (reminder_time - now).total_seconds()
      except ValueError:
        # Try parsing as "in X units" format
        if not when.lower().startswith("in "):
          raise ValueError("Time must be either ISO format or start with 'in'")
        
        parts = when.lower().split()[1:]  # Skip the "in" part
        if len(parts) != 2:
          raise ValueError("Format must be 'in X units' (e.g. 'in 3 days')")
        
        try:
          amount = int(parts[0])
          unit = parts[1]
        except (ValueError, IndexError):
          raise ValueError("Invalid time format")
        
        # Use the same seconds mapping as remind_every
        seconds_map = {
          "second": 1,
          "seconds": 1,
          "minute": 60,
          "minutes": 60,
          "hour": 3600,
          "hours": 3600,
          "day": 86400,
          "days": 86400,
          "week": 604800,
          "weeks": 604800
        }
        
        if unit not in seconds_map:
          raise ValueError(f"Invalid unit. Must be one of: {', '.join(set(seconds_map.keys()))}")
        
        delay = amount * seconds_map[unit]
        reminder_time = now + datetime.timedelta(seconds=delay)
      
      if delay < 0:
        await ctx.send("Cannot set reminders in the past!")
        return

      # Store in database
      reminder_data = {
        "server_id": str(ctx.guild_id),
        "channel_id": str(ctx.channel_id),
        "author_id": str(ctx.author.id),
        "target_id": str(who.id),
        "description": description,
        "reminder_time": reminder_time.isoformat(),
        "is_recurring": False
      }
      
      reminder_id = await self.db.store_reminder(reminder_data)
      if not reminder_id:
        await ctx.send("Failed to create reminder. Please try again.")
        return

      # Schedule the reminder
      self.reminders[reminder_id] = asyncio.create_task(self._schedule_reminder(
        ctx.channel, who, description, delay, reminder_id
      ))

      await ctx.send(f"I'll remind <@{who.id}> about '{description}' at {reminder_time}")

    except ValueError as e:
      await ctx.send(f"Invalid time format: {str(e)}. Please use either ISO format (YYYY-MM-DD HH:MM:SS) or relative format (e.g. 'in 3 days')")

  @slash_command(
    name="remind",
    description="remind someone about something",
    sub_cmd_name="every",
    sub_cmd_description="remind at a certain interval"
  )
  @slash_option(
    name="interval",
    description="time between reminders (e.g. '1h', '30m', '1d')",
    required=True,
    opt_type=OptionType.STRING
  )
  @slash_option(
    name="who",
    description="who to remind",
    required=True,
    opt_type=OptionType.MENTIONABLE
  )
  @slash_option(
    name="description",
    description="what to remind about",
    required=True,
    opt_type=OptionType.STRING
  )
  @slash_option(
    name="starting_at",
    description="when to start reminding",
    required=False,
    opt_type=OptionType.STRING
  )
  async def remind_every(self, ctx: SlashContext, interval: str, who: Union[Member, User, Role], description: str, starting_at: str = None):
    try:
      # Parse interval (simple implementation)
      interval_parts = interval.lower().split()
      amount = int(interval_parts[1])
      unit = interval_parts[2]
      
      # Convert to seconds
      seconds_map = {
        "second": 1,
        "seconds": 1,
        "minute": 60,
        "minutes": 60,
        "hour": 3600,
        "hours": 3600,
        "day": 86400,
        "days": 86400,
        "week": 604800,
        "weeks": 604800
      }
      
      interval_seconds = amount * seconds_map.get(unit, 0)
      
      if interval_seconds == 0:
        await ctx.send("Invalid interval format")
        return

      # Handle starting time
      if starting_at:
        start_time = datetime.datetime.fromisoformat(starting_at)
      else:
        start_time = datetime.datetime.now() + datetime.timedelta(seconds=interval_seconds)

      # Store in database
      reminder_data = {
        "server_id": str(ctx.guild_id),
        "channel_id": str(ctx.channel_id),
        "author_id": str(ctx.author.id),
        "target_id": str(who.id),
        "description": description,
        "reminder_time": start_time.isoformat(),
        "is_recurring": True,
        "interval_seconds": interval_seconds
      }
      
      reminder_id = await self.db.store_reminder(reminder_data)
      if not reminder_id:
        await ctx.send("Failed to create reminder. Please try again.")
        return

      # Schedule recurring reminder
      self.reminders[reminder_id] = asyncio.create_task(self._schedule_recurring_reminder(
        ctx.channel, who, description, interval_seconds, start_time, reminder_id
      ))

      await ctx.send(f"I'll remind <@{who.id}> about '{description}' every {interval} starting {start_time}")

    except (ValueError, IndexError):
      await ctx.send("Invalid interval format. Use format like 'every 2 hours'")

  @slash_command(
    name="endreminder",
    description="end a recurring reminder"
  )
  @slash_option(
    name="description",
    description="the description you used for the reminder",
    required=True,
    opt_type=OptionType.STRING
  )
  async def end_reminder(self, ctx: SlashContext, description: str):
    # Find active reminders by description and author
    reminders = await self.db.get_data('reminders', {
      'author_id': str(ctx.author.id),
      'description': description,
      'is_active': True
    })
    
    if not reminders:
      await ctx.send("No matching reminder found")
      return
      
    for reminder in reminders:
      reminder_id = reminder['id']
      if reminder_id in self.reminders:
        self.reminders[reminder_id].cancel()
        del self.reminders[reminder_id]
      
      await self.db.update_reminder(reminder_id, {'is_active': False})
    
    await ctx.send(f"Reminder '{description}' has been cancelled")

  async def _schedule_reminder(self, channel, who, description, delay, reminder_id):
    try:
      await asyncio.sleep(delay)
      await channel.send(f"<@{who.id}>: {description}")
      # Mark as inactive once completed
      await self.db.update_reminder(reminder_id, {'is_active': False})
      if reminder_id in self.reminders:
        del self.reminders[reminder_id]
    except asyncio.CancelledError:
      return
    except Exception as e:
      LOGGER.error(f"Error in reminder {reminder_id}: {e}")

  async def _schedule_recurring_reminder(self, channel, who, description, interval, start_time, reminder_id):
    try:
      while True:
        now = datetime.datetime.now()
        delay = (start_time - now).total_seconds()
        
        if delay > 0:
          await asyncio.sleep(delay)
        
        await channel.send(f"<@{who.id}>: {description}")
        
        # Update next reminder time in database
        start_time += datetime.timedelta(seconds=interval)
        await self.db.update_reminder(reminder_id, {
          'reminder_time': start_time.isoformat()
        })
    except asyncio.CancelledError:
      return
    except Exception as e:
      LOGGER.error(f"Error in recurring reminder {reminder_id}: {e}")
      # Mark as inactive if there's an error
      await self.db.update_reminder(reminder_id, {'is_active': False})
      if reminder_id in self.reminders:
        del self.reminders[reminder_id]

  async def _load_active_reminders(self):
    """Load and schedule all active reminders from the database"""
    try:
      active_reminders = await self.db.get_active_reminders()
      for reminder in active_reminders:
        now = datetime.datetime.now()
        reminder_time = datetime.datetime.fromisoformat(reminder['reminder_time'])
        delay = (reminder_time - now).total_seconds()
        
        if delay < 0:
          # Mark old reminders as inactive
          await self.db.update_reminder(reminder['id'], {'is_active': False})
          continue
        
        channel = await self.client.fetch_channel(reminder['channel_id'])
        who = await self.client.fetch_user(reminder['target_id'])
        
        if reminder['is_recurring']:
          self.reminders[reminder['id']] = asyncio.create_task(
            self._schedule_recurring_reminder(
              channel,
              who,
              reminder['description'],
              reminder['interval_seconds'],
              reminder_time,
              reminder['id']
            )
          )
        else:
          self.reminders[reminder['id']] = asyncio.create_task(
            self._schedule_reminder(
              channel,
              who,
              reminder['description'],
              delay,
              reminder['id']
            )
          )
    except Exception as e:
      LOGGER.error(f"Error loading active reminders: {e}")

def setup(bot):
  Remind(bot)