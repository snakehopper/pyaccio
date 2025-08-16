"""
This module contains the BybitClient class, which is a wrapper around the
official pybit SDK to interact with the Bybit V5 API.
"""
import logging
import time
from pybit.unified_trading import HTTP


class BybitClient:
    """
    A client for interacting with the Bybit V5 API (Unified Trading Account).
    This class is a wrapper around the pybit library.
    NOTE: This code is written based on documentation and has not been tested
    with live API keys.
    """
    def __init__(self, api_key: str, api_secret: str):
        """
        Initializes the BybitClient.

        Args:
            api_key (str): The Bybit API key.
            api_secret (str): The Bybit API secret.
        """
        self.logger = logging.getLogger(__name__)
        try:
            self.session = HTTP(
                testnet=False,  # Set to True for testnet environment
                api_key=api_key,
                api_secret=api_secret,
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize Bybit HTTP session: {e}")
            raise

    def get_api_key_info(self):
        """
        Retrieves information and permissions for the current API key.
        This is used to verify the key has the necessary permissions.
        Endpoint: /v5/user/query-api
        """
        try:
            self.logger.info("Fetching API key information...")
            result = self.session.get_api_key_information()
            self.logger.debug(f"API key info response: {result}")
            return result
        except Exception as e:
            self.logger.error(f"Error fetching API key info: {e}")
            return None

    def get_positions(self, category: str, settle_coin: str = None):
        """
        Gets open positions for a specific category
        (e.g., 'linear', 'inverse', 'option').
        Endpoint: /v5/position/list
        """
        try:
            self.logger.info(f"Fetching positions for category: {category}...")
            params = {"category": category}
            if settle_coin:
                params["settleCoin"] = settle_coin
            result = self.session.get_positions(**params)
            self.logger.debug(f"Positions response: {result}")
            return result.get('result', {}).get('list', [])
        except Exception as e:
            self.logger.error(f"Error fetching positions: {e}")
            return []

    def place_order(self, category: str, symbol: str, side: str, order_type: str, qty: str):
        """
        Places an order. Used to close positions or sell spot assets.
        Endpoint: /v5/order/create
        """
        try:
            self.logger.info(f"Placing {side} {order_type} order for {qty} of {symbol}...")
            result = self.session.place_order(
                category=category,
                symbol=symbol,
                side=side,
                orderType=order_type,
                qty=qty,
            )
            self.logger.debug(f"Place order response: {result}")
            return result
        except Exception as e:
            self.logger.error(f"Error placing order for {symbol}: {e}")
            return None

    def get_wallet_balance(self, account_type: str = "UNIFIED"):
        """
        Gets the wallet balance for a specific account type.
        Endpoint: /v5/account/wallet-balance
        """
        try:
            self.logger.info(f"Fetching wallet balance for account type: {account_type}...")
            result = self.session.get_wallet_balance(accountType=account_type)
            self.logger.debug(f"Wallet balance response: {result}")
            return result.get('result', {}).get('list', [])
        except Exception as e:
            self.logger.error(f"Error fetching wallet balance: {e}")
            return []

    def get_whitelisted_addresses(self, coin: str = "USDT"):
        """
        Retrieves the whitelisted withdrawal addresses.
        NOTE: The pybit SDK might not have a direct method for this.
        This method might need a custom implementation or a call to a different endpoint.
        Let's assume there is a method, but add a placeholder.
        Endpoint: /v5/asset/withdrawal/query-address
        """
        try:
            self.logger.info(f"Fetching whitelisted addresses for {coin}...")
            # This endpoint is not directly in pybit as of some versions,
            # but we can call it manually if needed.
            # For now, let's assume it exists or we'll add it.
            # Placeholder:
            # result = self.session.get_withdrawal_addresses(coin=coin)
            # The actual endpoint is /v5/asset/withdrawal/query-address, let's use a generic call
            result = self.session._get(
                "/v5/asset/withdrawal/query-address",
                {"coin": coin}
            )
            self.logger.debug(f"Whitelisted addresses response: {result}")
            return result.get('result', {}).get('list', [])
        except Exception as e:
            self.logger.error(f"Error fetching whitelisted addresses: {e}")
            return []

    def withdraw(self, coin: str, chain: str, address: str, amount: str):
        """
        Initiates a withdrawal to a whitelisted address.
        Endpoint: /v5/asset/withdrawal/create
        """
        try:
            self.logger.info(f"Initiating withdrawal of {amount} {coin} to {address} on {chain} chain...")
            result = self.session.withdraw(
                coin=coin,
                chain=chain,
                address=address,
                amount=amount,
                timestamp=int(time.time() * 1000) # Required parameter
            )
            self.logger.debug(f"Withdrawal response: {result}")
            return result
        except Exception as e:
            self.logger.error(f"Error initiating withdrawal: {e}")
            return None

    def delete_other_api_keys(self, current_api_key: str):
        """
        Deletes all API keys with trade permissions except the current one.
        This is a critical security step. Read-only keys are preserved.
        Endpoint: /v5/user/delete-api
        """
        try:
            self.logger.info("Fetching all API keys to find and delete those with trade permissions...")
            all_keys_response = self.session.get_api_key_information()
            if all_keys_response.get('retCode') != 0:
                self.logger.error("Could not fetch API keys to delete.")
                return False

            all_keys = all_keys_response.get('result', {}).get('list', [])
            success = True
            for key_info in all_keys:
                api_key_to_check = key_info.get('apiKey')
                if api_key_to_check == current_api_key:
                    continue

                permissions = key_info.get('permissions', {})
                # A key has trade permissions if the 'Trade' list is not empty.
                if permissions.get('Trade'):
                    self.logger.warning(f"Deleting API key with trade permissions: {api_key_to_check}")
                    delete_response = self.session._post(
                        "/v5/user/delete-api",
                        {"apiKey": api_key_to_check}
                    )
                    if delete_response.get('retCode') != 0:
                        self.logger.error(f"Failed to delete API key {api_key_to_check}: {delete_response.get('retMsg')}")
                        success = False
                else:
                    self.logger.info(f"Skipping deletion of read-only API key: {api_key_to_check}")
            return success
        except Exception as e:
            self.logger.error(f"An exception occurred while deleting API keys: {e}")
            return False
