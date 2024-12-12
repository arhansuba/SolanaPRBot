from typing import Optional, Dict, List, Any
import aiohttp
import logging
from datetime import datetime
import asyncio
from enum import Enum
import backoff

logger = logging.getLogger(__name__)

class WalletType(Enum):
    SOLANA_CUSTODIAL = "solana-custodial-wallet"

class TransactionStatus(Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"

class CrossmintWalletError(Exception):
    """Base exception for wallet operations."""
    pass

class WalletManager:
    def __init__(
        self,
        api_key: str,
        environment: str = "staging"  # or "production"
    ):
        self.api_key = api_key
        self.base_url = f"https://{environment}.crossmint.com/api/v1-alpha2"
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()

    async def initialize(self):
        """Initialize the wallet manager."""
        self.session = aiohttp.ClientSession(
            headers={
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json"
            }
        )

    async def cleanup(self):
        """Cleanup resources."""
        if self.session:
            await self.session.close()

    @backoff.on_exception(
        backoff.expo,
        aiohttp.ClientError,
        max_tries=3
    )
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None
    ) -> Dict:
        """Make an API request with retry logic."""
        if not self.session:
            await self.initialize()

        url = f"{self.base_url}/{endpoint}"
        
        try:
            async with self.session.request(method, url, json=data) as response:
                response_data = await response.json()
                if response.status not in {200, 201}:
                    raise CrossmintWalletError(
                        f"API request failed: {response_data.get('message', 'Unknown error')}"
                    )
                return response_data
                
        except Exception as e:
            logger.error(f"Request error: {str(e)}")
            raise CrossmintWalletError(f"Request failed: {str(e)}")

    async def create_wallet(self, email: str) -> Dict[str, Any]:
        """
        Create a new Solana custodial wallet.
        """
        try:
            payload = {
                "type": WalletType.SOLANA_CUSTODIAL.value,
                "linkedUser": f"email:{email}"
            }

            response = await self._make_request("POST", "wallets", payload)
            logger.info(f"Created wallet for {email}")
            return response

        except Exception as e:
            logger.error(f"Error creating wallet: {str(e)}")
            raise CrossmintWalletError(f"Failed to create wallet: {str(e)}")

    async def fund_wallet(
        self,
        wallet_locator: str,
        amount: float,
        currency: str = "usdc"
    ) -> Dict[str, Any]:
        """
        Fund a wallet with USDC (only available in staging).
        """
        try:
            payload = {
                "amount": amount,
                "currency": currency
            }

            response = await self._make_request(
                "POST",
                f"wallets/{wallet_locator}/balances",
                payload
            )
            logger.info(f"Funded wallet {wallet_locator} with {amount} {currency}")
            return response

        except Exception as e:
            logger.error(f"Error funding wallet: {str(e)}")
            raise CrossmintWalletError(f"Failed to fund wallet: {str(e)}")

    async def get_balance(
        self,
        wallet_locator: str,
        currency: str = "usdc"
    ) -> Dict[str, Any]:
        """
        Get wallet balance for a specific currency.
        """
        try:
            response = await self._make_request(
                "GET",
                f"wallets/{wallet_locator}/balances?currency={currency}"
            )
            return response

        except Exception as e:
            logger.error(f"Error getting balance: {str(e)}")
            raise CrossmintWalletError(f"Failed to get balance: {str(e)}")

    async def create_transaction(
        self,
        wallet_locator: str,
        serialized_transaction: str
    ) -> Dict[str, Any]:
        """
        Create and submit a transaction.
        """
        try:
            payload = {
                "params": {
                    "transaction": serialized_transaction
                }
            }

            response = await self._make_request(
                "POST",
                f"wallets/{wallet_locator}/transactions",
                payload
            )
            logger.info(f"Created transaction for wallet {wallet_locator}")
            return response

        except Exception as e:
            logger.error(f"Error creating transaction: {str(e)}")
            raise CrossmintWalletError(f"Failed to create transaction: {str(e)}")

    async def get_transaction_status(
        self,
        wallet_locator: str,
        transaction_id: str
    ) -> Dict[str, Any]:
        """
        Get status of a transaction.
        """
        try:
            response = await self._make_request(
                "GET",
                f"wallets/{wallet_locator}/transactions/{transaction_id}"
            )
            return response

        except Exception as e:
            logger.error(f"Error getting transaction status: {str(e)}")
            raise CrossmintWalletError(f"Failed to get transaction status: {str(e)}")

    async def poll_transaction_status(
        self,
        wallet_locator: str,
        transaction_id: str,
        interval: int = 3,
        timeout: int = 60
    ) -> Dict[str, Any]:
        """
        Poll transaction status until completion or timeout.
        """
        start_time = datetime.now()
        while True:
            if (datetime.now() - start_time).seconds > timeout:
                raise CrossmintWalletError("Transaction polling timeout")

            status = await self.get_transaction_status(wallet_locator, transaction_id)
            if status["status"] in [TransactionStatus.SUCCESS.value, TransactionStatus.FAILED.value]:
                return status

            await asyncio.sleep(interval)

# Example usage
if __name__ == "__main__":
    async def main():
        wallet_manager = WalletManager(api_key="your-api-key")
        
        try:
            # Create a new wallet
            wallet = await wallet_manager.create_wallet("user@example.com")
            wallet_locator = wallet["address"]
            
            # Fund the wallet (staging only)
            await wallet_manager.fund_wallet(wallet_locator, 5, "usdc")
            
            # Check balance
            balance = await wallet_manager.get_balance(wallet_locator)
            print(f"Balance: {balance}")
            
            # Create a transaction (example with pre-prepared transaction)
            serialized_tx = "your-base58-encoded-transaction"
            tx = await wallet_manager.create_transaction(
                wallet_locator,
                serialized_tx
            )
            
            # Poll for status
            final_status = await wallet_manager.poll_transaction_status(
                wallet_locator,
                tx["id"]
            )
            print(f"Final transaction status: {final_status}")
            
        except CrossmintWalletError as e:
            print(f"Error: {str(e)}")
        finally:
            await wallet_manager.cleanup()

    asyncio.run(main())