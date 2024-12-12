import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands

from config import AppConfig
from bot.discord_client import DiscordClient
from ai.groq_client import GroqClient
from github.client import GitHubClient
from blockchain.crossmint.wallet import WalletManager
from blockchain.jupiter.swaps import SwapManager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

class GithubDAOBot:
    def __init__(self):
        self.config: Optional[AppConfig] = None
        self.discord_client: Optional[DiscordClient] = None
        self.groq_client: Optional[GroqClient] = None
        self.github_client: Optional[GitHubClient] = None
        self.wallet_manager: Optional[WalletManager] = None
        self.swap_manager: Optional[SwapManager] = None

    async def initialize(self):
        """Initialize all components of the application."""
        try:
            # Load configuration
            logger.info("Loading configuration...")
            self.config = AppConfig.load()

            # Initialize AI client
            logger.info("Initializing AI client...")
            self.groq_client = GroqClient(
                api_key=self.config.ai.groq_api_key,
                model_name=self.config.ai.model_name
            )

            # Initialize GitHub client
            logger.info("Initializing GitHub client...")
            self.github_client = GitHubClient(
                token=self.config.github.token,
                api_url=self.config.github.api_url
            )

            # Initialize blockchain components
            logger.info("Initializing blockchain components...")
            self.wallet_manager = WalletManager(
                api_key=self.config.blockchain.crossmint_api_key,
                network=self.config.blockchain.network
            )
            self.swap_manager = SwapManager(
                api_key=self.config.blockchain.jupiter_api_key,
                rpc_url=self.config.blockchain.rpc_url
            )

            # Initialize Discord client
            logger.info("Initializing Discord client...")
            self.discord_client = DiscordClient(
                token=self.config.discord.token,
                command_prefix=self.config.discord.command_prefix,
                ai_client=self.groq_client,
                github_client=self.github_client,
                wallet_manager=self.wallet_manager,
                swap_manager=self.swap_manager
            )

            # Set up error handlers
            self.setup_error_handlers()

            logger.info("All components initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize application: {str(e)}")
            raise

    def setup_error_handlers(self):
        """Set up global error handlers."""
        @self.discord_client.event
        async def on_error(event, *args, **kwargs):
            logger.error(f"Error in {event}: {sys.exc_info()}")

        @self.discord_client.event
        async def on_command_error(ctx, error):
            if isinstance(error, commands.CommandNotFound):
                await ctx.send("Command not found. Use !help to see available commands.")
            elif isinstance(error, commands.MissingPermissions):
                await ctx.send("You don't have permission to use this command.")
            else:
                logger.error(f"Command error: {str(error)}")
                await ctx.send(f"An error occurred: {str(error)}")

    async def start(self):
        """Start the Discord bot and related services."""
        try:
            logger.info("Starting bot services...")
            await self.discord_client.start(self.config.discord.token)
        except Exception as e:
            logger.error(f"Failed to start bot: {str(e)}")
            raise

    async def cleanup(self):
        """Clean up resources before shutdown."""
        try:
            if self.discord_client:
                await self.discord_client.close()
            # Add any other cleanup needed
            logger.info("Cleanup completed successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            raise

async def main():
    """Main entry point of the application."""
    bot = GithubDAOBot()
    
    try:
        # Initialize components
        await bot.initialize()

        # Start the bot
        await bot.start()

    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
    finally:
        # Ensure proper cleanup
        await bot.cleanup()

if __name__ == "__main__":
    try:
        # Run the main application
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application shutdown complete")
    except Exception as e:
        logger.critical(f"Application crashed: {str(e)}")
        sys.exit(1)