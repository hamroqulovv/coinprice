"""Shared number/message formatting (single source of truth).

Used by main.py (price cards, profile) and utils/scheduler.py (alerts),
so on-demand and notification formatting can never drift apart.
"""


def format_price(value, currency='USD'):
    """Format small prices with adaptive precision to avoid 0.0000 output.
    currency: 'USD', 'RUB', or 'UZS'
    """
    try:
        v = float(value)
    except Exception:
        return "N/A"

    # USD formatting
    if currency == 'USD':
        if v >= 1:
            return f"${v:,.2f}"
        if v >= 0.01:
            return f"${v:,.4f}"
        if v >= 0.0001:
            return f"${v:,.6f}"
        return f"${v:.8f}"

    # RUB formatting
    if currency == 'RUB':
        if v >= 1:
            return f"{v:,.2f} ₽"
        if v >= 0.01:
            return f"{v:,.4f} ₽"
        return f"{v:.6f} ₽"

    # UZS formatting (correct thousands separator, incl. negatives)
    if currency == 'UZS':
        if abs(v) >= 1000:
            return f"{int(round(v)):,} so'm"
        if abs(v) >= 1:
            return f"{v:,.2f} so'm"
        return f"{v:.4f} so'm"

    return str(value)


def format_alert_block(line):
    """Bitta coin uchun scheduler xabar bloki (HTML matn).

    line: {'coin', 'emoji', 'price': {'usd','rub','uzs','name'?}, ...}
    """
    p = line['price']
    usd_str = format_price(p['usd'], 'USD')
    rub_str = format_price(p['rub'], 'RUB')
    uzs_str = format_price(p['uzs'], 'UZS')

    nm = p.get('name')
    title = f"{line['emoji']} <b>{line['coin']}</b>" + (f" ({nm})" if nm and nm.upper() != line['coin'] else "")
    block = title + "\n"
    block += f"   💵 {usd_str}\n"

    if line.get('change') is not None:
        block += f"   📊 {line.get('sign', '')}{line['change']:.2f}%\n"

    block += f"   🇺🇿 {uzs_str}\n"
    block += f"   🇷🇺 {rub_str}\n\n"
    return block
