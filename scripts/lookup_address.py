import sys

from sqlalchemy import text

from app.core.addresses import normalize_address
from app.db.session import get_engine
from app.providers.alchemy import build_alchemy_client
from app.providers.goplus import GoPlusClient


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m scripts.lookup_address 0xADDRESS")
        return 2
    try:
        addr = normalize_address(sys.argv[1])
    except Exception as exc:
        print("invalid address:", type(exc).__name__)
        return 2
    print("address:", addr)

    print("\n[1] Lists stored in our database")
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "select s.name, e.category, e.label from intel_entries e "
                "join intel_sources s on s.id = e.source_id where e.address = :a"
            ),
            {"a": addr},
        ).all()
    if rows:
        for name, category, label in rows:
            print(f"  LISTED in {name}: {category}" + (f" ({label})" if label else ""))
    else:
        print("  not in the OFAC or ScamSniffer data we hold. This does not mean safe.")

    print("\n[2] On-chain code (Alchemy)")
    alchemy = build_alchemy_client()
    if alchemy is None:
        print("  Alchemy key not configured")
    else:
        r = alchemy.get_code(1, addr)
        if r.status != "ok":
            print(f"  {r.status}: {r.detail}")
        elif r.data == "0x":
            print("  no code: a plain account (not a contract)")
        elif r.data.startswith("0xef0100"):
            print("  EIP-7702 delegation to 0x" + r.data[8:])
        else:
            print(f"  contract code, {(len(r.data) - 2) // 2} bytes")

    gp = GoPlusClient()
    print("\n[3] GoPlus token security")
    t = gp.token_security(1, addr)
    if t.status != "ok":
        print(f"  {t.status}: {t.detail}")
    else:
        d = t.data
        print(f"  {d.symbol} / {d.name}: honeypot={d.is_honeypot} proxy={d.is_proxy} "
              f"open_source={d.is_open_source} buy_tax={d.buy_tax} sell_tax={d.sell_tax} "
              f"fields_provided={len(d.fields_present)}")

    print("\n[4] GoPlus address security")
    a = gp.address_security(1, addr)
    if a.status != "ok":
        print(f"  {a.status}: {a.detail}")
    else:
        print(f"  flags raised: {a.data.positive_flags() or 'none (not flagged, not proof of safety)'}")
        print(f"  GoPlus data sources: {list(a.data.data_sources) or 'none listed'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
