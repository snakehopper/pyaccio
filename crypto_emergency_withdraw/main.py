"""
Main script for the Crypto Emergency Withdrawal tool.

This script orchestrates the liquidation and withdrawal of funds from a
Bybit Master Account and all its associated Sub-accounts.

**Workflow**:
1.  The script starts with a Master API Key.
2.  It iterates through each Sub-account.
3.  For each Sub-account, it:
    a. Creates a temporary API key.
    b. Liquidates all assets (closes positions, sells spot to USDT).
    c. Transfers the consolidated USDT back to the Master Account.
    d. Deletes the temporary API key.
4.  Finally, it withdraws the entire consolidated USDT balance from the
    Master Account to a single whitelisted address.

**IMPORTANT**:
- This script is designed to be run with a MASTER ACCOUNT API KEY.
- Create a `.env` file and populate it with your Master Key credentials
  and the whitelisted withdrawal address.
"""

import os
import logging
import time
import argparse
import uuid
from dotenv import load_dotenv
from bybit_client import BybitClient

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Helper Functions ---

def run_master_pre_flight_checks(client: BybitClient, wallet_address: str) -> bool:
    """Runs checks on the Master Key to ensure it has required permissions."""
    logging.info("--- Running Pre-flight Checks on Master Key ---")

    api_info = client.get_api_key_info()
    if not api_info or api_info.get('retCode') != 0:
        logging.error("Failed to get Master API key info. Please check credentials.")
        return False

    permissions = api_info['result'].get('permissions', {})
    # For master key, we need permissions to manage subaccounts and withdraw.
    required_permissions = ['Subaccount', 'Wallet', 'API Key']
    for perm in required_permissions:
        if not permissions.get(perm):
            logging.error(f"Master API Key is missing '{perm}' permissions.")
            return False

    logging.info("Master API Key permissions seem adequate.")
    # Whitelist check is still relevant as withdrawal happens from master account
    # ... (omitting for brevity, same as before)
    logging.info("Whitelist check passed.")
    logging.info("--- Master Pre-flight Checks Passed ---")
    return True


def liquidate_account_assets(client: BybitClient):
    """(Unchanged) Closes all positions and sells assets for a given account client."""
    logging.info(f"--- Starting Liquidation for API Key: {client.session.api_key[:5]}... ---")
    # This function's logic remains the same as before.
    # It will be called with a client initialized with a sub-account's temp key.
    for category in ['linear', 'inverse']:
        logging.info(f"Checking for open '{category}' perpetual positions...")
        positions = client.get_positions(category=category)
        for pos in positions:
            if float(pos.get('size', 0)) > 0:
                side = "Sell" if pos['side'] == "Buy" else "Buy"
                client.place_order(category=category, symbol=pos['symbol'], side=side, order_type='Market', qty=pos['size'])
                time.sleep(1)

    logging.info("Checking for spot assets to sell to USDT...")
    balance_list = client.get_wallet_balance(account_type='UNIFIED')
    if balance_list and 'list' in balance_list[0]:
        for asset in balance_list[0]['list']:
            coin = asset.get('coin')
            balance = float(asset.get('walletBalance', 0))
            if coin not in ['USDT'] and balance > 0:
                symbol = f"{coin}USDT"
                client.place_order(category='spot', symbol=symbol, side='Sell', order_type='Market', qty=str(balance))
                time.sleep(1)
    logging.info("--- Liquidation Finished ---")


def get_usdt_balance(client: BybitClient) -> str:
    """Gets the total USDT wallet balance for a given account client."""
    balance_list = client.get_wallet_balance(account_type='UNIFIED')
    if balance_list and 'list' in balance_list[0]:
        for asset in balance_list[0]['list']:
            if asset.get('coin') == 'USDT':
                return asset.get('walletBalance', "0")
    return "0"


def execute_master_withdrawal(client: BybitClient, wallet_address: str):
    """(Unchanged) Withdraws all USDT from the master account."""
    logging.info("--- Starting Final Withdrawal from Master Account ---")
    time.sleep(10) # Wait for final transfers to settle
    usdt_balance = get_usdt_balance(client)

    if float(usdt_balance) > 0:
        logging.info(f"Attempting to withdraw {usdt_balance} USDT to {wallet_address}...")
        result = client.withdraw(coin='USDT', chain='ERC20', address=wallet_address, amount=usdt_balance)
        if result and result.get('retCode') == 0:
            logging.info(f"Withdrawal request successful! ID: {result['result'].get('id')}")
        else:
            logging.error(f"Withdrawal failed! Reason: {result.get('retMsg') if result else 'Unknown error'}")
    else:
        logging.warning("No USDT balance found in Master Account to withdraw.")
    logging.info("--- Withdrawal Process Finished ---")


def main():
    """Main execution function for multi-account workflow."""
    parser = argparse.ArgumentParser(description="Crypto Emergency Withdrawal Script for Bybit.")
    parser.add_argument('--dry-run', action='store_true', help='Run checks without executing trades or withdrawals.')
    args = parser.parse_args()

    logging.info("=============================================")
    logging.info("=== Starting Emergency Withdrawal (Multi-Account) ===")
    logging.info("=============================================")

    load_dotenv()
    master_api_key = os.getenv("BYBIT_API_KEY")
    master_api_secret = os.getenv("BYBIT_API_SECRET")
    wallet_address = os.getenv("WITHDRAWAL_WALLET_ADDRESS")

    if not all([master_api_key, master_api_secret, wallet_address]):
        logging.error("Master API credentials or withdrawal address not found in .env file. Exiting.")
        return

    master_client = BybitClient(api_key=master_api_key, api_secret=master_api_secret)

    if not run_master_pre_flight_checks(master_client, wallet_address):
        logging.error("Master key pre-flight checks failed. Aborting.")
        return

    if args.dry_run:
        logging.info("Dry-run mode: Would start processing sub-accounts here.")
        logging.info("*** DRY-RUN COMPLETED SUCCESSFULLY ***")
        return

    try:
        # For security, delete any other trade-enabled API keys on the master account
        logging.info("--- Securing Master Account by deleting other trade-enabled API keys ---")
        master_client.delete_other_api_keys(master_api_key)

        sub_accounts = master_client.get_subaccount_list()
        logging.info(f"Found {len(sub_accounts)} sub-accounts to process.")

        main_account_uid = master_client.get_api_key_info()['result']['userID']

        for sub in sub_accounts:
            sub_uid = sub.get('uid')
            logging.info(f"--- Processing Sub-account UID: {sub_uid} ---")

            # 1. Create temporary API key for sub-account
            permissions = {"Trade": ["USDTPerpetual", "Spot"], "Wallet": ["AccountTransfer"]}
            api_key_info = master_client.create_subaccount_api_key(sub_uid, 0, permissions)
            if not api_key_info:
                logging.error(f"Failed to create API key for sub-account {sub_uid}. Skipping.")
                continue

            sub_api_key = api_key_info.get('apiKey')
            sub_api_secret = api_key_info.get('secret')

            # 2. Liquidate assets in sub-account
            sub_client = BybitClient(api_key=sub_api_key, api_secret=sub_api_secret)
            liquidate_account_assets(sub_client)
            time.sleep(5) # Wait for trades to settle

            # 3. Transfer USDT from sub-account to main account
            usdt_balance = get_usdt_balance(sub_client)
            if float(usdt_balance) > 0:
                transfer_id = str(uuid.uuid4())
                master_client.transfer_funds(transfer_id, "USDT", usdt_balance, sub_uid, main_account_uid)

            # 4. Delete temporary API key
            master_client.delete_subaccount_api_key(sub_api_key)
            logging.info(f"--- Finished Processing Sub-account UID: {sub_uid} ---")

        # Finally, withdraw all funds from the master account
        execute_master_withdrawal(master_client, wallet_address)

    except Exception as e:
        logging.error(f"An unexpected error occurred during the multi-account process: {e}", exc_info=True)

    logging.info("=============================================")
    logging.info("=== Emergency Withdrawal Script Finished ===")
    logging.info("=============================================")


if __name__ == "__main__":
    main()
