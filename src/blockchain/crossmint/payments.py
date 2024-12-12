from typing import Optional, Dict, Any
from decimal import Decimal
from enum import Enum
import aiohttp
import logging
import asyncio
import backoff

logger = logging.getLogger(__name__)

class PaymentMethod(Enum):
    USDC = "usdc"
    STRIPE = "stripe-payment-element"
    
class PaymentStatus(Enum):
    QUOTE = "quote"
    PAYMENT = "payment"
    DELIVERY = "delivery"
    COMPLETED = "completed"
    FAILED = "failed"

class PaymentError(Exception):
    """Base exception for payment operations."""
    pass

class CrossmintPaymentManager:
    def __init__(
        self,
        api_key: str,
        environment: str = "staging"
    ):
        self.api_key = api_key
        self.base_url = f"https://{environment}.crossmint.com/api/2022-06-09"
        self.session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        """Initialize the HTTP session."""
        self.session = aiohttp.ClientSession(
            headers={
                "x-api-key": self.api_key,
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
        """Make API request with retry logic."""
        if not self.session:
            await self.initialize()

        url = f"{self.base_url}/{endpoint}"
        
        async with self.session.request(method, url, json=data) as response:
            if response.status not in {200, 201}:
                error_data = await response.json()
                raise PaymentError(f"API request failed: {error_data.get('message', 'Unknown error')}")
            return await response.json()

    async def create_usdc_payment_order(
        self,
        collection_id: str,
        payer_address: str,
        email: str
    ) -> Dict[str, Any]:
        """
        Create USDC payment order and return serialized transaction for wallet signing.
        Frontend will handle the actual signing and sending of the transaction.
        """
        try:
            order_data = {
                "recipient": {
                    "email": email
                },
                "locale": "en-US",
                "payment": {
                    "method": "base-sepolia",  # For testnet
                    "currency": "usdc",
                    "payerAddress": payer_address
                },
                "lineItems": {
                    "collectionLocator": f"crossmint:{collection_id}"
                }
            }

            response = await self._make_request("POST", "orders", order_data)
            
            # Extract serialized transaction for wallet signing
            if "payment" in response and "preparation" in response["payment"]:
                return {
                    "order_id": response["orderId"],
                    "serialized_transaction": response["payment"]["preparation"]["serializedTransaction"],
                    "client_secret": response.get("clientSecret")
                }
            else:
                raise PaymentError("No serialized transaction in response")

        except Exception as e:
            logger.error(f"Error creating USDC order: {str(e)}")
            raise PaymentError(f"Failed to create USDC order: {str(e)}")

    async def create_card_payment_intent(
        self,
        collection_id: str,
        email: str
    ) -> Dict[str, Any]:
        """
        Create card payment order and return Stripe details.
        Frontend will handle the actual payment using Stripe Elements.
        """
        try:
            # Initial order creation
            order_data = {
                "payment": {
                    "method": "stripe-payment-element"
                },
                "lineItems": {
                    "collectionLocator": f"crossmint:{collection_id}"
                }
            }

            response = await self._make_request("POST", "orders", order_data)
            order_id = response["orderId"]

            # Add recipient email
            await self._make_request(
                "PATCH",
                f"orders/{order_id}",
                {"recipient": {"email": email}}
            )

            # Return data needed for Stripe Payment Element
            return {
                "order_id": order_id,
                "client_secret": response.get("clientSecret"),
                "stripe_data": response.get("payment", {}).get("preparation", {})
            }

        except Exception as e:
            logger.error(f"Error creating card payment intent: {str(e)}")
            raise PaymentError(f"Failed to create card payment intent: {str(e)}")

    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Get current status of an order."""
        try:
            return await self._make_request("GET", f"orders/{order_id}")
        except Exception as e:
            logger.error(f"Error getting order status: {str(e)}")
            raise PaymentError(f"Failed to get order status: {str(e)}")

# Example usage (Backend only - frontend handling would be separate)
if __name__ == "__main__":
    async def main():
        payment_manager = CrossmintPaymentManager(api_key="your-api-key")

        try:
            # Example USDC order creation
            usdc_result = await payment_manager.create_usdc_payment_order(
                collection_id="your-collection-id",
                payer_address="wallet-address",
                email="user@example.com"
            )
            print("USDC Transaction to sign:", usdc_result["serialized_transaction"])
            
            # Example card payment intent creation
            card_result = await payment_manager.create_card_payment_intent(
                collection_id="your-collection-id",
                email="user@example.com"
            )
            print("Stripe payment data:", card_result["stripe_data"])

        except PaymentError as e:
            print(f"Error: {e}")
        finally:
            await payment_manager.cleanup()

    asyncio.run(main())