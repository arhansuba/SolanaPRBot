import discord
from discord.ext import commands
import logging
from typing import Optional
from datetime import datetime

from ai.groq_client import GroqClient
from github.client import GitHubClient
from blockchain.crossmint.wallet import WalletManager
from blockchain.jupiter.swaps import SwapManager

logger = logging.getLogger(__name__)

class EventHandler:
    def __init__(
        self,
        bot: commands.Bot,
        ai_client: GroqClient,
        github_client: GitHubClient,
        wallet_manager: WalletManager,
        swap_manager: SwapManager
    ):
        self.bot = bot
        self.ai_client = ai_client
        self.github_client = github_client
        self.wallet_manager = wallet_manager
        self.swap_manager = swap_manager
        
        # Track guild statistics
        self.guild_stats = {}
        
        # Set up event handlers
        self.setup_events()

    def setup_events(self):
        """Set up all event handlers."""
        
        @self.bot.event
        async def on_ready():
            """Handle bot ready event."""
            try:
                logger.info(f"Bot is ready. Logged in as {self.bot.user.name} ({self.bot.user.id})")
                
                # Update presence
                await self.bot.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.watching,
                        name="GitHub PRs"
                    )
                )
                
                # Initialize guild statistics
                for guild in self.bot.guilds:
                    await self._initialize_guild_stats(guild)
                    
            except Exception as e:
                logger.error(f"Error in on_ready: {str(e)}")

        @self.bot.event
        async def on_guild_join(guild: discord.Guild):
            """Handle bot joining a new server."""
            try:
                logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")
                
                # Initialize guild statistics
                await self._initialize_guild_stats(guild)
                
                # Send welcome message
                welcome_channel = self._get_welcome_channel(guild)
                if welcome_channel:
                    await welcome_channel.send(
                        "👋 Hello! I'm GitHub DAO Bot. I help manage GitHub repositories "
                        "and handle DAO governance. Use `/help` to see available commands!"
                    )
                    
            except Exception as e:
                logger.error(f"Error in on_guild_join: {str(e)}")

        @self.bot.event
        async def on_message(message: discord.Message):
            """Handle incoming messages."""
            try:
                # Ignore bot messages
                if message.author.bot:
                    return

                # Process commands first
                await self.bot.process_commands(message)
                
                # Handle bot mentions
                if self.bot.user in message.mentions:
                    await self._handle_mention(message)
                    
                # Update statistics
                if message.guild:
                    self._update_guild_stats(message.guild.id, "messages")
                    
            except Exception as e:
                logger.error(f"Error in on_message: {str(e)}")

        @self.bot.event
        async def on_command_error(ctx: commands.Context, error: Exception):
            """Handle command errors."""
            try:
                if isinstance(error, commands.CommandNotFound):
                    await ctx.send(
                        "Command not found. Use `/help` to see available commands."
                    )
                    
                elif isinstance(error, commands.MissingPermissions):
                    await ctx.send(
                        "You don't have permission to use this command."
                    )
                    
                elif isinstance(error, commands.CheckFailure):
                    await ctx.send(
                        "You don't meet the requirements to use this command."
                    )
                    
                else:
                    logger.error(f"Command error in {ctx.command}: {str(error)}")
                    await ctx.send(
                        "An error occurred while processing your command. "
                        "Please try again later."
                    )
                    
            except Exception as e:
                logger.error(f"Error in on_command_error: {str(e)}")

        @self.bot.event
        async def on_member_join(member: discord.Member):
            """Handle new member joins."""
            try:
                logger.info(f"New member joined: {member.name} (Guild: {member.guild.name})")
                
                # Update statistics
                self._update_guild_stats(member.guild.id, "members")
                
                # Send welcome message
                welcome_channel = self._get_welcome_channel(member.guild)
                if welcome_channel:
                    await welcome_channel.send(
                        f"Welcome {member.mention} to {member.guild.name}! "
                        f"Use `/help` to see what I can do."
                    )
                    
            except Exception as e:
                logger.error(f"Error in on_member_join: {str(e)}")

        @self.bot.event
        async def on_reaction_add(reaction: discord.Reaction, user: discord.User):
            """Handle reaction additions."""
            try:
                if user.bot:
                    return
                    
                # Handle governance vote reactions
                if reaction.message.channel.name == "governance":
                    await self._handle_governance_reaction(reaction, user)
                    
            except Exception as e:
                logger.error(f"Error in on_reaction_add: {str(e)}")

    async def _initialize_guild_stats(self, guild: discord.Guild):
        """Initialize statistics for a guild."""
        self.guild_stats[guild.id] = {
            "joined_at": datetime.now(),
            "member_count": guild.member_count,
            "message_count": 0,
            "command_usage": {},
            "last_activity": datetime.now()
        }

    def _update_guild_stats(self, guild_id: int, stat_type: str):
        """Update guild statistics."""
        if guild_id in self.guild_stats:
            if stat_type == "messages":
                self.guild_stats[guild_id]["message_count"] += 1
            elif stat_type == "members":
                self.guild_stats[guild_id]["member_count"] += 1
            
            self.guild_stats[guild_id]["last_activity"] = datetime.now()

    async def _handle_mention(self, message: discord.Message):
        """Handle when the bot is mentioned."""
        try:
            # Generate response using AI
            response = await self.ai_client.analyze_message(message.content)
            
            await message.reply(
                f"Hi {message.author.mention}! {response}\n"
                f"Use `/help` to see what I can do!"
            )
            
        except Exception as e:
            logger.error(f"Error handling mention: {str(e)}")
            await message.reply(
                "Sorry, I couldn't process that mention. Please try using a command instead!"
            )

    async def _handle_governance_reaction(
        self,
        reaction: discord.Reaction,
        user: discord.User
    ):
        """Handle reactions in governance channel."""
        try:
            # Check if reaction is on a proposal message
            if "Proposal #" in reaction.message.content:
                # Record vote
                vote_type = str(reaction.emoji)
                await self._record_vote(
                    user.id,
                    reaction.message.id,
                    vote_type
                )
                
        except Exception as e:
            logger.error(f"Error handling governance reaction: {str(e)}")

    def _get_welcome_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Get appropriate welcome channel for a guild."""
        # Try to find a welcome channel
        welcome_channels = ["welcome", "general", "lobby"]
        
        for channel_name in welcome_channels:
            channel = discord.utils.get(
                guild.text_channels,
                name=channel_name
            )
            if channel:
                return channel
        
        # Fall back to first text channel
        return guild.text_channels[0] if guild.text_channels else None

    async def _record_vote(self, user_id: int, proposal_id: int, vote_type: str):
        """Record a governance vote."""
        try:
            # Check if user has voting power
            wallet = await self.wallet_manager.get_wallet(str(user_id))
            
            if not wallet or wallet.balance <= 0:
                logger.warning(f"User {user_id} attempted to vote without tokens")
                return
            
            # Record vote with voting power
            logger.info(
                f"Recorded vote from {user_id} on proposal {proposal_id}: {vote_type}"
            )
            
        except Exception as e:
            logger.error(f"Error recording vote: {str(e)}")

# Example usage
if __name__ == "__main__":
    async def main():
        # Initialize bot and clients
        bot = commands.Bot(command_prefix="/")
        groq_client = GroqClient(api_key="your-key")
        github_client = GitHubClient(token="your-token")
        wallet_manager = WalletManager(api_key="your-key")
        swap_manager = SwapManager(api_key="your-key")
        
        # Initialize event handler
        event_handler = EventHandler(
            bot=bot,
            ai_client=groq_client,
            github_client=github_client,
            wallet_manager=wallet_manager,
            swap_manager=swap_manager
        )
        
        # Start bot
        await bot.start("your-token")

    import asyncio
    asyncio.run(main())
