import discord
from discord.ext import commands
import logging
from typing import Optional, Dict, Any
import asyncio
from datetime import datetime

from ai.groq_client import GroqClient
from github.client import GitHubClient
from blockchain.crossmint.wallet import WalletManager
from blockchain.jupiter.swaps import SwapManager

logger = logging.getLogger(__name__)

class BotState:
    """Manages the bot's state and active sessions."""
    def __init__(self):
        self.active_analyses: Dict[int, datetime] = {}  # channel_id -> last_analysis_time
        self.user_sessions: Dict[int, Dict[str, Any]] = {}  # user_id -> session_data
        self.guild_settings: Dict[int, Dict[str, Any]] = {}  # guild_id -> settings
        
    def get_user_session(self, user_id: int) -> Dict[str, Any]:
        """Get or create a user session."""
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = {
                'last_command': None,
                'command_count': 0,
                'premium_status': False
            }
        return self.user_sessions[user_id]

    def update_analysis_time(self, channel_id: int):
        """Update the last analysis time for a channel."""
        self.active_analyses[channel_id] = datetime.now()

    def can_analyze(self, channel_id: int) -> bool:
        """Check if enough time has passed for a new analysis."""
        if channel_id not in self.active_analyses:
            return True
        time_diff = datetime.now() - self.active_analyses[channel_id]
        return time_diff.seconds >= 60  # Rate limit: 1 minute

class DiscordClient(commands.Bot):
    def __init__(
        self,
        token: str,
        command_prefix: str,
        ai_client: GroqClient,
        github_client: GitHubClient,
        wallet_manager: WalletManager,
        swap_manager: SwapManager,
    ):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(command_prefix=command_prefix, intents=intents)
        
        self.token = token
        self.ai_client = ai_client
        self.github_client = github_client
        self.wallet_manager = wallet_manager
        self.swap_manager = swap_manager
        self.state = BotState()
        
        # Register commands and events
        self.setup_commands()
        self.setup_events()

    def setup_commands(self):
        """Register bot commands."""
        
        @self.command(name='analyze')
        async def analyze_code(ctx, *, code: str):
            """Analyze code using AI."""
            if not self.state.can_analyze(ctx.channel.id):
                await ctx.send("Please wait a moment before requesting another analysis.")
                return
            
            try:
                analysis = await self.ai_client.analyze_code(code)
                self.state.update_analysis_time(ctx.channel.id)
                await ctx.send(f"Analysis results:\n```{analysis}```")
            except Exception as e:
                logger.error(f"Error analyzing code: {e}")
                await ctx.send("Sorry, I encountered an error while analyzing the code.")

        @self.command(name='pr')
        async def analyze_pr(ctx, pr_url: str):
            """Analyze a GitHub pull request."""
            try:
                pr_data = await self.github_client.get_pr(pr_url)
                analysis = await self.ai_client.analyze_pr(pr_data)
                await ctx.send(f"Pull request analysis:\n```{analysis}```")
            except Exception as e:
                logger.error(f"Error analyzing PR: {e}")
                await ctx.send("Sorry, I couldn't analyze that pull request.")

        @self.command(name='wallet')
        async def wallet_info(ctx):
            """Get wallet information."""
            try:
                user_session = self.state.get_user_session(ctx.author.id)
                wallet = await self.wallet_manager.get_or_create_wallet(ctx.author.id)
                await ctx.send(f"Wallet address: `{wallet.address}`\nBalance: {wallet.balance}")
            except Exception as e:
                logger.error(f"Error getting wallet info: {e}")
                await ctx.send("Sorry, I couldn't retrieve your wallet information.")

    def setup_events(self):
        """Set up event handlers."""

        @self.event
        async def on_ready():
            """Called when the bot is ready."""
            logger.info(f'Bot is ready. Logged in as {self.user.name} ({self.user.id})')
            await self.change_presence(activity=discord.Game(name="Analyzing Code"))

        @self.event
        async def on_guild_join(guild):
            """Called when the bot joins a new server."""
            logger.info(f'Joined new guild: {guild.name} ({guild.id})')
            self.state.guild_settings[guild.id] = {
                'welcome_channel': None,
                'admin_role': None
            }

        @self.event
        async def on_command_completion(ctx):
            """Called when a command completes successfully."""
            user_session = self.state.get_user_session(ctx.author.id)
            user_session['last_command'] = ctx.command.name
            user_session['command_count'] += 1

        @self.event
        async def on_message(message):
            """Called for every message."""
            if message.author.bot:
                return
            
            # Process commands
            await self.process_commands(message)
            
            # Additional message handling
            if self.user.mentioned_in(message):
                await message.channel.send(
                    "Hi! Use !help to see available commands."
                )

    async def start_bot(self):
        """Start the bot with error handling."""
        try:
            await self.start(self.token)
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise

    async def cleanup(self):
        """Cleanup bot resources."""
        try:
            await self.close()
            logger.info("Bot shutdown complete")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            raise

# Example usage
if __name__ == "__main__":
    # This would be handled by main.py in production
    async def run_bot():
        # Initialize dependencies (mock objects for example)
        bot = DiscordClient(
            token="your_token",
            command_prefix="!",
            ai_client=None,  # Mock objects
            github_client=None,
            wallet_manager=None,
            swap_manager=None
        )
        
        try:
            await bot.start_bot()
        except KeyboardInterrupt:
            await bot.cleanup()

    asyncio.run(run_bot())