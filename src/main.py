import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands

# Import Config
from config import AppConfig

# Import AI Components
from ai.groq_client import GroqClient
from ai.code_analyzer import CodeAnalyzer
from ai.doc_generator import DocGenerator

# Import Bot Components
from bot.discord_client import DiscordClient
from bot.commands import register_commands
from bot.events import register_events

# Import Blockchain Components
from blockchain.crossmint.wallet import WalletManager
from blockchain.jupiter.swaps import SwapManager

# Import DAO Components
from dao.governance import GovernanceManager
from dao.token import TokenManager

# Import GitHub Client
from github import GitHubClient

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
        # Config
        self.config: Optional[AppConfig] = None
        
        # AI Components
        self.groq_client: Optional[GroqClient] = None
        self.code_analyzer: Optional[CodeAnalyzer] = None
        self.doc_generator: Optional[DocGenerator] = None
        
        # Bot Components
        self.discord_client: Optional[DiscordClient] = None
        
        # GitHub Client
        self.github_client: Optional[GitHubClient] = None
        
        # Blockchain Components
        self.wallet_manager: Optional[WalletManager] = None
        self.swap_manager: Optional[SwapManager] = None
        
        # DAO Components
        self.governance_manager: Optional[GovernanceManager] = None
        self.token_manager: Optional[TokenManager] = None

    async def initialize(self):
        """Initialize all components of the application."""
        try:
            # Load configuration
            logger.info("Loading configuration...")
            self.config = AppConfig.load()

            # Initialize AI components
            logger.info("Initializing AI components...")
            self.groq_client = GroqClient(
                api_key=self.config.ai.groq_api_key,
                model_name=self.config.ai.model_name
            )
            self.code_analyzer = CodeAnalyzer(self.groq_client)
            self.doc_generator = DocGenerator(self.groq_client)

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

            # Initialize DAO components
            logger.info("Initializing DAO components...")
            self.governance_manager = GovernanceManager(
                wallet_manager=self.wallet_manager,
                config=self.config.dao
            )
            self.token_manager = TokenManager(
                wallet_manager=self.wallet_manager,
                config=self.config.dao
            )

            # Initialize Discord client
            logger.info("Initializing Discord client...")
            self.discord_client = DiscordClient(
                token=self.config.discord.token,
                command_prefix=self.config.discord.command_prefix,
                ai_client=self.groq_client,
                code_analyzer=self.code_analyzer,
                doc_generator=self.doc_generator,
                github_client=self.github_client,
                wallet_manager=self.wallet_manager,
                swap_manager=self.swap_manager,
                governance_manager=self.governance_manager,
                token_manager=self.token_manager
            )

            # Register commands and events
            register_commands(self.discord_client)
            register_events(self.discord_client)

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
            # Cleanup Discord client
            if self.discord_client:
                await self.discord_client.close()
            
            # Cleanup blockchain components
            if self.wallet_manager:
                await self.wallet_manager.cleanup()
            if self.swap_manager:
                await self.swap_manager.cleanup()
            
            # Cleanup AI components
            if self.groq_client:
                await self.groq_client.cleanup()
            
            # Cleanup DAO components
            if self.governance_manager:
                await self.governance_manager.cleanup()
            if self.token_manager:
                await self.token_manager.cleanup()
                
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