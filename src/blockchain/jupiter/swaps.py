import logging
from typing import Any, Dict, List, Optional, Tuple
import aiohttp
import json
from dataclasses import dataclass
from datetime import datetime
import asyncio
from decimal import Decimal
import backoff

logger = logging.getLogger(__name__)

@dataclass
class Token:
    address: str
    symbol: str
    decimals: int
    name: str

@dataclass
class Route:
    in_amount: Decimal
    out_amount: Decimal
    price_impact: float
    market_infos: List[Dict]
    slippage: float
    fees: List[Dict]

@dataclass
class SwapResult:
    transaction_id: str
    input_token: Token
    output_token: Token
    input_amount: Decimal
    output_amount: Decimal
    price_impact: float
    route: Route
    timestamp: datetime
@dataclass
class DynamicSlippageConfig:
    min_bps: int
    max_bps: int

@dataclass
class PriorityFeeConfig:
    type: str  # 'auto', 'autoMultiplier', 'jitoTipLamports', 'priorityLevelWithMaxLamports'
    value: Any  # Could be int for jitoTipLamports, float for autoMultiplier, etc.

@dataclass
class SwapConfig:
    wrap_unwrap_sol: bool = True
    use_shared_accounts: bool = True
    fee_account: Optional[str] = None
    tracking_account: Optional[str] = None
    compute_unit_price: Optional[int] = None
    prioritization_fee: Optional[PriorityFeeConfig] = None
    as_legacy_transaction: bool = False
    use_token_ledger: bool = False
    destination_token_account: Optional[str] = None
    dynamic_compute_unit_limit: bool = False
    skip_user_accounts_rpc_calls: bool = False
    dynamic_slippage: Optional[DynamicSlippageConfig] = None

class JupiterSwapError(Exception):
    """Base exception for Jupiter swap operations."""
    pass

class SwapManager:
    def __init__(
        self,
        api_key: str,
        rpc_url: str,
        default_slippage: float = 0.5  # 0.5%
    ):
        self.api_key = api_key
        self.rpc_url = rpc_url
        self.default_slippage = default_slippage
        self.session: Optional[aiohttp.ClientSession] = None
        self.token_cache: Dict[str, Token] = {}
        
        # Base API URLs
        self.api_url = "https://quote-api.jup.ag/v6"

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.cleanup()

    async def initialize(self):
        """Initialize the swap manager."""
        self.session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )
        # Initialize token list
        await self._update_token_cache()

    async def cleanup(self):
        """Cleanup resources."""
        if self.session:
            await self.session.close()

    @backoff.on_exception(
        backoff.expo,
        (aiohttp.ClientError, JupiterSwapError),
        max_tries=3
    )
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        data: Optional[dict] = None
    ) -> dict:
        """Make an API request with retry logic."""
        if not self.session:
            await self.initialize()

        url = f"{self.api_url}/{endpoint}"
        
        try:
            async with self.session.request(
                method,
                url,
                params=params,
                json=data
            ) as response:
                if response.status not in {200, 201}:
                    error_data = await response.json()
                    raise JupiterSwapError(
                        f"API request failed: {error_data.get('message', 'Unknown error')}"
                    )
                return await response.json()
        except Exception as e:
            logger.error(f"Request error: {str(e)}")
            raise JupiterSwapError(f"Request failed: {str(e)}")

    async def _update_token_cache(self):
        """Update local token cache."""
        try:
            response = await self._make_request('GET', 'tokens')
            
            for token_data in response:
                token = Token(
                    address=token_data['address'],
                    symbol=token_data['symbol'],
                    decimals=token_data['decimals'],
                    name=token_data['name']
                )
                self.token_cache[token.address] = token
                
        except Exception as e:
            logger.error(f"Error updating token cache: {str(e)}")
            raise JupiterSwapError(f"Failed to update token cache: {str(e)}")

    async def get_token_price(
        self,
        input_token: str,
        output_token: str,
        amount: Decimal
    ) -> Tuple[Decimal, float]:
        """Get token price and price impact."""
        try:
            response = await self._make_request(
                'GET',
                'price',
                params={
                    'inputMint': input_token,
                    'outputMint': output_token,
                    'amount': str(amount),
                    'slippage': self.default_slippage
                }
            )
            
            return Decimal(response['outAmount']), float(response['priceImpact'])
            
        except Exception as e:
            logger.error(f"Error getting token price: {str(e)}")
            raise JupiterSwapError(f"Failed to get token price: {str(e)}")

    async def get_swap_routes(
        self,
        input_token: str,
        output_token: str,
        amount: Decimal,
        slippage: Optional[float] = None
    ) -> List[Route]:
        """Get optimized swap routes."""
        try:
            response = await self._make_request(
                'GET',
                'quote',
                params={
                    'inputMint': input_token,
                    'outputMint': output_token,
                    'amount': str(amount),
                    'slippage': slippage or self.default_slippage,
                    'feeBps': 4
                }
            )
            
            routes = []
            for route_data in response['routes']:
                route = Route(
                    in_amount=Decimal(route_data['inAmount']),
                    out_amount=Decimal(route_data['outAmount']),
                    price_impact=float(route_data['priceImpact']),
                    market_infos=route_data['marketInfos'],
                    slippage=float(route_data['slippage']),
                    fees=route_data['fees']
                )
                routes.append(route)
                
            return routes
            
        except Exception as e:
            logger.error(f"Error getting swap routes: {str(e)}")
            raise JupiterSwapError(f"Failed to get swap routes: {str(e)}")

    async def execute_swap(
        self,
        input_token: str,
        output_token: str,
        amount: Decimal,
        wallet_address: str,
        slippage: Optional[float] = None
    ) -> SwapResult:
        """Execute a token swap."""
        try:
            # Get best route
            routes = await self.get_swap_routes(
                input_token,
                output_token,
                amount,
                slippage
            )
            
            if not routes:
                raise JupiterSwapError("No valid routes found")
            
            best_route = routes[0]  # Jupiter returns routes sorted by best price
            
            # Prepare transaction
            swap_data = {
                'route': best_route,
                'userPublicKey': wallet_address,
                'wrapUnwrapSOL': True  # Auto wrap/unwrap SOL
            }
            
            # Get transaction data
            tx_response = await self._make_request(
                'POST',
                'swap',
                data=swap_data
            )
            
            # Execute transaction
            transaction_id = tx_response['txid']
            
            # Create swap result
            result = SwapResult(
                transaction_id=transaction_id,
                input_token=self.token_cache[input_token],
                output_token=self.token_cache[output_token],
                input_amount=amount,
                output_amount=best_route.out_amount,
                price_impact=best_route.price_impact,
                route=best_route,
                timestamp=datetime.now()
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing swap: {str(e)}")
            raise JupiterSwapError(f"Failed to execute swap: {str(e)}")

    async def get_swap_status(self, transaction_id: str) -> dict:
        """Get status of a swap transaction."""
        try:
            response = await self._make_request(
                'GET',
                f'swap/status/{transaction_id}'
            )
            return response
            
        except Exception as e:
            logger.error(f"Error getting swap status: {str(e)}")
            raise JupiterSwapError(f"Failed to get swap status: {str(e)}")
    async def execute_swap_with_config(
        self,
        input_token: str,
        output_token: str,
        amount: Decimal,
        wallet_address: str,
        config: SwapConfig,
        slippage: Optional[float] = None
    ) -> SwapResult:
        """Execute a token swap with advanced configuration."""
        try:
            # Get best route
            routes = await self.get_swap_routes(
                input_token,
                output_token,
                amount,
                slippage
            )
            
            if not routes:
                raise JupiterSwapError("No valid routes found")
            
            best_route = routes[0]
            
            # Prepare transaction with advanced configuration
            swap_data = {
                'userPublicKey': wallet_address,
                'wrapAndUnwrapSol': config.wrap_unwrap_sol,
                'useSharedAccounts': config.use_shared_accounts,
                'dynamicComputeUnitLimit': config.dynamic_compute_unit_limit,
                'skipUserAccountsRpcCalls': config.skip_user_accounts_rpc_calls,
                'asLegacyTransaction': config.as_legacy_transaction,
                'useTokenLedger': config.use_token_ledger
            }

            # Add optional configurations
            if config.fee_account:
                swap_data['feeAccount'] = config.fee_account
            
            if config.tracking_account:
                swap_data['trackingAccount'] = config.tracking_account
            
            if config.compute_unit_price:
                swap_data['computeUnitPriceMicroLamports'] = config.compute_unit_price
            
            if config.destination_token_account:
                swap_data['destinationTokenAccount'] = config.destination_token_account
            
            if config.prioritization_fee:
                if config.prioritization_fee.type == 'auto':
                    swap_data['prioritizationFeeLamports'] = 'auto'
                elif config.prioritization_fee.type == 'autoMultiplier':
                    swap_data['prioritizationFeeLamports'] = {
                        'autoMultiplier': config.prioritization_fee.value
                    }
                elif config.prioritization_fee.type == 'jitoTipLamports':
                    swap_data['prioritizationFeeLamports'] = {
                        'jitoTipLamports': config.prioritization_fee.value
                    }
                elif config.prioritization_fee.type == 'priorityLevelWithMaxLamports':
                    swap_data['prioritizationFeeLamports'] = {
                        'priorityLevelWithMaxLamports': config.prioritization_fee.value
                    }

            if config.dynamic_slippage:
                swap_data['dynamicSlippage'] = {
                    'minBps': config.dynamic_slippage.min_bps,
                    'maxBps': config.dynamic_slippage.max_bps
                }

            # Add quote response
            swap_data['quoteResponse'] = {
                'inputMint': input_token,
                'inAmount': str(amount),
                'outputMint': output_token,
                'outAmount': str(best_route.out_amount),
                'otherAmountThreshold': str(best_route.out_amount),
                'swapMode': 'ExactIn',
                'slippageBps': int(slippage * 100) if slippage else int(self.default_slippage * 100),
                'priceImpactPct': str(best_route.price_impact),
                'routePlan': best_route.market_infos
            }
            
            # Execute the swap
            tx_response = await self._make_request(
                'POST',
                'swap',
                data=swap_data
            )
            
            # Create swap result with additional information
            result = SwapResult(
                transaction_id=tx_response['swapTransaction'],
                input_token=self.token_cache[input_token],
                output_token=self.token_cache[output_token],
                input_amount=amount,
                output_amount=best_route.out_amount,
                price_impact=best_route.price_impact,
                route=best_route,
                timestamp=datetime.now()
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing swap: {str(e)}")
            raise JupiterSwapError(f"Failed to execute swap: {str(e)}")
# Example usage
if __name__ == "__main__":
    async def main():
        swap_manager = SwapManager(
            api_key="your-api-key",
            rpc_url="https://api.mainnet-beta.solana.com"
        )
        
        try:
            # Create swap configuration
            config = SwapConfig(
                wrap_unwrap_sol=True,
                use_shared_accounts=True,
                dynamic_compute_unit_limit=True,
                prioritization_fee=PriorityFeeConfig(
                    type='auto',
                    value=None
                ),
                dynamic_slippage=DynamicSlippageConfig(
                    min_bps=50,  # 0.5%
                    max_bps=300  # 3%
                )
            )
            
            # Execute swap with configuration
            result = await swap_manager.execute_swap_with_config(
                input_token="SOL_ADDRESS",
                output_token="USDC_ADDRESS",
                amount=Decimal("1.0"),
                wallet_address="WALLET_ADDRESS",
                config=config
            )
            
            print(f"Swap executed: {result.transaction_id}")
            
        except JupiterSwapError as e:
            print(f"Error: {str(e)}")
        finally:
            await swap_manager.cleanup()

    asyncio.run(main())