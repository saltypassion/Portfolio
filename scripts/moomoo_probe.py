"""Read-only probe: does the moomoo OpenAPI report dividends in account cash flows?

Requires moomoo OpenD running locally and logged in. Never unlocks trading or places orders.

Usage:
    python3 scripts/moomoo_probe.py                      # checks the 2026-04-02 dividend days
    python3 scripts/moomoo_probe.py 2026-03-13 2026-03-17
"""

import sys

import pandas as pd
from moomoo import RET_OK, OpenSecTradeContext, SecurityFirm, TrdEnv, TrdMarket

HOST = "127.0.0.1"
PORT = 11111

# Several dividends were recorded as paid on 2026-04-02 (NVO, NKE, VTI, NVDA);
# neighbouring days are included in case moomoo clears them on a different date.
DEFAULT_DATES = ["2026-04-01", "2026-04-02", "2026-04-03"]


def main(dates: list[str]) -> None:
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_colwidth", None)

    ctx = OpenSecTradeContext(
        filter_trdmarket=TrdMarket.US,
        host=HOST,
        port=PORT,
        security_firm=SecurityFirm.FUTUSG,
    )
    try:
        ret, accounts = ctx.get_acc_list()
        if ret != RET_OK:
            print(f"Could not list accounts: {accounts}")
            return

        print("Accounts visible to OpenD:")
        print(accounts.to_string(index=False))

        real_accounts = accounts[accounts["trd_env"] == TrdEnv.REAL]
        if real_accounts.empty:
            print("\nNo real (non-paper) accounts found. Is OpenD logged into the right moomoo account?")
            return

        for acc_id in real_accounts["acc_id"]:
            for date in dates:
                ret, flows = ctx.get_acc_cash_flow(clearing_date=date, trd_env=TrdEnv.REAL, acc_id=int(acc_id))
                print(f"\n=== acc_id {acc_id} · {date} ===")
                if ret != RET_OK:
                    print(f"Error: {flows}")
                elif flows.empty:
                    print("(no cash flows)")
                else:
                    print(flows.to_string(index=False))
    finally:
        ctx.close()


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_DATES)
