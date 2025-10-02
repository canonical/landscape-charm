#!/usr/bin/env python3

"""
This script can turn autoregistration on or off for a given landscape-server
installation. It's in a seperate script to avoid polluting the charm source
with landscape imports.
"""

import argparse
import logging

from canonical.landscape.application import setup_logging
from canonical.landscape.model.account.management import AccountManagement
from canonical.landscape.model.main.account import get_account_by_name
from canonical.landscape.setup import load_config
import transaction


def main() -> None:
    """Parses arguments and updates the autoregistration setting."""
    parser = argparse.ArgumentParser(
        prog="Landscape autoregistration",
        description="Turns on or off autoregistration for self-hosted landscape-server.",  # noqa
    )

    parser.add_argument(
        "setting",
        choices=("on", "off"),
        help="The desired state of the autoregistration setting.",
    )

    args = parser.parse_args()

    _update_autoregistration(args.setting == "on")


def _update_autoregistration(on: bool) -> None:
    """Turns autoregistration on if `on` is `True`. Otherwise, turns it off."""
    setup_logging("autoregistration", level=logging.INFO)
    load_config("maintenance")

    with transaction.manager:
        account = get_account_by_name("standalone")

        if account is None:
            logging.error(
                "autoregistration script can only be used for self-hosted "
                "landscape-server after the first account has been bootstrapped"
            )
            return

        management = AccountManagement(account)
        logging.info(
            "setting autoregistration to %s for account %s",
            "on" if on else "off",
            account.name,
        )

        management.set_preferences(auto_register_new_computers=on)


if __name__ == "__main__":
    main()
