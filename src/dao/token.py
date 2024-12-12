from typing import Dict, List, Optional, Tuple
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import asyncio
from enum import Enum
import json
import backoff

from blockchain.crossmint.wallet import WalletManager

logger = logging.getLogger(__name__)

class StakingType(Enum):
    FLEXIBLE = "flexible"  # Can unstake anytime
    LOCKED = "locked"      # Fixed staking period

@dataclass
class StakingPool:
    pool_id: int
    staking_type: StakingType
    apr: Decimal
    min_stake: Decimal
    lock_period: Optional[timedelta]
    total_staked: Decimal = Decimal(0)
    total_rewards_distributed: Decimal = Decimal(0)

@dataclass
class StakingPosition:
    position_id: int
    user: str
    pool_id: int
    amount: Decimal
    start_time: datetime
    end_time: Optional[datetime]
    rewards_claimed: Decimal = Decimal(0)
    last_claim_time: datetime = None

@dataclass
class TokenInfo:
    name: str
    symbol: str
    decimals: int
    total_supply: Decimal
    circulating_supply: Decimal

class TokenManager:
    def __init__(self, wallet_manager: WalletManager):
        self.wallet_manager = wallet_manager
        
        # Initialize token info
        self.token_info = TokenInfo(
            name="GitHub DAO Token",
            symbol="GDT",
            decimals=9,
            total_supply=Decimal("1000000000"),  # 1 billion tokens
            circulating_supply=Decimal(0)
        )
        
        # Initialize staking pools
        self.staking_pools: Dict[int, StakingPool] = {
            1: StakingPool(
                pool_id=1,
                staking_type=StakingType.FLEXIBLE,
                apr=Decimal("0.15"),  # 15% APR
                min_stake=Decimal("1000"),
                lock_period=None
            ),
            2: StakingPool(
                pool_id=2,
                staking_type=StakingType.LOCKED,
                apr=Decimal("0.25"),  # 25% APR
                min_stake=Decimal("5000"),
                lock_period=timedelta(days=30)
            )
        }
        
        # Track staking positions
        self.staking_positions: Dict[int, StakingPosition] = {}
        self.next_position_id: int = 1
        
        # Track balances and rewards
        self.balances: Dict[str, Decimal] = {}
        self.treasury_balance: Decimal = Decimal(0)

    async def initialize(self):
        """Initialize token contract and settings."""
        try:
            # Set initial treasury allocation (10% of total supply)
            self.treasury_balance = self.token_info.total_supply * Decimal("0.1")
            self.token_info.circulating_supply = self.treasury_balance
            
            logger.info("Token manager initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing token manager: {str(e)}")
            raise

    async def get_balance(self, address: str) -> Decimal:
        """Get token balance for an address."""
        return self.balances.get(address, Decimal(0))

    async def transfer(self, from_address: str, to_address: str, amount: Decimal) -> bool:
        """Transfer tokens between addresses."""
        try:
            # Check balance
            from_balance = await self.get_balance(from_address)
            if from_balance < amount:
                raise ValueError("Insufficient balance")

            # Update balances
            self.balances[from_address] = from_balance - amount
            self.balances[to_address] = self.balances.get(to_address, Decimal(0)) + amount
            
            logger.info(f"Transferred {amount} tokens from {from_address} to {to_address}")
            return True
            
        except Exception as e:
            logger.error(f"Error transferring tokens: {str(e)}")
            raise

    async def stake_tokens(
        self,
        user: str,
        pool_id: int,
        amount: Decimal
    ) -> StakingPosition:
        """Stake tokens in a pool."""
        try:
            # Get pool
            pool = self.staking_pools.get(pool_id)
            if not pool:
                raise ValueError(f"Invalid pool ID: {pool_id}")

            # Validate amount
            if amount < pool.min_stake:
                raise ValueError(f"Minimum stake is {pool.min_stake}")

            # Check balance
            balance = await self.get_balance(user)
            if balance < amount:
                raise ValueError("Insufficient balance")

            # Create staking position
            now = datetime.now()
            position = StakingPosition(
                position_id=self.next_position_id,
                user=user,
                pool_id=pool_id,
                amount=amount,
                start_time=now,
                end_time=now + pool.lock_period if pool.lock_period else None,
                last_claim_time=now
            )

            # Update state
            self.balances[user] -= amount
            pool.total_staked += amount
            self.staking_positions[position.position_id] = position
            self.next_position_id += 1

            logger.info(f"User {user} staked {amount} tokens in pool {pool_id}")
            return position
            
        except Exception as e:
            logger.error(f"Error staking tokens: {str(e)}")
            raise

    async def unstake_tokens(self, user: str, position_id: int) -> Tuple[Decimal, Decimal]:
        """Unstake tokens and claim rewards."""
        try:
            # Get position
            position = self.staking_positions.get(position_id)
            if not position or position.user != user:
                raise ValueError("Invalid staking position")

            # Get pool
            pool = self.staking_pools[position.pool_id]

            # Check if locked period has ended
            if pool.staking_type == StakingType.LOCKED:
                if datetime.now() < position.end_time:
                    raise ValueError("Tokens are still locked")

            # Calculate rewards
            rewards = await self._calculate_rewards(position)

            # Update state
            self.balances[user] += position.amount + rewards
            pool.total_staked -= position.amount
            pool.total_rewards_distributed += rewards
            del self.staking_positions[position_id]

            logger.info(
                f"User {user} unstaked {position.amount} tokens "
                f"and claimed {rewards} rewards"
            )
            return position.amount, rewards
            
        except Exception as e:
            logger.error(f"Error unstaking tokens: {str(e)}")
            raise

    async def claim_rewards(self, user: str, position_id: int) -> Decimal:
        """Claim staking rewards without unstaking."""
        try:
            # Get position
            position = self.staking_positions.get(position_id)
            if not position or position.user != user:
                raise ValueError("Invalid staking position")

            # Calculate rewards
            rewards = await self._calculate_rewards(position)

            # Update state
            position.rewards_claimed += rewards
            position.last_claim_time = datetime.now()
            self.balances[user] += rewards

            # Update pool statistics
            pool = self.staking_pools[position.pool_id]
            pool.total_rewards_distributed += rewards

            logger.info(f"User {user} claimed {rewards} rewards from position {position_id}")
            return rewards
            
        except Exception as e:
            logger.error(f"Error claiming rewards: {str(e)}")
            raise

    async def _calculate_rewards(self, position: StakingPosition) -> Decimal:
        """Calculate pending rewards for a staking position."""
        pool = self.staking_pools[position.pool_id]
        
        # Calculate time period
        now = datetime.now()
        time_staked = now - (position.last_claim_time or position.start_time)
        years = Decimal(time_staked.total_seconds()) / Decimal(31536000)  # seconds in a year
        
        # Calculate rewards
        rewards = position.amount * pool.apr * years
        return rewards

    async def get_staking_stats(self) -> Dict:
        """Get global staking statistics."""
        total_staked = sum(pool.total_staked for pool in self.staking_pools.values())
        total_rewards = sum(pool.total_rewards_distributed for pool in self.staking_pools.values())
        
        return {
            "total_staked": float(total_staked),
            "total_rewards_distributed": float(total_rewards),
            "staking_pools": [
                {
                    "pool_id": pool.pool_id,
                    "type": pool.staking_type.value,
                    "apr": float(pool.apr),
                    "total_staked": float(pool.total_staked),
                    "min_stake": float(pool.min_stake),
                    "lock_period": pool.lock_period.days if pool.lock_period else None
                }
                for pool in self.staking_pools.values()
            ]
        }

    async def get_user_positions(self, user: str) -> List[Dict]:
        """Get all staking positions for a user."""
        user_positions = [
            pos for pos in self.staking_positions.values()
            if pos.user == user
        ]
        
        return [
            {
                "position_id": pos.position_id,
                "pool_id": pos.pool_id,
                "amount": float(pos.amount),
                "rewards_claimed": float(pos.rewards_claimed),
                "pending_rewards": float(await self._calculate_rewards(pos)),
                "start_time": pos.start_time.isoformat(),
                "end_time": pos.end_time.isoformat() if pos.end_time else None
            }
            for pos in user_positions
        ]

# Example usage
if __name__ == "__main__":
    async def main():
        # Initialize manager (mock wallet manager for example)
        token_manager = TokenManager(wallet_manager=None)
        await token_manager.initialize()
        
        try:
            # Simulate token distribution
            user_address = "user123"
            token_manager.balances[user_address] = Decimal("10000")
            
            # Stake tokens
            position = await token_manager.stake_tokens(
                user=user_address,
                pool_id=1,
                amount=Decimal("5000")
            )
            
            # Simulate time passage
            await asyncio.sleep(5)  # In real scenario, this would be longer
            
            # Claim rewards
            rewards = await token_manager.claim_rewards(
                user=user_address,
                position_id=position.position_id
            )
            
            # Get user positions
            positions = await token_manager.get_user_positions(user_address)
            print(f"User positions: {json.dumps(positions, indent=2)}")
            
        except Exception as e:
            print(f"Error: {str(e)}")

    asyncio.run(main())