import asyncio
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local", override=True)


async def main() -> None:
    from db import get_repo, reset_repo_cache

    reset_repo_cache()
    repo = await get_repo()
    rows = await repo.pool.fetch(
        "SELECT fiscal_year, COUNT(*) cnt, COALESCE(SUM(amount),0) total "
        "FROM grant_awards WHERE is_latest_amendment AND amount IS NOT NULL "
        "GROUP BY fiscal_year ORDER BY fiscal_year DESC LIMIT 15"
    )
    print("fiscal years (desc):")
    for r in rows:
        print(f"  {r['fiscal_year']}: {r['cnt']} awards, ${float(r['total']):,.0f}")

    fys = await repo._recent_fiscal_years(2)
    print("selected recent 2:", fys)

    on = await repo.sector_summary("IT_SOFTWARE", "ON", years=2)
    print("IT_SOFTWARE ON summary:", on["award_count"], on["total_amount"])

    all_ca = await repo.sector_summary("IT_SOFTWARE", None, years=2)
    print("IT_SOFTWARE all Canada:", all_ca["award_count"], all_ca["total_amount"])

    # try last 2 years with actual data
    if len(rows) >= 2:
        data_fys = [r["fiscal_year"] for r in rows if r["cnt"] > 0][:2]
        data_fys = data_fys[::-1]
        cond = (
            "sector_normalized = $1 AND fiscal_year = ANY($2::text[]) "
            "AND is_latest_amendment AND amount IS NOT NULL AND province = $3"
        )
        row = await repo.pool.fetchrow(
            f"SELECT COUNT(*) cnt, COALESCE(SUM(amount),0) total FROM grant_awards WHERE {cond}",
            "IT_SOFTWARE",
            data_fys,
            "ON",
        )
        print(f"IT_SOFTWARE ON with FYs {data_fys}:", dict(row))

    await repo.close()


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
    asyncio.run(main())
