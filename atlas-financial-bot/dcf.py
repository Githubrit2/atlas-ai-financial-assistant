def dcf_value(fcf, growth, discount_rate=0.10, terminal_growth=0.03, years=5, shares=1):
    """Intrinsic value per share from a simple discounted cash flow model."""
    if fcf <= 0:
        raise ValueError("free cash flow must be positive")
    if shares <= 0:
        raise ValueError("shares must be positive")
    if discount_rate <= terminal_growth:
        raise ValueError("discount_rate must be greater than terminal_growth")

    pv, cash = 0.0, fcf
    for t in range(1, years + 1):
        cash *= 1 + growth
        pv += cash / (1 + discount_rate) ** t
    terminal = cash * (1 + terminal_growth) / (discount_rate - terminal_growth)
    pv += terminal / (1 + discount_rate) ** years
    return pv / shares