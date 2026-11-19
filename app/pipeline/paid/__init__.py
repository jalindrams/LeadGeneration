"""
Paid lead sources (plan Phase 3). Every provider is OFF until BOTH its API key
and a monthly rupee cap are set in .env; every paid call goes through
ledger.charge() first, which refuses once the provider cap or the total cap
would be exceeded.
"""
