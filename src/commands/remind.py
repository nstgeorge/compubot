import asyncio
import datetime
import logging
from typing import Dict, Union
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from interactions import (ActionRow, Button, ButtonStyle, Client,
                          ComponentContext, Extension, Member, OptionType,
                          Role, SlashContext, StringSelectMenu,
                          StringSelectOption, User, component_callback, listen,
                          slash_command, slash_option)
from interactions.api.events import Startup

from src.database.supabase_client import get_client
from src.utils.emotes import emotes

LOGGER = logging.getLogger(__name__)
load_dotenv()

class Remind(Extension):
  def __init__(self, client: Client):
    LOGGER.debug("Initialized /remind shard")
    self.client = client
    self.db = get_client()
    self.reminders: Dict[str, asyncio.Task] = {}  # Store active reminder tasks
    self.pending_delete = None  # Store ID of reminder pending deletion
    self.ready = False

  @listen(Startup)
  async def on_startup(self):
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
    name="when",
    description="when to remind ([YYYY-MM-DD] HH:MM[:SS] [±HH:MM] or 'in X units')",
    required=True,
    opt_type=OptionType.STRING
  )
  @slash_option(
    name="description",
    description="what to remind about",
    required=True,
    opt_type=OptionType.STRING
  )
  @slash_option(
    name="who",
    description="who to remind",
    required=True,
    opt_type=OptionType.MENTIONABLE
  )
  async def remind_on(self, ctx: SlashContext, when: str, description: str, who: Union[Member, User, Role]):
    try:
      now = datetime.datetime.now(ZoneInfo("UTC"))
      
      # First check if time has timezone offset
      time_parts = when.split()
      has_timezone = len(time_parts) > 1 and (time_parts[-1].startswith('+') or time_parts[-1].startswith('-'))
      
      # Try relative time format only if there's no timezone
      parts = when.lower().split()
      if not has_timezone and (len(parts) == 2 or (len(parts) == 3 and parts[0] == "in")):
        # Try relative time format
        if parts[0] == "in":
          parts = parts[1:]
        
        try:
          amount = int(parts[0])
          unit = parts[1]
          
          # Use the same seconds mapping as remind_every
          seconds_map = {
            "second": 1, "seconds": 1,
            "minute": 60, "minutes": 60,
            "hour": 3600, "hours": 3600,
            "day": 86400, "days": 86400,
            "week": 604800, "weeks": 604800
          }
          
          if unit not in seconds_map:
            raise ValueError(f"Invalid unit. Must be one of: {', '.join(set(seconds_map.keys()))}")
          
          delay = amount * seconds_map[unit]
          reminder_time = now + datetime.timedelta(seconds=delay)
          if reminder_time.tzinfo is None:
            reminder_time = reminder_time.replace(tzinfo=ZoneInfo("UTC"))
          
        except (ValueError, IndexError):
          raise ValueError("For relative format, use: NUMBER UNIT (e.g. '3 days' or 'in 3 days')")
          
      else:
        # Try ISO format
        try:
          # Handle timezone offset
          if has_timezone:
            offset = time_parts[-1]
            when = ' '.join(time_parts[:-1])
            if ':' not in offset:  # If format is just +/-N, append :00
              offset = f"{offset}:00"
          else:
            offset = ""
          
          # Try parsing as time-only format (HH:MM or HH:MM:SS)
          try:
            parsed_time = datetime.datetime.strptime(when, "%H:%M")
            when = now.strftime("%Y-%m-%d ") + when
          except ValueError:
            try:
              parsed_time = datetime.datetime.strptime(when, "%H:%M:%S")
              when = now.strftime("%Y-%m-%d ") + when
            except ValueError:
              pass  # Not a time-only format, continue with full datetime parsing
          
          # Add back the timezone if it was present
          if offset:
            when = f"{when} {offset}"
          
          reminder_time = datetime.datetime.fromisoformat(when)
          if reminder_time.tzinfo is None:
            reminder_time = reminder_time.replace(tzinfo=ZoneInfo("UTC"))
          delay = (reminder_time - now).total_seconds()
        except ValueError:
          raise ValueError("For absolute times, use: [YYYY-MM-DD] HH:MM[:SS] [±HH:MM] (e.g. '15:00', '2023-08-27 15:00' or '15:00 -08:00')")
      
      if delay < 0:
        await ctx.send("Cannot set reminders in the past!", ephemeral=True)
        return

      # Store in database
      reminder_data = {
        "channel_id": str(ctx.channel_id),
        "user_id": str(ctx.author.id),
        "target_id": str(who.id),
        "message": description,
        "reminder_time": reminder_time.isoformat(),
        "is_recurring": False
      }
      
      reminder_id = await self.db.store_reminder(reminder_data)
      if not reminder_id:
        await ctx.send("Failed to create reminder. Please try again.", ephemeral=True)
        return

      # Schedule the reminder
      self.reminders[reminder_id] = asyncio.create_task(self._schedule_reminder(
        ctx.channel, who, description, delay, reminder_id
      ))

      unix_timestamp = int(reminder_time.timestamp())
      mention = f"<@&{who.id}>" if isinstance(who, Role) else f"<@{who.id}>"
      await ctx.send(f"{emotes.get_emote('Okay')} I'll remind {mention} about '{description}' at <t:{unix_timestamp}:F>")

    except ValueError as e:
      await ctx.send(str(e), ephemeral=True)

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
    name="description",
    description="what to remind about",
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
    name="starting_at",
    description="when to start reminding ([YYYY-MM-DD] HH:MM[:SS] [±HH:MM])",
    required=False,
    opt_type=OptionType.STRING
  )
  async def remind_every(self, ctx: SlashContext, interval: str, description: str, who: Union[Member, User, Role], starting_at: str = None):
    try:
      # Parse interval (simple implementation)
      interval_parts = interval.lower().split()
      # Remove "every" if it exists
      if interval_parts[0] == "every":
          interval_parts = interval_parts[1:]
          
      if len(interval_parts) != 2:
          raise ValueError("Format must be '[every] X units' (e.g. '2 hours' or 'every 2 hours')")
          
      amount = int(interval_parts[0])
      unit = interval_parts[1]
      
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
        await ctx.send("Invalid interval format", ephemeral=True)
        return

      # Handle starting time
      if starting_at:
        try:
          # Check if the time string has a timezone offset at the end
          time_parts = starting_at.split()
          has_timezone = len(time_parts) > 1 and (time_parts[-1].startswith('+') or time_parts[-1].startswith('-'))
          
          if has_timezone:
            offset = time_parts[-1]
            starting_at = ' '.join(time_parts[:-1])
            if ':' not in offset:  # If format is just +/-N, append :00
              offset = f"{offset}:00"
          else:
            offset = ""
            
          # Try parsing as time-only format (HH:MM or HH:MM:SS)
          try:
            parsed_time = datetime.datetime.strptime(starting_at, "%H:%M")
            starting_at = datetime.datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d ") + starting_at
          except ValueError:
            try:
              parsed_time = datetime.datetime.strptime(starting_at, "%H:%M:%S")
              starting_at = datetime.datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d ") + starting_at
            except ValueError:
              pass  # Not a time-only format, continue with full datetime parsing
          
          # Add back the timezone if it was present
          if offset:
            starting_at = f"{starting_at} {offset}"
          
          start_time = datetime.datetime.fromisoformat(starting_at)
          if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=ZoneInfo("UTC"))
        except ValueError as e:
          raise ValueError(f"Invalid starting time format. Use: [YYYY-MM-DD] HH:MM[:SS] [±HH:MM] (e.g. '15:00', '2023-08-27 15:00' or '15:00 -08:00')")
      else:
        start_time = datetime.datetime.now(ZoneInfo("UTC")) + datetime.timedelta(seconds=interval_seconds)

      # Store in database
      reminder_data = {
        "channel_id": str(ctx.channel_id),
        "user_id": str(ctx.author.id),
        "target_id": str(who.id),
        "message": description,
        "reminder_time": start_time.isoformat(),
        "is_recurring": True,
        "interval_seconds": interval_seconds
      }
      
      reminder_id = await self.db.store_reminder(reminder_data)
      if not reminder_id:
        await ctx.send("Failed to create reminder. Please try again.", ephemeral=True)
        return

      # Schedule recurring reminder
      self.reminders[reminder_id] = asyncio.create_task(self._schedule_recurring_reminder(
        ctx.channel, who, description, interval_seconds, start_time, reminder_id
      ))

      unix_timestamp = int(start_time.timestamp())
      mention = f"<@&{who.id}>" if isinstance(who, Role) else f"<@{who.id}>"
      await ctx.send(f"{emotes.get_emote('Okay')} I'll remind {mention} about '{description}' every {interval} starting at <t:{unix_timestamp}:F>")

    except (ValueError, IndexError) as e:
      await ctx.send(f"Invalid interval format: {str(e)}. Use format like '2 hours' or 'every 2 hours'", ephemeral=True)

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
      'user_id': str(ctx.author.id),
      'message': description,
      'is_active': True
    })
    
    if not reminders:
      await ctx.send("No matching reminder found", ephemeral=True)
      return
      
    for reminder in reminders:
      reminder_id = reminder['id']
      if reminder_id in self.reminders:
        self.reminders[reminder_id].cancel()
        del self.reminders[reminder_id]
      
      self.db.update_reminder(reminder_id, {'is_active': False})
    
    await ctx.send(f"Reminder '{description}' has been cancelled")

  @slash_command(
    name="reminders",
    description="manage your reminders"
  )
  async def manage_reminders(self, ctx: SlashContext):
    reminders = await self.db.get_data('reminders', {
      'user_id': str(ctx.author.id),
      'is_active': True
    })
    
    if not reminders:
      await ctx.send("You have no active reminders", ephemeral=True)
      return

    select_menu = StringSelectMenu(
      custom_id="cancel_reminder_select",
      placeholder="Select a reminder to cancel",
      min_values=1,
      max_values=1
    )

    for reminder in reminders:
      reminder_time = datetime.datetime.fromisoformat(reminder['reminder_time'])
      recurring = "🔄" if reminder['is_recurring'] else "⏰"
      
      # Get target name in plain text
      try:
        role = await ctx.guild.fetch_role(int(reminder['target_id']))
        if role is not None:
          target = f"@{role.name}"
        else:
          user = await ctx.guild.fetch_member(int(reminder['target_id']))
          target = f"@{user.display_name}" if user else "unknown user"
      except:
        target = "unknown user"
      
      # Format time in a human-readable way
      now = datetime.datetime.now(ZoneInfo("UTC"))
      time_diff = reminder_time - now
      
      if time_diff.days > 0:
        if time_diff.days == 1:
          time_text = "tomorrow"
        else:
          time_text = f"in {time_diff.days} days"
      else:
        hours = time_diff.seconds // 3600
        minutes = (time_diff.seconds % 3600) // 60
        if hours > 0:
          time_text = f"in {hours}h {minutes}m"
        else:
          time_text = f"in {minutes}m"
      
      # Add option to select menu
      label = f"{recurring} {reminder['message'][:50]}"  # Truncate long messages
      description = f"For: {target} • Next: {time_text}"
      select_menu.options.append(
        StringSelectOption(
          label=label,
          value=str(reminder['id']),
          description=description
        )
      )
    
    components = ActionRow(select_menu)
    await ctx.send(
      "Select a reminder to cancel:",
      components=components,
      ephemeral=True
    )

  @component_callback("cancel_reminder_select")
  async def cancel_reminder_callback(self, ctx: ComponentContext):
    reminder_id = ctx.values[0]
    
    # Update the selection menu to show we're processing
    await ctx.edit_origin(content="Processing selection...", components=[])
    
    reminder = await self.db.get_data('reminders', {
      'id': reminder_id,
      'user_id': str(ctx.author.id),
      'is_active': True
    })
    
    if not reminder:
      await ctx.send("This reminder no longer exists!", ephemeral=True)
      return
      
    reminder = reminder[0]
    recurring = "🔄" if reminder['is_recurring'] else "⏰"
    
    # Check if target_id corresponds to a role by trying to fetch it
    try:
      role = await ctx.guild.fetch_role(int(reminder['target_id']))
      is_role = role is not None
    except:
      is_role = False
      
    mention = f"<@&{reminder['target_id']}>" if is_role else f"<@{reminder['target_id']}>"
    
    # Store the current reminder ID for deletion
    self.pending_delete = reminder_id
    
    delete_button = Button(
      style=ButtonStyle.DANGER,
      label="Delete Reminder",
      custom_id="confirm_delete"
    )
    
    await ctx.send(
      f"Are you sure you want to delete this reminder?\n\n{recurring} **{reminder['message']}**\nFor: {mention}\n",
      components=ActionRow(delete_button),
      ephemeral=True
    )

  @component_callback("confirm_delete")
  async def confirm_delete_callback(self, ctx: ComponentContext):
    try:
      await ctx.defer(ephemeral=True)
      
      if not self.pending_delete:
        await ctx.send("No reminder selected for deletion.", ephemeral=True)
        return
        
      reminder_id = self.pending_delete
      LOGGER.debug(f"Attempting to delete reminder {reminder_id}")
      
      # First check if reminder exists and belongs to user
      reminder = self.db.get_data('reminders', {
        'id': reminder_id,
        'user_id': str(ctx.author.id),
        'is_active': True
      })
      
      if not reminder:
        await ctx.send("This reminder no longer exists!", ephemeral=True)
        return
      
      reminder = reminder[0]
      
      # Cancel the task if it exists
      if reminder_id in self.reminders:
        self.reminders[reminder_id].cancel()
        del self.reminders[reminder_id]
      
      # Update database
      self.db.update_reminder(reminder_id, {'is_active': False})
      
      # Format mention
      try:
        role = await ctx.guild.fetch_role(int(reminder['target_id']))
        mention = f"<@&{reminder['target_id']}>" if role else f"<@{reminder['target_id']}>"
      except:
        mention = f"<@{reminder['target_id']}>"
      
      # Update the confirmation message with success
      await ctx.edit_origin(
        content=f"✅ Reminder cancelled successfully.\nThe reminder '{reminder['message']}' has been deleted.",
        components=[]
      )
      
      LOGGER.debug(f"Successfully cancelled reminder {reminder_id}")
      self.pending_delete = None  # Clear the pending deletion
      
    except Exception as e:
      LOGGER.error(f"Error in confirm_delete_callback: {e}", exc_info=True)
      try:
        # Update the confirmation message to show detailed error
        await ctx.edit_origin(
          content="❌ Failed to cancel reminder.\nPlease try again or contact an administrator if the problem persists.",
          components=[]
        )
      except Exception as send_error:
        LOGGER.error(f"Failed to send error message: {send_error}", exc_info=True)

  async def _schedule_reminder(self, channel, who, description, delay, reminder_id):
    try:
      await asyncio.sleep(delay)
      unix_timestamp = int(datetime.datetime.now().timestamp())
      mention = f"<@&{who.id}>" if isinstance(who, Role) else f"<@{who.id}>"
      await channel.send(f"{emotes.get_emote('dinkDonk')} {mention}: {description}")
      # Mark as inactive once completed
      self.db.update_reminder(reminder_id, {'is_active': False})
      if reminder_id in self.reminders:
        del self.reminders[reminder_id]
    except asyncio.CancelledError:
      return
    except Exception as e:
      LOGGER.error(f"Error in reminder {reminder_id}: {e}")

  async def _schedule_recurring_reminder(self, channel, who, description, interval, start_time, reminder_id):
    try:
      while True:
        now = datetime.datetime.now(ZoneInfo("UTC"))
        
        # Calculate next occurrence if we're past the start time
        while start_time <= now:
          start_time += datetime.timedelta(seconds=interval)
        
        # Wait until next reminder time
        delay = (start_time - now).total_seconds()
        await asyncio.sleep(delay)
        
        # Send the reminder
        mention = f"<@&{who.id}>" if isinstance(who, Role) else f"<@{who.id}>"
        await channel.send(f"{emotes.get_emote('dinkDonk')} {mention}: {description}")
        
        # Calculate next reminder time and update database
        start_time = start_time + datetime.timedelta(seconds=interval)
        self.db.update_reminder(reminder_id, {
          'reminder_time': start_time.isoformat()
        })
    except asyncio.CancelledError:
      return
    except Exception as e:
      LOGGER.error(f"Error in recurring reminder {reminder_id}: {e}")
      # Mark as inactive if there's an error
      self.db.update_reminder(reminder_id, {'is_active': False})
      if reminder_id in self.reminders:
        del self.reminders[reminder_id]

  async def _load_active_reminders(self):
    """Load and schedule all active reminders from the database"""
    try:
      active_reminders = self.db.get_active_reminders()
      for reminder in active_reminders:
        now = datetime.datetime.now(ZoneInfo("UTC"))
        reminder_time = datetime.datetime.fromisoformat(reminder['reminder_time'])
        if reminder_time.tzinfo is None:
          reminder_time = reminder_time.replace(tzinfo=ZoneInfo("UTC"))
        delay = (reminder_time - now).total_seconds()
        
        if delay < 0:
          if reminder['is_recurring']:
            # For recurring reminders, calculate next occurrence
            while reminder_time <= now:
              reminder_time += datetime.timedelta(seconds=reminder['interval_seconds'])
            delay = (reminder_time - now).total_seconds()
            # Update the next reminder time in the database
            self.db.update_reminder(reminder['id'], {'reminder_time': reminder_time.isoformat()})
          else:
            # For one-time reminders, mark as inactive
            self.db.update_reminder(reminder['id'], {'is_active': False})
            continue
        
        channel = await self.client.fetch_channel(reminder['channel_id'])
        who = await self.client.fetch_user(reminder['target_id'])

        if who is None:
          # User not found, mark reminder as inactive
          self.db.update_reminder(reminder['id'], {'is_active': False})
          continue

        LOGGER.debug(f"Scheduling reminder {reminder['id']} for {who.id} in channel {channel.id} in {delay} seconds")

        if reminder['is_recurring']:
          self.reminders[reminder['id']] = asyncio.create_task(
            self._schedule_recurring_reminder(
              channel,
              who,
              reminder['message'],
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
              reminder['message'],
              delay,
              reminder['id']
            )
          )
    except Exception as e:
      LOGGER.error(f"Error loading active reminders: {e}")

def setup(bot):
  Remind(bot)