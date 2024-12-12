from dataclasses import dataclass
from typing import Optional
import os
from enum import Enum
from dotenv import load_dotenv
from pathlib import Path

class Environment(Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"

@dataclass
class AIConfig:
    groq_api_key: str
    assister_api_key: str
    model_name: str = "mixtral-8x7b-32768"  # Default model
    max_tokens: int = 4096
    temperature: float = 0.7

    @classmethod
    def from_env(cls) -> 'AIConfig':
        return cls(
            groq_api_key=get_required_env("GROQ_API_KEY"),
            assister_api_key=get_required_env("ASSISTER_API_KEY")
        )

@dataclass
class DiscordConfig:
    token: str
    command_prefix: str = "!"
    guild_ids: list[int] = None

    @classmethod
    def from_env(cls) -> 'DiscordConfig':
        guild_ids_str = os.getenv("DISCORD_GUILD_IDS", "")
        guild_ids = [int(id_) for id_ in guild_ids_str.split(",")] if guild_ids_str else None
        
        return cls(
            token=get_required_env("DISCORD_TOKEN"),
            guild_ids=guild_ids
        )

@dataclass
class GitHubConfig:
    token: str
    api_url: str = "https://api.github.com"
    
    @classmethod
    def from_env(cls) -> 'GitHubConfig':
        return cls(
            token=get_required_env("GITHUB_TOKEN")
        )

@dataclass
class BlockchainConfig:
    network: str
    crossmint_api_key: str
    helius_api_key: str
    jupiter_api_key: str
    rpc_url: Optional[str] = None

    @classmethod
    def from_env(cls) -> 'BlockchainConfig':
        network = os.getenv("NETWORK", "devnet")
        rpc_url = os.getenv("RPC_URL") or f"https://api.{network}.solana.com"
        
        return cls(
            network=network,
            crossmint_api_key=get_required_env("CROSSMINT_API_KEY"),
            helius_api_key=get_required_env("HELIUS_API_KEY"),
            jupiter_api_key=get_required_env("JUPITER_API_KEY"),
            rpc_url=rpc_url
        )

@dataclass
class DatabaseConfig:
    url: str
    max_connections: int = 10
    ssl_mode: str = "require"

    @classmethod
    def from_env(cls) -> 'DatabaseConfig':
        return cls(
            url=get_required_env("DATABASE_URL"),
            max_connections=int(os.getenv("DB_MAX_CONNECTIONS", "10")),
            ssl_mode=os.getenv("DB_SSL_MODE", "require")
        )

class AppConfig:
    def __init__(
        self,
        environment: Environment,
        ai: AIConfig,
        discord: DiscordConfig,
        github: GitHubConfig,
        blockchain: BlockchainConfig,
        database: DatabaseConfig
    ):
        self.environment = environment
        self.ai = ai
        self.discord = discord
        self.github = github
        self.blockchain = blockchain
        self.database = database

    @classmethod
    def load(cls) -> 'AppConfig':
        """Load and create a complete application configuration."""
        load_env_file()
        
        environment = get_environment()
        
        return cls(
            environment=environment,
            ai=AIConfig.from_env(),
            discord=DiscordConfig.from_env(),
            github=GitHubConfig.from_env(),
            blockchain=BlockchainConfig.from_env(),
            database=DatabaseConfig.from_env()
        )

def get_required_env(key: str) -> str:
    """Get a required environment variable or raise an error."""
    value = os.getenv(key)
    if value is None:
        raise ValueError(f"Missing required environment variable: {key}")
    return value

def get_environment() -> Environment:
    """Get the current environment or default to development."""
    env_name = os.getenv("ENVIRONMENT", "development").lower()
    try:
        return Environment(env_name)
    except ValueError:
        return Environment.DEVELOPMENT

def load_env_file():
    """Load the appropriate .env file based on the environment."""
    env_name = os.getenv("ENVIRONMENT", "development").lower()
    env_file = Path(f".env.{env_name}")
    
    # Fall back to .env if specific environment file doesn't exist
    if not env_file.exists():
        env_file = Path(".env")
    
    if env_file.exists():
        load_dotenv(env_file)

# Example usage
if __name__ == "__main__":
    try:
        config = AppConfig.load()
        print(f"Loaded configuration for environment: {config.environment.value}")
    except ValueError as e:
        print(f"Configuration error: {e}")