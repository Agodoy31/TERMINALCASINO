from typing import Optional
from casino.accounts import Account
from casino.games.day_trading.models import Portfolio
from casino.games.day_trading.market import Market, Stock
from casino.utils import clear_screen, cprint, cinput

DAY_TRADING_HEADER = """
┌────────────────────────────────────────────────────────┐
│              📈 DAY TRADING SIMULATOR 📉               │
│                 VIRTUAL STOCK MARKET                   │
└────────────────────────────────────────────────────────┘
"""


class DayTradingView:
    ITEMS_PER_PAGE: int = 10

    def __init__(self, *args, **kwargs) -> None:
        pass

    @staticmethod
    def get_total_pages(total_items: int, per_page: int = 10) -> int:
        if total_items <= 0:
            return 1
        safe_per_page = max(1, per_page)
        return max(1, (total_items + safe_per_page - 1) // safe_per_page)

    @staticmethod
    def get_page_slice(items: list, page: int, per_page: int = 10) -> list:
        total_pages = DayTradingView.get_total_pages(len(items), per_page)
        clamped_page = max(1, min(page, total_pages))
        start = (clamped_page - 1) * max(1, per_page)
        end = start + max(1, per_page)
        return items[start:end]

    @staticmethod
    def format_header(account: Optional[Account] = None) -> str:
        banner = DAY_TRADING_HEADER.strip("\n")
        if account is not None:
            account_line = f"Trader: {account.name} | Balance: {account.balance} chips"
            return f"{banner}\n{account_line}"
        return banner

    @staticmethod
    def format_news_banner(news: Optional[str]) -> str:
        if not news or not news.strip():
            return ""
        clean_news = news.strip()
        inner_width = max(len(clean_news), 56)
        width = inner_width + 4
        border = "═" * (width - 2)
        top = f"╔{border}╗"
        tag = f"║ {'[ MARKET NEWS ]':^{inner_width}} ║"
        body = f"║ {clean_news:^{inner_width}} ║"
        bottom = f"╚{border}╝"
        return f"{top}\n{tag}\n{body}\n{bottom}"

    @staticmethod
    def format_market_table(stocks: list[Stock], page: int, total_pages: int, tick_count: int) -> str:
        header_line = f"Market Tick {tick_count} | Page {page} of {total_pages}"
        col_headers = f"{'SYMBOL':<8} {'NAME':<28} {'PRICE':>10} {'CHANGE':>10} {'% CHG':>10}"
        divider = "─" * 70
        rows = []
        for stock in stocks:
            price_str = f"${stock.price:.2f}"
            change = stock.price_change
            pct = stock.percent_change
            chg_sign = "+" if change > 0 else ""
            pct_sign = "+" if pct > 0 else ""
            chg_str = f"{chg_sign}{change:.2f}"
            pct_str = f"{pct_sign}{pct:.2f}%"
            name_truncated = stock.name[:27]
            row = f"{stock.symbol:<8} {name_truncated:<28} {price_str:>10} {chg_str:>10} {pct_str:>10}"
            rows.append(row)

        if not rows:
            rows.append("No equities available to display.")

        return "\n".join([header_line, divider, col_headers, divider, *rows, divider])

    @staticmethod
    def format_portfolio_summary(portfolio: Portfolio, current_prices: dict[str, float]) -> str:
        cash_str = f"${portfolio.cash:.2f}"
        pos_val = sum(
            shares * float(current_prices.get(sym, current_prices.get(sym.upper(), 0.0)))
            for sym, shares in portfolio.holdings.items()
        )
        positions_str = f"${pos_val:.2f}"
        total_val = round(portfolio.cash + pos_val, 2)
        total_str = f"${total_val:.2f}"

        summary_lines = [
            "PORTFOLIO SUMMARY",
            f"Cash Balance: {cash_str} | Positions Value: {positions_str} | Total Portfolio Value: {total_str}",
        ]

        if not portfolio.holdings:
            summary_lines.append("No open stock positions.")
        else:
            summary_lines.append("─" * 54)
            summary_lines.append(f"{'SYMBOL':<8} {'SHARES':>8} {'PRICE':>12} {'VALUE':>14}")
            summary_lines.append("─" * 54)
            for sym, shares in sorted(portfolio.holdings.items()):
                cur_price = float(current_prices.get(sym, current_prices.get(sym.upper(), 0.0)))
                val = shares * cur_price
                summary_lines.append(
                    f"{sym:<8} {shares:>8} {f'${cur_price:.2f}':>12} {f'${val:.2f}':>14}"
                )
            summary_lines.append("─" * 54)

        return "\n".join(summary_lines)

    @staticmethod
    def format_notice(notice: Optional[str]) -> str:
        if not notice or not notice.strip():
            return ""
        return f">> {notice.strip()}"

    @staticmethod
    def format_menu() -> str:
        return "COMMANDS: [B]uy  [S]ell  [N]ext Tick  [P]age  [D]eposit  [W]ithdraw  [E]xport  [I]mport  [Q]uit"

    @staticmethod
    def render_screen(
        portfolio: Portfolio,
        market: Market,
        page: int = 1,
        notice: Optional[str] = None,
        account: Optional[Account] = None,
    ) -> str:
        sections = []

        sections.append(DayTradingView.format_header(account))

        news_banner = DayTradingView.format_news_banner(market.last_news)
        if news_banner:
            sections.append(news_banner)

        quotes = list(market.get_quotes().values())
        quotes.sort(key=lambda s: s.symbol)
        total_pages = DayTradingView.get_total_pages(len(quotes), DayTradingView.ITEMS_PER_PAGE)
        clamped_page = max(1, min(page, total_pages))
        slice_stocks = DayTradingView.get_page_slice(quotes, clamped_page, DayTradingView.ITEMS_PER_PAGE)
        market_table = DayTradingView.format_market_table(
            slice_stocks,
            page=clamped_page,
            total_pages=total_pages,
            tick_count=market.tick_count,
        )
        sections.append(market_table)

        current_prices = {s.symbol: s.price for s in quotes}
        portfolio_summary = DayTradingView.format_portfolio_summary(portfolio, current_prices)
        sections.append(portfolio_summary)

        notice_str = DayTradingView.format_notice(notice)
        if notice_str:
            sections.append(notice_str)

        sections.append(DayTradingView.format_menu())

        return "\n\n".join(sections)

    @staticmethod
    def display_screen(
        portfolio: Portfolio,
        market: Market,
        page: int = 1,
        notice: Optional[str] = None,
        account: Optional[Account] = None,
    ) -> None:
        clear_screen()
        screen_content = DayTradingView.render_screen(
            portfolio=portfolio,
            market=market,
            page=page,
            notice=notice,
            account=account,
        )
        print(screen_content)

    @staticmethod
    def prompt(prompt_text: str = "Select an option: ") -> str:
        try:
            return cinput(prompt_text).strip()
        except Exception:
            return input(prompt_text).strip()

    @staticmethod
    def announce(message: str) -> None:
        try:
            cprint(message)
        except Exception:
            print(message)
