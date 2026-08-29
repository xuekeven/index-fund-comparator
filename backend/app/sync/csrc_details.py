import argparse

from app.sync.csrc_funds import run_details_sync


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Script F: sync details, NAV, fees, scales, subscription states, "
            "and returns for script E targets"
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate without committing",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="process only the first N active targets",
    )
    parser.add_argument(
        "--code",
        action="append",
        help="sync only the product containing this six-digit share code; may repeat",
    )
    args = parser.parse_args()
    stats = run_details_sync(
        dry_run=args.dry_run,
        limit=args.limit,
        codes=tuple(args.code or ()),
    )
    action = "validated" if args.dry_run else "synced"
    print(
        f"CSRC off-exchange script F details {action}: "
        f"{stats.products} products, {stats.shares} shares, "
        f"{stats.fee_shares} fee shares, {stats.scales} scales, "
        f"{stats.nav_rows} NAV rows, "
        f"{stats.subscription_states} subscription states, "
        f"{stats.return_metrics} return metrics, "
        f"{len(stats.failures)} failures, {len(stats.warnings)} warnings"
    )
    for failure in stats.failures:
        print(f"WARNING {failure}")
    for warning in stats.warnings:
        print(f"WARNING {warning}")


if __name__ == "__main__":
    main()
