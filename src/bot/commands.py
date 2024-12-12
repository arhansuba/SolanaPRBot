import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Literal
import logging
from datetime import datetime

from ai.groq_client import GroqClient
from github import Github as GitHubClient
from blockchain.crossmint.wallet import WalletManager
from blockchain.jupiter.swaps import SwapManager
from dao.governance import GovernanceManager
from dao.token import TokenManager

logger = logging.getLogger(__name__)

class CommandPermissions:
    """Permission checks for commands"""
    @staticmethod
    def is_admin(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            return False
        return interaction.user.guild_permissions.administrator

    @staticmethod
    def has_token_holdings(interaction: discord.Interaction) -> bool:
        # This would check if user has required token holdings for governance
        # Implementation depends on your token tracking system
        return True  # Placeholder implementation

class BotCommands(commands.Cog):
    def __init__(
        self, 
        bot: commands.Bot,
        ai_client: GroqClient,
        github_client: GitHubClient,
        wallet_manager: WalletManager,
        swap_manager: SwapManager,
        governance_manager: GovernanceManager,
        token_manager: TokenManager
    ):
        self.bot = bot
        self.ai_client = ai_client
        self.github_client = github_client
        self.wallet_manager = wallet_manager
        self.swap_manager = swap_manager
        self.governance_manager = governance_manager
        self.token_manager = token_manager
        self.permissions = CommandPermissions()
        self.last_analysis = {}  # Rate limiting tracker

    async def can_analyze(self, user_id: int) -> bool:
        """Check rate limiting for analysis commands"""
        if user_id not in self.last_analysis:
            return True
        
        time_diff = datetime.now() - self.last_analysis[user_id]
        return time_diff.seconds >= 30  # 30 second cooldown

    @app_commands.command(name="analyze-pr")
    @app_commands.describe(url="GitHub pull request URL to analyze")
    async def analyze_pr(self, interaction: discord.Interaction, url: str):
        """Analyze a GitHub pull request"""
        if not await self.can_analyze(interaction.user.id):
            await interaction.response.send_message(
                "Please wait before requesting another analysis.",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        try:
            # Fetch PR data
            pr_data = await self.github_client.get_pr(url)
            
            # Analyze with AI
            analysis = await self.ai_client.analyze_pr(pr_data)
            
            # Create embed for response
            embed = discord.Embed(
                title="Pull Request Analysis",
                url=url,
                color=discord.Color.blue()
            )
            embed.add_field(name="Summary", value=analysis['summary'], inline=False)
            embed.add_field(name="Changes", value=analysis['changes'], inline=False)
            embed.add_field(name="Recommendations", value=analysis['recommendations'], inline=False)
            
            self.last_analysis[interaction.user.id] = datetime.now()
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error analyzing PR: {e}")
            await interaction.followup.send(
                "Sorry, I encountered an error analyzing that pull request.",
                ephemeral=True
            )

    @app_commands.command(name="review-code")
    @app_commands.describe(code="Code snippet to review")
    async def review_code(self, interaction: discord.Interaction, code: str):
        """Review a code snippet"""
        if not await self.can_analyze(interaction.user.id):
            await interaction.response.send_message(
                "Please wait before requesting another review.",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        try:
            review = await self.ai_client.analyze_code(code)
            
            embed = discord.Embed(
                title="Code Review",
                color=discord.Color.green()
            )
            embed.add_field(name="Analysis", value=review['analysis'], inline=False)
            embed.add_field(name="Best Practices", value=review['best_practices'], inline=False)
            embed.add_field(name="Suggestions", value=review['suggestions'], inline=False)
            
            self.last_analysis[interaction.user.id] = datetime.now()
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error reviewing code: {e}")
            await interaction.followup.send(
                "Sorry, I encountered an error reviewing the code.",
                ephemeral=True
            )

    @app_commands.command(name="governance")
    @app_commands.describe(
        action="Governance action to perform",
        proposal_id="ID of the proposal (for vote/execute actions)",
        description="Description of the proposal (for create action)"
    )
    async def governance(
        self,
        interaction: discord.Interaction,
        action: Literal["create", "vote", "execute"],
        proposal_id: Optional[int] = None,
        description: Optional[str] = None
    ):
        """Manage DAO governance"""
        if not self.permissions.has_token_holdings(interaction):
            await interaction.response.send_message(
                "You need to hold tokens to participate in governance.",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        try:
            if action == "create":
                if not description:
                    await interaction.followup.send("Description required for creating proposal.")
                    return
                
                result = await self.governance_manager.create_proposal(
                    user_id=interaction.user.id,
                    description=description
                )
                
                embed = discord.Embed(
                    title="Proposal Created",
                    description=f"Proposal ID: {result['proposal_id']}",
                    color=discord.Color.green()
                )
                
            elif action == "vote":
                if not proposal_id:
                    await interaction.followup.send("Proposal ID required for voting.")
                    return
                
                result = await self.governance_manager.vote(
                    user_id=interaction.user.id,
                    proposal_id=proposal_id
                )
                
                embed = discord.Embed(
                    title="Vote Recorded",
                    description=f"Voted on proposal {proposal_id}",
                    color=discord.Color.blue()
                )
                
            elif action == "execute":
                if not proposal_id:
                    await interaction.followup.send("Proposal ID required for execution.")
                    return
                
                result = await self.governance_manager.execute_proposal(proposal_id)
                
                embed = discord.Embed(
                    title="Proposal Executed",
                    description=f"Executed proposal {proposal_id}",
                    color=discord.Color.green()
                )

            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in governance action: {e}")
            await interaction.followup.send(
                f"Error performing governance action: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="token")
    @app_commands.describe(
        action="Token action to perform",
        amount="Amount of tokens (for transfer/stake actions)",
        recipient="Recipient address (for transfer action)"
    )
    async def token(
        self,
        interaction: discord.Interaction,
        action: Literal["balance", "transfer", "stake", "unstake"],
        amount: Optional[float] = None,
        recipient: Optional[str] = None
    ):
        """Manage tokens"""
        await interaction.response.defer()

        try:
            if action == "balance":
                balance = await self.token_manager.get_balance(interaction.user.id)
                staked = await self.token_manager.get_staked_amount(interaction.user.id)
                
                embed = discord.Embed(
                    title="Token Balance",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Available", value=f"{balance} GDT")
                embed.add_field(name="Staked", value=f"{staked} GDT")
                
            elif action == "transfer":
                if not amount or not recipient:
                    await interaction.followup.send("Amount and recipient required for transfer.")
                    return
                
                result = await self.token_manager.transfer(
                    from_user_id=interaction.user.id,
                    to_address=recipient,
                    amount=amount
                )
                
                embed = discord.Embed(
                    title="Transfer Complete",
                    description=f"Transferred {amount} GDT to {recipient}",
                    color=discord.Color.green()
                )
                
            elif action in ["stake", "unstake"]:
                if not amount:
                    await interaction.followup.send("Amount required for staking/unstaking.")
                    return
                
                if action == "stake":
                    result = await self.token_manager.stake(interaction.user.id, amount)
                else:
                    result = await self.token_manager.unstake(interaction.user.id, amount)
                
                embed = discord.Embed(
                    title=f"{action.capitalize()} Complete",
                    description=f"{action.capitalize()}d {amount} GDT",
                    color=discord.Color.green()
                )

            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in token action: {e}")
            await interaction.followup.send(
                f"Error performing token action: {str(e)}",
                ephemeral=True
            )

    async def cog_load(self):
        """Called when the cog is loaded"""
        logger.info("Commands cog loaded")

    async def cog_unload(self):
        """Called when the cog is unloaded"""
        logger.info("Commands cog unloaded")

def setup(bot: commands.Bot):
    """Setup function for the cog"""
    bot.add_cog(BotCommands(bot))