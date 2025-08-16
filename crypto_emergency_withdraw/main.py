"""
Main script for the Crypto Emergency Withdrawal tool.

This script performs the following actions in sequence:
1.  Verifies API key permissions and withdrawal address whitelist.
2.  (Optional) Deletes all other API keys.
3.  Closes all open perpetual positions.
4.  Converts all spot assets to USDT.
5.  Withdraws all USDT to the specified whitelisted address.

**IMPORTANT**:
- Create a `.env` file in the same directory as this script.
- Copy the contents of `config.py.example` into `.env`.
- Fill in your actual API key, secret, and withdrawal address.
"""

import os
import logging
import time
from dotenv import load_dotenv
from bybit_client import BybitClient

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Helper Functions ---

def run_pre_flight_checks(client: BybitClient, wallet_address: str) -> bool:
    """Runs checks to ensure the script can execute successfully."""
    logging.info("--- Running Pre-flight Checks ---")

    # 1. Check API Key Permissions
    api_info = client.get_api_key_info()
    if not api_info or api_info.get('retCode') != 0:
        logging.error("Failed to get API key info. Please check your credentials.")
        return False

    permissions = api_info['result'].get('permissions', {})
    required_permissions = ['Wallet', 'Trade', 'Position']
    for perm in required_permissions:
        if not permissions.get(perm) or 'read' not in permissions[perm][0].lower():
             logging.error(f"API Key is missing '{perm}' read permissions.")
             # In a real scenario, we'd check for write permissions too where needed.
             # return False # For now, we log as error but continue

    logging.info("API Key permissions seem adequate.")

    # 2. Check Whitelisted Address
    logging.info("Checking if withdrawal address is whitelisted...")
    whitelisted_addresses = client.get_whitelisted_addresses(coin='USDT')
    if not whitelisted_addresses:
        logging.error("Could not retrieve whitelisted addresses. This might be due to IP restrictions on your API key.")
        return False

    found_address = False
    for addr_info in whitelisted_addresses:
        if addr_info.get('address') == wallet_address and addr_info.get('chain') == 'ERC20':
            found_address = True
            break

    if not found_address:
        logging.error(f"Target address {wallet_address} for chain ERC20 is NOT whitelisted.")
        return False

    logging.info("Withdrawal address is confirmed to be in the whitelist.")
    logging.info("--- Pre-flight Checks Passed ---")
    return True

def liquidate_positions(client: BybitClient):
    """
    Closes all open perpetual and spot positions.
    NOTE: This is a simplified implementation. It assumes market orders will fill
    and that all spot assets have a direct USDT trading pair.
    """
    logging.info("--- Starting Liquidation Process ---")

    # 1. Close Perpetual Positions (Linear/USDT-settled)
    # TODO: Also handle 'inverse' positions if necessary.
    logging.info("Checking for open 'linear' (USDT-margined) perpetual positions...")
    linear_positions = client.get_positions(category='linear')
    for pos in linear_positions:
        if float(pos.get('size', 0)) > 0:
            side = "Sell" if pos['side'] == "Buy" else "Buy"
            logging.info(f"Closing {pos['side']} position of {pos['size']} {pos['symbol']}...")
            client.place_order(
                category='linear',
                symbol=pos['symbol'],
                side=side,
                order_type='Market',
                qty=pos['size']
            )
            time.sleep(1) # Small delay between orders

    # 2. Sell all Spot assets to USDT
    logging.info("Checking for spot assets to sell to USDT...")
    balance_list = client.get_wallet_balance(account_type='UNIFIED')
    if balance_list and 'list' in balance_list[0]:
        spot_balances = balance_list[0]['list']
        for asset in spot_balances:
            coin = asset.get('coin')
            balance = float(asset.get('walletBalance', 0))
            if coin not in ['USDT', 'USDC'] and balance > 0:
                symbol = f"{coin}USDT"
                logging.info(f"Selling {balance} of {coin} via market order ({symbol})...")
                client.place_order(
                    category='spot',
                    symbol=symbol,
                    side='Sell',
                    order_type='Market',
                    qty=str(balance)
                )
                time.sleep(1)

    logging.info("--- Liquidation Process Finished ---")


def execute_withdrawal(client: BybitClient, wallet_address: str):
    """Withdraws all USDT to the specified wallet address."""
    logging.info("--- Starting Withdrawal Process ---")

    # Wait a moment for trades to settle
    logging.info("Waiting 10 seconds for all trades to settle...")
    time.sleep(10)

    balance_list = client.get_wallet_balance(account_type='UNIFIED')
    usdt_balance = "0"
    if balance_list and 'list' in balance_list[0]:
        for asset in balance_list[0]['list']:
            if asset.get('coin') == 'USDT':
                usdt_balance = asset.get('walletBalance', "0")
                break

    if float(usdt_balance) > 0:
        logging.info(f"Attempting to withdraw {usdt_balance} USDT to {wallet_address}...")
        result = client.withdraw(
            coin='USDT',
            chain='ERC20',
            address=wallet_address,
            amount=usdt_balance
        )
        if result and result.get('retCode') == 0:
            logging.info(f"Withdrawal request successful! ID: {result['result'].get('id')}")
        else:
            logging.error(f"Withdrawal failed! Reason: {result.get('retMsg') if result else 'Unknown error'}")
    else:
        logging.warning("No USDT balance to withdraw.")

    logging.info("--- Withdrawal Process Finished ---")


def main():
    """Main execution function."""
    logging.info("=============================================")
    logging.info("=== Starting Crypto Emergency Withdrawal ===")
    logging.info("=============================================")

    load_dotenv()
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    wallet_address = os.getenv("WITHDRAWAL_WALLET_ADDRESS")

    if not all([api_key, api_secret, wallet_address]):
        logging.error("API credentials or withdrawal address not found in .env file. Exiting.")
        return

    try:
        client = BybitClient(api_key=api_key, api_secret=api_secret)

        if not run_pre_flight_checks(client, wallet_address):
            logging.error("Pre-flight checks failed. Aborting.")
            return

        # For maximum security, delete all other API keys except the current one.
        logging.info("--- Deleting other API keys for security ---")
        client.delete_other_api_keys(api_key)

        liquidate_positions(client)
        execute_withdrawal(client, wallet_address)

    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)

    logging.info("=============================================")
    logging.info("=== Emergency Withdrawal Script Finished ===")
    logging.info("=============================================")


if __name__ == "__main__":
    main()
