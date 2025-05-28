#!/usr/bin/env python3
"""
Telegram Bot that kicks new group members who don't post a video within 30 seconds.
"""

import os
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Set

from telegram import Update, ChatMember, Message
from telegram.ext import (
    Application, 
    ChatMemberHandler, 
    MessageHandler, 
    CommandHandler,
    filters, 
    ContextTypes
)
from telegram.error import TelegramError, Forbidden, BadRequest

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('telegram_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class VideoKickBot:
    def __init__(self, token: str, timeout_seconds: int = 30):
        """
        Initialize the Video Kick Bot.
        
        Args:
            token: Telegram bot token from BotFather
            timeout_seconds: Time limit for users to post a video (default: 30)
        """
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.application = Application.builder().token(token).build()
        
        # Track new users and their timers
        # Format: {(chat_id, user_id): {'timer': threading.Timer, 'join_time': datetime}}
        self.pending_users: Dict[tuple, Dict] = {}
        self.pending_users_lock = threading.Lock()
        
        # Track users who have posted videos (to avoid multiple kicks)
        self.verified_users: Set[tuple] = set()
        
        # Bot control settings
        self.bot_paused = False
        self.interaction_mode = False  # If True, timer starts on first message, not on join
        self.anti_spam_enabled = True
        self.require_profile_pic = False
        self.banned_words = ['spam', 'promotion', 'advertisement', 'buy now', 'click here']
        
        # Interactive features
        self.custom_welcome = "👋 Welcome {name}! 📹 Post a video within {timer} seconds to stay in the group!"
        self.reward_system_enabled = True
        self.user_points = {}  # Track user rewards
        self.scheduled_mode = False
        self.active_hours = {"start": 8, "end": 22}  # 8 AM to 10 PM
        
        self.stats = {
            'users_kicked': 0,
            'users_verified': 0,
            'total_joins': 0,
            'spam_blocked': 0,
            'links_blocked': 0,
            'suspicious_kicked': 0
        }
        
        self._setup_handlers()
        
    def _setup_handlers(self):
        """Set up message and chat member handlers."""
        # Handle new chat members
        self.application.add_handler(
            ChatMemberHandler(self.handle_chat_member_update, ChatMemberHandler.CHAT_MEMBER)
        )
        
        # Handle video messages
        video_filter = (
            filters.VIDEO | 
            filters.VIDEO_NOTE | 
            filters.Document.VIDEO
        )
        self.application.add_handler(
            MessageHandler(video_filter, self.handle_video_message)
        )
        
        # Handle text messages to send welcome message
        self.application.add_handler(
            MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, self.handle_new_members)
        )
        
        # Add command handlers for bot control
        self.application.add_handler(CommandHandler("settimer", self.set_timer_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("pause", self.pause_command))
        self.application.add_handler(CommandHandler("resume", self.resume_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("interaction", self.interaction_mode_command))
        self.application.add_handler(CommandHandler("antispam", self.antispam_command))
        self.application.add_handler(CommandHandler("report", self.daily_report_command))
        self.application.add_handler(CommandHandler("setwelcome", self.set_welcome_command))
        self.application.add_handler(CommandHandler("rewards", self.rewards_command))
        self.application.add_handler(CommandHandler("schedule", self.schedule_command))
        self.application.add_handler(CommandHandler("leaderboard", self.leaderboard_command))
        
        # Handle all text messages to track interactions and spam
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message)
        )
        
        # Handle all messages for spam detection
        self.application.add_handler(
            MessageHandler(~filters.COMMAND, self.handle_spam_detection)
        )

    async def handle_chat_member_update(self, update: Update, context):
        """Handle chat member updates (joins, leaves, etc.)."""
        try:
            chat_member_update = update.chat_member
            if not chat_member_update:
                return
                
            old_status = chat_member_update.old_chat_member.status
            new_status = chat_member_update.new_chat_member.status
            user = chat_member_update.new_chat_member.user
            chat_id = chat_member_update.chat.id
            
            # Check if user joined the group
            if (old_status in ["left", "kicked"] and 
                new_status in ["member", "administrator", "creator"]):
                
                await self._handle_new_member(chat_id, user.id, user.full_name, context)
                
        except Exception as e:
            logger.error(f"Error handling chat member update: {e}")

    async def handle_new_members(self, update: Update, context):
        """Handle new members status update message."""
        try:
            if not update.message or not update.message.new_chat_members:
                return
                
            chat_id = update.message.chat_id
            
            for user in update.message.new_chat_members:
                if not user.is_bot:  # Don't process bots
                    await self._handle_new_member(chat_id, user.id, user.full_name, context)
                    
        except Exception as e:
            logger.error(f"Error handling new members: {e}")

    async def _handle_new_member(self, chat_id: int, user_id: int, user_name: str, context):
        """Handle a single new member joining."""
        try:
            user_key = (chat_id, user_id)
            
            # Update stats
            self.stats['total_joins'] += 1
            
            # Check if bot is paused
            if self.bot_paused:
                welcome_msg = (
                    f"👋 Welcome {user_name}!\n\n"
                    f"🔴 Bot is currently paused - no video verification required right now.\n"
                    f"Enjoy the group!"
                )
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=welcome_msg,
                        disable_notification=True
                    )
                except Exception as e:
                    logger.warning(f"Could not send paused welcome message: {e}")
                return
            
            # Check if interaction mode is enabled
            if self.interaction_mode:
                # Just send welcome message, timer will start when they send first message
                welcome_msg = (
                    f"👋 Welcome {user_name}!\n\n"
                    f"📹 To stay in this group, please post a video after your first message.\n"
                    f"⏰ Timer will start when you interact with the group!"
                )
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=welcome_msg,
                        disable_notification=True
                    )
                    logger.info(f"New member {user_name} (ID: {user_id}) joined chat {chat_id}. Waiting for interaction.")
                except Exception as e:
                    logger.warning(f"Could not send interaction welcome message: {e}")
                return
            
            with self.pending_users_lock:
                # Check if user is already being tracked
                if user_key in self.pending_users:
                    # Cancel existing timer
                    self.pending_users[user_key]['timer'].cancel()
                
                # Start new timer for this user
                timer = threading.Timer(
                    self.timeout_seconds, 
                    self._kick_user_timeout, 
                    args=[chat_id, user_id, user_name, context]
                )
                
                self.pending_users[user_key] = {
                    'timer': timer,
                    'join_time': datetime.now(),
                    'user_name': user_name
                }
                
                timer.start()
            
            # Send custom welcome message
            welcome_msg = self.custom_welcome.format(
                name=user_name,
                timer=self.timeout_seconds
            )
            
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=welcome_msg,
                    disable_notification=True
                )
                logger.info(f"New member {user_name} (ID: {user_id}) joined chat {chat_id}. Timer started.")
            except Exception as e:
                logger.warning(f"Could not send welcome message: {e}")
                
        except Exception as e:
            logger.error(f"Error handling new member {user_name}: {e}")

    def _kick_user_timeout(self, chat_id: int, user_id: int, user_name: str, context):
        """Kick user after timeout (runs in separate thread)."""
        try:
            user_key = (chat_id, user_id)
            
            with self.pending_users_lock:
                # Check if user is still pending (hasn't posted video)
                if user_key not in self.pending_users:
                    return
                
                # Remove from pending users
                del self.pending_users[user_key]
            
            # Check if user already verified
            if user_key in self.verified_users:
                return
            
            # Use asyncio to run the async kick function
            import asyncio
            
            async def kick_user():
                try:
                    await context.bot.ban_chat_member(
                        chat_id=chat_id,
                        user_id=user_id
                    )
                    
                    # Unban immediately to allow rejoin (kick only)
                    await context.bot.unban_chat_member(
                        chat_id=chat_id,
                        user_id=user_id
                    )
                    
                    # Send notification
                    kick_msg = (
                        f"⚠️ {user_name} was removed for not posting a video within "
                        f"{self.timeout_seconds} seconds."
                    )
                    
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=kick_msg,
                        disable_notification=True
                    )
                    
                    # Update stats
                    self.stats['users_kicked'] += 1
                    
                    logger.info(f"Kicked user {user_name} (ID: {user_id}) from chat {chat_id} for timeout.")
                    
                except Forbidden:
                    logger.error(f"Bot lacks permission to kick user {user_name} in chat {chat_id}")
                except BadRequest as e:
                    logger.error(f"Bad request when kicking user {user_name}: {e}")
                except Exception as e:
                    logger.error(f"Error kicking user {user_name}: {e}")
            
            # Run the async function
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(kick_user())
            loop.close()
            
        except Exception as e:
            logger.error(f"Error in kick timeout for user {user_name}: {e}")

    async def handle_video_message(self, update: Update, context):
        """Handle video messages from users."""
        try:
            if not update.message or not update.message.from_user:
                return
                
            chat_id = update.message.chat_id
            user_id = update.message.from_user.id
            user_name = update.message.from_user.full_name
            user_key = (chat_id, user_id)
            
            with self.pending_users_lock:
                # Check if this user is pending verification
                if user_key in self.pending_users:
                    # Cancel the timer
                    timer_info = self.pending_users[user_key]
                    timer_info['timer'].cancel()
                    
                    # Calculate response time
                    response_time = datetime.now() - timer_info['join_time']
                    response_seconds = response_time.total_seconds()
                    
                    # Remove from pending users
                    del self.pending_users[user_key]
                    
                    # Add to verified users
                    self.verified_users.add(user_key)
                    
                    # Update stats
                    self.stats['users_verified'] += 1
                    
                    # Award points if reward system is enabled
                    points_awarded = 0
                    if self.reward_system_enabled:
                        # Award more points for faster responses
                        if response_seconds <= 10:
                            points_awarded = 100  # Super fast
                        elif response_seconds <= 30:
                            points_awarded = 50   # Fast
                        else:
                            points_awarded = 25   # Regular
                        
                        if user_key not in self.user_points:
                            self.user_points[user_key] = 0
                        self.user_points[user_key] += points_awarded
                    
                    # Send success message with points
                    if points_awarded > 0:
                        success_msg = (
                            f"✅ Great job {user_name}! You posted a video in "
                            f"{response_seconds:.1f} seconds. Welcome to the group! 🎉\n"
                            f"🏆 You earned {points_awarded} points! Total: {self.user_points[user_key]} points"
                        )
                    else:
                        success_msg = (
                            f"✅ Great job {user_name}! You posted a video in "
                            f"{response_seconds:.1f} seconds. Welcome to the group! 🎉"
                        )
                    
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=success_msg,
                        disable_notification=True
                    )
                    
                    logger.info(f"User {user_name} (ID: {user_id}) verified with video in {response_seconds:.1f}s")
                    
        except Exception as e:
            logger.error(f"Error handling video message: {e}")

    async def set_timer_command(self, update: Update, context):
        """Handle /settimer command to change timeout duration."""
        try:
            # Check if user is admin
            chat_id = update.effective_chat.id
            user_id = update.effective_user.id
            
            chat_member = await context.bot.get_chat_member(chat_id, user_id)
            if chat_member.status not in ['administrator', 'creator']:
                await update.message.reply_text("⚠️ Only group admins can change bot settings.")
                return
            
            if not context.args or len(context.args) != 1:
                await update.message.reply_text(
                    "Usage: /settimer <seconds>\n"
                    "Example: /settimer 120 (for 2 minutes)"
                )
                return
            
            try:
                new_timeout = int(context.args[0])
                if new_timeout < 10 or new_timeout > 600:
                    await update.message.reply_text("⚠️ Timer must be between 10 seconds and 10 minutes (600 seconds).")
                    return
                
                self.timeout_seconds = new_timeout
                await update.message.reply_text(f"✅ Timer updated to {new_timeout} seconds!")
                logger.info(f"Timer changed to {new_timeout} seconds by user {user_id}")
                
            except ValueError:
                await update.message.reply_text("⚠️ Please enter a valid number of seconds.")
                
        except Exception as e:
            logger.error(f"Error in set_timer_command: {e}")

    async def status_command(self, update: Update, context):
        """Handle /status command to show bot status."""
        try:
            pending_count = len(self.pending_users)
            verified_count = len(self.verified_users)
            
            status_msg = (
                f"🤖 **Video Kick Bot Status**\n\n"
                f"⏱️ Timer: {self.timeout_seconds} seconds\n"
                f"▶️ Status: {'Paused' if self.bot_paused else 'Active'}\n"
                f"👥 Pending verification: {pending_count}\n"
                f"✅ Verified members: {verified_count}\n\n"
                f"📊 **Statistics**\n"
                f"• Total joins: {self.stats['total_joins']}\n"
                f"• Users verified: {self.stats['users_verified']}\n"
                f"• Users kicked: {self.stats['users_kicked']}"
            )
            
            await update.message.reply_text(status_msg, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in status_command: {e}")

    async def help_command(self, update: Update, context):
        """Handle /help command to show available commands."""
        try:
            help_msg = "🎮 Video Kick Bot Commands:\n\n"
            help_msg += "📊 Basic Controls:\n"
            help_msg += "/help - Show commands\n"
            help_msg += "/status - Bot status\n"
            help_msg += "/settimer 300 - Change timer\n"
            help_msg += "/pause - Stop kicking\n"
            help_msg += "/resume - Start kicking\n\n"
            help_msg += "🛡️ Protection Features:\n"
            help_msg += "/antispam - Toggle spam protection\n"
            help_msg += "/interaction - Toggle interaction mode\n"
            help_msg += "/stats - Show statistics\n"
            help_msg += "/report - Daily protection report\n\n"
            help_msg += "🎉 Interactive Features:\n"
            help_msg += "/setwelcome - Custom welcome message\n"
            help_msg += "/rewards - Toggle point system\n"
            help_msg += "/leaderboard - Top video posters\n"
            help_msg += "/schedule - Set active hours\n\n"
            help_msg += f"⚙️ Current Settings:\n"
            help_msg += f"Timer: {self.timeout_seconds}s | "
            help_msg += f"Interaction: {'ON' if self.interaction_mode else 'OFF'} | "
            help_msg += f"Anti-spam: {'ON' if self.anti_spam_enabled else 'OFF'}\n"
            help_msg += f"Rewards: {'ON' if self.reward_system_enabled else 'OFF'} | "
            help_msg += f"Schedule: {'ON' if self.scheduled_mode else 'OFF'}"
            
            await update.message.reply_text(help_msg)
            
        except Exception as e:
            logger.error(f"Error in help_command: {e}")

    async def pause_command(self, update: Update, context):
        """Handle /pause command to pause the bot."""
        try:
            # Check if user is admin
            chat_id = update.effective_chat.id
            user_id = update.effective_user.id
            
            chat_member = await context.bot.get_chat_member(chat_id, user_id)
            if chat_member.status not in ['administrator', 'creator']:
                await update.message.reply_text("⚠️ Only group admins can pause the bot.")
                return
            
            self.bot_paused = True
            await update.message.reply_text("⏸️ Bot paused! New members won't be kicked until you use /resume")
            logger.info(f"Bot paused by user {user_id}")
            
        except Exception as e:
            logger.error(f"Error in pause_command: {e}")

    async def resume_command(self, update: Update, context):
        """Handle /resume command to resume the bot."""
        try:
            # Check if user is admin
            chat_id = update.effective_chat.id
            user_id = update.effective_user.id
            
            chat_member = await context.bot.get_chat_member(chat_id, user_id)
            if chat_member.status not in ['administrator', 'creator']:
                await update.message.reply_text("⚠️ Only group admins can resume the bot.")
                return
            
            self.bot_paused = False
            await update.message.reply_text("▶️ Bot resumed! Video verification is now active.")
            logger.info(f"Bot resumed by user {user_id}")
            
        except Exception as e:
            logger.error(f"Error in resume_command: {e}")

    async def stats_command(self, update: Update, context):
        """Handle /stats command to show detailed statistics."""
        try:
            uptime = datetime.now() - datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            stats_msg = (
                f"📊 **Detailed Bot Statistics**\n\n"
                f"⏱️ Current timer: {self.timeout_seconds} seconds\n"
                f"📈 Success rate: {(self.stats['users_verified'] / max(self.stats['total_joins'], 1) * 100):.1f}%\n\n"
                f"**Today's Activity:**\n"
                f"👥 Total joins: {self.stats['total_joins']}\n"
                f"✅ Users verified: {self.stats['users_verified']}\n"
                f"❌ Users kicked: {self.stats['users_kicked']}\n"
                f"🛡️ Spam blocked: {self.stats['spam_blocked']}\n"
                f"🔗 Links blocked: {self.stats['links_blocked']}\n"
                f"⚠️ Suspicious kicked: {self.stats['suspicious_kicked']}\n"
                f"⏳ Currently pending: {len(self.pending_users)}\n\n"
                f"**Settings:**\n"
                f"Status: {'🔴 Paused' if self.bot_paused else '🟢 Active'}\n"
                f"Anti-spam: {'🟢 ON' if self.anti_spam_enabled else '🔴 OFF'}\n"
                f"Timer: {self.timeout_seconds}s ({self.timeout_seconds//60}min {self.timeout_seconds%60}s)"
            )
            
            await update.message.reply_text(stats_msg, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in stats_command: {e}")

    async def interaction_mode_command(self, update: Update, context):
        """Handle /interaction command to toggle interaction mode."""
        try:
            # Check if user is admin
            chat_id = update.effective_chat.id
            user_id = update.effective_user.id
            
            chat_member = await context.bot.get_chat_member(chat_id, user_id)
            if chat_member.status not in ['administrator', 'creator']:
                await update.message.reply_text("⚠️ Only group admins can change bot settings.")
                return
            
            # Toggle interaction mode
            self.interaction_mode = not self.interaction_mode
            
            if self.interaction_mode:
                msg = "🔄 Interaction mode ON! Timer now starts when users send their first message (better for offline users)"
            else:
                msg = "⏰ Interaction mode OFF! Timer starts immediately when users join (default behavior)"
            
            await update.message.reply_text(msg)
            logger.info(f"Interaction mode {'enabled' if self.interaction_mode else 'disabled'} by user {user_id}")
            
        except Exception as e:
            logger.error(f"Error in interaction_mode_command: {e}")

    async def antispam_command(self, update: Update, context):
        """Handle /antispam command to toggle anti-spam protection."""
        try:
            # Check if user is admin
            chat_id = update.effective_chat.id
            user_id = update.effective_user.id
            
            chat_member = await context.bot.get_chat_member(chat_id, user_id)
            if chat_member.status not in ['administrator', 'creator']:
                await update.message.reply_text("⚠️ Only group admins can change bot settings.")
                return
            
            # Toggle anti-spam mode
            self.anti_spam_enabled = not self.anti_spam_enabled
            
            if self.anti_spam_enabled:
                msg = "🛡️ Anti-spam protection ON! Now blocking links, banned words, and suspicious users"
            else:
                msg = "⚠️ Anti-spam protection OFF! Only video verification is active"
            
            await update.message.reply_text(msg)
            logger.info(f"Anti-spam {'enabled' if self.anti_spam_enabled else 'disabled'} by user {user_id}")
            
        except Exception as e:
            logger.error(f"Error in antispam_command: {e}")

    async def daily_report_command(self, update: Update, context):
        """Handle /report command to show daily summary."""
        try:
            total_actions = (self.stats['users_kicked'] + self.stats['spam_blocked'] + 
                           self.stats['links_blocked'] + self.stats['suspicious_kicked'])
            
            report_msg = f"""📈 Daily Protection Report

🛡️ Total Protection Actions: {total_actions}
👥 New Members: {self.stats['total_joins']}
✅ Verified: {self.stats['users_verified']}
❌ Kicked (no video): {self.stats['users_kicked']}
🚫 Spam blocked: {self.stats['spam_blocked']}
🔗 Links blocked: {self.stats['links_blocked']}
⚠️ Suspicious users: {self.stats['suspicious_kicked']}

📊 Success Rate: {(self.stats['users_verified'] / max(self.stats['total_joins'], 1) * 100):.1f}%
🔒 Protection Rate: {(total_actions / max(self.stats['total_joins'], 1) * 100):.1f}%

Settings:
Timer: {self.timeout_seconds}s
Anti-spam: {'ON' if self.anti_spam_enabled else 'OFF'}
Status: {'Active' if not self.bot_paused else 'Paused'}"""
            
            await update.message.reply_text(report_msg)
            
        except Exception as e:
            logger.error(f"Error in daily_report_command: {e}")

    async def set_welcome_command(self, update: Update, context):
        """Handle /setwelcome command to customize welcome message."""
        try:
            # Check if user is admin
            chat_id = update.effective_chat.id
            user_id = update.effective_user.id
            
            chat_member = await context.bot.get_chat_member(chat_id, user_id)
            if chat_member.status not in ['administrator', 'creator']:
                await update.message.reply_text("⚠️ Only group admins can change bot settings.")
                return
            
            if not context.args:
                current_msg = self.custom_welcome.replace("{name}", "[NAME]").replace("{timer}", "[TIMER]")
                await update.message.reply_text(f"Current welcome message:\n\n{current_msg}\n\nUse: /setwelcome Your custom message here\nUse {{name}} for user name and {{timer}} for timer seconds")
                return
            
            # Set new welcome message
            new_welcome = " ".join(context.args)
            self.custom_welcome = new_welcome
            
            preview = new_welcome.replace("{name}", "John").replace("{timer}", str(self.timeout_seconds))
            await update.message.reply_text(f"✅ Welcome message updated!\n\nPreview:\n{preview}")
            logger.info(f"Welcome message changed by user {user_id}")
            
        except Exception as e:
            logger.error(f"Error in set_welcome_command: {e}")

    async def rewards_command(self, update: Update, context):
        """Handle /rewards command to toggle reward system."""
        try:
            # Check if user is admin
            chat_id = update.effective_chat.id
            user_id = update.effective_user.id
            
            chat_member = await context.bot.get_chat_member(chat_id, user_id)
            if chat_member.status not in ['administrator', 'creator']:
                await update.message.reply_text("⚠️ Only group admins can change bot settings.")
                return
            
            # Toggle reward system
            self.reward_system_enabled = not self.reward_system_enabled
            
            if self.reward_system_enabled:
                msg = "🏆 Reward system ON! Users earn points for posting videos quickly:\n• 10s or less: 100 points\n• 30s or less: 50 points\n• Regular: 25 points"
            else:
                msg = "📝 Reward system OFF! No points will be awarded for videos"
            
            await update.message.reply_text(msg)
            logger.info(f"Reward system {'enabled' if self.reward_system_enabled else 'disabled'} by user {user_id}")
            
        except Exception as e:
            logger.error(f"Error in rewards_command: {e}")

    async def leaderboard_command(self, update: Update, context):
        """Handle /leaderboard command to show top users."""
        try:
            if not self.user_points:
                await update.message.reply_text("🏆 No points awarded yet! Reward system may be disabled.")
                return
            
            # Sort users by points
            sorted_users = sorted(self.user_points.items(), key=lambda x: x[1], reverse=True)
            
            leaderboard_msg = "🏆 Group Leaderboard - Top Video Posters:\n\n"
            
            for i, (user_key, points) in enumerate(sorted_users[:10], 1):
                chat_id, user_id = user_key
                if i == 1:
                    emoji = "🥇"
                elif i == 2:
                    emoji = "🥈"
                elif i == 3:
                    emoji = "🥉"
                else:
                    emoji = f"{i}."
                
                # Try to get user info from verified users
                leaderboard_msg += f"{emoji} User {user_id}: {points} points\n"
            
            await update.message.reply_text(leaderboard_msg)
            
        except Exception as e:
            logger.error(f"Error in leaderboard_command: {e}")

    async def schedule_command(self, update: Update, context):
        """Handle /schedule command to set active hours."""
        try:
            # Check if user is admin
            chat_id = update.effective_chat.id
            user_id = update.effective_user.id
            
            chat_member = await context.bot.get_chat_member(chat_id, user_id)
            if chat_member.status not in ['administrator', 'creator']:
                await update.message.reply_text("⚠️ Only group admins can change bot settings.")
                return
            
            if not context.args:
                current_status = f"Scheduled mode: {'ON' if self.scheduled_mode else 'OFF'}"
                current_hours = f"Active hours: {self.active_hours['start']}:00 - {self.active_hours['end']}:00"
                await update.message.reply_text(f"{current_status}\n{current_hours}\n\nUsage:\n/schedule toggle - Enable/disable\n/schedule 8 22 - Set hours (8 AM to 10 PM)")
                return
            
            if context.args[0].lower() == "toggle":
                self.scheduled_mode = not self.scheduled_mode
                msg = f"⏰ Scheduled mode {'ON' if self.scheduled_mode else 'OFF'}! "
                if self.scheduled_mode:
                    msg += f"Bot only active {self.active_hours['start']}:00-{self.active_hours['end']}:00"
                await update.message.reply_text(msg)
            elif len(context.args) == 2:
                try:
                    start_hour = int(context.args[0])
                    end_hour = int(context.args[1])
                    if 0 <= start_hour <= 23 and 0 <= end_hour <= 23:
                        self.active_hours = {"start": start_hour, "end": end_hour}
                        await update.message.reply_text(f"✅ Active hours set to {start_hour}:00 - {end_hour}:00")
                    else:
                        await update.message.reply_text("⚠️ Hours must be between 0-23")
                except ValueError:
                    await update.message.reply_text("⚠️ Please provide valid hour numbers")
            
            logger.info(f"Schedule settings changed by user {user_id}")
            
        except Exception as e:
            logger.error(f"Error in schedule_command: {e}")

    async def handle_text_message(self, update: Update, context):
        """Handle text messages to start timer in interaction mode."""
        try:
            if not self.interaction_mode or self.bot_paused:
                return
                
            chat_id = update.message.chat_id
            user_id = update.message.from_user.id
            user_name = update.message.from_user.full_name
            user_key = (chat_id, user_id)
            
            # Check if this user is new and not yet being tracked
            if user_key not in self.pending_users and user_key not in self.verified_users:
                # Start timer for this user since they just interacted
                with self.pending_users_lock:
                    timer = threading.Timer(
                        self.timeout_seconds, 
                        self._kick_user_timeout, 
                        args=[chat_id, user_id, user_name, context]
                    )
                    
                    self.pending_users[user_key] = {
                        'timer': timer,
                        'join_time': datetime.now(),
                        'user_name': user_name
                    }
                    
                    timer.start()
                
                # Send reminder message
                reminder_msg = (
                    f"⏰ Hi {user_name}! You have {self.timeout_seconds} seconds to post a video to stay in the group!"
                )
                
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=reminder_msg,
                        disable_notification=True
                    )
                    logger.info(f"Started timer for {user_name} (ID: {user_id}) after first message in chat {chat_id}")
                except Exception as e:
                    logger.warning(f"Could not send interaction timer message: {e}")
                    
        except Exception as e:
            logger.error(f"Error handling text message: {e}")

    async def handle_spam_detection(self, update: Update, context):
        """Handle spam detection for all messages."""
        try:
            if not self.anti_spam_enabled or self.bot_paused:
                return
                
            message = update.message
            if not message or not message.from_user:
                return
                
            user_id = message.from_user.id
            user_name = message.from_user.full_name
            chat_id = message.chat_id
            user_key = (chat_id, user_id)
            
            # Skip if user is already verified
            if user_key in self.verified_users:
                return
                
            # Check for links from new users
            if message.text and any(link in message.text.lower() for link in ['http', 'www.', '.com', '.org', 't.me']):
                await self._handle_spam_violation(message, context, "posting links", "links_blocked")
                return
                
            # Check for banned words
            if message.text:
                text_lower = message.text.lower()
                for banned_word in self.banned_words:
                    if banned_word in text_lower:
                        await self._handle_spam_violation(message, context, f"using banned word: {banned_word}", "spam_blocked")
                        return
                        
            # Check for suspicious usernames
            if self._is_suspicious_username(message.from_user):
                await self._handle_spam_violation(message, context, "suspicious username", "suspicious_kicked")
                return
                
        except Exception as e:
            logger.error(f"Error in spam detection: {e}")

    def _is_suspicious_username(self, user) -> bool:
        """Check if username appears suspicious."""
        username = user.username or ""
        full_name = user.full_name or ""
        
        # Check for common spam patterns
        suspicious_patterns = [
            'crypto', 'bitcoin', 'forex', 'investment', 'profit', 'earn',
            'casino', 'betting', 'loan', 'pharmacy', 'pills'
        ]
        
        combined_text = (username + " " + full_name).lower()
        return any(pattern in combined_text for pattern in suspicious_patterns)

    async def _handle_spam_violation(self, message, context, reason: str, stat_key: str):
        """Handle spam violations by deleting message and potentially kicking user."""
        try:
            user_name = message.from_user.full_name
            user_id = message.from_user.id
            chat_id = message.chat_id
            
            # Delete the spam message
            await context.bot.delete_message(chat_id=chat_id, message_id=message.message_id)
            
            # Update stats
            self.stats[stat_key] += 1
            
            # Kick the user
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
            
            # Send notification
            warning_msg = f"⚠️ {user_name} was removed for {reason}"
            await context.bot.send_message(
                chat_id=chat_id,
                text=warning_msg,
                disable_notification=True
            )
            
            logger.info(f"Kicked user {user_name} (ID: {user_id}) for {reason}")
            
        except Exception as e:
            logger.error(f"Error handling spam violation: {e}")

    def load_config(self, config_file: str = "config.json") -> dict:
        """Load configuration from JSON file."""
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file {config_file} not found. Using defaults.")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing config file: {e}")
            return {}

    def run(self):
        """Start the bot."""
        logger.info("Starting Video Kick Bot...")
        logger.info(f"Timeout setting: {self.timeout_seconds} seconds")
        
        try:
            self.application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
        except Exception as e:
            logger.error(f"Error running bot: {e}")
            raise

def main():
    """Main function to start the bot."""
    # Load configuration
    config = {}
    try:
        with open("config.json", 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        logger.info("Config file not found, using environment variables and defaults.")
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing config file: {e}")
    
    # Get bot token from environment variable or config
    token = os.getenv("TELEGRAM_BOT_TOKEN", config.get("bot_token", ""))
    
    if not token:
        logger.error("No bot token provided! Set TELEGRAM_BOT_TOKEN environment variable or add to config.json")
        return
    
    # Get timeout from config (default 30 seconds)
    timeout_seconds = config.get("timeout_seconds", 30)
    
    # Create and run bot
    bot = VideoKickBot(token, timeout_seconds)
    
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}")

if __name__ == "__main__":
    main()
